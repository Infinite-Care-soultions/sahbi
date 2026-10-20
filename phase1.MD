# PHASE 1: Financial Data Model

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase designs and implements the initial Sahbi Frappe DocTypes.
It does not implement LLM integration, chat routing, or posting APIs.

Do not proceed to later phases from this file.

---

## Scope of this phase

Design and implement the initial Sahbi Frappe DocTypes.

Start by proposing the schema and its relationships.
Then implement the schema and tests.

The design must cover:

1. Financial Workspace
2. Person
3. Financial Transaction
4. Payment
5. Payment Allocation
6. Opening Balance
7. Audit History

Before implementation, explain how the schema will prevent:

- Duplicate income
- Duplicate expenses
- Duplicate payment recording
- Incorrect outstanding balances
- Cross-user data access
- Deletion of posted financial history

Use Frappe naming, permissions, migrations, and validations.
Create automated tests for schema constraints and relationships.

---

## Schema

One original money document, one payment document, and one
allocation document. Opening balance is a classification on the
original document, not a second ledger.

```
User 1---1 Sahbi Workspace
Sahbi Workspace 1---* Sahbi Person
Sahbi Workspace 1---* Sahbi Entry
Sahbi Workspace 1---* Sahbi Payment
Sahbi Payment 1---* Sahbi Payment Allocation
Sahbi Entry 1---* Sahbi Payment Allocation
Sahbi Person 0---* Sahbi Entry
Sahbi Person 0---* Sahbi Payment
```

### 1. Sahbi Workspace

One default workspace per user. Unique on `user`.

Extensible later by dropping that unique constraint and allowing
more than one workspace per user. MVP records stay valid.

Fields: title, user, is_default, disabled, notes.

Not submittable. Cannot be deleted once people, entries, or
payments exist.

### 2. Sahbi Person

Optional on every entry and payment. No role field.

A person is a name inside a workspace. The same human can be a
buyer on a sale and a lender on a loan without a second record.

`person_name` is required on the person row itself. Contact fields
are optional. Names are unique per workspace after normalization
(trim, collapse spaces, casefold). The same name may exist in
another workspace.

### 3. Sahbi Entry

The original financial operation. Submittable. Amend is disabled.

Types:

- Income
- Expense
- Sale
- Purchase
- Loan
- Opening Balance

Amount is always positive. Sign comes from type and direction.

Direction:

- Sale: always Receivable
- Purchase: always Payable
- Loan and Opening Balance: required Receivable or Payable
- Income and Expense: no direction, not allocatable

Required: type, amount, transaction_date, workspace, currency.
Optional: person, description.

`creation` is the Frappe timestamp. `transaction_date` is the
business date and defaults to today in the site timezone.

Paid and outstanding amounts are read-only and derived from
submitted allocations. They are not a second source of truth.

### 4. Sahbi Payment

An independent submitted payment. Not an income or expense row.

Required: workspace, amount, payment_date, payment_kind
(Incoming or Outgoing), currency.

Optional: person, description.

Allocated and unallocated amounts are derived from submitted
allocations.

### 5. Sahbi Payment Allocation

Links one payment to one original entry and stores the allocated
amount.

Rules enforced on validate / submit:

- Payment and entry must be submitted
- Both must belong to the same workspace
- Entry type must be Sale, Purchase, Loan, or Opening Balance
- Incoming payments allocate only to Receivable entries
- Outgoing payments allocate only to Payable entries
- Sum of allocations for a payment cannot exceed the payment
- Sum of allocations for an entry cannot exceed the entry
- Overpayment is not allowed in this phase

Cancelling a payment cancels its submitted allocations and
recomputes outstanding amounts. An entry cannot be cancelled
while a submitted allocation still points at it.

### 6. Opening Balance

`entry_type = Opening Balance` with a required direction.

It is not Income, Expense, Sale, Purchase, or Loan. It can receive
allocations so old balances can be settled later.

### 7. Audit History

Posted rows are never deleted.

Each entry and payment has:

- Frappe owner, creation, modified, modified_by, docstatus
- `track_changes`
- `idempotency_key`
- `reversal_of`, `replaces`, `replaced_by`
- `cancellation_reason`

Correction and cancellation workflows are later phases. The
fields and cancel/delete guards exist now so later work does not
rewrite the ledger.

---

## How the schema prevents the listed failures

### Duplicate income and duplicate expenses

Technical: unique `(workspace, idempotency_key)` on Sahbi Entry.
The same retried request key cannot post twice.

Income and expense cannot receive allocations, so a collection
cannot be posted a second time as income through this schema.

Semantic near-duplicate prompts are a later posting-service
concern. This phase only makes silent double-inserts fail.

### Duplicate payment recording

Unique `(workspace, idempotency_key)` on Sahbi Payment.
Payments are their own documents. A payment is not an expense
or income row.

### Incorrect outstanding balances

Outstanding is `entry.amount - sum(submitted allocations)`.
Paid is the same sum. Both are rewritten from allocations on
submit and cancel. Decimal arithmetic uses `decimal.Decimal`
quantized to 0.01. Income and expense outstanding stays zero.

### Cross-user data access

Every money row carries `workspace`. List queries restrict
non-system users to workspaces they own. Document permission
hooks deny read/write across workspaces. Sahbi User has no
delete on posted money documents.

### Deletion of posted financial history

Submitted and cancelled entries, payments, and allocations
cannot be deleted. Frappe amend is disabled. Linked workspace
and person rows cannot be deleted.

---

## Implementation notes

- Money helper: `sahbi/money.py`. Do not add raw floats.
- Shared allocation math: `sahbi/ledger.py`.
- Workspace bootstrap: `sahbi/workspace.py`.
  `after_migrate` / `after_install` create Role `Sahbi User`
  and one workspace per enabled user.
- New users get a workspace on `User.after_insert`.
- Currency default is EGP. Site timezone remains Africa/Cairo.
- Household vs work is not a field in this phase. Sale,
  purchase, and loan already imply work. Adding a tag later
  does not break these tables.
- No LLM, no chat DocType, no ERPNext.

---

## Files created or changed

Created:

- `sahbi/money.py`
- `sahbi/ledger.py`
- `sahbi/permissions.py`
- `sahbi/workspace.py`
- `sahbi/sahbi/doctype/sahbi_workspace/`
- `sahbi/sahbi/doctype/sahbi_person/`
- `sahbi/sahbi/doctype/sahbi_entry/`
- `sahbi/sahbi/doctype/sahbi_payment/`
- `sahbi/sahbi/doctype/sahbi_payment_allocation/`
- `sahbi/tests/helpers.py`
- `sahbi/tests/test_financial_schema.py`

Changed:

- `sahbi/hooks.py` — permissions, User hook, after_migrate
- `phase1.MD` — this report

Site only (not in the app repo):

- `shbi.localhost` migrated
- Workspaces `WS-00001` (Administrator) and `WS-00002`
  (beshoyatef31@gmail.com)

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost migrate
bench --site shbi.localhost run-tests --app sahbi
```

Migrate: Sahbi DocTypes synced, `after_migrate` ran.

Tests: `Ran 18 tests in 4.201s` — OK

Covered:

- One workspace per user
- Person has no role; optional on entries
- Person unique per workspace, reusable across workspaces
- Income not allocatable
- Opening Balance is its own type
- Loan requires direction
- Sale / Purchase set direction
- Idempotency on entries and payments
- Decimal allocations 10.10 + 10.20 = 20.30
- Allocation cannot exceed payment or entry
- Direction mismatch rejected
- Cross-workspace allocation rejected
- Person must belong to the entry workspace
- Submitted and cancelled rows cannot be deleted
- Entry cancel blocked while allocations exist
- Payment cancel restores outstanding and keeps allocation history
- Audit reference fields exist
- Users cannot list or read another workspace

---

## Phase 1 conclusion

The financial tables exist and the constraint tests passed.

Next phase may add a deterministic posting service on top of
these documents. It must not add LLM calls or a chat UI.

Still open, and not decided in this phase:

- Incoming default for `محمد اداني` when no open debt exists
- Channel for the text interface
- Larger Qwen model
- Correction / reverse-and-repost workflow
