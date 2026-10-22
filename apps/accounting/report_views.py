"""B4 report screens and CSV hand-offs; every figure comes from reports.py."""

import csv
import datetime as dt

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from apps.accounting import reports
from apps.accounts.permissions import ManagerRequiredMixin


def _date(value, fallback):
    try:
        return dt.date.fromisoformat(value)
    except TypeError, ValueError:
        return fallback


def _period(request):
    today = timezone.localdate()
    start = _date(request.GET.get("start"), today.replace(month=1, day=1))
    end = _date(request.GET.get("end"), today)
    return start, end


def _csv(name, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([str(value) if value is not None else "" for value in row])
    return response


class ReportIndexView(ManagerRequiredMixin, View):
    def get(self, request):
        return render(request, "management/accounting_reports.html")


class IncomeStatementView(ManagerRequiredMixin, View):
    template_name = "management/accounting_income_statement.html"

    def get(self, request):
        start, end = _period(request)
        report = reports.income_statement(start, end)
        if request.GET.get("format") == "csv":
            rows = [
                (start, end, "Income", row["account"].code, row["account"].name, row["amount"])
                for row in report["income"]
            ] + [
                (start, end, "Expense", row["account"].code, row["account"].name, row["amount"])
                for row in report["expenses"]
            ]
            return _csv(
                f"income-statement-{start}-{end}",
                ["start", "end", "section", "code", "account", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "start": start, "end": end})


class BalanceSheetView(ManagerRequiredMixin, View):
    template_name = "management/accounting_balance_sheet.html"

    def get(self, request):
        as_of = _date(request.GET.get("as_of"), timezone.localdate())
        report = reports.balance_sheet(as_of)
        if request.GET.get("format") == "csv":
            rows = [
                (as_of, kind, row["code"], row["name"], row["amount"])
                for kind in ("assets", "liabilities", "equity")
                for row in report[kind]
            ]
            return _csv(
                f"balance-sheet-{as_of}",
                ["as_of", "section", "code", "account", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "as_of": as_of})


class CashFlowView(ManagerRequiredMixin, View):
    template_name = "management/accounting_cash_flow.html"

    def get(self, request):
        start, end = _period(request)
        report = reports.cash_flow(start, end)
        if request.GET.get("format") == "csv":
            rows = [
                (start, end, row["category"], row["label"], row["amount"]) for row in report["rows"]
            ]
            return _csv(
                f"cash-flow-{start}-{end}",
                ["start", "end", "category", "label", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "start": start, "end": end})


class ScheduleEView(ManagerRequiredMixin, View):
    template_name = "management/accounting_schedule_e.html"

    def get(self, request):
        start, end = _period(request)
        report = reports.schedule_e(start, end)
        if request.GET.get("format") == "csv":
            rows = [
                (start, end, row["line"], row["label"], row["amount"]) for row in report["lines"]
            ]
            return _csv(
                f"schedule-e-{start}-{end}",
                ["start", "end", "line", "label", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "start": start, "end": end})


class ARAgingView(ManagerRequiredMixin, View):
    template_name = "management/accounting_ar_aging.html"

    def get(self, request):
        as_of = _date(request.GET.get("as_of"), timezone.localdate())
        report = reports.ar_aging(as_of)
        if request.GET.get("format") == "csv":
            rows = [
                (
                    as_of,
                    row["lease"].unit.property.name,
                    row["lease"].unit.label,
                    row["date"],
                    row["description"],
                    row["bucket"],
                    row["amount"],
                )
                for row in report["rows"]
            ]
            return _csv(
                f"ar-aging-{as_of}",
                ["as_of", "property", "unit", "date", "description", "bucket", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "as_of": as_of})


class APAgingView(ManagerRequiredMixin, View):
    template_name = "management/accounting_ap_aging.html"

    def get(self, request):
        as_of = _date(request.GET.get("as_of"), timezone.localdate())
        report = reports.ap_aging(as_of)
        if request.GET.get("format") == "csv":
            rows = [
                (
                    as_of,
                    row["bill"].property.name,
                    row["bill"].description,
                    row["bill"].due_date,
                    row["bucket"],
                    row["amount"],
                )
                for row in report["rows"]
            ]
            return _csv(
                f"ap-aging-{as_of}",
                ["as_of", "property", "description", "due", "bucket", "amount"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "as_of": as_of})


class DepositRegisterView(ManagerRequiredMixin, View):
    template_name = "management/accounting_deposit_register.html"

    def get(self, request):
        as_of = _date(request.GET.get("as_of"), timezone.localdate())
        report = reports.deposit_register(as_of)
        if request.GET.get("format") == "csv":
            rows = [
                (as_of, row["lease"].unit.property.name, row["lease"].unit.label, row["held"])
                for row in report["rows"]
            ]
            return _csv(
                f"deposit-register-{as_of}",
                ["as_of", "property", "unit", "held"],
                rows,
            )
        return render(request, self.template_name, {"report": report, "as_of": as_of})
