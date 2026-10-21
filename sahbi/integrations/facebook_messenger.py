# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Meta Messenger Send API adapter and signature helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import frappe

from sahbi.integrations.settings import get_graph_api_base, get_page_access_token

MESSENGER_TEXT_LIMIT = 2000
_http_post = None


class MessengerSendError(Exception):
	def __init__(self, message: str, *, permanent: bool = False, status_code: int | None = None):
		super().__init__(message)
		self.permanent = permanent
		self.status_code = status_code


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
	if not signature_header or not app_secret or raw_body is None:
		return False
	if not signature_header.startswith("sha256="):
		return False
	expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
	provided = signature_header.split("=", 1)[1].strip()
	return hmac.compare_digest(expected, provided)


def verify_token_match(provided: str | None, expected: str | None) -> bool:
	if not provided or not expected:
		return False
	return hmac.compare_digest(str(provided), str(expected))


def split_message(text: str, limit: int = MESSENGER_TEXT_LIMIT) -> list[str]:
	text = text or ""
	if len(text) <= limit:
		return [text] if text else []
	chunks: list[str] = []
	remaining = text
	while remaining:
		chunks.append(remaining[:limit])
		remaining = remaining[limit:]
	return chunks


class FacebookMessengerClient:
	def __init__(
		self,
		*,
		page_access_token: str | None = None,
		graph_api_base: str | None = None,
	):
		self.page_access_token = page_access_token or get_page_access_token()
		self.graph_api_base = (graph_api_base or get_graph_api_base()).rstrip("/")

	@property
	def uses_local_override(self) -> bool:
		return "graph.facebook.com" not in (self.graph_api_base or "")

	@property
	def send_url(self) -> str:
		base = (self.graph_api_base or "").rstrip("/")
		if base.endswith("/me/messages"):
			return base
		return f"{base}/me/messages"

	def send_text(
		self,
		psid: str,
		text: str,
		*,
		messaging_type: str = "RESPONSE",
		tag: str | None = None,
	) -> list[dict[str, Any]]:
		if not self.page_access_token and not self.uses_local_override:
			raise MessengerSendError("Page access token is not configured", permanent=True)
		results = []
		for chunk in split_message(text):
			payload: dict[str, Any] = {
				"recipient": {"id": psid},
				"messaging_type": messaging_type,
				"message": {"text": chunk},
			}
			if tag:
				payload["tag"] = tag
			results.append(self._post(payload))
		return results

	def send_typing_on(self, psid: str) -> dict[str, Any]:
		return self._post({"recipient": {"id": psid}, "sender_action": "typing_on"})

	def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
		global _http_post
		body = json.dumps(payload).encode("utf-8")
		url = self.send_url
		token = self.page_access_token or ("local-dev" if self.uses_local_override else "")
		if token and "access_token=" not in url:
			sep = "&" if "?" in url else "?"
			url = f"{url}{sep}access_token={token}"
		if _http_post is not None:
			return _http_post(url, body, payload)

		req = urlrequest.Request(
			url,
			data=body,
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urlrequest.urlopen(req, timeout=15) as resp:
				raw = resp.read().decode("utf-8")
				return json.loads(raw) if raw else {"ok": True}
		except urlerror.HTTPError as exc:
			detail = exc.read().decode("utf-8", errors="replace")
			permanent = exc.code in (400, 401, 403, 404)
			if exc.code == 401 and not self.uses_local_override:
				_log_integration("send_message", "Failed", f"Token unhealthy: {detail[:200]}")
			raise MessengerSendError(
				f"Messenger Send API HTTP {exc.code}: {detail[:300]}",
				permanent=permanent,
				status_code=exc.code,
			) from exc
		except urlerror.URLError as exc:
			raise MessengerSendError(f"Messenger Send API network error: {exc}", permanent=False) from exc


def set_http_post_for_tests(fn) -> None:
	global _http_post
	_http_post = fn


def _log_integration(operation: str, status: str, error_summary: str) -> None:
	try:
		from sahbi.integrations.logs import insert_integration_log

		insert_integration_log(
			integration="Meta",
			operation=operation,
			status=status,
			error_summary=error_summary,
		)
	except Exception:
		frappe.log_error("Failed to log Meta token unhealthy state")
