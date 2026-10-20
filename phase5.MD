# PHASE 5: Financial Queries and Reports

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase adds deterministic financial queries and reports.
The LLM may classify a question and extract search terms.
It never calculates the result.

Do not proceed to later phases from this file.

---

## Scope of this phase

Support questions such as:

- صرفت كام الشهر ده؟
- دخل لي كام الشهر اللي فات؟
- اشتريت خشب بكام؟
- صرفنا كام على نقل الخشب؟
- محمد لسه ليه كام؟
- أنا عليّ لمحمد كام؟
- سلفت العمال كام؟
- دفعت لمحمد كام في الفترة دي؟

Reports distinguish:

- Income
- Expenses
- Sales
- Purchases
- Collections and repayments
- Outstanding receivables
- Outstanding payables
- Loan balances
- Opening balances

Settlements are not counted again as income or expense.
Period filters use `transaction_date` for entries and
`payment_date` for payments.
Current outstanding includes carried-forward unpaid amounts
and opening balances.

Do not claim cash or bank balances.
Do not call a figure net profit.
Wood purchase cost does not include wood transportation.

---

## Design

Public API: `sahbi.engine.run_financial_query`

The chat path is:

User question
    -> `interpret_message` (kind + terms + person + date)
    -> `run_financial_query` (Python / MariaDB)
    -> Egyptian Arabic template

The model cannot send totals. Forbidden LLM fields still
include `totals`, `sql`, and `python`.

Query kinds:

| Kind | Result |
|---|---|
| `income` / `expense` / `sale` / `purchase` | Submitted entry totals, optional description terms |
| `loan_receivable` / `loan_payable` | Loan principals, not repayments |
| `opening_balance` | Opening balances only |
| `collections` / `repayments` | Submitted payments |
| `outstanding_receivable` / `outstanding_payable` | Current outstanding, including openings |
| `person_balance` | Both directions for one person |
| `income_expense` | Income and expense, plus the difference, not profit |
| `period_report` | All activity types kept separate |
| `search` | Description search, types not mixed into one total |
| `cash_or_bank` / `profit` | Limitation, no number |

Description matching requires every search term to appear.
If the description also contains a distinguishing token
(`نقل`, `شحن`, `توصيل`, `مصنعية`, `أجرة`) that was not in
the question, the row is excluded. That keeps "خشب" apart
from "نقل الخشب".

Cancelled documents (`docstatus=2`) are ignored.

---

## Files created or changed

Created:

- `sahbi/tests/test_financial_reports.py`

Changed:

- `sahbi/engine/reports.py` — `run_financial_query`, typed totals, limitations
- `sahbi/engine/__init__.py` — export `run_financial_query`
- `sahbi/chat/service.py` — queries go only through the engine
- `sahbi/chat/replies.py` — typed Arabic answers and limitation text
- `sahbi/llm/schema.py` — extra query kinds
- `sahbi/llm/prompts.py` — extract kinds and terms, do not calculate
- `sahbi/llm/egyptian_messages.json` — Phase 5 questions
- `sahbi/tests/test_chat_workflow.py` — chat uses engine numbers
- `phase5.MD` — this report

The LLM package still does not import `sahbi.engine`.

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost run-tests --app sahbi
```

Tests: `Ran 73 tests in 11.807s` — OK

58 earlier tests still pass.
New report tests cover:

- Date filters on `transaction_date`
- Wood purchase versus wood transport
- Settlements counted as payments, not income or expense
- Cancelled entries and linked payments excluded
- Outstanding includes opening balances and unpaid sales
- Receivable and payable kept separate
- Worker loans are not expenses
- Period report keeps every type distinct
- Cash/bank and profit return a limitation, not a number
- Another user's workspace stays hidden

Chat tests, with the LLM mocked:

- Income total comes from the engine
- Wood purchase reply does not include transport cost
- Bank-balance questions explain the limitation

---

## Phase 5 conclusion

Money questions are answered by Python and MariaDB.
Qwen only names the question type and the search terms.

Still open:

- Historical outstanding as of a past date (MVP uses current outstanding)
- A larger Qwen model for live Egyptian Arabic quality
- WhatsApp or another channel, if approved later
