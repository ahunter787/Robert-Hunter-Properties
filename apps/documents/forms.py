"""Forms for uploading a document, and for removing one filed in error."""

from django import forms
from django.conf import settings

from apps.accounts.models import Role, User
from apps.common.files import validate_document_upload
from apps.common.forms import StyledForm, StyledModelForm
from apps.documents.models import Document
from apps.leases.models import Lease, LeaseStatus
from apps.properties.models import Property


class DocumentForm(StyledModelForm):
    """File one document against a tenancy, a property or a tenant.

    The attachment is preset by the screen the office came from (a tenancy's page
    files against that tenancy), and chosen here only when it is not.
    """

    class Meta:
        model = Document
        # The attachment is asked for only when the screen did not already know it: a
        # tenancy's page files against that tenancy, and the desk's own upload screen
        # lets the office choose.
        fields = [
            "title",
            "category",
            "file",
            "lease",
            "property",
            "tenant",
            "document_date",
            "tenant_visible",
            "note",
        ]
        widgets = {"document_date": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "lease": "Tenancy",
            "property": "Property",
            "tenant": "Tenant",
            "tenant_visible": "The tenant can see this",
        }
        help_texts = {
            "file": "PDF, JPEG, PNG, WebP, Word, Excel, CSV or text, up to "
            f"{settings.RHP_MAX_UPLOAD_MB} MB.",
            "lease": "File it against the tenancy when it is about one — a lease, an addendum, "
            "that tenant's notice.",
            "tenant_visible": "Leave it unticked and this stays in the office.",
            "note": "Office notes. Never shown to a tenant.",
        }

    def __init__(self, *args, lease=None, property=None, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # One place to file it, so the screen does not ask again — and the instance
        # carries it, because the model's own clean() is what checks that a document
        # belongs to something. A popped field the model complains about would be a
        # 500 instead of a form error.
        self.presets = {"lease": lease, "property": property, "tenant": tenant}
        for name, value in self.presets.items():
            if value is not None:
                self.fields.pop(name, None)
                setattr(self.instance, name, value)
        if "lease" in self.fields:
            self.fields["lease"].queryset = (
                Lease.objects.exclude(status=LeaseStatus.DRAFT)
                .select_related("unit__property")
                .order_by("unit__property__name", "unit__identifier")
            )
            self.fields["lease"].empty_label = "Not about one tenancy"
        if "property" in self.fields:
            self.fields["property"].queryset = Property.objects.active().order_by("name")
            self.fields["property"].empty_label = "Not about one property"
        if "tenant" in self.fields:
            self.fields["tenant"].queryset = User.objects.filter(
                role=Role.TENANT, is_active=True
            ).order_by("first_name", "last_name", "username")
            self.fields["tenant"].empty_label = "Not about one tenant"

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        return validate_document_upload(upload, max_bytes=settings.RHP_MAX_UPLOAD_MB * 1024 * 1024)

    def clean(self):
        cleaned = super().clean()
        if not any(self.presets.values()) and not any(
            cleaned.get(name) for name in ("lease", "property", "tenant")
        ):
            self.add_error("title", "File this against a tenancy, a property or a tenant.")
        if cleaned.get("tenant_visible") and not (
            self.presets.get("lease")
            or self.presets.get("tenant")
            or cleaned.get("lease")
            or cleaned.get("tenant")
        ):
            self.add_error(
                "tenant_visible",
                "A property document has no tenant to show it to. Attach it to a tenancy "
                "or a tenant first.",
            )
        return cleaned


class DocumentRemoveForm(StyledForm):
    """Removing a document uploaded in error: an admin's act, with a reason."""

    note = forms.CharField(
        max_length=200,
        label="Why it is being removed",
        help_text="What was wrong with it. Recorded in the tenancy's history for good.",
    )
