I have a Frappe 15 app called `sahbi` with a Facebook Messenger integration
(sahbi/integrations/facebook_messenger.py). The webhook currently processes the
message and calls the LLM synchronously before returning, so it responds slowly.
Meta then retries the webhook, which causes duplicate replies and a Page
messaging restriction (Messenger error code 10, subcode 1893063).

Task: refactor the webhook so it returns HTTP 200 immediately and does all the
heavy work in a background job.

First, read the existing webhook handler and the code it calls (message
parsing, LLM call, MessengerSendError, send function). Summarize how it works
before changing anything.

Requirements:

1. Webhook endpoint (whitelisted, allow_guest=True)
   - GET: keep the existing hub.verify_token / hub.challenge verification.
   - POST: verify the X-Hub-Signature-256 header with the app secret (keep the
     existing check if there is one). Parse the payload, and for each
     messaging event enqueue one background job. Then return 200 right away.
   - Do no LLM calls, DB-heavy work or Send API calls in the request.
   - Always return 200 for valid payloads, even if enqueueing fails (log the
     error with frappe.log_error). Never raise from the webhook.

2. Event filtering (before enqueueing)
   - Ignore events where message.is_echo is true.
   - Ignore delivery, read, and other non-message events (only handle
     `message` and `postback`).
   - Ignore events with no sender id or no text/payload.

3. Deduplication
   - Use the message `mid` (for postbacks, use sender id + timestamp).
   - Before enqueueing, do an atomic check with the Redis cache, for example
     frappe.cache().set(key, 1, nx=True, ex=86400) or an equivalent atomic
     approach. If the key already exists, skip silently.
   - Also pass `job_id=f"msgr:{mid}"` and `deduplicate=True` to frappe.enqueue
     so the same message can never be queued twice.

4. Background job
   - Create `process_messenger_event(event: dict)` and enqueue it with
     frappe.enqueue(queue="default", timeout=300, enqueue_after_commit=False).
   - Inside the job: send `typing_on` first, run the existing logic (LLM, RAG,
     DB writes), then send the reply with messaging_type="RESPONSE".
   - Wrap everything in try/except. On failure, log with frappe.log_error and
     send a short fallback message to the user only if it is safe to do so.

5. Messenger restriction handling
   - Catch MessengerSendError in the job. If the Graph error has code 10 or
     subcode 1893063, do not retry. Mark that conversation or sender as
     restricted (cache key with a TTL of a few hours) and stop sending to it.
   - Never retry on 4xx errors. Only retry on transient 5xx or network errors,
     with a small capped backoff.

6. Rate limiting
   - Add a simple per-sender limit (for example, max N replies per minute using
     a Redis counter). If exceeded, skip sending and log it.

7. Ordering
   - Messages from the same user should not be processed in parallel. Use a
     per-sender lock (frappe.cache().lock or a Redis lock) inside the job so
     replies stay in order.

Constraints:
- Do not change the public webhook URL or the existing business logic.
- Keep the code in Frappe v15 style, and add type hints and short docstrings.
- Don't add new dependencies.

Deliverables:
- The modified code (show a diff or full changed files).
- A short test plan: how to simulate a payload with curl, confirm the response
  time is under 1 second, confirm a duplicate `mid` is ignored, confirm an
  echo event is ignored, and confirm the job shows up in the RQ Job list.
- Notes on required bench processes (workers must be running: `bench worker`
  or the supervisor config).