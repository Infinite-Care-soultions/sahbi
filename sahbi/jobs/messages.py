# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Inbound Messenger processing. Replies go through the same Sahbi chat engine."""

from __future__ import annotations

import time

import frappe

from sahbi.chat import replies
from sahbi.chat.service import handle_message
from sahbi.integrations.events import extract_inbound_content
from sahbi.integrations.facebook_messenger import FacebookMessengerClient, MessengerSendError
from sahbi.integrations.facebook_signup import handle_unmapped_sender
from sahbi.integrations.logs import insert_integration_log, insert_webhook_event_log, mark_webhook_event
from sahbi.integrations.messenger_runtime import (
	mark_sender_restricted,
	reply_rate_ok,
	sender_lock,
	sender_restricted,
)

MAX_SEND_ATTEMPTS = 3


def process_messenger_event(page_id: str, messaging_event: dict, event_key: str) -> None:
	"""RQ job entrypoint. `event` cannot be used as a kwarg — frappe.enqueue reserves it."""
	process_messaging_event(page_id, messaging_event, event_key)


def process_messaging_event(page_id: str, messaging_event: dict, event_key: str) -> None:
	frappe.set_user("Administrator")
	_ensure_event_log(event_key, page_id)
	mark_webhook_event(event_key, "Processing")

	sender = (messaging_event.get("sender") or {}).get("id")
	if not sender:
		mark_webhook_event(event_key, "Rejected", "missing_sender")
		return

	with sender_lock(str(sender)):
		_process_locked(page_id, messaging_event, event_key, str(sender))


def _process_locked(page_id: str, messaging_event: dict, event_key: str, sender: str) -> None:
	content = extract_inbound_content(messaging_event)
	text = (content.get("text") or "").strip()

	workspace = _resolve_workspace(sender)
	if not workspace:
		reply = handle_unmapped_sender(sender, text)
		if reply:
			_try_send(sender, reply, event_key)
		mark_webhook_event(event_key, "Processed", "signup")
		frappe.db.commit()
		return

	if content.get("kind") == "attachment":
		_try_send(sender, replies.unsupported_attachment(), event_key)
		mark_webhook_event(event_key, "Processed", "unsupported_attachment")
		frappe.db.commit()
		return

	if not text:
		mark_webhook_event(event_key, "Processed", "empty_text")
		frappe.db.commit()
		return

	owner = frappe.db.get_value("Sahbi Workspace", workspace, "user")
	if not owner:
		mark_webhook_event(event_key, "Processed", "missing_workspace_owner")
		frappe.db.commit()
		return

	reply = ""
	conversation = ""
	deliver = True
	try:
		frappe.set_user(owner)
		result = handle_message(text)
		reply = (result or {}).get("reply") or ""
		conversation = (result or {}).get("conversation") or ""
		deliver = (result or {}).get("deliver", True)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.set_user("Administrator")
		mark_webhook_event(event_key, "Processed", "error")
		_log_send(event_key, "Failed", error_summary="message processing failed")
		frappe.log_error(title="sahbi message processing failed")
		_safe_fallback(sender, event_key, conversation)
		return
	finally:
		frappe.set_user("Administrator")

	if not deliver:
		mark_webhook_event(event_key, "Processed", "ai_paused_or_handoff")
		_log_send(event_key, "Success", conversation=conversation, error_summary="ai_paused_or_handoff")
		return
	if reply:
		_send_and_log(sender, reply, event_key, conversation)
		return
	mark_webhook_event(event_key, "Processed", "empty_reply")
	_log_send(event_key, "Success", conversation=conversation, error_summary="empty_reply")


def _ensure_event_log(event_key: str, page_id: str) -> None:
	if frappe.db.exists("Sahbi Webhook Event Log", {"event_key": event_key}):
		return
	insert_webhook_event_log(event_key, "Received", page_id or "", "")


def _resolve_workspace(psid: str) -> str | None:
	return frappe.db.get_value(
		"Sahbi Workspace",
		{"facebook_psid": psid, "disabled": 0},
		"name",
	)


def _maybe_typing_on(psid: str) -> None:
	if sender_restricted(psid):
		return
	try:
		FacebookMessengerClient().send_typing_on(psid)
	except Exception:
		pass


def _send_and_log(psid: str, text: str, event_key: str, conversation: str = "") -> None:
	if sender_restricted(psid):
		mark_webhook_event(event_key, "Processed", "sender_restricted")
		_log_send(event_key, "Failed", conversation=conversation, error_summary="sender_restricted")
		return
	if not reply_rate_ok(psid):
		mark_webhook_event(event_key, "Processed", "rate_limited_reply")
		_log_send(event_key, "Failed", conversation=conversation, error_summary="rate_limited_reply")
		return

	try:
		_maybe_typing_on(psid)
		_send_with_retry(psid, text)
		mark_webhook_event(event_key, "Processed")
		_log_send(event_key, "Success", conversation=conversation)
	except MessengerSendError as exc:
		if exc.is_page_restriction:
			mark_sender_restricted(psid)
		mark_webhook_event(event_key, "Processed", "send_failed")
		_log_send(event_key, "Failed", conversation=conversation, error_summary=str(exc)[:1400])
	except Exception as exc:
		mark_webhook_event(event_key, "Processed", "send_failed")
		_log_send(event_key, "Failed", conversation=conversation, error_summary=str(exc)[:1400])
		frappe.log_error(title="sahbi facebook send failed")


def _send_with_retry(psid: str, text: str) -> None:
	delay = 0.4
	last_exc: Exception | None = None
	for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
		try:
			FacebookMessengerClient().send_text(psid, text, messaging_type="RESPONSE")
			return
		except MessengerSendError as exc:
			last_exc = exc
			if not exc.retryable or attempt >= MAX_SEND_ATTEMPTS:
				raise
			if not frappe.flags.in_test:
				time.sleep(delay)
				delay = min(delay * 2, 2.0)
	if last_exc:
		raise last_exc


def _try_send(psid: str, text: str, event_key: str = "") -> None:
	try:
		_send_and_log(psid, text, event_key)
	except Exception:
		frappe.log_error(title="sahbi facebook fallback send failed")


def _safe_fallback(psid: str, event_key: str, conversation: str = "") -> None:
	if sender_restricted(psid):
		return
	try:
		_send_and_log(psid, replies.error_generic(), event_key, conversation)
	except Exception:
		pass


def _log_send(
	event_key: str,
	status: str,
	*,
	conversation: str = "",
	error_summary: str = "",
) -> None:
	kwargs = {
		"integration": "Meta",
		"operation": "send_message",
		"status": status,
		"error_summary": error_summary,
		"correlation_id": event_key,
	}
	if conversation:
		kwargs["related_doctype"] = "Sahbi Conversation"
		kwargs["related_name"] = conversation
	insert_integration_log(**kwargs)
