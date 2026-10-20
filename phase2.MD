# PHASE 2: Deterministic Financial Engine

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase implements the financial business logic in Python using
Frappe. It does not implement LLM integration or a chat UI.

Do not proceed to later phases from this file.

---

## Scope of this phase

The engine must support:

- Create income, expense, sale, purchase, generic loan
- Create optional opening balances
- Record independent payment records
- Allocate payments to original transactions
- Calculate paid amounts and outstanding balances
- Calculate person receivables and payables
- Calculate income and expense totals
- Calculate period reports using transaction dates
- Handle partial payments and multiple installments
- Handle one payment allocated across multiple operations

Agreed classification rules:

Incoming money:
- If no clearly identifiable previous operation exists,
  classify it as new income.
- If it clearly settles a previous sale or loan receivable,
  link it to the existing operation.
- Never count a settlement twice.

Outgoing money:
- If no clearly identifiable previous obligation exists,
  classify it as a new expense.
- If it settles an existing purchase or payable,
  link it to that operation.
- Never count the same payment twice.

Loan rules:
- Money lent creates a receivable.
- Money borrowed creates a payable.
- Loan repayment does not create new income or expense.

Require explicit confirmation before correction or cancellation.
Use database transactions. Use Decimal-safe money. Use
idempotency for retried requests.

Do not implement automatic semantic duplicate rejection.
Do not implement LLM integration.

---

## Engine design

Public API: `sahbi.engine`

| Function | Purpose |
|---|---|
| `create_income` / `create_expense` | Cash entries. Not allocatable. |
| `create_sale` / `create_purchase` | Original operations with outstanding. |
| `create_loan` | Receivable if lent, payable if borrowed. |
| `create_opening_balance` | Separate type. Never income or expense. |
| `record_payment` | Independent payment plus optional allocations. |
| `record_incoming_money` | Classify or settle incoming cash. |
| `record_outgoing_money` | Classify or settle outgoing cash. |
| `cancel_entry` / `cancel_payment` | Preview, then cancel if `confirm=True`. |
| `correct_entry` | Preview, then cancel original and post replacement. |
| `get_person_balances` | Outstanding receivable and payable. |
| `get_income_expense_totals` | Period totals from transaction dates. |
| `get_period_report` | Income, expense, sales, purchases, loans, openings, collections. |

All writes go through `run_atomic`: a MariaDB savepoint rolls back
if any step fails.

Amounts are quantized with `decimal.Decimal` to 0.01. Paid and
outstanding amounts stay derived from submitted allocations.

### Classification

`record_incoming_money` / `record_outgoing_money`:

1. Explicit `allocations` → payment plus those links.
2. Explicit `settle_entry` → allocate to that operation.
3. Else, if a person is present, look for that person's open
   submitted operations in the matching direction.
4. Zero matches → income (incoming) or expense (outgoing).
5. One match → payment + allocation. Not income or expense.
6. Several matches → `AmbiguousSettlement`. Nothing is posted.

"Clearly identifiable" means exactly one open matching operation
for that person. No person means no identifiable prior operation.

A leftover above outstanding becomes a remainder income/expense
and is not added to the settled operation.

Loan repayments use the same settlement path, so they never post
as income or expense.

### Confirmation

`cancel_*` and `correct_entry` without `confirm=True` return
`status=needs_confirmation` and a preview of current values,
proposed change, linked payments, and impact. The database is
unchanged.

With `confirm=True`:

- Cancel linked allocations first.
- Cancel payments that then have no remaining allocations.
- Cancel the entry. Rows stay in the database.
- Correction posts a replacement and sets `replaces` /
  `replaced_by`. Posted amounts are never edited in place.

### Idempotency

The same `(workspace, idempotency_key)` returns the original
submitted document with `replayed=True`. It does not post again.

Semantic near-duplicates are not rejected.

### Permissions

Every engine call checks workspace ownership. A Sahbi User cannot
create, cancel, or report against another user's workspace.

---

## Files created or changed

Created:

- `sahbi/engine/__init__.py`
- `sahbi/engine/utils.py`
- `sahbi/engine/posting.py`
- `sahbi/engine/settlement.py`
- `sahbi/engine/corrections.py`
- `sahbi/engine/reports.py`
- `sahbi/tests/test_financial_engine.py`

Changed:

- `sahbi/permissions.py` — `assert_workspace_access`
- `phase2.MD` — this report

No DocType fields were added. No LLM code was added.

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost run-tests --app sahbi
```

`Ran 36 tests in 9.821s` — OK

18 schema tests from Phase 1 still pass.
18 engine tests from this phase pass, including:

1. Fully paid sale
2. Unpaid sale
3. Partial payment
4. Multiple payments against one sale
5. One payment allocated across multiple sales
6. Purchase with installments
7. Loan issued and partially repaid (not counted as income)
8. Incoming money without an identifiable prior operation
9. Incoming money settling an existing sale
10. Outgoing money without an identifiable prior obligation
11. Outgoing money settling an existing purchase
12. Optional person and description
13. Opening balances excluded from income/expense
14. Cancelled transactions and linked payments, plus confirmed correction
15. Repeated technical requests
16. Permission boundaries between users
17. Date-range reports
18. Ambiguous incoming money requires an explicit choice

---

## Phase 2 conclusion

The deterministic posting engine is in place on the Phase 1
documents. Totals come from Python and MariaDB, not from a model.

Next phase may add a text inbox or a rule-based classifier in
front of this API. It must not let the LLM write the database or
calculate money.

Still open, and not decided here:

- Channel for the text interface
- Default when `محمد اداني` is used and the user must be asked
- Larger Qwen model
