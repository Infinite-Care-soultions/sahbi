# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Desk actions for Sahbi Conversation: pause/resume, staff reply, handoff."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from sahbi.chat.desk import (
	facebook_psid,
	within_human_agent_window,
	within_standard_messaging_window,
)
from sahbi.integrations.facebook_messenger import FacebookMessengerClient, MessengerSendError
from sahbi.integrations.logs import insert_integration_log
from sahbi.permissions import STAFF_ROLES
from sahbi.services.escalation import EscalationService


def _assert_staff() -> None:
	if not set(frappe.get_roles()).intersection(STAFF_ROLES) and frappe.session.user != "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def pause_ai(conversation: str, reason: str | None = None) -> dict:
	_assert_staff()
	doc = EscalationService().pause_ai(conversation, reason=reason)
	return {"ok": True, "ai_paused": doc.ai_paused, "status": doc.status}


@frappe.whitelist()
def resume_ai(conversation: str) -> dict:
	_assert_staff()
	doc = EscalationService().resume_ai(conversation)
	return {"ok": True, "ai_paused": doc.ai_paused, "status": doc.status}


@frappe.whitelist()
def assign_staff(conversation: str, user: str) -> dict:
	_assert_staff()
	doc = EscalationService().assign_staff(conversation, user)
	return {"ok": True, "assigned_staff": doc.assigned_staff}


@frappe.whitelist()
def create_handoff(conversation: str, reason: str, priority: str = "Normal") -> dict:
	_assert_staff()
	name = EscalationService().create_handoff(conversation, reason=reason, priority=priority)
	return {"ok": True, "handoff": name}


@frappe.whitelist()
def resolve_handoff(handoff: str, notes: str | None = None, resume_ai: int = 1) -> dict:
	_assert_staff()
	ho = EscalationService().resolve_handoff(handoff, notes=notes, resume_ai=bool(int(resume_ai)))
	return {"ok": True, "status": ho.status}


@frappe.whitelist()
def get_transcript(conversation: str, limit: int = 200) -> list[dict[str, Any]]:
	if not conversation or not frappe.db.exists("Sahbi Conversation", conversation):
		frappe.throw(_("Conversation not found"))
	conv = frappe.get_doc("Sahbi Conversation", conversation)
	if not conv.has_permission("read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	limit = max(1, min(int(limit or 200), 500))
	return frappe.get_all(
		"Sahbi Chat Message",
		filters={"conversation": conversation},
		fields=["name", "role", "status", "content", "creation", "correlation_id"],
		order_by="creation desc",
		limit_page_length=limit,
	)


@frappe.whitelist()
def staff_reply(conversation: str, text: str) -> dict[str, Any]:
	"""
	Send a manual staff reply via Messenger.
	Inside 24h: RESPONSE. Outside 24h (≤7d): HUMAN_AGENT tag. Else blocked.
	"""
	_assert_staff()
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Message text is required"))
	conv = frappe.get_doc("Sahbi Conversation", conversation)
	psid = facebook_psid(conv)
	if not psid:
		frappe.throw(_("This conversation is not linked to Facebook"))

	use_human_agent = False
	if not within_standard_messaging_window(conv):
		if not within_human_agent_window(conv):
			frappe.throw(_("Messaging window closed. The user must message first before staff can reply."))
		use_human_agent = True

	try:
		if use_human_agent:
			FacebookMessengerClient().send_text(
				psid,
				text,
				messaging_type="MESSAGE_TAG",
				tag="HUMAN_AGENT",
			)
		else:
			FacebookMessengerClient().send_text(psid, text, messaging_type="RESPONSE")
	except MessengerSendError as exc:
		insert_integration_log(
			integration="Meta",
			operation="send_message",
			status="Failed",
			error_summary=str(exc)[:1400],
			correlation_id=f"staff:{frappe.session.user}",
			related_doctype="Sahbi Conversation",
			related_name=conv.name,
		)
		frappe.throw(_("Send failed: {0}").format(str(exc)[:200]))

	frappe.get_doc(
		{
			"doctype": "Sahbi Chat Message",
			"conversation": conv.name,
			"workspace": conv.workspace,
			"role": "Staff",
			"status": "ok",
			"content": text,
			"correlation_id": f"staff:{frappe.session.user}",
		}
	).insert(ignore_permissions=True)
	insert_integration_log(
		integration="Meta",
		operation="send_message",
		status="Success",
		error_summary="staff_reply",
		correlation_id=f"staff:{frappe.session.user}",
		related_doctype="Sahbi Conversation",
		related_name=conv.name,
	)
	frappe.db.commit()
	return {"ok": True, "human_agent_tag": use_human_agent}
