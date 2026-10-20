# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe

from sahbi.chat.service import get_conversation_history, handle_message


@frappe.whitelist(allow_guest=False)
def send_message(text: str, conversation: str | None = None):
	return handle_message(text, conversation)


@frappe.whitelist(allow_guest=False)
def get_history(conversation: str | None = None, limit: int = 50):
	return get_conversation_history(conversation, limit=int(limit or 50))
