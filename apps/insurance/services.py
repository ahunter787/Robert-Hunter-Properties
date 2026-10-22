"""Proof intake and manager decision; no automated screening or insurance advice."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.documents.services import upload_document

from .models import InsuranceProof, ProofStatus, TenantState


def current_proof(lease):
    return (
        lease.insurance_proofs.select_related("document").order_by("-submitted_at", "-pk").first()
    )


def state_for(lease):
    if not lease.renters_insurance_required:
        return TenantState.NOT_REQUIRED
    proof = current_proof(lease)
    if proof is None:
        return TenantState.MISSING
    return proof.status


def can_submit(lease, actor):
    return bool(
        getattr(actor, "is_authenticated", False)
        and actor.is_tenant
        and lease.lease_tenants.filter(tenant=actor).exists()
    )


@transaction.atomic
def submit_proof(*, lease, actor, file, policy_start=None, policy_end=None):
    if not can_submit(lease, actor):
        raise PermissionDenied
    if not lease.renters_insurance_required:
        raise ValidationError("This lease does not require renters insurance.")
    if policy_start and policy_end and policy_end < policy_start:
        raise ValidationError("The policy end date is before its start date.")
    document = upload_document(
        title="Renters insurance proof",
        category="INSURANCE",
        file=file,
        lease=lease,
        tenant_visible=True,
        actor=actor,
    )
    proof = InsuranceProof.objects.create(
        lease=lease,
        document=document,
        policy_start=policy_start,
        policy_end=policy_end,
        submitted_by=actor,
        replaces=current_proof(lease),
    )
    record(
        actor,
        AuditAction.INSURANCE_PROOF_SUBMITTED,
        obj=proof,
        lease=lease,
        summary="Renters insurance proof submitted.",
        status=proof.status,
    )
    return proof


@transaction.atomic
def review_proof(*, proof, actor, decision, note=""):
    if not actor.is_manager_or_above:
        raise PermissionDenied
    if decision not in (ProofStatus.ACCEPTED, ProofStatus.REJECTED):
        raise ValidationError("Choose Accepted or Rejected.")
    note = (note or "").strip()
    if decision == ProofStatus.REJECTED and not note:
        raise ValidationError("Say why the proof was rejected; the tenant will see it.")
    proof = InsuranceProof.objects.select_for_update().get(pk=proof.pk)
    if proof.status != ProofStatus.SUBMITTED:
        raise ValidationError("This proof has already been reviewed.")
    proof.status = decision
    proof.reviewed_by = actor
    proof.reviewed_at = timezone.now()
    proof.review_note = note[:500]
    proof.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    record(
        actor,
        AuditAction.INSURANCE_PROOF_REVIEWED,
        obj=proof,
        lease=proof.lease,
        summary=f"Renters insurance proof {decision.lower()}.",
        status=decision,
        note=note,
    )
    return proof
