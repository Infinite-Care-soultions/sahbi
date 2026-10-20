# PHASE R0 — Inspect and Diagnose

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost

Do not treat this file as permission to change money rules.
RAG was not implemented in this phase.

---

## Repository findings

Current routing in `sahbi/chat/service.py` `_start_turn`:

1. Thanks / greeting → conversation, no Ollama
2. `parse_account_query` → engine report
3. `parse_local_operation` → sale / purchase / pay only, needs amount + person
4. Else `interpret_message` (qwen2.5:1.5b) → validate → query or operation

JSON contract after `validate_extraction`:

```
intent: financial_operation | financial_query | ordinary_conversation
operation: type, amount, person_name, description, date_expression,
           previous_operation_references, loan_direction
query: kind, search_terms, person_name, date_expression
missing_fields, is_ambiguous, ambiguity_reason, clarification_question
```

Forbidden model keys: sql, python, totals, and related.
`sahbi.llm` does not import `sahbi.engine`.
Chat replies `اتسجل` only after `_committed`.

Ollama on this machine: `qwen2.5:1.5b`, `embeddinggemma`, `medical-ar`,
`gemma4`, TinyLlama. Generation stays on Qwen. Embeddings, if used later,
can use `embeddinggemma` (not Qwen).

Existing dataset `sahbi/llm/egyptian_messages.json` has 19 cases and
is used with a **mocked** model. It does not measure live Egyptian quality.

---

## Current flow

```
user text
  ├─ greeting / thanks → Arabic template
  ├─ local account query → run_financial_query
  ├─ local sale/purchase/pay + person → engine
  └─ Ollama JSON
        ├─ ordinary_conversation → template
        ├─ financial_query → engine
        └─ financial_operation
              ├─ missing fields → ask
              ├─ incoming/outgoing ambiguous → ask
              ├─ unknown / several people → ask
              ├─ cancel / correct → confirm, then engine
              └─ else engine → commit → template
```

---

## Failure categories (from live chat and code)

| Code | Category | Evidence |
|---|---|---|
| A | Egyptian Arabic | `جنية`, `ايوة`/`ايوه`, `بيعت`, glued `ل` |
| B | Intent | `اداني` is income or loan; local parse correctly leaves it to LLM |
| C | Entity extraction | Qwen invented `لحيمة حنفي` from `لاحمد حنفي` |
| D | JSON / validation | 1.5B sometimes empty, timeout, or invalid JSON |
| E | Routing | `كشف حساب` used to search `كشف محمد حامد`; greetings used to call Ollama |
| F | Business logic | Engine settlement / outstanding / Decimal hold in tests |
| G | Query construction | Need STOP words; wood vs transport already in reports |
| H | Context | Prefix person match, last entry for cancel, no RAG memory |

---

## Must not regress

- Engine is the only money writer
- Decimal 0.01, no float money
- Collections / loans / openings stay out of income
- Unknown person asks before create
- Cancel / correct need confirmation
- Idempotent retries
- Cross-workspace isolation
- `cash_or_bank` / `profit` return no number
- Existing 103 app tests (measured 2026-10-20)

---

## Existing test baseline

```
bench --site shbi.localhost run-tests --app sahbi
Ran 103 tests in 17.490s  OK
```

Modules: schema, engine, LLM (mocked), chat, reports, acceptance.

---

## Files that actually need changes (later phases)

- `sahbi/chat/local_query.py` — more dialect, numerals, openings, queries
- `sahbi/llm/prompts.py` — name-preposition and contrastive few-shots
- `sahbi/llm/service.py` / `prompts.py` — optional bounded RAG context
- new `sahbi/rag/` — knowledge + lexical (+ optional embeddings)
- new evaluation dataset and tests

Do not change `sahbi/engine` money rules for RAG.
