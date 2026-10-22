from django import forms

from apps.common.forms import StyledForm
from apps.insurance.models import ProofStatus


class InsuranceProofForm(StyledForm):
    file = forms.FileField(
        label="Proof of renters insurance",
        help_text="PDF, JPG, JPEG or PNG. One current policy document.",
    )
    policy_start = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Policy start"
    )
    policy_end = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Policy end"
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        suffix = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
        if suffix not in ("pdf", "jpg", "jpeg", "png"):
            raise forms.ValidationError("Upload a PDF, JPG, JPEG or PNG file.")
        return upload


class InsuranceReviewForm(StyledForm):
    decision = forms.ChoiceField(
        choices=[
            (ProofStatus.ACCEPTED, "Accept"),
            (ProofStatus.REJECTED, "Reject"),
        ]
    )
    note = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Required when rejecting; the tenant sees the reason.",
    )
