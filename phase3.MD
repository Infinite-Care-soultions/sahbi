# PHASE 3: Local LLM Integration

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase integrates a small Qwen model served by local Ollama.
It extracts structured intent only. It does not post money, and
it does not add a chat interface.

Do not proceed to later phases from this file.

---

## Scope of this phase

- Inspect the existing Ollama installation and models
- Keep the integration behind a dedicated Python service
- Return structured JSON for intent, type, amount, person,
  description, date expression, previous-operation references,
  search terms, missing fields, ambiguity, and a clarification
  question
- Support Egyptian colloquial Arabic
- Three intents: financial operation, financial query,
  ordinary conversation
- Validate all model output server-side
- Handle invalid JSON and unavailable Ollama
- Keep the model name configurable
- Test with mocked LLM responses
- Add an Egyptian Arabic message dataset
- Do not let the LLM write the database, calculate totals, or
  emit SQL or Python
- Do not build the chat interface

---

## Ollama inspection

Inspected on 2026-10-20. A new install was not required.

| Item | Value |
|---|---|
| Binary | `/usr/local/bin/ollama` 0.20.7 |
| Service | active (`ollama serve`) |
| API | `http://127.0.0.1:11434` |
| Qwen model | `qwen2.5:1.5b` (Qwen2, 1.5B, Q4_K_M) |
| Also present | `medical-ar` (Qwen2 1.5B), gemma4, TinyLlama, embeddinggemma |

Default configured model: `qwen2.5:1.5b`.

Override with site config or environment:

- `sahbi_ollama_model` / `SAHBI_OLLAMA_MODEL`
- `sahbi_ollama_url` / `SAHBI_OLLAMA_URL`
- `sahbi_ollama_timeout` / `SAHBI_OLLAMA_TIMEOUT`

A larger Qwen can be set later without changing call sites.

---

## Service design

Public API: `sahbi.llm`

| Function | Purpose |
|---|---|
| `interpret_message(text, model=None)` | Call Ollama, parse JSON, validate, return a dict |
| `llm_status()` | Report whether Ollama is up and whether the configured model is present |
| `validate_extraction(payload)` | Server-side allowlist and type checks |

The LLM package does not import `sahbi.engine`. It cannot create
entries, payments, or allocations.

Returned shape after validation:

```
intent: financial_operation | financial_query | ordinary_conversation
operation.type, amount, person_name, description,
        date_expression, previous_operation_references, loan_direction
query.kind, search_terms, person_name, date_expression
missing_fields
is_ambiguous, ambiguity_reason, clarification_question
```

Amount, if present, is checked with `Decimal` and stored as a
2-decimal string. The model is not asked to add totals. Any
`sql`, `python`, `code`, `totals`, or similar field is rejected.

Invalid JSON, empty output, or a bad intent raises
`SahbiLLMInvalidOutput`. Connection and HTTP failures raise
`SahbiLLMUnavailable` with a clear message.

Ordinary conversation clears operation and query so a greeting
cannot be posted later by accident.

---

## Dataset

`sahbi/llm/egyptian_messages.json` includes the required phrases
plus incomplete, ambiguous, opening-balance, correction, greeting,
and person-balance cases.

| Message | Expected |
|---|---|
| اشتريت خشب بـ5000 | purchase 5000, خشب |
| بعت مطبخ بـ20000 | sale 20000 |
| محمد اداني 2000 | incoming_money, ambiguous |
| محمد سدد 2000 من حساب الخشب | incoming settlement, ref حساب الخشب |
| سلفت أحمد 1000 | loan_receivable |
| أحمد رجع 300 من السلفة | incoming settlement of a loan |
| صرفنا كام على نقل الخشب؟ | query search نقل / خشب |
| ازيك يا صاحبي | ordinary conversation |
| دفعت لمحمد | outgoing, missing amount |

---

## Files created or changed

Created:

- `sahbi/llm/__init__.py`
- `sahbi/llm/settings.py`
- `sahbi/llm/errors.py`
- `sahbi/llm/schema.py`
- `sahbi/llm/prompts.py`
- `sahbi/llm/client.py`
- `sahbi/llm/validate.py`
- `sahbi/llm/service.py`
- `sahbi/llm/dataset.py`
- `sahbi/llm/egyptian_messages.json`
- `sahbi/tests/test_llm_service.py`

Changed:

- `phase3.MD` — this report

No chat DocType, no www page, no engine writes from this package.

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost run-tests --app sahbi
```

`Ran 50 tests in 7.248s` — OK

36 Phase 1–2 tests still pass.
14 new LLM tests pass, all mocked. They do not need a running
Ollama server.

Covered:

- Required Egyptian examples are in the dataset
- Each dataset row validates through `interpret_message` with a
  mocked model response
- Invalid JSON
- Fenced JSON
- Invalid amount
- Forbidden SQL / Python / totals
- Ollama unavailable
- Configurable model name
- interpret_message does not write Sahbi Entry
- The service module does not import the posting engine
- Empty message rejected

Live model quality against `qwen2.5:1.5b` was not claimed. That
1.5B model may be weak on Egyptian Arabic. Tests prove the
boundary and validation, not Qwen accuracy.

---

## Phase 3 conclusion

Structured extraction is isolated behind `sahbi.llm`. Money still
moves only through `sahbi.engine`.

Next phase may add the text inbox that calls `interpret_message`
and then the engine. It must still require confirmation for
corrections and must not let the model write the database.

Still open:

- Whether to pull a larger Qwen before the chat phase
- Channel for the text UI
