# PHASE 4: Sahbi Conversational Interface

Status: COMPLETE
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase adds a text chat inside the Sahbi Frappe app. It does
not add voice, Messenger, WhatsApp, or other external channels.

Do not proceed to later phases from this file.

---

## Scope of this phase

The interface must support:

1. Sending a message
2. Displaying the user message
3. Displaying Sahbi's response
4. A transaction summary after a successful save
5. Short clarification questions
6. Confirmation of corrections and cancellations
7. Financial query results
8. Useful error messages
9. Conversation context for previous operations

Processing flow:

User message
    -> Intent classification
    -> Structured interpretation
    -> Server-side validation
    -> Clarification or confirmation if necessary
    -> Financial engine
    -> Database commit
    -> Verified response

Never show a successful-save message before the database commit.
Never let the frontend bypass permissions or financial rules.

---

## Design

Desk page: `sahbi-chat` (title صاحبي).

Server API:

- `sahbi.chat.api.send_message`
- `sahbi.chat.api.get_history`

The browser only sends text. It cannot create Sahbi Entry or
Sahbi Payment documents.

One `Sahbi Conversation` per workspace stores pending
clarification or confirmation and the last person, entry, and
payment. Each turn writes two `Sahbi Chat Message` rows: User
then Sahbi.

`handle_message`:

1. Require a logged-in user and their workspace.
2. Store the user text.
3. If a confirmation is pending, accept أيوه / لأ only.
4. If a clarification is pending, continue that payload.
5. Otherwise call `interpret_message` (Qwen).
6. Ordinary conversation gets a greeting. No posting.
7. Queries call `sahbi.engine` reports or a description search.
8. Operations call the posting engine only after validation.
9. Ambiguous incoming/outgoing money asks one question and
   does not post.
10. Unknown person names ask before create.
11. Cancel and correct use the last entry and require confirm.
12. The success reply is built from committed engine results.

Replies are Egyptian Arabic templates. The model does not
invent totals.

---

## Files created or changed

Created:

- `sahbi/chat/__init__.py`
- `sahbi/chat/api.py`
- `sahbi/chat/service.py`
- `sahbi/chat/replies.py`
- `sahbi/chat/dates.py`
- `sahbi/sahbi/doctype/sahbi_conversation/`
- `sahbi/sahbi/doctype/sahbi_chat_message/`
- `sahbi/sahbi/page/sahbi_chat/`
- `sahbi/tests/test_chat_workflow.py`

Changed:

- `sahbi/hooks.py` — conversation and message permissions
- `sahbi/permissions.py` — workspace queries for chat DocTypes
- `sahbi/engine/utils.py` — `PersonNotFound`
- `phase4.MD` — this report

No WhatsApp, Telegram, or voice code.

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost migrate
bench --site shbi.localhost run-tests --app sahbi
```

Migrate: new DocTypes and the `sahbi-chat` page synced.

Tests: `Ran 58 tests in 8.869s` — OK

50 earlier tests still pass.
8 chat workflow tests pass, with the LLM mocked:

- User and Sahbi messages are stored and returned
- Sale summary is shown only after a submitted entry exists
- Ambiguous incoming money asks a question and does not save
- "دخل" after that question posts income
- Cancel asks for confirmation, then cancels and keeps the row
- Income query returns engine totals
- Ollama failure returns an error and posts nothing
- Another user cannot send into this conversation
- Missing amount asks and does not save

The Desk page was not clicked in a browser in this phase.
Open `/app/sahbi-chat` on `shbi.localhost` to check the layout.

---

## Phase 4 conclusion

The in-app chat is the only user channel. Money still moves
only through `sahbi.engine` after commit.

Natural-language search is a description filter plus reports.
A later phase can deepen search without changing this flow.

Still open:

- Larger Qwen model for live Egyptian Arabic quality
- WhatsApp or another channel, if approved later
