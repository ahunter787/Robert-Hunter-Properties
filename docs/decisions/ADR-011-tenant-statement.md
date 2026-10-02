# ADR-011: How a tenant reads their money

- **Status:** Accepted (review round on Phase 5)
- **Date:** 2026-10-02
- **Context:** a corrected rent charge read as money arriving and leaving again

## Context

The owner read their own tenant's payment history and described the problem precisely:

> Since the box is "What you were charged", then I see 2084 paid, then -2084 credited, it feels like I
> paid 2084, then received it. I want the tenant to see they were charged 0 after the adjusted price.

They were right, and the cause is structural rather than cosmetic. ADR-008 requires corrections to be
**their own entries**: a charge is never edited, an adjustment is a second row that names what it
corrects, and the office can always see who changed what and why. That is the right record. But Phase 4
surfaced those entries directly to the tenant, and an entry-level reading of an accounting record is not
a statement — it is a transaction log.

Two further problems came from the same place: the page split charges and payments into two boxes, which
read as unrelated, and a monthly charge means the list grows forever on a page a tenant may open on a
phone.

## Decision

### The tenant reads a statement; the office reads the entries

`LeaseLedger` keeps `charges` and `activity` exactly as they are — the staff ledger, the lease panel and
the audit trail are untouched. A second, read-only derivation, `LeaseLedger.statement`, reads the *same*
loaded rows the way a person paying a bill reads them. It costs no queries (the adjustments are already
in memory as charges with an `adjusts` link), and it cannot disagree with the balance because it is
derived from the same `ChargeLine` allocation.

### An adjustment is absorbed into the charge it corrects

- A charge's headline figure is its **net**: what it costs now.
- The adjustment appears beneath it as an explanation — *"was $2,084.00, adjusted down by $2,084.00"* —
  never as a row of its own. A charge raised at $2,084 and corrected to nothing reads **$0.00, nothing to
  pay**.
- An adjustment that names no charge is a charge in its own right and stays its own line: there is
  nothing to net it into.
- An adjustment that overshoots says so: the row shows $0.00 and notes how much is in credit.

### Paid and credited are never confused

Phase 4 applies a correction to its own charge first, then allocates real payments to what remains, so
`settled = credited + paid`. The statement separates them again: **paid** is money received, and a credit
never appears as one. A charge adjusted down by $400 and paid $600 shows *paid $600.00*, not $1,000.

### One list, in date order, paginated

Charges (netted) and payments sit in a single **statement**, newest first, with the charge shown before
the payment on a shared date. Each charge row states its own settlement — *"paid $400.00 of $1,000.00"* —
which is the connection two separate boxes could not express. The list is paginated at 20 entries, so a
long tenancy reads a page at a time; an out-of-range link falls back rather than failing.

The same statement feeds the dashboard's recent activity and the lease page's activity block, so the
three tenant surfaces cannot tell three stories.

### The tenant-facing state machine is its own

`ChargeLine.state` answers the office's question against the **gross** charge. The statement answers the
tenant's against the **net**: `Adjusted` (nothing to pay), `Paid`, `Payment pending`, `Overdue`,
`Partly paid`, `Unpaid` — in that order of precedence.

### The adjustment's free-text reason is not shown

The tenant sees that a charge was adjusted and by how much. The wording an administrator typed
("raised in error", "goodwill") stays office-facing. This is a deliberate default: the field is free
text, and free text written for colleagues is not automatically fit to publish. If the owner wants the
reason shown, it is one template line.

## Consequences

**Positive**

- A correction reads as a correction. The most common case — a charge raised in error and cancelled —
  now reads as "$0.00, nothing to pay" instead of two opposing amounts.
- Paid money and credited money are visibly different, which matters when a tenant is trying to work out
  what they actually sent.
- One list with per-charge settlement answers "did that payment cover this month?" without arithmetic.
- The list cannot sprawl: it pages.
- The office's record is unchanged, so nothing about auditability or immutability was traded away.

**Negative / accepted trade-offs**

- The same records now have two readings, and they must be kept in step. The risk is contained by having
  one derivation over one `LeaseLedger`, with tests asserting both, rather than two independent queries.
- A tenant cannot see the individual adjustment entry, its author, or its reason on their page. Accepted:
  that is the office's account of the correction, and the tenant sees its effect.
- Netting hides *when* a correction happened. The statement's date is the charge's due date, not the date
  of the adjustment. Accepted for now; if a tenant needs the timeline, a "history" expander is the next
  step rather than a return to opposing rows.
- Pagination adds a second page state to a small page. Cheap, and better than an unbounded list.

## Alternatives considered

- **Showing the adjustment as its own row with a friendlier label** ("Reduced by" instead of a negative
  number): less confusing than today and still two rows for one bill, and still the tenant's job to
  subtract. Rejected.
- **Hiding adjustments from the tenant entirely**: the balance would change with no explanation, which is
  worse than a confusing one. Rejected.
- **Editing the original charge instead of adding an adjustment**: simpler to display and forbidden by
  ADR-008 — the record must show what was raised and what corrected it.
- **Showing the reason text**: may be useful, and is free text written for colleagues. Deferred, one line
  away.
- **Keeping two boxes with a running balance in each**: preserves the current layout and keeps the two
  halves unrelated, which was half the complaint.
- **A "history" view separate from the statement**: the statement already is the history; a second view
  would need its own explanation of why it differs.
