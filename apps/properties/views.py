"""Portfolio management screens: properties and their units.

Every view is gated server-side (ADR-003, ADR-005): MANAGER and above read and
edit, hard deletion is ADMIN-only behind a confirmation page, and a property that
still has units cannot be deleted at all - PROTECT makes that a database fact,
not a UI convention.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from apps.accounts.permissions import AdminRequiredMixin, ManagerRequiredMixin
from apps.properties.forms import PropertyForm, UnitForm
from apps.properties.locations import embed_url, external_url
from apps.properties.models import Property, Unit
from apps.responsibilities import services as responsibility_services

logger = logging.getLogger("apps.properties")


# --- Properties -----------------------------------------------------------


class PropertyListView(ManagerRequiredMixin, ListView):
    """The portfolio: every property with its unit counts."""

    template_name = "management/property_list.html"
    context_object_name = "properties"
    paginate_by = 25

    def get_queryset(self):
        queryset = Property.objects.annotate(
            unit_total=Count("units", distinct=True),
            unit_active=Count("units", filter=Q(units__is_active=True), distinct=True),
        ).order_by("name")
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(street__icontains=search)
                | Q(city__icontains=search)
                | Q(postal_code__icontains=search)
            )
        status = self.request.GET.get("status", "")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        return context


class PropertyCreateView(ManagerRequiredMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = "management/property_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info("property created pk=%s by=%s", self.object.pk, self.request.user.pk)
        messages.success(self.request, f"{self.object.name} was added to the portfolio.")
        return response

    def get_success_url(self):
        return reverse("portfolio:property-detail", args=[self.object.pk])


class PropertyDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/property_detail.html"
    context_object_name = "property"

    def get_queryset(self):
        return Property.objects.prefetch_related("units")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        units = list(self.object.units.all())
        context["units"] = units
        context["unit_total"] = len(units)
        context["unit_active"] = sum(1 for unit in units if unit.is_active)
        # The bills this property carries and who is carrying them (E2).
        context["responsibilities"] = responsibility_services.property_overview(self.object)
        context["can_manage_responsibilities"] = self.request.user.is_admin_or_above
        # Only meaningful when at least one unit records a size; the template hides
        # the line rather than showing "0 sq ft".
        context["total_square_feet"] = sum(unit.square_feet or 0 for unit in units) or None
        # Units that are currently under an active lease. Reading this per unit
        # costs one query each; the occupancy rule itself lives in apps.leases.
        context["occupancy"] = [
            {"unit": unit, "lease": unit.current_lease}
            for unit in units
            if unit.current_lease is not None
        ]
        if self.object.has_map_pin:
            context["map_embed_url"] = embed_url(
                self.object.latitude,
                self.object.longitude,
                settings.GOOGLE_MAPS_EMBED_API_KEY,
            )
            context["map_external_url"] = external_url(self.object.latitude, self.object.longitude)
        return context


class PropertyBannerView(ManagerRequiredMixin, View):
    """Serve a property banner through the application.

    Deliberately not a media URL: uploads are served by a view that checks the
    role first, and the reverse proxy never exposes /media (docs/security.md).
    """

    http_method_names = ["get"]

    def get(self, request, pk):
        property_ = get_object_or_404(Property, pk=pk)
        if not property_.banner_image:
            raise Http404("This property has no banner photo.")

        banner = property_.banner_image
        banner.open("rb")
        response = FileResponse(banner)
        response["Cache-Control"] = "private, max-age=300"
        return response


class PropertyUpdateView(ManagerRequiredMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = "management/property_form.html"

    def form_valid(self, form):
        # Read the stored name before the form binds a replacement: a ModelForm
        # mutates its instance during validation.
        previous_banner = (
            Property.objects.filter(pk=self.object.pk)
            .values_list("banner_image", flat=True)
            .first()
            or ""
        )
        storage = self.object.banner_image.storage

        response = super().form_valid(form)

        current_banner = self.object.banner_image.name if self.object.banner_image else ""
        if previous_banner and previous_banner != current_banner:
            storage.delete(previous_banner)

        logger.info("property updated pk=%s by=%s", self.object.pk, self.request.user.pk)
        messages.success(self.request, f"{self.object.name} was updated.")
        return response

    def get_success_url(self):
        return reverse("portfolio:property-detail", args=[self.object.pk])


class PropertyToggleActiveView(ManagerRequiredMixin, View):
    """Take a property out of service, or put it back. Reversible by design."""

    http_method_names = ["post"]

    def post(self, request, pk):
        property_ = get_object_or_404(Property, pk=pk)
        property_.is_active = not property_.is_active
        property_.save(update_fields=["is_active"])
        logger.info(
            "property active=%s pk=%s by=%s", property_.is_active, property_.pk, request.user.pk
        )
        if property_.is_active:
            messages.success(request, f"{property_.name} is back in service.")
        else:
            active_units = property_.units.active().count()
            note = f" Its {active_units} in-service unit(s) are unaffected." if active_units else ""
            messages.success(request, f"{property_.name} was taken out of service.{note}")
        return redirect("portfolio:property-detail", pk=property_.pk)


class PropertyDeleteView(AdminRequiredMixin, DeleteView):
    """Hard delete: ADMIN only, behind a confirmation page, refused while units exist."""

    model = Property
    template_name = "management/property_confirm_delete.html"
    context_object_name = "property"
    success_url = reverse_lazy("portfolio:property-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unit_total"] = self.object.units.count()
        return context

    def form_valid(self, form):
        property_ = self.object
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"{property_.name} still has units, so it cannot be deleted. "
                "Take it out of service instead.",
            )
            return redirect("portfolio:property-detail", pk=property_.pk)
        logger.info(
            "property deleted pk=%s name=%r by=%s",
            property_.pk,
            property_.name,
            self.request.user.pk,
        )
        messages.success(self.request, f"{property_.name} was deleted.")
        return response


# --- Units ----------------------------------------------------------------


class UnitListView(ManagerRequiredMixin, ListView):
    """Every unit, grouped under the property it belongs to.

    The page is paginated by **property**, not by unit, so the grouping survives
    pagination: a page holds up to 25 properties with all of their matching units,
    which is how the portfolio is actually read. Filters scope both levels — a
    property appears because it has a matching unit, and shows only those units.
    """

    template_name = "management/unit_list.html"
    context_object_name = "properties"
    paginate_by = 25

    def _matching_units(self):
        units = Unit.objects.order_by("identifier")
        search = self.request.GET.get("q", "").strip()
        if search:
            units = units.filter(
                Q(identifier__icontains=search)
                | Q(property__name__icontains=search)
                | Q(property__city__icontains=search)
            )
        status = self.request.GET.get("status", "")
        if status == "active":
            units = units.filter(is_active=True)
        elif status == "inactive":
            units = units.filter(is_active=False)
        return units

    def get_queryset(self):
        units = self._matching_units()
        properties = (
            Property.objects.filter(units__in=units)
            .prefetch_related(Prefetch("units", queryset=units, to_attr="listed_units"))
            .distinct()
            .order_by("name")
        )
        property_id = self.request.GET.get("property", "")
        if property_id.isdigit():
            properties = properties.filter(pk=property_id)
        return properties

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        context["all_properties"] = Property.objects.order_by("name")
        context["selected_property"] = self.request.GET.get("property", "")
        # The page's units, flattened: the summary line reads from this, and it
        # keeps one familiar list for anything that only needs the units.
        context["units"] = [
            unit for property_ in context["properties"] for unit in property_.listed_units
        ]
        return context


class UnitCreateView(ManagerRequiredMixin, CreateView):
    model = Unit
    form_class = UnitForm
    template_name = "management/unit_form.html"

    def get_initial(self):
        initial = super().get_initial()
        property_id = self.request.GET.get("property", "")
        if property_id.isdigit() and Property.objects.active().filter(pk=property_id).exists():
            initial["property"] = int(property_id)
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info("unit created pk=%s by=%s", self.object.pk, self.request.user.pk)
        messages.success(
            self.request,
            f"{self.object.display_name} was added to {self.object.property.name}.",
        )
        return response

    def get_success_url(self):
        return reverse("portfolio:unit-detail", args=[self.object.pk])


class UnitDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/unit_detail.html"
    context_object_name = "unit"

    def get_queryset(self):
        return Unit.objects.select_related("property")


class UnitUpdateView(ManagerRequiredMixin, UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = "management/unit_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info("unit updated pk=%s by=%s", self.object.pk, self.request.user.pk)
        messages.success(self.request, f"{self.object.display_name} was updated.")
        return response

    def get_success_url(self):
        return reverse("portfolio:unit-detail", args=[self.object.pk])


class UnitToggleActiveView(ManagerRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk)
        unit.is_active = not unit.is_active
        unit.save(update_fields=["is_active"])
        logger.info("unit active=%s pk=%s by=%s", unit.is_active, unit.pk, request.user.pk)
        state = "in service" if unit.is_active else "out of service"
        messages.success(request, f"{unit.display_name} at {unit.property.name} is {state}.")
        return redirect("portfolio:unit-detail", pk=unit.pk)


class UnitDeleteView(AdminRequiredMixin, DeleteView):
    model = Unit
    template_name = "management/unit_confirm_delete.html"
    context_object_name = "unit"
    success_url = reverse_lazy("portfolio:unit-list")

    def form_valid(self, form):
        unit = self.object
        label = unit.label
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            # Phase 3 attaches leases to units with PROTECT; this is the message
            # staff will see then.
            messages.error(
                self.request,
                f"{label} has records attached to it, so it cannot be deleted. "
                "Take it out of service instead.",
            )
            return redirect("portfolio:unit-detail", pk=unit.pk)
        logger.info("unit deleted pk=%s by=%s", unit.pk, self.request.user.pk)
        messages.success(self.request, f"{label} was deleted.")
        return response
