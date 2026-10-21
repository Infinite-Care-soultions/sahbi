# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Inbound Messenger processing. Replies go through the same Sahbi chat engine."""

from __future__ import annotations

import frappe

from sahbi.chat import replies
from sahbi.chat.service import handle_message
from sahbi.integrations.events import extract_inbound_content
from sahbi.integrations.facebook_messenger import FacebookMessengerClient, MessengerSendError
from sahbi.integrations.logs import insert_integration_log, mark_webhook_event
from sahbi.integrations.settings import get_default_facebook_workspace


def process_messaging_event(page_id: str, messaging_event: dict, event_key: str) -> None:
	frappe.set_user("Administrator")
	mark_webhook_event(event_key, "Processing")

	sender = (messaging_event.get("sender") or {}).get("id")
	if not sender:
		mark_webhook_event(event_key, "Rejected", "missing_sender")
		return

	workspace = _resolve_workspace(sender)
	if not workspace:
		_try_send(sender, replies.facebook_unmapped())
		mark_webhook_event(event_key, "Processed", "unmapped_workspace")
		frappe.db.commit()
		return

	content = extract_inbound_content(messaging_event)
	if content.get("kind") == "attachment":
		_try_send(sender, replies.unsupported_attachment())
		mark_webhook_event(event_key, "Processed", "unsupported_attachment")
		frappe.db.commit()
		return

	text = (content.get("text") or "").strip()
	if not text:
		mark_webhook_event(event_key, "Processed", "empty_text")
		frappe.db.commit()
		return

	owner = frappe.db.get_value("Sahbi Workspace", workspace, "user")
	if not owner:
		mark_webhook_event(event_key, "Processed", "missing_workspace_owner")
		frappe.db.commit()
		return

	try:
		frappe.set_user(owner)
		result = handle_message(text)
		reply = (result or {}).get("reply") or ""
		if reply:
			client = FacebookMessengerClient()
			client.send_typing_on(sender)
			client.send_text(sender, reply)
		mark_webhook_event(event_key, "Processed")
		insert_integration_log(
			integration="Meta",
			operation="send_message",
			status="Success",
			correlation_id=event_key,
			related_doctype="Sahbi Conversation",
			related_name=(result or {}).get("conversation") or "",
		)
		frappe.db.commit()
	except MessengerSendError as exc:
		mark_webhook_event(event_key, "Processed", "send_failed")
		insert_integration_log(
			integration="Meta",
			operation="send_message",
			status="Failed",
			error_summary=str(exc)[:1400],
			correlation_id=event_key,
		)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		mark_webhook_event(event_key, "Processed", "error")
		frappe.log_error(title="sahbi message processing failed")
		raise
	finally:
		frappe.set_user("Administrator")


def _resolve_workspace(psid: str) -> str | None:
	linked = frappe.db.get_value(
		"Sahbi Workspace",
		{"facebook_psid": psid, "disabled": 0},
		"name",
	)
	if linked:
		return linked
	workspace = get_default_facebook_workspace()
	if not workspace or not frappe.db.exists("Sahbi Workspace", workspace):
		return None
	if frappe.db.get_value("Sahbi Workspace", workspace, "disabled"):
		return None
	if not frappe.db.get_value("Sahbi Workspace", workspace, "facebook_psid"):
		frappe.db.set_value("Sahbi Workspace", workspace, "facebook_psid", psid)
	return workspace


def _try_send(psid: str, text: str) -> None:
	try:
		FacebookMessengerClient().send_text(psid, text)
	except Exception:
		frappe.log_error(title="sahbi facebook fallback send failed")
