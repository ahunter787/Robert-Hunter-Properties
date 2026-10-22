"""B5 accountant exports: a CSV journal and a plain-text journal, both checksummed."""

import csv
import hashlib
import io
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import ExportBatch, ExportKind, JournalLine
from apps.audit.models import AuditAction
from apps.audit.services import record


def _lines(start, end):
    return (
        JournalLine.objects.select_related("entry", "account", "property")
        .filter(entry__posted_on__gte=start, entry__posted_on__lte=end)
        .order_by("entry__posted_on", "entry__pk", "pk")
    )


def _csv_bytes(start, end):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "source",
            "account_code",
            "account_name",
            "property",
            "memo",
            "debit",
            "credit",
            "event",
        ]
    )
    count = 0
    for line in _lines(start, end):
        writer.writerow(
            [
                line.entry.posted_on.isoformat(),
                line.entry.source_key,
                line.account.code,
                line.account.name,
                line.property.name if line.property else "",
                line.memo,
                str(line.debit),
                str(line.credit),
                line.entry.event_type,
            ]
        )
        count += 1
    return output.getvalue().encode("utf-8"), count


def _text_bytes(start, end):
    output = io.StringIO()
    count = 0
    current_entry = None
    for line in _lines(start, end):
        if current_entry != line.entry_id:
            current_entry = line.entry_id
            output.write(
                f"{line.entry.posted_on.isoformat()} * {line.entry.source_key} | "
                f"{line.entry.memo}\n"
            )
        amount = line.debit if line.debit else -line.credit
        output.write(f"    {line.account.code} {line.account.name}  ${amount}\n")
        count += 1
    return output.getvalue().encode("utf-8"), count


@transaction.atomic
def create_journal_export(*, kind, start, end, actor=None):
    if start > end:
        raise ValidationError("The export period ends before it starts.")
    if kind == ExportKind.JOURNAL_CSV:
        content, count = _csv_bytes(start, end)
    elif kind == ExportKind.JOURNAL_TEXT:
        content, count = _text_bytes(start, end)
    else:
        raise ValidationError("Choose a supported export format.")
    batch = ExportBatch.objects.create(
        key=uuid4(),
        kind=kind,
        period_start=start,
        period_end=end,
        row_count=count,
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    record(
        actor,
        AuditAction.ACCOUNTING_EXPORT_CREATED,
        obj=batch,
        summary=f"{batch.get_kind_display()} {start}–{end}",
        rows=count,
        checksum=batch.checksum,
    )
    return batch, content
