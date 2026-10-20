# Financial language, icons and color — approved specification

**Status:** Owner-approved financial meanings, October 20, 2026. Implementation begins with the
shared lease workspace checkpoint. Earlier blue/amber/purple-credit proposals are superseded.

## The five questions every financial screen should answer

1. Whose account or property is this?
2. Is this money owed, money received, a cost, or a correction?
3. Is it recorded, only scheduled, pending, or complete?
4. What will this action change, and will any money actually move?
5. What is the next action?

Use familiar headings rather than expose model/service names. Keep Rent & Payments and Expense
recoveries in the main navigation for this proposal; do not reopen the accepted dashboard/navigation
design wholesale. A lease is the contract/context; Rent & Payments is its account activity. Ledger
may remain a secondary description such as “Transaction history (ledger),” not a competing place.

## Vocabulary matrix

| Current | Proposed primary wording | Meaning / guardrail |
| --- | --- | --- |
| Lease workspace | Lease details | Contract, people, dates, rent schedule, documents and linked account |
| Full-width ledger / Lease ledger | Rent & Payments for Studio A | Same account through either preserved URL; no second account |
| Post due charges | Post due charges + “Add amounts due to this tenant's account” | Records debt only; not a transfer, invoice email or payment |
| Not posted | Not yet added to account | Scheduled/expected, excluded from current recorded balance |
| Upcoming | Upcoming charges OR Next scheduled rent | Explicit recorded versus expected label, never one interchangeable definition |
| Position today | Account balance / Credit balance | Conditional positive debt or credit; not “negative owed” |
| Record payment | Record payment received | Record an outside payment; do not imply portal processing |
| Cleared — the money is in | Received — counts toward the balance | Use only where existing cleared state applies; not bank-reconciled proof |
| Pending — money expected | Expected payment — not yet received | Does not reduce the balance |
| Mark cleared | Confirm payment received | Show expected payment, tenant, amount and resulting balance |
| Void | Cancel expected payment | Does not send money and does not delete history |
| Reverse payment | Undo recorded payment | Undo the recorded effect, not issue a bank refund |
| Adjust | Correct charge | Choose Increase/Reduce; show resulting total before confirmation |
| What this does | Change to charge | Explicit Increase / Reduce, not ambiguous debit/credit direction |
| Component paid / remaining | Bill payment status and remaining amount | No per-component settlement breakdown; payments remain separate records |
| Settle financial account | Close financial account | Proposed display label; immutable settled-account lock remains unchanged |
| Reopen financial account | Reopen financial account | Enables allowed corrections/payments; never restores occupancy |
| Complete disposition | Deposit return and deductions recorded | Do not suggest an unimplemented workflow is available now |
| Set up prior lease activity | Set up starting account records | One-time setup; not a recurring daily task |
| Recreate charges from lease start | Enter full account history | Retain existing generation and aggregate historical-receipt behavior with an explicit preview |
| Enter an opening balance | Start with a known balance | Record balance at cutover, not a newly received payment |
| Figures as of | Balance / payment total as of | Label matches the chosen method and exact effective date |
| Received before RHP | Payments already received | Actual historical receipts supplied by manager, not implied from arithmetic |
| One settling payment | One summary of earlier payments | Explain the effect without implying it happened today |
| Stated rent amounts | Rent amounts entered from the lease | Exact contract schedule, not a new rent-calculation feature |
| NNN | Triple-net (NNN) charges | Expand on first use on independently reachable screens |
| Send remainder to | Assign remaining monthly amount to | Allocation only; no cash transfer |
| Prepare tenant recharge | Charge a tenant for this repair | Separate manual responsibility decision and existing review |
| Net tenant charges posted | Charges added to tenant accounts | Charge links and corrections explain net amount; not collected income |
| Repair expense / increase | Record repair cost / Increase recorded cost | Cost record, not vendor payment |
| File document / filed against | Upload document / Related to | Keep exact visibility and association rules |
| Publish internal note | Share a copy with selected tenants | Publication is explicit; original private history remains private |

Short examples: “Payment of $500.00 recorded for Alex Example.” “Charge reduced by $20.00; corrected
charge total $80.00.” “Allocations saved. No tenant charges were added.” These are synthetic examples,
not actual transactions or changes performed by this audit.

## Approved semantic visual system

Use small first-party inline SVG line icons from one visual family. Pair every icon with a type label;
decorative icons use `aria-hidden`, while the adjacent text provides the accessible name. Do not add an
icon/chart dependency. Amount signs describe the stated perspective, not a hidden bank-ledger convention.

| Meaning | Icon shape | Text / color on white | Must not imply |
| --- | --- | --- | --- |
| Payment received | Banknote with check mark | Amount green `#1c6b45`; label black | Download action, automatically bank-verified, processed by RHP, or rent-only |
| Rent | House with dollar sign | Owed amount red; label black | Document upload or payment already received |
| Expense Recovery | Receipt with dollar sign | Owed amount red; actual expense name retained | Vendor paid or money already collected |
| Other charge / amount owed | Dollar circle with plus | Amount red `#9c231c`; label black | Document upload or cash already received |
| Recorded cost / bill | Receipt with dollar sign | Amount red; label black | Vendor paid, cash left bank, or tenant liability |
| Expected payment | Clock | Black; “Expected—not received” | Receipt or balance reduction |
| Credit balance | Circle with minus | Amount green | Refund, income, or a newly received payment |
| Correction / undo | Curved arrow | Change amount purple `#6b21a8` | Transfer, deletion or rewritten history |
| Scheduled rent | Calendar | Black; “not yet added” | A recorded charge or part of the account balance |
| Historical setup | Open account book | Black labels; owed amount red, credit green | Money newly received on the setup date |

October 20 icon review: the initial tray-arrow and folded-document glyphs were rejected because
they resembled download/upload actions. Type-specific mappings above replace them in staff rows
and tenant statements, including grouped monthly components. Canceled expected payments use a
crossed clock; standalone adjustments use the correction symbol, not the generic charge symbol.
All icons remain first-party SVGs with adjacent visible text and no icon dependency.

The visible charge type is **Expense Recovery**, not the historical model label Responsibility.
Stored enum identifiers, existing financial entries, and tenant-facing actual expense names are
unchanged; tenant grouped statements retain their plain Property charges heading.

Bills are named by exact due date, for example **October 5th 2026 Bill**, not an isolated stream of
rent, NNN and expense-recovery charges. Include same-date one-time charges. Show the total and one
payment-progress summary on the bill; expanded components show amounts and corrections, never
individual paid/remaining figures. Payment records stay outside bills. Staff Adjust actions belong
to components only. The bill is a read-only grouping, not a new invoice or an emailed demand.

Measured text contrast on white: green 6.48:1, red 7.86:1 and purple 8.72:1.
These calculations do not certify real component contrast or focus states;
production surfaces, hover/disabled states and charts require separate checks. Soft tinted backgrounds
may support grouping, but the text/icon label remains essential in grayscale or color-vision differences.

Apply color only to the relevant monetary amount, not headings, unit names, percentages or entire rows.
A correction's delta is purple; resulting debt is red and resulting credit green. Blue and orange have
no financial meaning. Transaction type and status remain separate: a cost is not marked overdue without
an actual due-status rule. Preserve stable blue/pink unit identity
in allocation diagrams independently of financial statuses. Never recolor unit slices by occupancy or
debt. A vacant unit keeps its allocation and “Funded by RHP” label without a duplicate RHP slice.

## Layout and interaction rules

- Identity and balance context precede editable fields; retain property, unit and tenant names.
- Show one task per form; group dense edit pages rather than inventing a multi-step wizard for every
  short form. Two or three steps are appropriate for mutually exclusive setup/correction tasks.
- Essential consequences remain visible before submission. Optional definitions and technical history
  may be disclosed; legal/privacy consequences, errors and selected recipients may not be hidden.
- Preserve entered values, server-side validation and Back/Cancel without writes. Plain forms expose
  the same steps; JavaScript enhances rather than defines eligibility or arithmetic.
- Use a full-width financial table with inline corrections and meaningful phone labels. Compact
  summary/ring treatments must not push the first input several viewports below the task title.
- “Review” writes nothing; the final button names the outcome. Direct harmless edits can keep Save
  changes; add an explicit review where amounts, targets or consequential state changes need it.
- Keep account-history detail distinct from ordinary entry help. No raw audit metadata is exposed.

## Owner review

The owner approved these meanings and implementation scope in chat. Original scratch-sheet notes
remain preserved separately. No label change authorizes bank transfers, refunds, extra charging
permissions or rewriting old records. Nonfinancial editing findings remain deferred.
