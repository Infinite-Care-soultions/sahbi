# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Meta Messenger webhook endpoints. Logs every hit; processes only signed page events."""

from __future__ import annotations

import json
from typing import Any

import frappe
from werkzeug.wrappers import Response

from sahbi.integrations.events import build_event_key, should_ignore_messaging_event
from sahbi.integrations.facebook_messenger import verify_token_match, verify_webhook_signature
from sahbi.integrations.logs import persist_webhook_request
from sahbi.integrations.messenger_runtime import claim_event, inbound_rate_ok
from sahbi.integrations.settings import facebook_enabled, get_app_secret, get_page_id, get_verify_token


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def webhook():
	"""
	Meta callback URL: /api/method/sahbi.api.facebook_webhook.webhook
	"""
	method = (frappe.request.method or "OTHER").upper()
	raw = b""
	if method == "POST":
		raw = frappe.request.get_data(as_text=False) or b""

	log: dict[str, Any] = {
		"is_valid": False,
		"http_status": 500,
		"reason": "unhandled",
		"body": raw,
		"page_id": "",
	}
	log_name = _save_webhook_request(
		method=method,
		is_valid=0,
		http_status=0,
		reason="received",
		body=raw,
		page_id="",
	)
	try:
		if method == "GET":
			resp = _handle_verification(log)
		else:
			resp = _handle_event(log, raw)
		return resp
	except Exception:
		frappe.log_error(title="sahbi.facebook_webhook.webhook exception")
		# Valid Meta retries must not see 5xx. Log and ack.
		if method == "POST":
			log.update(is_valid=True, http_status=200, reason="exception_acked")
			return Response("EVENT_RECEIVED", mimetype="text/plain", status=200)
		log["reason"] = "exception"
		log["http_status"] = 500
		frappe.local.response.http_status_code = 500
		return Response("Server Error", mimetype="text/plain", status=500)
	finally:
		_save_webhook_request(
			method=method,
			is_valid=1 if log.get("is_valid") else 0,
			http_status=int(log.get("http_status") or 0),
			reason=str(log.get("reason") or ""),
			body=log.get("body") if log.get("body") is not None else raw,
			page_id=str(log.get("page_id") or ""),
			update_name=log_name,
		)


def _handle_verification(log: dict[str, Any]):
	args = frappe.request.args
	mode = args.get("hub.mode")
	token = args.get("hub.verify_token")
	challenge = args.get("hub.challenge")
	expected = get_verify_token()
	if mode == "subscribe" and verify_token_match(token, expected) and challenge is not None:
		log.update(is_valid=True, http_status=200, reason="verification_ok")
		return Response(str(challenge), mimetype="text/plain", status=200)

	frappe.local.response.http_status_code = 403
	log.update(is_valid=False, http_status=403, reason="verification_failed")
	return Response("Forbidden", mimetype="text/plain", status=403)


def _handle_event(log: dict[str, Any], raw: bytes):
	log["body"] = raw
	payload: dict[str, Any] | None = None
	try:
		parsed = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
		if isinstance(parsed, dict):
			payload = parsed
			log["page_id"] = _extract_any_page_id(payload)
	except Exception:
		payload = None

	signature = frappe.get_request_header("X-Hub-Signature-256")
	sig_ok = verify_webhook_signature(raw, signature, get_app_secret())

	if payload and _is_meta_console_sample(payload):
		return _handle_meta_console_sample(payload, log, process_events=bool(sig_ok))

	if not sig_ok:
		_rate_limit_ok(f"bad_sig:{frappe.local.request_ip or 'unknown'}", limit=30, seconds=60)
		frappe.local.response.http_status_code = 403
		log.update(is_valid=False, http_status=403, reason="invalid_signature")
		return Response("Invalid signature", mimetype="text/plain", status=403)

	if payload is None:
		frappe.local.response.http_status_code = 400
		log.update(is_valid=False, http_status=400, reason="malformed_json")
		return Response("Malformed JSON", mimetype="text/plain", status=400)

	if payload.get("object") != "page":
		log.update(is_valid=True, http_status=200, reason="logged_non_page_payload", page_id=_extract_any_page_id(payload))
		return Response("EVENT_RECEIVED", mimetype="text/plain", status=200)

	configured_page = get_page_id()
	entries = payload.get("entry") or []
	if not isinstance(entries, list):
		log.update(is_valid=True, http_status=200, reason="logged_invalid_entry_shape")
		return Response("EVENT_RECEIVED", mimetype="text/plain", status=200)

	messaging_count = 0
	mismatched_pages: list[str] = []
	change_fields: list[str] = []
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		page_id = str(entry.get("id") or "")
		page_mismatch = bool(configured_page and page_id and page_id != configured_page)
		if page_mismatch:
			mismatched_pages.append(page_id)
		use_page = (configured_page if page_mismatch and configured_page else None) or page_id or configured_page
		for messaging_event in entry.get("messaging") or []:
			if not isinstance(messaging_event, dict):
				continue
			messaging_count += 1
			_accept_messaging_event(use_page or "unknown", messaging_event)
		for change in entry.get("changes") or []:
			if not isinstance(change, dict) or not change.get("field"):
				continue
			change_fields.append(str(change.get("field")))

	page_id = _first_page_id(payload) or configured_page
	if mismatched_pages:
		reason = "event_accepted:page_id_mismatch:" + ",".join(mismatched_pages[:3])
	elif messaging_count:
		reason = "event_accepted"
	elif change_fields:
		reason = "event_accepted:changes:" + ",".join(change_fields[:8])
	else:
		reason = "event_accepted:empty"
	log.update(is_valid=True, http_status=200, reason=reason, page_id=page_id)
	return Response("EVENT_RECEIVED", mimetype="text/plain", status=200)


def _is_meta_console_sample(payload: dict[str, Any]) -> bool:
	sample = payload.get("sample")
	return isinstance(sample, dict) and ("field" in sample or "value" in sample)


def _handle_meta_console_sample(payload: dict[str, Any], log: dict[str, Any], *, process_events: bool):
	sample = payload.get("sample") or {}
	field = str(sample.get("field") or "")
	value = sample.get("value") if isinstance(sample.get("value"), dict) else {}
	configured_page = get_page_id()
	recipient_id = str((value.get("recipient") or {}).get("id") or "")
	page_id = configured_page or recipient_id
	log["page_id"] = page_id
	messaging_event = dict(value) if value else {}
	if process_events and field in ("messages", "messaging_postbacks") and (
		messaging_event.get("message") or messaging_event.get("postback")
	):
		_accept_messaging_event(page_id or "meta_console_test", messaging_event)
	reason = f"meta_console_sample:{field or 'unknown'}"
	if not process_events:
		reason += ":invalid_or_missing_signature"
	log.update(is_valid=True, http_status=200, reason=reason, page_id=page_id)
	return Response("EVENT_RECEIVED", mimetype="text/plain", status=200)


def _accept_messaging_event(page_id: str, messaging_event: dict[str, Any]) -> None:
	"""Filter, Redis-dedup, and enqueue. Never raise; never do LLM/Send API work."""
	try:
		ignore, _reason = should_ignore_messaging_event(messaging_event, page_id)
		if ignore:
			return

		sender = (messaging_event.get("sender") or {}).get("id")
		if sender and not inbound_rate_ok(str(sender)):
			return

		if not facebook_enabled():
			return

		event_key = build_event_key(messaging_event)
		if not claim_event(event_key):
			return

		mid = ((messaging_event.get("message") or {}).get("mid") or event_key)
		# frappe.enqueue reserves the name `event`, so the payload is passed as kwargs.
		frappe.enqueue(
			"sahbi.jobs.messages.process_messenger_event",
			queue="default",
			timeout=300,
			enqueue_after_commit=False,
			job_id=f"msgr:{mid}",
			deduplicate=True,
			page_id=page_id,
			messaging_event=messaging_event,
			event_key=event_key,
		)
	except Exception:
		frappe.log_error(title="sahbi facebook enqueue failed")


def _first_page_id(payload: dict[str, Any]) -> str:
	entries = payload.get("entry") or []
	if isinstance(entries, list) and entries and isinstance(entries[0], dict):
		return str(entries[0].get("id") or "")
	return ""


def _extract_any_page_id(payload: dict[str, Any]) -> str:
	pid = _first_page_id(payload)
	if pid:
		return pid
	sample = payload.get("sample")
	if isinstance(sample, dict):
		value = sample.get("value")
		if isinstance(value, dict):
			return str((value.get("recipient") or {}).get("id") or "")
	return ""


def _save_webhook_request(**kwargs) -> str | None:
	"""Always persist the HTTP hit. Failures must not break the webhook."""
	try:
		return persist_webhook_request(**kwargs)
	except Exception:
		frappe.log_error(title="sahbi webhook request persist failed")
		return kwargs.get("update_name")


def _rate_limit_ok(key: str, limit: int = 60, seconds: int = 60) -> bool:
	from sahbi.integrations.messenger_runtime import _incr_under_limit

	return _incr_under_limit(f"sahbi:rl:{key}", limit=limit, seconds=seconds)
