"""Document screens: the office's list and upload, the tenant's own, and removal.

Authorization is server-side throughout (ADR-003, ADR-007): the office area is a
manager's, removal is an admin's act alone, and the tenant area resolves every
document through the tenancy scope, so another tenancy's id is a 404 rather than a
refusal that admits the document exists.
"""

import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import User
from apps.accounts.permissions import AdminRequiredMixin, ManagerRequiredMixin, TenantAreaMixin
from apps.common.files import document_response
from apps.documents import services
from apps.documents.forms import DocumentForm, DocumentRemoveForm
from apps.documents.models import Document, DocumentCategory
from apps.leases.models import Lease
from apps.properties.models import Property, Unit

logger = logging.getLogger("apps.documents")


def _presets(request):
    """What the document is being filed against, from the screen it was opened from."""
    lease = property_obj = tenant = None
    if pk := request.GET.get("lease") or request.POST.get("lease"):
        if not str(pk).isdigit():
            raise Http404
        lease = get_object_or_404(Lease.objects.select_related("unit__property"), pk=pk)
    if pk := request.GET.get("property") or request.POST.get("property"):
        if not str(pk).isdigit():
            raise Http404
        property_obj = get_object_or_404(Property, pk=pk)
    if pk := request.GET.get("tenant") or request.POST.get("tenant"):
        if not str(pk).isdigit():
            raise Http404
        tenant = get_object_or_404(User, pk=pk)
    return lease, property_obj, tenant


def _back_to(request, lease=None, property_obj=None, tenant=None) -> str:
    """Where the office came from, so filing a document does not lose their place."""
    if lease is not None:
        return reverse("leases:lease-detail", args=[lease.pk]) + "?section=documents"
    if property_obj is not None:
        return reverse("portfolio:property-detail", args=[property_obj.pk]) + "?section=documents"
    if tenant is not None:
        return reverse("manage:account-detail", args=[tenant.pk])
    return reverse("documents:list")


class DocumentListView(ManagerRequiredMixin, ListView):
    """Every document the office holds, filtered the way a desk actually asks."""

    template_name = "management/document_list.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        documents = Document.objects.for_staff()
        search = self.request.GET.get("q", "").strip()
        if search:
            documents = documents.filter(
                Q(title__icontains=search)
                | Q(original_name__icontains=search)
                | Q(note__icontains=search)
            )
        if category := self.request.GET.get("category"):
            documents = documents.filter(category=category)
        if self.request.GET.get("visibility") == "tenant":
            documents = documents.filter(tenant_visible=True)
        elif self.request.GET.get("visibility") == "staff":
            documents = documents.filter(tenant_visible=False)
        if property_id := self.request.GET.get("property"):
            if not property_id.isdigit():
                raise Http404
            property_obj = get_object_or_404(Property, pk=property_id)
            documents = documents.filter(
                Q(property=property_obj) | Q(lease__unit__property=property_obj)
            )
        if unit_id := self.request.GET.get("unit"):
            if not unit_id.isdigit():
                raise Http404
            unit = get_object_or_404(
                Unit, pk=unit_id, **({"property_id": property_id} if property_id else {})
            )
            documents = documents.filter(lease__unit=unit)
        return documents.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "search": self.request.GET.get("q", "").strip(),
                "category": self.request.GET.get("category", ""),
                "visibility": self.request.GET.get("visibility", ""),
                "property_id": self.request.GET.get("property", ""),
                "categories": DocumentCategory.choices,
                "properties": Property.objects.active().order_by("name"),
                "can_remove": self.request.user.is_admin_or_above,
                "unit_id": self.request.GET.get("unit", ""),
                "filter_query": urlencode(
                    {
                        key: self.request.GET[key]
                        for key in ("q", "category", "visibility", "property", "unit")
                        if key in self.request.GET
                    }
                ),
            }
        )
        return context


class DocumentUploadView(ManagerRequiredMixin, View):
    """File a document against a tenancy, a property or a tenant."""

    template_name = "management/document_form.html"

    def _context(self, form, lease, property_obj, tenant):
        return {
            "form": form,
            "lease": lease,
            "property": property_obj,
            "tenant": tenant,
            "attachment": lease or property_obj or tenant,
            "back_url": _back_to(self.request, lease, property_obj, tenant),
        }

    def get(self, request):
        lease, property_obj, tenant = _presets(request)
        return render(
            request,
            self.template_name,
            self._context(
                DocumentForm(lease=lease, property=property_obj, tenant=tenant),
                lease,
                property_obj,
                tenant,
            ),
        )

    def post(self, request):
        lease, property_obj, tenant = _presets(request)
        form = DocumentForm(
            request.POST, request.FILES, lease=lease, property=property_obj, tenant=tenant
        )
        if form.is_valid():
            document = services.upload_document(
                title=form.cleaned_data["title"],
                category=form.cleaned_data["category"],
                file=form.cleaned_data["file"],
                lease=lease or form.cleaned_data.get("lease"),
                property=property_obj or form.cleaned_data.get("property"),
                tenant=tenant or form.cleaned_data.get("tenant"),
                tenant_visible=form.cleaned_data["tenant_visible"],
                document_date=form.cleaned_data["document_date"],
                note=form.cleaned_data["note"],
                actor=request.user,
            )
            logger.info("document uploaded pk=%s by=%s", document.pk, request.user.pk)
            messages.success(
                request,
                f"{document.title} filed."
                + (" The tenant can see it." if document.tenant_visible else ""),
            )
            return redirect(_back_to(request, lease, property_obj, tenant))
        return render(
            request,
            self.template_name,
            self._context(form, lease, property_obj, tenant),
        )


class DocumentDownloadView(ManagerRequiredMixin, View):
    """The office's copy of one document, served through the application."""

    http_method_names = ["get"]

    def get(self, request, pk):
        document = get_object_or_404(Document.objects.for_staff(), pk=pk)
        if not document.file or not document.file.storage.exists(document.file.name):
            # A row whose bytes are gone (a restore that missed media, a lost volume) is a
            # 404 with a sentence, not a 500 from the storage backend.
            raise Http404("That document's file is not on this server.")
        return document_response(document.file, filename=document.display_name)


class DocumentRemoveView(AdminRequiredMixin, View):
    """Remove a document uploaded in error — an admin's act, with a reason (P6-Q4)."""

    template_name = "management/document_remove.html"

    def get_document(self, pk) -> Document:
        return get_object_or_404(Document.objects.for_staff(), pk=pk)

    def get(self, request, pk):
        document = self.get_document(pk)
        return render(
            request, self.template_name, {"document": document, "form": DocumentRemoveForm()}
        )

    def post(self, request, pk):
        document = self.get_document(pk)
        form = DocumentRemoveForm(request.POST)
        if form.is_valid():
            try:
                services.remove_document(
                    document, note=form.cleaned_data["note"], actor=request.user
                )
            except ValidationError as exc:
                for error in exc.messages:
                    form.add_error(None, error)
            else:
                logger.info("document removed pk=%s by=%s", pk, request.user.pk)
                messages.success(
                    request,
                    f"{document.title} was removed, and its file with it. The removal is in "
                    "the history.",
                )
                return redirect("documents:list")
        return render(request, self.template_name, {"document": document, "form": form})


# --- the tenant's own documents -------------------------------------------


class TenantDocumentListView(TenantAreaMixin, ListView):
    """The documents the office has chosen to show this tenant, and only those."""

    template_name = "tenancy/documents.html"
    context_object_name = "documents"

    def get_queryset(self):
        return Document.objects.visible_to(self.request.user).select_related(
            "lease__unit__property", "property"
        )


class TenantDocumentDownloadView(TenantAreaMixin, View):
    """One document, resolved through the tenancy scope.

    A document belonging to somebody else is a 404: the answer must not confirm that
    it exists (ADR-022).
    """

    http_method_names = ["get"]

    def get(self, request, pk):
        document = get_object_or_404(Document.objects.visible_to(request.user), pk=pk)
        if not document.file or not document.file.storage.exists(document.file.name):
            raise Http404("That document's file is not on this server.")
        return document_response(document.file, filename=document.display_name)
