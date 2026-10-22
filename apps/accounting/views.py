"""Manager-only B1 accounting surfaces: controls, journals and the chart.

There is deliberately no tenant-facing journal screen. The GL is an office view over the
same tenancy facts; a tenant sees their statement, not the books.
"""

from django.views.generic import DetailView, ListView, TemplateView

from apps.accounting import services
from apps.accounting.models import ChartAccount, JournalEntry
from apps.accounts.permissions import ManagerRequiredMixin


class AccountingOverviewView(ManagerRequiredMixin, TemplateView):
    template_name = "management/accounting_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = services.trial_balance()
        context["rows"] = rows
        context["debit_total"] = sum((row["debit"] for row in rows), services.ZERO)
        context["credit_total"] = sum((row["credit"] for row in rows), services.ZERO)
        context["tie"] = services.ar_control_tie()
        context["unposted"] = services.unposted_count()
        context["journal_count"] = JournalEntry.objects.count()
        context["account_count"] = ChartAccount.objects.filter(is_active=True).count()
        return context


class ChartAccountListView(ManagerRequiredMixin, ListView):
    template_name = "management/accounting_chart.html"
    context_object_name = "accounts"

    def get_queryset(self):
        return ChartAccount.objects.prefetch_related("mappings").order_by("code")


class JournalListView(ManagerRequiredMixin, ListView):
    template_name = "management/accounting_journal_list.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_queryset(self):
        entries = JournalEntry.objects.select_related(
            "lease__unit__property", "property"
        ).prefetch_related("lines__account")
        search = self.request.GET.get("q", "").strip()
        if search:
            entries = entries.filter(source_key__icontains=search) | entries.filter(
                event_type__icontains=search
            )
        return entries.order_by("-posted_on", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "").strip()
        return context


class JournalDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/accounting_journal_detail.html"
    context_object_name = "entry"

    def get_queryset(self):
        return JournalEntry.objects.select_related(
            "lease__unit__property", "property", "created_by"
        ).prefetch_related("lines__account")


class ControlTieView(ManagerRequiredMixin, TemplateView):
    template_name = "management/accounting_control.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tie"] = services.ar_control_tie()
        context["rows"] = services.trial_balance()
        return context
