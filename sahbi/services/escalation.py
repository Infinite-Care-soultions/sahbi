# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Pause / resume AI and human handoffs for Desk operators."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime


class EscalationService:
	def pause_ai(self, conversation_name: str, *, reason: str | None = None) -> Any:
		doc = frappe.get_doc("Sahbi Conversation", conversation_name)
		doc.ai_paused = 1
		if (doc.status or "Open") == "Open":
			doc.status = "Paused"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return doc

	def resume_ai(self, conversation_name: str) -> Any:
		doc = frappe.get_doc("Sahbi Conversation", conversation_name)
		doc.ai_paused = 0
		if doc.status in ("Paused", "Handed Off"):
			doc.status = "Open"
		if doc.handoff_status in ("Pending", "Active"):
			doc.handoff_status = "Resolved"
		doc.save(ignore_permissions=True)
		for name in frappe.get_all(
			"Sahbi Human Handoff",
			filters={"conversation": doc.name, "status": ("in", ["Open", "In Progress"])},
			pluck="name",
		):
			ho = frappe.get_doc("Sahbi Human Handoff", name)
			ho.status = "Resolved"
			ho.resolved_at = now_datetime()
			ho.resolution_notes = ((ho.resolution_notes or "") + "\nAI resumed").strip()
			ho.save(ignore_permissions=True)
		frappe.db.commit()
		return doc

	def assign_staff(self, conversation_name: str, user: str) -> Any:
		doc = frappe.get_doc("Sahbi Conversation", conversation_name)
		doc.assigned_staff = user
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return doc

	def create_handoff(
		self,
		conversation_name: str,
		*,
		reason: str,
		priority: str = "Normal",
		pause_ai: bool = True,
	) -> str:
		conv = frappe.get_doc("Sahbi Conversation", conversation_name)
		if pause_ai:
			conv.ai_paused = 1
			conv.status = "Handed Off"
			conv.handoff_status = "Pending"
			conv.save(ignore_permissions=True)
		ho = frappe.get_doc(
			{
				"doctype": "Sahbi Human Handoff",
				"conversation": conversation_name,
				"workspace": conv.workspace,
				"reason": (reason or "Staff handoff")[:200],
				"priority": priority or "Normal",
				"status": "Open",
				"assignee": conv.assigned_staff,
				"created_at": now_datetime(),
			}
		)
		ho.insert(ignore_permissions=True)
		frappe.db.commit()
		return ho.name

	def resolve_handoff(self, handoff_name: str, *, notes: str | None = None, resume_ai: bool = True) -> Any:
		ho = frappe.get_doc("Sahbi Human Handoff", handoff_name)
		ho.status = "Resolved"
		ho.resolved_at = now_datetime()
		if notes:
			ho.resolution_notes = notes
		ho.save(ignore_permissions=True)
		if resume_ai and ho.conversation:
			self.resume_ai(ho.conversation)
		else:
			frappe.db.commit()
		return ho
