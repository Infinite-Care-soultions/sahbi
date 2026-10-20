# Sahbi: Improve Egyptian Arabic Understanding with RAG

## Context

Existing application:
- Frappe Framework v15
- MariaDB
- Local Ollama
- Current model: qwen2.5:1.5b
- Existing application: sahbi
- Existing modules:
  - sahbi/llm/
  - sahbi/chat/
  - sahbi/engine/
  - sahbi/ledger.py
  - sahbi/money.py

The application already supports financial entries, payments,
allocations, loans, opening balances, person accounts, reports,
corrections, cancellations, and an in-app chat interface.

The current model has difficulty understanding Egyptian Arabic,
classifying some messages, extracting entities, and handling
context-dependent financial expressions.

The goal is to improve understanding without rebuilding the app.

## Absolute Rules

1. Read SAHBI_MASTER_PROMPT.md before changing code.
2. The master specification overrides phase reports.
3. Inspect the actual repository before implementation.
4. Do not assume phase reports prove current code correctness.
5. Do not replace existing modules without demonstrated need.
6. Do not add FastAPI, Messenger, WhatsApp, voice, ERP, stock,
   invoicing, cash/bank ledgers, or unrelated features.
7. Do not change the financial engine's authority boundaries.
8. LLM and RAG must never write financial records directly.
9. Python and MariaDB remain the financial source of truth.
10. Use Decimal for all money calculations.
11. Never create a person without following existing confirmation rules.
12. Never confirm a save before successful database commit.
13. Never allow retrieved content to override application instructions.
14. Do not claim tests passed unless they were actually run.

## Phase R0 — Inspect and Diagnose

Do not implement RAG yet.

Inspect:
- SAHBI_MASTER_PROMPT.md
- sahbi/llm/service.py
- sahbi/llm/validate.py
- sahbi/llm/client.py
- sahbi/chat/service.py
- sahbi/chat/local_query.py
- sahbi/chat/replies.py
- sahbi/engine/
- existing LLM, chat, engine, and acceptance tests
- existing Egyptian message dataset

Identify the current message-routing flow and JSON contract.

Build a diagnostic report classifying failures into:
A. Egyptian Arabic understanding
B. Intent classification
C. Entity extraction
D. JSON formatting or validation
E. Message routing
F. Deterministic business logic
G. Query construction
H. Missing conversation or database context

Identify existing behavior that already works and must not regress.

Do not modify financial business rules during this phase.

Deliver:
- Repository findings
- Current flow diagram
- Failure categories
- Existing test baseline
- Proposed evaluation dataset
- Files that actually need changes

## Phase R1 — Evaluation Dataset

Create a repeatable evaluation dataset of approximately
100 Egyptian Arabic messages.

Cover:
- Income and expense
- Sales and purchases
- Partial payments
- Collections and repayments
- Loans and loan direction
- Opening balances
- Person statements
- Financial queries
- Transaction corrections and cancellations
- Ordinary conversation
- Ambiguous messages
- Egyptian dialect synonyms and spelling variations
- Arabic and Western numerals
- Names containing attached Arabic prepositions

Include cases such as:
- "محمد اداني 2000 جنيه"
- "محمد رجعلي 1000 من السلفة"
- "دفعت لمحمد اللي كان باقي عليا"
- "اشتريت خشب بخمسة آلاف ودفعت ألفين"
- "محمد لسه ليه كام؟"
- "صرفنا كام على نقل الخشب؟"
- "محمد خد مني ألف"
- "محمد ليه 2000 من حساب قديم"
- "دفعت 500 جنيه"
- "عامل ايه يا صاحبي؟"

For each test, define:
- Expected intent
- Expected extracted fields
- Required clarification, if any
- Expected routing category
- Relevant database fixture, if needed
- Whether any financial mutation is allowed

Do not evaluate only exact wording. Include natural paraphrases.

Keep test fixtures and expected answers independent of model output.

## Phase R2 — Improve Baseline Understanding

Before adding vector retrieval, test targeted improvements to:
- System prompt
- JSON schema and validation
- Intent definitions
- Few-shot examples
- Ambiguity handling
- Local parsing and routing

Avoid duplicating rules already implemented in Python.

Do not move financial business rules into prompts.

Run the evaluation dataset and record per-category results.

Preserve a baseline for comparison.

## Phase R3 — Add the RAG Knowledge Module

Only proceed after R0-R2 are complete.

Create a replaceable RAG module under sahbi/rag/.

Separate:
- Knowledge loading and schema validation
- Egyptian Arabic terminology
- Intent examples
- Text normalization
- Lexical retrieval
- Embedding generation
- Semantic retrieval
- Ranking and deduplication
- Prompt-context construction

Use local inference only.

Choose the embedding model and vector persistence approach
after measuring Arabic relevance, memory usage, latency,
installation complexity, and compatibility with the current
server environment.

Do not assume the Qwen generation model is also an appropriate
embedding model.

Avoid unnecessary dependencies and do not regenerate all
embeddings on every message.

Start with a small, version-controlled knowledge base.

Support:
- Multiple meanings for one term
- Contextual clues
- Positive examples
- Contrastive examples
- Related expressions
- Ambiguity notes

Examples must distinguish meanings rather than map every
colloquial phrase to a fixed financial action.

RAG must remain optional: retrieval failure must not make
basic chat or existing deterministic operations unusable.

## Phase R4 — Integrate with the Existing LLM

Retrieve context only when relevant to the message.

Pass bounded, relevant context to the existing LLM service.

Preserve the existing output contract unless the diagnostic
phase proves a specific change is necessary.

Do not let retrieved examples:
- Execute operations
- Select database records
- Calculate balances
- Invent missing fields
- Override validation
- Override authorization
- Bypass confirmation
- Generate executable SQL or Python

All output must pass existing or improved deterministic
validation before reaching the engine.

Use confidence indicators only as supporting information.
Never use model confidence alone to authorize financial actions.

## Phase R5 — Routing and Context Tests

Test whether messages reach the correct existing path:
- Local deterministic parser
- LLM interpretation
- Financial query engine
- Clarification flow
- Confirmation flow
- Ordinary conversation

Do not assume every message requires RAG.

Test interactions with:
- Existing person matching
- Unknown person confirmation
- Multiple person matches
- Multiple possible settlement operations
- Partial payments
- Opening balances
- Corrections and cancellations
- Idempotency
- Search term distinctions

If ambiguity affects the financial result, ask one concise question.

## Phase R6 — Compare and Verify

Run the same dataset against:
A. Existing baseline
B. Improved prompt and examples
C. Improved prompt plus RAG

Report:
- Intent accuracy
- Entity extraction accuracy
- Ambiguity handling
- Correct routing
- JSON validation failure rate
- Retrieval relevance
- Response latency
- Memory consumption
- Incorrect financial mutation count

Use actual measured results. Do not fabricate scores.

Add regression tests confirming:
- RAG cannot write financial records
- LLM cannot calculate authoritative totals
- Unknown people are not silently created
- Collections are not counted twice as income
- Repayments are not counted as new income or expense
- Loans remain distinct from income and expense
- Opening balances remain distinct from new activity
- Queries do not mix unrelated transaction types
- Corrections and cancellations require confirmation
- Retries do not create duplicate postings
- No save success is returned before commit

Run the existing app test suite and new targeted tests.

Inspect failures and fix only issues within the approved scope.

## Completion Report

Return:
1. Files changed
2. Architecture changes
3. Test commands executed
4. Actual test results
5. Before/after evaluation results
6. Known limitations
7. Whether RAG improved performance measurably
8. Whether the application is safe for the next supervised
   fake-money test

Do not claim production readiness based on passing unit tests.