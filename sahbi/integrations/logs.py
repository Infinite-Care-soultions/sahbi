# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any

import frappe

_BODY_LOG_LIMIT = 100_000


def insert_integration_log(
	*,
	integration: str,
	operation: str,
	status: str,
	error_summary: str = "",
	correlation_id: str = "",
	related_doctype: str = "",
	related_name: str = "",
	attempts: int = 1,
) -> None:
	if not frappe.db.exists("DocType", "Sahbi Integration Log"):
		frappe.logger("sahbi").error(f"{operation} {status}: {error_summary}")
		return
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Integration Log",
			"integration": integration,
			"operation": operation,
			"status": status,
			"timestamp": frappe.utils.now_datetime(),
			"error_summary": (error_summary or "")[:1400],
			"correlation_id": correlation_id,
			"related_doctype": related_doctype or None,
			"related_name": related_name or None,
			"attempts": attempts,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def insert_webhook_event_log(event_key: str, status: str, page_id: str, notes: str) -> None:
	if frappe.db.exists("Sahbi Webhook Event Log", {"event_key": event_key}):
		name = frappe.db.get_value("Sahbi Webhook Event Log", {"event_key": event_key}, "name")
		if name and status == "Duplicate":
			frappe.db.set_value("Sahbi Webhook Event Log", name, "status", "Duplicate")
		return
	try:
		frappe.get_doc(
			{
				"doctype": "Sahbi Webhook Event Log",
				"event_key": event_key,
				"received_at": frappe.utils.now_datetime(),
				"status": status,
				"page_id": page_id,
				"notes": notes,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.db.rollback()
		if frappe.db.exists("Sahbi Webhook Event Log", {"event_key": event_key}):
			return
		frappe.log_error(title="Sahbi Webhook Event Log insert failed")


def mark_webhook_event(event_key: str, status: str, notes: str | None = None) -> None:
	name = frappe.db.get_value("Sahbi Webhook Event Log", {"event_key": event_key}, "name")
	if not name:
		return
	values = {"status": status}
	if notes is not None:
		values["notes"] = notes
	frappe.db.set_value("Sahbi Webhook Event Log", name, values)


def persist_webhook_request(
	*,
	method: str,
	is_valid: int,
	http_status: int,
	reason: str,
	body: bytes | str | None,
	page_id: str = "",
	update_name: str | None = None,
) -> str | None:
	if method not in ("GET", "POST"):
		method = "OTHER"
	body_text = _body_to_text(body)
	signature = ""
	try:
		signature = frappe.get_request_header("X-Hub-Signature-256") or ""
	except Exception:
		pass

	values = {
		"received_at": frappe.utils.now_datetime(),
		"method": method,
		"is_valid": 1 if is_valid else 0,
		"http_status": http_status,
		"reason": (reason or "")[:500],
		"request_ip": getattr(frappe.local, "request_ip", None) or "",
		"page_id": page_id or "",
		"content_type": "",
		"signature_present": 1 if signature else 0,
		"query_params": "",
		"headers_json": "",
		"body": body_text,
	}
	try:
		values["content_type"] = frappe.get_request_header("Content-Type") or ""
	except Exception:
		pass
	try:
		values["query_params"] = json.dumps(_all_query_params(), ensure_ascii=False, indent=2)
	except Exception:
		values["query_params"] = ""
	try:
		values["headers_json"] = json.dumps(_all_headers(), ensure_ascii=False, indent=2)
	except Exception:
		values["headers_json"] = ""

	prev_user = None
	try:
		prev_user = frappe.session.user
		frappe.set_user("Administrator")

		if not frappe.db.exists("DocType", "Sahbi Webhook Request"):
			insert_integration_log(
				integration="Meta",
				operation="webhook_request",
				status="Success" if is_valid else "Failed",
				error_summary=f"{method} status={http_status} valid={is_valid} reason={reason} page={page_id}\n{body_text}",
			)
			return None

		if update_name and frappe.db.exists("Sahbi Webhook Request", update_name):
			frappe.db.set_value(
				"Sahbi Webhook Request",
				update_name,
				{
					"is_valid": values["is_valid"],
					"http_status": values["http_status"],
					"reason": values["reason"],
					"page_id": values["page_id"],
					"body": values["body"],
					"signature_present": values["signature_present"],
					"headers_json": values["headers_json"],
					"query_params": values["query_params"],
				},
				update_modified=True,
			)
			frappe.db.commit()
			return update_name

		doc = frappe.get_doc({"doctype": "Sahbi Webhook Request", **values})
		doc.insert(ignore_permissions=True, ignore_links=True)
		frappe.db.commit()
		return doc.name
	except Exception:
		try:
			frappe.db.rollback()
		except Exception:
			pass
		frappe.log_error(title="Sahbi Webhook Request log failed", message=f"{method} status={http_status} reason={reason}")
		try:
			insert_integration_log(
				integration="Meta",
				operation="webhook_request",
				status="Success" if is_valid else "Failed",
				error_summary=f"{method} status={http_status} valid={is_valid} reason={reason} page={page_id}",
			)
		except Exception:
			pass
		return update_name
	finally:
		if prev_user is not None:
			try:
				frappe.set_user(prev_user)
			except Exception:
				pass


def _all_query_params() -> dict[str, Any]:
	try:
		return dict(frappe.request.args or {})
	except Exception:
		return {}


def _all_headers() -> dict[str, str]:
	out: dict[str, str] = {}
	try:
		environ = getattr(frappe.request, "environ", None) or {}
		for key, value in environ.items():
			if key.startswith("HTTP_") and value is not None:
				name = key[5:].replace("_", "-").title()
				out[name] = str(value)[:2000]
		for cgi_key, header_name in (("CONTENT_TYPE", "Content-Type"), ("CONTENT_LENGTH", "Content-Length")):
			if environ.get(cgi_key):
				out[header_name] = str(environ.get(cgi_key))[:2000]
	except Exception:
		pass
	return out


def _body_to_text(body: bytes | str | None) -> str:
	if body is None:
		return ""
	if isinstance(body, (bytes, bytearray)):
		try:
			text = body.decode("utf-8")
		except Exception:
			text = body.decode("utf-8", errors="replace")
	else:
		text = str(body)
	if len(text) > _BODY_LOG_LIMIT:
		return text[:_BODY_LOG_LIMIT] + f"\n…[truncated {len(text) - _BODY_LOG_LIMIT} chars]"
	return text
