"""Manager-only B1 accounting surfaces: controls, journals and the chart.

There is deliberately no tenant-facing journal screen. The GL is an office view over the
same tenancy facts; a tenant sees their statement, not the books.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views import View
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


class OpeningBalanceListView(ManagerRequiredMixin, ListView):
    template_name = "management/accounting_opening_list.html"
    context_object_name = "batches"

    def get_queryset(self):
        from apps.accounting.models import OpeningBalanceBatch

        return OpeningBalanceBatch.objects.select_related("journal", "created_by").prefetch_related(
            "lines__account"
        )


class OpeningBalanceCreateView(ManagerRequiredMixin, View):
    template_name = "management/accounting_opening_form.html"

    def get(self, request):
        from django.utils import timezone

        from apps.accounting.forms import OpeningBalanceForm, OpeningLineFormSet

        return render(
            request,
            self.template_name,
            {
                "form": OpeningBalanceForm(initial={"as_of": timezone.localdate()}),
                "formset": OpeningLineFormSet(),
            },
        )

    def post(self, request):
        from django.contrib import messages

        from apps.accounting.forms import OpeningBalanceForm, OpeningLineFormSet

        form = OpeningBalanceForm(request.POST)
        formset = OpeningLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            lines = []
            for row in formset.cleaned_data:
                if not row or not row.get("account"):
                    continue
                lines.append(
                    {
                        "account": row["account"],
                        "property": row.get("property"),
                        "debit": row.get("debit") or 0,
                        "credit": row.get("credit") or 0,
                        "memo": row.get("memo", ""),
                    }
                )
            try:
                services.post_opening_batch(
                    as_of=form.cleaned_data["as_of"],
                    note=form.cleaned_data["note"],
                    lines=lines,
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                messages.success(request, "Opening balances posted.")
                return redirect("accounting:opening-list")
        return render(
            request,
            self.template_name,
            {"form": form, "formset": formset},
        )


class VendorBillListView(ManagerRequiredMixin, ListView):
    template_name = "management/accounting_bill_list.html"
    context_object_name = "bills"
    paginate_by = 50

    def get_queryset(self):
        from apps.accounting.models import VendorBill

        return (
            VendorBill.objects.select_related("property", "vendor", "expense_account")
            .prefetch_related("payments")
            .order_by("due_date", "pk")
        )


class VendorBillCreateView(ManagerRequiredMixin, View):
    template_name = "management/accounting_bill_form.html"

    def get(self, request):
        from apps.accounting.forms import VendorBillForm

        return render(request, self.template_name, {"form": VendorBillForm()})

    def post(self, request):
        from django.contrib import messages

        from apps.accounting.forms import VendorBillForm

        form = VendorBillForm(request.POST)
        if form.is_valid():
            try:
                bill = services.record_vendor_bill(
                    property=form.cleaned_data["property"],
                    vendor=form.cleaned_data.get("vendor"),
                    expense_account=form.cleaned_data["expense_account"],
                    description=form.cleaned_data["description"],
                    amount=form.cleaned_data["amount"],
                    received_on=form.cleaned_data["received_on"],
                    due_date=form.cleaned_data["due_date"],
                    note=form.cleaned_data.get("note", ""),
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                messages.success(request, "Vendor bill recorded.")
                return redirect("accounting:bill-detail", pk=bill.pk)
        return render(request, self.template_name, {"form": form})


class VendorBillDetailView(ManagerRequiredMixin, View):
    template_name = "management/accounting_bill_detail.html"

    def _bill(self, pk):
        from django.shortcuts import get_object_or_404

        from apps.accounting.models import VendorBill

        return get_object_or_404(
            VendorBill.objects.select_related("property", "vendor").prefetch_related("payments"),
            pk=pk,
        )

    def get(self, request, pk):
        from django.utils import timezone

        from apps.accounting.forms import VendorPaymentForm

        bill = self._bill(pk)
        return render(
            request,
            self.template_name,
            {
                "bill": bill,
                "payment_form": VendorPaymentForm(initial={"paid_on": timezone.localdate()}),
            },
        )

    def post(self, request, pk):
        from django.contrib import messages

        from apps.accounting.forms import VendorPaymentForm

        bill = self._bill(pk)
        form = VendorPaymentForm(request.POST)
        if form.is_valid():
            try:
                services.pay_vendor_bill(
                    bill,
                    amount=form.cleaned_data["amount"],
                    paid_on=form.cleaned_data["paid_on"],
                    method=form.cleaned_data["method"],
                    reference=form.cleaned_data.get("reference", ""),
                    note=form.cleaned_data.get("note", ""),
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                messages.success(request, "Vendor payment recorded.")
                return redirect("accounting:bill-detail", pk=bill.pk)
        return render(
            request,
            self.template_name,
            {"bill": bill, "payment_form": form},
        )


class BankAccountListView(ManagerRequiredMixin, ListView):
    template_name = "management/accounting_bank_list.html"
    context_object_name = "accounts"

    def get_queryset(self):
        from apps.accounting.models import BankAccount

        return BankAccount.objects.select_related("chart_account").filter(is_active=True)


class BankAccountCreateView(ManagerRequiredMixin, View):
    template_name = "management/accounting_bank_form.html"

    def get(self, request):
        from apps.accounting.forms import BankAccountForm

        return render(request, self.template_name, {"form": BankAccountForm()})

    def post(self, request):
        from django.contrib import messages

        from apps.accounting.forms import BankAccountForm
        from apps.accounting.models import BankAccount

        form = BankAccountForm(request.POST)
        if form.is_valid():
            BankAccount.objects.create(
                name=form.cleaned_data["name"],
                institution=form.cleaned_data["institution"],
                last_four=form.cleaned_data["last_four"],
                kind=form.cleaned_data["kind"],
                chart_account=form.cleaned_data["chart_account"],
            )
            messages.success(request, "Bank account added.")
            return redirect("accounting:bank-list")
        return render(request, self.template_name, {"form": form})


class BankAccountDetailView(ManagerRequiredMixin, View):
    template_name = "management/accounting_bank_detail.html"

    def _account(self, pk):
        from django.shortcuts import get_object_or_404

        from apps.accounting.models import BankAccount

        return get_object_or_404(
            BankAccount.objects.select_related("chart_account").prefetch_related(
                "movements", "statements"
            ),
            pk=pk,
        )

    def get(self, request, pk):
        from django.utils import timezone

        from apps.accounting.forms import BankMovementForm, BankStatementForm

        bank = self._account(pk)
        return render(
            request,
            self.template_name,
            {
                "bank": bank,
                "movement_form": BankMovementForm(initial={"date": timezone.localdate()}),
                "statement_form": BankStatementForm(),
                "tie": services.bank_control_tie(bank),
            },
        )

    def post(self, request, pk):
        from django.contrib import messages

        from apps.accounting.bank_csv import parse
        from apps.accounting.forms import BankMovementForm, BankStatementForm

        bank = self._account(pk)
        if request.POST.get("action") == "movement":
            form = BankMovementForm(request.POST)
            if form.is_valid():
                services.record_bank_movement(
                    bank,
                    date=form.cleaned_data["date"],
                    kind=form.cleaned_data["kind"],
                    amount=form.cleaned_data["amount"],
                    reference=form.cleaned_data.get("reference", ""),
                    memo=form.cleaned_data.get("memo", ""),
                    actor=request.user,
                )
                messages.success(request, "Bank movement recorded.")
                return redirect("accounting:bank-detail", pk=bank.pk)
        else:
            form = BankStatementForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    rows = parse(form.cleaned_data["file"].read().decode("utf-8-sig"))
                    statement = services.import_bank_statement(
                        bank,
                        period_start=form.cleaned_data["period_start"],
                        period_end=form.cleaned_data["period_end"],
                        opening_balance=form.cleaned_data["opening_balance"],
                        closing_balance=form.cleaned_data["closing_balance"],
                        rows=rows,
                        source_name=form.cleaned_data.get("source_name", ""),
                        actor=request.user,
                    )
                except (ValidationError, UnicodeDecodeError) as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, "Statement imported and auto-matched.")
                    return redirect("accounting:statement-detail", pk=statement.pk)
        return render(
            request,
            self.template_name,
            {
                "bank": bank,
                "movement_form": BankMovementForm(request.POST or None),
                "statement_form": BankStatementForm(request.POST or None, request.FILES or None),
                "tie": services.bank_control_tie(bank),
            },
        )


class BankStatementDetailView(ManagerRequiredMixin, View):
    template_name = "management/accounting_statement_detail.html"

    def _statement(self, pk):
        from django.shortcuts import get_object_or_404

        from apps.accounting.models import BankStatement

        return get_object_or_404(
            BankStatement.objects.select_related("bank_account", "reconciliation").prefetch_related(
                "lines__matched_journal_line__entry"
            ),
            pk=pk,
        )

    def get(self, request, pk):
        return render(request, self.template_name, {"statement": self._statement(pk)})

    def post(self, request, pk):
        from django.contrib import messages

        statement = self._statement(pk)
        if request.POST.get("action") == "match":
            matched = services.auto_match_statement(statement)
            messages.success(request, f"{matched} line(s) matched.")
        else:
            try:
                services.reconcile_bank_statement(statement, actor=request.user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Statement reconciled.")
        return redirect("accounting:statement-detail", pk=statement.pk)
