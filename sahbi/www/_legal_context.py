# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Shared context for public Facebook legal pages."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import nowdate

from sahbi.hooks import app_email


def build_legal_context(context: dict[str, Any]) -> dict[str, Any]:
	contact_email = str(frappe.conf.get("mail_from") or app_email or "beshoyatef31@gmail.com")

	context.no_cache = 1
	context.sitemap = 1
	context.full_width = True
	context.app_name = "Sahbi"
	context.contact_email = contact_email
	context.last_updated = str(nowdate())
	return context
