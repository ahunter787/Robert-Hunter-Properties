from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.leases.models import Lease
from apps.timeline import services
from apps.timeline.forms import ManualEntryForm


@login_required
def staff_list(request):
    if not request.user.is_manager_or_above:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    leases = Lease.objects.exclude(status="DRAFT").select_related("unit__property")
    return render(request, "timeline/staff_list.html", {"leases": leases})


@login_required
def staff_lease(request, pk):
    if not request.user.is_manager_or_above:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    lease = get_object_or_404(
        Lease.objects.select_related("unit__property"), pk=pk
    )
    form = ManualEntryForm(request.POST or None, lease=lease)
    if request.method == "POST" and form.is_valid():
        services.add_manual_entry(
            lease=lease,
            actor=request.user,
            kind=form.cleaned_data["kind"],
            body=form.cleaned_data["body"],
            occurred_at=form.cleaned_data["occurred_at"],
            visible_to_tenant=form.cleaned_data["visible_to_tenant"],
            document=form.cleaned_data.get("document"),
        )
        messages.success(request, "Timeline entry added.")
        return redirect("timeline:lease", pk=lease.pk)
    events = services.timeline_for(lease, request.user)
    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "timeline/lease.html",
        {
            "lease": lease,
            "page": page,
            "form": form,
            "staff": True,
        },
    )


@login_required
def tenant_timeline(request):
    lease = (
        Lease.objects.filter(lease_tenants__tenant=request.user)
        .select_related("unit__property")
        .order_by("-start_date", "-pk")
        .first()
    )
    if lease is None:
        return render(request, "timeline/tenant.html", {"lease": None, "page": None})
    events = services.timeline_for(lease, request.user)
    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "timeline/tenant.html",
        {"lease": lease, "page": page, "staff": False},
    )
