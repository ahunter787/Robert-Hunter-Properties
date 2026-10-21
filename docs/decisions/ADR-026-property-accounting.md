# ADR-026 — Property accounting is built in, and exported, not outsourced

**Cutover amendment, October 20:** ADR-027 is approved for the tenant starting-account release before
B1–B5. It introduces tenant-facing starting records but no GL. The blueprint's pending/receipt/bank and
deposit assumptions require the corrections in its cutover amendment before accounting code is built.

Status: Accepted for design, October 20, 2026. The owner approved this direction after the industry
comparison below and rejected GnuCash as a backend. Implementation proceeds in the slices recorded in
[the blueprint](../design/property-accounting.md), one owner review at a time.

## Context

RHP records tenant money as an append-only **sub-ledger**: charges (rent, NNN, expense recoveries,
adjustments, brought-forward balances), payments (received, cleared, voided, reversed), allocations and
derived statements ([ADR-008](ADR-008-rent-ledger.md), [ADR-017](ADR-017-charge-lifecycle.md)). It has no
general ledger — no chart of accounts, no bank accounts or reconciliation, no accounts payable, no
financial statements — and E10 has always said its design must define *"a chart of accounts, bank
reconciliation, expenses, owner reports, and the boundary between tenant ledger transactions and the
general ledger before implementation begins"* ([extensions §11](../extensions.md)).

The owner's question was whether RHP should integrate an established accounting system instead of building
one. GnuCash was the proposed candidate. The answer turned out to be the opposite of instinct: every
established property-management product **builds its accounting**, and treats external accounting software
as a downstream copy.

## What the established products do

- **Buildium** sells "purpose-built property management accounting software": accounts payable ("change
  work orders into bills, then pay them online"), **automatic bank-statement reconciliation**, reports
  that follow **trust-accounting rules**, 1099 e-filing, and an Open API for getting data out
  ([buildium.com](https://www.buildium.com/features/property-management-accounting/)).
- **AppFolio** keeps a full GL in the product: operating and escrow cash accounts, a Security Deposit
  escrow liability, a Prepayment liability, **every transaction must name a property**, and a **three-way
  reconciliation** (bank statement balance = cleared balance = adjusted cash balance from the property
  ledgers). Cash basis is its default, accrual available
  ([APM Help: how trust accounting works inside AppFolio](https://www.apmhelp.com/blog/appfolio/how-trust-accounting-actually-works-inside-appfolio-the-full-structure)).
- **TenantCloud** has its own income, expense and liability accounting, invoices, bills and deposits — and a
  **one-way sync out to QuickBooks Online**, mirroring transactions and contacts into QBO
  ([TenantCloud help](https://support.tenantcloud.com/en/articles/11908588-how-do-i-synchronize-my-data-into-quickbooks)).
- **Innago** likewise keeps bank accounts, invoices, expenses and reports in the product, and offers a
  one-way QuickBooks sync that maps a property to a QBO Customer or Class
  ([Innago help](https://help.innago.com/articles/what-data-syncs-from-innago-to-quickbooks/)).

The pattern is consistent: **property accounting is operationally coupled to the rent roll**, so the
product owns it; QuickBooks is the copy the owner's accountant may keep, never the other way round. Trust
and escrow accounting exists only because a property *manager* holds other people's money.

## GnuCash considered and rejected as a backend

GnuCash is a desktop application (current stable 5.17, GPL) with no network API and no server mode
([gnucash.org](https://www.gnucash.org/), [gnucash-cli man page](https://raw.githubusercontent.com/Gnucash/gnucash/stable/doc/gnucash-cli.1.in)).
Its SQL backends (PostgreSQL/MySQL/SQLite since 2.4) are explicitly **not** a multi-user database: one book
per database, a `gnclock` table that gives only *"weak protection against simultaneous access"*, and a
catch-all `slots` table that is an internal representation rather than an integration surface
([GnuCash wiki: SQL](https://wiki.gnucash.org/wiki/SQL)). The project says GnuCash *"is not designed to have
multiple instances manipulating the data at the same time"* ([wiki: Python bindings](https://wiki.gnucash.org/wiki/Python_Bindings)),
and its FAQ requires that the database *"must not"* be written except through the GnuCash libraries
([wiki: FAQ](https://wiki.gnucash.org/wiki/FAQ)). The only pip-installable library, `piecash`, is MIT but
*"not endorsed"* by the GnuCash developers, is beta, supports books only up to GnuCash 4.2, was last
released in July 2024 and was tested on Python 3.6–3.9 ([PyPI](https://pypi.org/project/piecash/)) — and it
**cannot post invoices**, because posting is engine work it does not link. Headless report generation exists
(`gnucash-cli --report run`) but it is a batch desktop tool, not a service.

GnuCash therefore cannot be a backend for generating invoices, reconciling accounts or producing statements
from a web application. Forcing it would mean writing to an unsupported database from outside its
libraries, with a single-user lock and a licensing question attached. The owner's instruction was explicit:
*"If gnucash is not designed for this, we should not force it to be something its not."*

## Decision

**RHP builds a bounded double-entry general ledger for landlord-side accounting, and exports it one-way for
an accountant.** The tenant sub-ledger remains the operational source of truth; the GL posts from it and
never re-derives it.

In scope:

- **Chart of accounts** — Schedule E-aligned by default, editable by an administrator.
- **Journals** — balanced entries posted automatically from charges, payments, adjustments, repair costs,
  disbursements and security-deposit movements, plus manual entries for owner draws, contributions and
  corrections. Posted entries are immutable; corrections are reversing entries, as everywhere in RHP.
- **Cash and banks** — bank/cash accounts, statement imports, a **three-way reconciliation** that refuses to
  mark a period reconciled until statement, cleared and adjusted balances agree.
- **Sub-ledger controls** — an AR control account that must equal the sum of the tenant-ledger balances,
  and an AP control that must equal recorded repair costs less disbursements.
- **Statements and reports** — trial balance, income statement by property and portfolio, balance sheet,
  cash flow, Schedule E summary, aging tie-outs and a security-deposit register.
- **Closing** — year-end closing entries into retained earnings/owner equity; owner draws and contributions.

Out of scope, recorded so nobody assumes them:

- **Trust/escrow accounting, management fees, third-party owners** — RHP owns its properties; there are no
  client funds to hold in trust. A bank-account *kind* keeps a separate deposit account possible where state
  law requires one, without a trust module.
- **1099 e-filing**, depreciation and tax schedules — the owner's business-side direction in
  [extensions §13](../extensions.md) is a separate domain, after Phase 12.
- **Payment processing** (Phase 11) and **tenant-facing changes** — none.
- **A SaaS or desktop dependency** — no QuickBooks/Xero requirement, no GnuCash on the write path. A journal
  export (accountant CSV, and a plain-text journal hledger/beancount can read) is the hand-off if an
  accountant wants one.

## Consequences

**Positive**

- The property's books and the tenant's ledger are one system of record, so an AR control total can be
  tested against the ledger rather than argued about.
- Self-hosted, no recurring SaaS cost, no tenant or owner financial data leaving the home server.
- Statements, reconciliation and owner reports are available where the operational data already lives.
- The export path keeps the door open to an accountant without making an external product the source of
  truth.

**Negative / accepted trade-offs**

- This is the largest extension in the plan: a GL, bank reconciliation, AP and statements are real work, and
  they are sliced (`E10-B1` … `E10-B5`) with an owner review between slices.
- The default chart of accounts and its Schedule E mapping need the owner's accountant to confirm them; the
  chart is editable for that reason.
- Accrual basis means the GL carries tenant receivables; a cash-basis report view is a later, additive
  report, not a second set of entries.
- The books are only as good as the bank statements fed to reconciliation and the disbursements recorded;
  RHP will now record cash out as well as cash in, which is new data discipline.

## Alternatives rejected

- **GnuCash as a backend** — see above; single-user, no API, unsupported writes.
- **A SaaS ledger as the primary system (QuickBooks Online, Xero)** — real APIs and real accounting, but a
  recurring cost, the money data leaves the self-hosted server, and the operational system would have to
  reconcile itself to an external truth. Kept as an export target if an accountant later requires it.
- **A full ERP (ERPNext, Odoo)** — a second server, database and admin surface for a dozen units.
- **No GL at all** — then reconciliation and financial statements cannot be produced from RHP, which is
  exactly what E10 exists to fix.
