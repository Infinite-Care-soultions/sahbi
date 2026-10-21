# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_event_key(messaging_event: dict[str, Any]) -> str:
	message = messaging_event.get("message") or {}
	mid = message.get("mid")
	if mid:
		return f"msg:{mid}"
	postback = messaging_event.get("postback") or {}
	if postback:
		payload = postback.get("payload") or ""
		ts = messaging_event.get("timestamp") or ""
		sender = (messaging_event.get("sender") or {}).get("id") or ""
		raw = f"{sender}|{ts}|{payload}".encode()
		return "pb:" + hashlib.sha256(raw).hexdigest()[:32]
	sender = (messaging_event.get("sender") or {}).get("id") or ""
	ts = str(messaging_event.get("timestamp") or "")
	blob = json.dumps(messaging_event, sort_keys=True, default=str).encode()
	return f"ev:{sender}:{ts}:" + hashlib.sha256(blob).hexdigest()[:24]


def should_ignore_messaging_event(messaging_event: dict[str, Any], page_id: str) -> tuple[bool, str]:
	if messaging_event.get("delivery") or messaging_event.get("read"):
		return True, "delivery_or_read"
	message = messaging_event.get("message") or {}
	postback = messaging_event.get("postback") or {}
	if message.get("is_echo"):
		return True, "echo"
	sender = (messaging_event.get("sender") or {}).get("id")
	if not sender:
		return True, "missing_sender"
	if page_id and sender == page_id:
		return True, "page_self"
	if not message and not postback:
		return True, "unsupported_event"
	if message and not postback:
		text = (message.get("text") or "").strip()
		attachments = message.get("attachments") or []
		if not text and not attachments:
			return True, "empty_text"
	if postback and not (postback.get("payload") or postback.get("title")):
		return True, "empty_postback"
	return False, ""


def extract_inbound_content(messaging_event: dict[str, Any]) -> dict[str, Any]:
	message = messaging_event.get("message") or {}
	postback = messaging_event.get("postback") or {}
	if postback:
		return {
			"kind": "postback",
			"text": (postback.get("title") or postback.get("payload") or "").strip(),
			"payload": postback.get("payload"),
			"mid": None,
			"attachments": [],
		}
	attachments = message.get("attachments") or []
	text = (message.get("text") or "").strip()
	if attachments and not text:
		return {
			"kind": "attachment",
			"text": "",
			"mid": message.get("mid"),
			"attachments": attachments,
		}
	return {
		"kind": "text",
		"text": text,
		"mid": message.get("mid"),
		"attachments": attachments,
	}
