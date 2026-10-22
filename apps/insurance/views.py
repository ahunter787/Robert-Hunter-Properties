from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.files import document_response
from apps.leases.models import Lease

from . import services
from .forms import InsuranceProofForm, InsuranceReviewForm
from .models import InsuranceProof, TenantState


def _tenant_lease(user):
    return (
        Lease.objects.filter(lease_tenants__tenant=user)
        .select_related("unit__property")
        .order_by("-start_date", "-pk")
        .first()
    )


@login_required
def tenant_insurance(request):
    if not request.user.is_tenant:
        raise PermissionDenied
    lease = _tenant_lease(request.user)
    proof = services.current_proof(lease) if lease else None
    form = InsuranceProofForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and lease is not None:
        if form.is_valid():
            try:
                services.submit_proof(
                    lease=lease,
                    actor=request.user,
                    file=form.cleaned_data["file"],
                    policy_start=form.cleaned_data.get("policy_start"),
                    policy_end=form.cleaned_data.get("policy_end"),
                )
            except (ValidationError, PermissionDenied) as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, "Proof submitted for manager review.")
                return redirect("tenant_insurance:insurance")
    return render(
        request,
        "insurance/tenant.html",
        {
            "lease": lease,
            "state": services.state_for(lease) if lease else TenantState.NOT_REQUIRED,
            "proof": proof,
            "form": form,
        },
    )


@login_required
def staff_list(request):
    if not request.user.is_manager_or_above:
        raise PermissionDenied
    leases = (
        Lease.objects.filter(renters_insurance_required=True)
        .exclude(status="DRAFT")
        .select_related("unit__property")
        .order_by("unit__property__name", "unit__identifier")
    )
    rows = [{"lease": lease, "state": services.state_for(lease)} for lease in leases]
    return render(request, "insurance/staff_list.html", {"rows": rows})


@login_required
def staff_detail(request, pk):
    if not request.user.is_manager_or_above:
        raise PermissionDenied
    lease = get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)
    proof = services.current_proof(lease)
    form = InsuranceReviewForm(request.POST or None)
    if request.method == "POST" and proof is not None:
        if form.is_valid():
            try:
                services.review_proof(
                    proof=proof,
                    actor=request.user,
                    decision=form.cleaned_data["decision"],
                    note=form.cleaned_data.get("note", ""),
                )
            except ValidationError as error:
                form.add_error(None, error.messages[0])
            else:
                messages.success(request, "Insurance proof reviewed.")
                return redirect("insurance:staff-detail", pk=lease.pk)
    return render(
        request,
        "insurance/staff_detail.html",
        {
            "lease": lease,
            "proof": proof,
            "state": services.state_for(lease),
            "form": form,
        },
    )


@login_required
def proof_document(request, pk):
    proof = get_object_or_404(InsuranceProof.objects.select_related("document", "lease"), pk=pk)
    allowed = request.user.is_manager_or_above or proof.lease.lease_tenants.filter(
        tenant=request.user
    ).exists()
    if not allowed:
        raise Http404
    document = proof.document
    if not document.file or not document.file.storage.exists(document.file.name):
        raise Http404("That proof file is not on this server.")
    return document_response(document.file, filename=document.display_name)
