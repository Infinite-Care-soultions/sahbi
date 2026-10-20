# Sahbi review brief

Use this file to audit the Sahbi app against the master specification.
Do not treat the phase reports as newer than the master spec.
`SAHBI_MASTER_PROMPT.md` wins on product rules.
This brief is a condensed copy for review. If a line here disagrees
with the master prompt, follow the master prompt.

App: `sahbi` 0.0.1 (develop)
Bench: `/home/beshoy/SAAS/frappe-press`
Site: `shbi.localhost`
Date of this brief: 2026-10-20
Language of the product: Egyptian Arabic
Stack: Frappe 15 + MariaDB + local Qwen through Ollama

Sources condensed here:

- `SAHBI_MASTER_PROMPT.md`
- `phase1.MD` through `phase6.MD` (each marked COMPLETE)
- Work done after Phase 6 that is not in those reports

---

## How to review

1. Read the master rules below as the required product.
2. Read the implemented architecture and phase claims as what the
   team says exists.
3. Open the listed files and tests. Do not trust a phase "OK" line
   unless you re-run tests.
4. Flag any place where code lets the LLM write money, invent a
   person, calculate a total, or claim a save before commit.
5. Flag any implemented feature that the master prompt forbids
   (ERP, stock, cash/bank ledger, formal invoices, woodworking
   product, extra channels).
6. Flag any master-prompt requirement that is still missing.

Suggested commands:

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost run-tests --app sahbi
```

Phase 6 last reported `93` tests OK. After Phase 6, chat and LLM
settings tests were added. Re-count from a fresh run.

---

## 1. Master product (from SAHBI_MASTER_PROMPT.md)

### What Sahbi is

A personal financial assistant for everyday Egyptian users
(tradespeople, drivers, households, small workshops).

Name: Sahbi (صاحبي).
Interface for MVP: text chat.
Feel: a practical, trustworthy Egyptian friend. Friendly, direct,
nonjudgmental. The user must not need accounting knowledge.

### Authority split (hard rule)

Frappe / Python / MariaDB are the only source of truth for:

- transactions, payments, outstanding, people, openings
- reports, audit, permissions, validations

Qwen / Ollama may only:

- understand Egyptian colloquial Arabic
- classify a message
- extract fields
- detect references to previous operations
- prepare a structured search request
- turn verified engine results into conversation

The LLM must never:

- calculate financial totals
- invent transactions
- modify database records
- fabricate results
- run SQL or Python
- be the only place a business rule lives

Never tell the user a transaction was saved until the database
operation has completed successfully.

Money must use decimal arithmetic, never binary floats.

### In scope

- Income, expense, sale, purchase, generic loan
- Partial payments, collections, repayments
- Amounts people owe the user, and amounts the user owes people
- Optional opening balances
- History
- Safe correct and cancel
- Natural-language search of recorded data
- Basic income/expense reports
- Person account statements
- Egyptian Arabic conversation

### Out of scope

- Full ERP
- Woodworking-specific product
- Formal invoicing
- Cash register
- Bank / cash / card ledger
- Stock
- Manufacturing

Do not add unrelated features without explicit approval.

### Workspace

One financial workspace per user in the MVP.
Household and work money can live in the same workspace.
Do not force separate household and work spaces.
Keep the schema able to grow to more spaces later.

Household types: income, expense.
Work types: income, expense, sale, purchase, loan.
Loans are not income or expense.

### People

A person is optional on every transaction.
One person record. No immutable business role
(buyer / seller / employee / borrower are not separate records).
If the named person does not exist, ask before creating.
Never invent a person's identity.

### Transaction shape

Required: type, amount, transaction date, creation timestamp,
workspace, audit.
Optional: person, description.
No categories in the MVP.
If no date is given, use today in the site timezone.
Store both `transaction_date` (when it happened) and creation
(when it was recorded).
Keep the original user description.

### Incoming money

Example: `محمد اداني 2000 جنيه`

- No identifiable prior debt → new income
- Clear repayment of a loan or payment on a sale → link the payment
- Never count a collection as new income a second time
- Several matching operations → ask which one
- Prefer few questions

### Outgoing money

Example: `دفعت لمحمد 1000 جنيه`

- No identifiable obligation → new expense
- Clear settlement of a purchase, loan, or other obligation → link
- Do not also post that same payment as a new expense
- Several obligations → one short question

### Sales and purchases

One original record holds the full value.
It can be unpaid, partial, or fully paid.
Every payment is its own record (id, amount, dates, links, audit).
Paid and outstanding come from payment / allocation records.
A payment does not create a new sale or purchase.
One payment can allocate across several originals.
Record the payment once; store allocations separately.
Never allocate at random. If unclear, ask.

### Loans

Separate from income and expense.

- `سلفت محمد 2000` → receivable from Mohamed
- `استلفت من محمد 2000` → payable by the user
- Repayment links to the loan when identifiable
- Repayment is not new income or expense
- Worker advances use this generic loan type

### Opening balances

Optional. Users can start without them.
Not new income, expense, sale, purchase, or loan activity.
Examples: `محمد ليه 2000 جنيه حساب قديم`,
`أنا عليّ لأحمد 1500 جنيه من حساب قديم`.
Do not force openings at setup.

### Cash and bank

MVP does not keep cash, bank, or card balances.
Do not claim to know cash or bank on hand.
The system may report income, expense, outstanding, loans, and
recorded activity. Keep those figures distinct.
Do not call a figure net profit.

### Correct and cancel

Never permanently delete posted financial records.
Never silently change posted values.
Need explicit confirmation.
Before change: identify the row, show current values, show the
proposed change, explain impact, get confirmation.
Keep audit: original, replacement if any, reason, user, time.
Review linked payments before changing an original.

### Duplicates

Two mechanisms:

1. Technical idempotency: a retried request must not post twice.
2. Semantic near-duplicate: amount alone is not enough. Ask if it
   might be new. Do not silently drop a real transaction.

### Search

Examples: `اشتريت خشب بكام الشهر ده؟`, `صرفنا كام على نقل الخشب؟`,
`محمد لسه ليه كام؟`, `دفعت لمحمد كام الشهر اللي فات؟`

Qwen extracts intent and terms.
Python and MariaDB filter and add.
Keep distinctions: income vs expense, sale vs purchase, wood vs
wood transport, new income vs collection, loan vs repayment.
Do not mix unrelated rows. If there is no data, say so clearly.

### Message routing

Every message is one of:

1. Create, correct, or cancel a financial operation
2. Query or report
3. Ordinary conversation

Do not post a greeting as money.
Correct and cancel need confirmation.

### UX

Ask only for missing required facts.
Do not ask for optional person, description, or category.
Default language: conversational Egyptian Arabic.
If the operation is complete, save it without extra questions.
Confirm success with an accurate summary.
If ambiguity would change the money, ask one short question.

### Engineering

Inspect the repo before changing it.
Follow Frappe structure. No extra dependencies.
DocTypes + server logic. Transactions for multi-step writes.
Permissions on every server operation.
Tests for money rules.
No secrets in logs.
Phased work. Do not claim tests or features that were not run
or built. Ambiguity should be named, not invented.

---

## 2. Implemented architecture (current repo)

```
User
  └─ 1 Sahbi Workspace
        ├─ * Sahbi Person
        ├─ * Sahbi Entry          (original money document)
        ├─ * Sahbi Payment        (independent payment)
        │     └─ * Sahbi Payment Allocation
        └─ 1 Sahbi Conversation
              └─ * Sahbi Chat Message
```

Opening balance is `Sahbi Entry.entry_type = Opening Balance`,
not a second ledger.

Site-wide Single: `Sahbi LLM Settings` (Ollama URL, model, timeout).
Desk workspace: `Sahbi` (shortcuts to chat, settings, and all
DocTypes). Chat page: `/app/sahbi-chat` (title صاحبي).

Packages:

| Package | Role |
|---|---|
| `sahbi.money` | `Decimal` to 0.01. No floats. |
| `sahbi.ledger` | Allocation math, outstanding refresh. |
| `sahbi.permissions` | Workspace ownership on list and document. |
| `sahbi.workspace` | Role `Sahbi User`, one workspace per user. |
| `sahbi.engine` | Only writer of money. Atomic. |
| `sahbi.llm` | Extract JSON only. Must not import `sahbi.engine`. |
| `sahbi.chat` | Inbox → local parse or LLM → engine → Arabic templates. |

Money write API (`sahbi.engine`):

- `create_income` / `create_expense` / `create_sale` / `create_purchase`
- `create_loan` / `create_opening_balance`
- `record_payment` / `record_incoming_money` / `record_outgoing_money`
- `cancel_entry` / `cancel_payment` / `correct_entry` (need `confirm=True`)
- `get_person_balances` / `get_person_statement`
- `get_income_expense_totals` / `get_period_report` / `run_financial_query`

Chat path:

```
user text
  -> greeting / thanks (no LLM)
  -> local account query (كشف / حساب / تفاصيل …)
  -> local sale/purchase/pay parse (بعت / بيعت / اشتريت / دفعت + amount + person)
  -> else interpret_message (Ollama)
  -> validate
  -> clarify or confirm if needed
  -> engine
  -> commit
  -> template reply from committed rows only
```

Person match: Arabic fold (أ/ا, ة/ه). Exact name, then prefix
(`محمد` → `محمد حامد` if that is the only match). Several matches
get a numbered list. Unknown name asks `أضيفه؟` before create.

Glued Arabic `ل` is stripped in local parse:
`بيعت ب 500 جنية لاحمد حنفي` → person `احمد حنفي`, not a
hallucinated name.

---

## 3. Phase reports

All six phase files say COMPLETE on 2026-10-20.
Each file told the implementer not to skip ahead.
Test counts below are what that phase reported at the time.

### Phase 1 — Financial data model

Built the DocTypes only. No LLM, no chat, no posting API.

DocTypes: Workspace, Person, Entry, Payment, Payment Allocation.
Person has no role field. Names unique per workspace after
normalize (trim, collapse spaces, casefold).

Entry types: Income, Expense, Sale, Purchase, Loan, Opening Balance.
Amount always positive. Direction from type:
Sale = Receivable, Purchase = Payable, Loan/Opening require a
direction, Income/Expense not allocatable.

Outstanding = `amount − sum(submitted allocations)`.
Unique `(workspace, idempotency_key)` on Entry and Payment.
Submitted / cancelled rows cannot be deleted. Amend disabled.

Reported tests: 18 OK.

Open then: incoming default for `محمد اداني`, chat channel,
larger Qwen, correction workflow.

### Phase 2 — Deterministic engine

Python posting on those documents. No LLM, no chat UI.

Incoming / outgoing classification:

1. Explicit allocations
2. Explicit `settle_entry`
3. Else, if a person is set, open operations in the matching direction
4. Zero matches → income or expense
5. One match → payment + allocation
6. Several → `AmbiguousSettlement`, post nothing

Leftover above outstanding becomes remainder income/expense.
Cancel / correct without `confirm=True` only preview.
Correction cancels the original and posts a replacement
(`replaces` / `replaced_by`). No in-place amount edit.
Idempotent replay returns `replayed=True`.
Semantic near-duplicates are not auto-rejected.

Reported tests: 36 OK (18 schema + 18 engine).

### Phase 3 — Local LLM extraction

Ollama `qwen2.5:1.5b` at `http://127.0.0.1:11434`.
`interpret_message` returns intent + operation + query +
missing_fields + ambiguity. Rejects `sql`, `python`, `totals`.
Does not import the engine. Tests mock the model.
Dataset: `sahbi/llm/egyptian_messages.json`.

Live Egyptian quality of the 1.5B model was **not** certified.

Reported tests: 50 OK.

Open then: larger Qwen, chat channel.

### Phase 4 — In-app chat

Only channel: Desk page `sahbi-chat`.
No WhatsApp, Messenger, voice.

`handle_message` stores User then Sahbi rows.
Success reply only after a submitted document exists.
Unknown person asks before create.
Cancel / correct use last entry and need `أيوه`.
Replies are templates, not model-invented totals.

Desk page was **not** clicked in a browser in that phase.

Reported tests: 58 OK.

### Phase 5 — Queries and reports

`run_financial_query` kinds: income, expense, sale, purchase,
loan receivable/payable, opening, collections, repayments,
outstanding either way, person balance, income_expense
(difference, not profit), period report, search,
`cash_or_bank` / `profit` → limitation, no number.

Period uses `transaction_date` / `payment_date`.
Search requires every term. Extra distinguishing tokens
(`نقل`, `شحن`, `توصيل`, `مصنعية`, `أجرة`) keep `خشب`
apart from `نقل الخشب`.
Cancelled `docstatus=2` ignored.
Current outstanding includes openings. No as-of historical
outstanding.

Reported tests: 73 OK.

### Phase 6 — Audit, not a product phase

Twenty controls, all claimed Pass, with tests in
`sahbi/tests/test_acceptance.py`.

Fixes in that phase:

- `has_permission` no longer allows a string document name
- financial DocTypes validate workspace access
- Sahbi User cannot change `Sahbi Workspace.user`
- chat whitelist `allow_guest=False`

Honest limits from the audit:

- Not production-ready
- `shbi.localhost` has `developer_mode` and `allow_tests`
- System Manager sees every workspace
- Sahbi User can still post and cancel from Desk forms
- Sequential names (`ENT-#####`)
- Ollama is not a trust boundary
- 1.5B model not certified
- Chat page not browser-tested in the audit
- Ready only for a **supervised pilot with fake money**

Reported tests: 93 OK.

---

## 4. Work after Phase 6 (not in phase1–6 files)

These landed while using live chat. They are part of the current
app and must be reviewed against the master spec.

### Chat robustness

- Greetings and first daily line (`عامل ايه النهاردة`) skip Ollama.
- Confirm words include `ايوة` / `ايوه` / `ضيفه` / `أضيفه` after
  Arabic fold (`ة`/`ه`, `أ`/`ا`).
- Account questions (`قولي حساب محمد`, `كشف حساب محمد حامد`,
  `تفاصيل حساب محمد`) parse in Python first and call the engine.
- Person statements print sale / purchase / pay / receive lines
  with a newline after each line (Desk JS turns `\n` into `<br>`).
- `دفعت لمحمد` matches `محمد حامد` when that is the only prefix
  match, or shows a numbered list when several محمدs exist.
- Query extraction must not search the words `كشف` / `تفاصيل`.

### Local operation parse

Small Qwen invented wrong Egyptian names (`لاحمد حنفي` →
`لحيمة حنفي`). Python now parses clear sale / purchase / pay
sentences with an amount and a person after `ل` / `من` and
strips the glued preposition.

Receive verbs such as `اداني` stay with the LLM because they
are income-vs-loan ambiguous (master §7).

### Desk

- Workspace **Sahbi** lists every Sahbi DocType plus chat.
- Single **Sahbi LLM Settings** is the live source for Ollama
  URL, model, and timeout. Chat reads it on the next message.

---

## 5. Master rules vs current code (review checklist)

Use this table. Mark each row Pass / Fail / Partial after reading
the code, not after reading a phase file.

| # | Master rule | Where to look | Phase claim | Watch for |
|---|---|---|---|---|
| 1 | LLM never writes money | `sahbi/llm/service.py` must not import engine | Phase 3, 6.15 | Chat must call engine only after validate |
| 2 | LLM never calculates totals | `sahbi/llm/validate.py` rejects `totals` | Phase 3, 5, 6.14 | Reply templates must use engine numbers |
| 3 | Save message only after commit | `sahbi/chat/service.py` `_committed` | Phase 4, 6.18 | `اتسجل` before insert is a fail |
| 4 | Decimal money, no float | `sahbi/money.py`, ledger, engine | Phase 1, 6.17 | Raw `float` on amounts |
| 5 | One workspace per user | `sahbi/workspace.py` | Phase 1 | Unique on `user` |
| 6 | Person has no role | `sahbi/sahbi/doctype/sahbi_person` | Phase 1 | `role` / `business_role` field |
| 7 | Ask before creating a person | `_handle_operation` unknown_person | Phase 4 | Silent create |
| 8 | Never invent a person | `parse_local_operation`, `_match_people` | After Phase 6 | LLM name hallucination on `ل`+name |
| 9 | Incoming: income vs settlement | `record_incoming_money` | Phase 2 §7 | Collection counted as income |
| 10 | Outgoing: expense vs settlement | `record_outgoing_money` | Phase 2 §8 | Payment counted twice |
| 11 | Payment is its own document | `Sahbi Payment` + Allocation | Phase 1–2 §9 | Payment stored only as Entry |
| 12 | Outstanding from allocations | `sahbi/ledger.py` | Phase 1, 6.6 | Editable outstanding field as truth |
| 13 | Loans ≠ income/expense | Entry type Loan, report kinds | Phase 2, 5, 6.8 | Loan in income total |
| 14 | Openings ≠ activity | Entry type Opening Balance | Phase 1, 5, 6.9 | Opening in income |
| 15 | No cash/bank/profit number | `cash_or_bank`, `profit` limitation | Phase 5, 6.20 | Any bank balance reply |
| 16 | Correct/cancel need confirm | engine `confirm=True`, chat pending | Phase 2, 4, 6.11–12 | Desk cancel still bypasses chat preview |
| 17 | No delete of posted rows | `on_trash` | Phase 1, 6.10 | `delete` on submitted |
| 18 | Idempotency | unique workspace+key | Phase 1–2, 6.3 | Retry posts a second row |
| 19 | Semantic duplicate asks, does not auto-drop | engine / chat | Phase 2, master §14 | Silent reject of a real sale |
| 20 | Search keeps types apart | `description_matches` | Phase 5, 6.19 | Wood + transport in one total |
| 21 | Ordinary chat is not a posting | greetings, intent 3 | Phase 4, master §16 | `ازيك` creates an entry |
| 22 | Egyptian Arabic UX | `sahbi/chat/replies.py` | Phase 4 | English money replies |
| 23 | No extra product (ERP, stock, WhatsApp) | repo tree | master §3 | Extra apps or channels |
| 24 | Permissions server-side | `sahbi/permissions.py` | Phase 6.1–2 | Guest chat, cross-workspace read |

---

## 6. Known gaps and honest leftovers

Still open from the phase reports and later chat work:

- Historical outstanding as of a past date (MVP is live outstanding)
- Live Qwen `qwen2.5:1.5b` is small; quality is not certified.
  Local Python parse exists because the model mangles Egyptian names.
- Chat Desk UI was not systematically browser-tested in Phase 4–6
- No WhatsApp / Messenger / voice (correct: not approved)
- No cash, bank, stock, or formal profit (correct)
- Semantic duplicate detection asks; it does not auto-reject
- Sahbi User can still create/cancel from Desk, skipping chat
  clarification
- System Manager sees all workspaces
- Site is a dev site (`developer_mode`, `allow_tests`)
- Sequential document names
- Production blockers from Phase 6: staging site, HTTPS, backups,
  larger evaluated model, Desk lock decision, Ollama-down support
  path, Error Log privacy review

Phase 0 was mentioned in chat history but there is no `phase0.MD`
in the repo.

---

## 7. Key files

| Area | Path |
|---|---|
| Master spec | `SAHBI_MASTER_PROMPT.md` |
| Phase reports | `phase1.MD` … `phase6.MD` |
| Money | `sahbi/money.py`, `sahbi/ledger.py` |
| Engine | `sahbi/engine/posting.py`, `settlement.py`, `corrections.py`, `reports.py` |
| LLM | `sahbi/llm/service.py`, `validate.py`, `client.py`, `settings.py` |
| Chat | `sahbi/chat/service.py`, `local_query.py`, `replies.py`, `api.py` |
| Permissions | `sahbi/permissions.py`, `sahbi/hooks.py` |
| LLM Single | `sahbi/sahbi/doctype/sahbi_llm_settings/` |
| Desk workspace | `sahbi/sahbi/workspace/sahbi/sahbi.json` |
| Tests | `sahbi/tests/test_financial_schema.py`, `test_financial_engine.py`, `test_llm_service.py`, `test_chat_workflow.py`, `test_financial_reports.py`, `test_acceptance.py` |

---

## 8. What another reviewer should return

A short audit, not a rewrite:

1. Master-spec violations in the current code
2. Phase claims that the code does not actually meet
3. After-Phase-6 behavior that conflicts with the master spec
4. Missing tests for money or permission rules
5. Anything that would post money or invent a person in live chat
6. What is safe for a fake-money pilot vs what must wait

Do not invent a new product. Do not treat Desk convenience
(workspace, LLM Settings) as a scope violation unless it writes
money or bypasses the engine.
