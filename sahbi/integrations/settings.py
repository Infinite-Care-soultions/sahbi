# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

DEFAULT_GRAPH_API_BASE = "https://graph.facebook.com/v26.0"


def get_settings():
	if not frappe.db.exists("DocType", "Sahbi LLM Settings"):
		return None
	return frappe.get_single("Sahbi LLM Settings")


def get_setting(fieldname: str, default: Any = "") -> Any:
	doc = get_settings()
	if not doc:
		return default
	value = doc.get(fieldname)
	return default if value in (None, "") else value


def get_password(fieldname: str) -> str:
	doc = get_settings()
	if not doc:
		return ""
	return doc.get_password(fieldname, raise_exception=False) or ""


def facebook_enabled() -> bool:
	return bool(get_setting("facebook_enabled", 0))


def get_app_secret() -> str:
	return get_password("facebook_app_secret")


def get_page_access_token() -> str:
	return get_password("facebook_page_access_token")


def get_verify_token() -> str:
	return get_password("facebook_verify_token")


def get_page_id() -> str:
	return str(get_setting("facebook_page_id", "") or "")


def get_default_facebook_workspace() -> str:
	return str(get_setting("facebook_workspace", "") or "")


def get_graph_api_base() -> str:
	configured = str(get_setting("graph_api_base", "") or "").strip()
	return configured.rstrip("/") if configured else DEFAULT_GRAPH_API_BASE


DEFAULT_REPLY_DELAY_SECONDS = 10
MAX_REPLY_DELAY_SECONDS = 60


def get_reply_delay_seconds() -> int:
	"""Seconds the Messenger job waits before the Graph send. Webhook is never delayed."""
	try:
		value = int(get_setting("reply_delay_seconds", DEFAULT_REPLY_DELAY_SECONDS) or 0)
	except (TypeError, ValueError):
		value = DEFAULT_REPLY_DELAY_SECONDS
	return max(0, min(value, MAX_REPLY_DELAY_SECONDS))
