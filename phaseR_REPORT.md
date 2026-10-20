# exam.MD completion report (R0–R6)

Date: 2026-10-20
Site: `shbi.localhost`
Model: `qwen2.5:1.5b`
Embedding model available but **off by default**: `embeddinggemma`

The master spec still wins. RAG does not write money.

---

## 1. Files changed

Created:

- `phaseR0.MD`
- `sahbi/chat/normalize.py`
- `sahbi/rag/` (loader, lexical, embeddings, retrieve, context, evaluate)
- `sahbi/rag/knowledge/terminology.json`
- `sahbi/rag/knowledge/examples.json`
- `sahbi/rag/evaluation/egyptian_eval.json` (101 messages)
- `sahbi/rag/evaluation/run_compare.py`
- `sahbi/tests/test_rag_and_eval.py`

Changed:

- `sahbi/chat/local_query.py` — dialect, numerals, openings, queries, glued `ل`
- `sahbi/chat/service.py` — `parse_local_query`, friendlier greetings/thanks
- `sahbi/llm/prompts.py` — stronger Egyptian few-shots; kept `BASELINE_SYSTEM_PROMPT`
- `sahbi/llm/service.py` — optional RAG context (`use_rag`, `use_baseline`)

Engine, ledger, and money rules were not rewritten.

---

## 2. Architecture changes

```
user text
  → greeting / thanks
  → local query (Python)
  → local operation (Python)
  → interpret_message
        → optional lexical RAG (≤4 rows)
        → Qwen JSON
        → validate_extraction
  → engine / clarification / confirm
```

RAG is a replaceable package. Retrieval failure returns empty context.
Retrieved rows cannot override the system prompt, run SQL, or post money.
Embeddings stay optional (`frappe.conf.sahbi_rag_embeddings`). Default path
is lexical only so chat stays usable if Ollama embeddings are down.

---

## 3. Test commands executed

```bash
bench --site shbi.localhost run-tests --app sahbi
bench --site shbi.localhost execute sahbi.rag.evaluate.run_deterministic_eval
bench --site shbi.localhost execute sahbi.rag.evaluation.run_compare.main
```

---

## 4. Actual test results

App suite: **`Ran 112 tests in 25.975s` — OK**

(Was 103 before this exam.)

New tests cover: dataset size, no mutation during eval, glued `ل`,
word/eastern amounts, opening ≠ account query, wood vs transport terms,
RAG does not write, RAG cannot override system rules, unknown person still asks.

---

## 5. Before / after evaluation

Dataset: **101** Egyptian messages (required phrases included).

### Deterministic routing (Python, no Ollama)

| | Pass | Accuracy | Route | Seconds |
|---|---|---|---|---|
| After R2–R5 local parse | 99 / 101 | **98.0%** | **100%** | 0.05 |

Remaining misses (entity only): `عليه كام` kind, `دفعت لعلي 200 من الخشب` person.

### Live Qwen sample (6 LLM-bound messages, measured)

| Mode | Setup | Pass | Accuracy | Seconds |
|---|---|---|---|---|
| A | Old prompt, no RAG | 3 / 6 | 50% | 37.7 |
| B | New prompt, no RAG | 4 / 6 | **67%** | 43.8 |
| C | New prompt + RAG | 3 / 6 | 50% | 39.6 |

JSON validation failures on this sample: 0 (invalid JSON would have been errors).
Incorrect financial mutations during eval: **0** (eval does not post).

---

## 6. Known limitations

- `qwen2.5:1.5b` is still weak on cancel / multi-action / some settlements.
- Live compare used 6 LLM-bound rows, not all 101, because each Ollama call
  is several seconds. Scores above are measured, not invented.
- RAG lexical context did **not** beat the improved prompt on that sample.
- Embeddings are implemented but disabled by default (latency / first-load).
- `عليه كام` and `من الخشب` as a trailing phrase still need tighter rules.
- Not production-ready. Same Phase 6 blockers remain (dev site, Desk cancel,
  small model, no browser certification).

---

## 7. Did RAG improve performance?

**Not on the live 6-message sample.** B (prompt only) was better than C
(prompt + RAG). The large gain is **local Python parse**: 98% of the 101
messages now route without calling Qwen, including `لاحمد حنفي` → احمد حنفي.

RAG remains optional context. It did not write records and did not break
the 112 unit tests.

---

## 8. Safe for the next supervised fake-money test?

**Yes, with the same Phase 6 caution:** fake amounts only, Sahbi User only,
Ollama up, stop if a total is wrong.

Do not treat this as production readiness.
