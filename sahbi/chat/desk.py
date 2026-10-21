# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Desk inbox helpers: pause gate and Messenger windows."""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

STANDARD_WINDOW_HOURS = 24
HUMAN_AGENT_WINDOW_DAYS = 7
HANDED_OFF_REPLY = "هرد عليك حد من الفريق دلوقتي."


def can_ai_reply(conversation) -> tuple[bool, str]:
	if int(getattr(conversation, "ai_paused", 0) or 0):
		return False, "ai_paused"
	if (conversation.status or "Open") in ("Paused", "Handed Off"):
		return False, "handed_off_or_paused"
	if (conversation.handoff_status or "None") in ("Pending", "Active"):
		return False, "handoff_active"
	return True, ""


def touch_inbound(conversation) -> None:
	conversation.db_set("last_inbound_at", now_datetime(), update_modified=False)
	if conversation.status == "Closed":
		conversation.db_set("status", "Open", update_modified=False)
	conversation.reload()


def last_user_activity(conversation):
	if conversation.last_inbound_at:
		return conversation.last_inbound_at
	return frappe.db.get_value(
		"Sahbi Chat Message",
		{"conversation": conversation.name, "role": "User"},
		"creation",
		order_by="creation desc",
	)


def within_standard_messaging_window(conversation) -> bool:
	return _within(last_user_activity(conversation), hours=STANDARD_WINDOW_HOURS)


def within_human_agent_window(conversation) -> bool:
	return _within(last_user_activity(conversation), days=HUMAN_AGENT_WINDOW_DAYS)


def facebook_psid(conversation) -> str:
	return str(frappe.db.get_value("Sahbi Workspace", conversation.workspace, "facebook_psid") or "")


def _within(last_inbound_at, *, hours: int = 0, days: int = 0) -> bool:
	if not last_inbound_at:
		return False
	last = get_datetime(last_inbound_at)
	return now_datetime() <= last + timedelta(hours=hours, days=days)
