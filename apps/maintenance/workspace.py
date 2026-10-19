"""Permission-scoped, read-only request presentation."""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.common.workspaces import section_navigation
from apps.leases.models import Lease


def request_workspace(request, ticket, audiences):
    audiences = list(audiences.order_by("pk"))
    raw = request.GET.get("audience")
    selected = None
    if raw is not None:
        selected = next((a for a in audiences if str(a.pk) == raw), None)
        if selected is None:
            raise Http404
    elif audiences:
        selected = next(
            (a for a in audiences if a.lease_id == ticket.reporting_lease_id), audiences[0]
        )
    sections = [("conversations", "Conversations"), ("work", "Work details")]
    if not request.user.is_tenant:
        sections.append(("internal", "Internal notes"))
    if request.user.is_manager_or_above:
        sections.extend((("costs", "Repair expenses"), ("history", "Delivery & history")))
    default = "conversations" if selected or request.user.is_tenant else "internal"
    section = request.GET.get("section", default)
    if section not in dict(sections):
        raise PermissionDenied
    params = {"audience": selected.pk} if selected else {}
    return {
        "request_section": section,
        "selected_audience": selected,
        "audiences": audiences,
        "record_tabs": section_navigation(request.path, sections, section, **params),
        "audience_query": f"?audience={selected.pk}" if selected else "",
        "can_write": not request.user.is_tenant
        or bool(selected and Lease.objects.current().filter(pk=selected.lease_id).exists()),
    }
