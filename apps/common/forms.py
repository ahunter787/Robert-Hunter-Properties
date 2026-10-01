"""Shared form building blocks.

Not a Django app - a plain package for code that more than one RHP domain needs.
The first tenant is the design-system form mixin: every RHP form inherits it so
templates can render ``{{ field }}`` without repeating classes, and so the
styling lives in one place instead of being copied per app.
"""

from django import forms


class StyledForm(forms.Form):
    """Applies the RHP design-system classes to all widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "h-4 w-4 rounded border-surface-muted text-primary"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "rhp-field pr-8"
            elif isinstance(widget, forms.Textarea):
                css = "rhp-field min-h-24"
            else:
                css = "rhp-field"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class StyledModelForm(StyledForm, forms.ModelForm):
    """ModelForm variant of :class:`StyledForm`."""
