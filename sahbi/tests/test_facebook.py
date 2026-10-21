# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from sahbi.integrations.events import build_event_key, should_ignore_messaging_event
from sahbi.integrations.facebook_messenger import (
	FacebookMessengerClient,
	set_http_post_for_tests,
	split_message,
	verify_token_match,
	verify_webhook_signature,
)
from sahbi.jobs.messages import process_messaging_event
from sahbi.tests.helpers import make_user, make_workspace

APP_SECRET = "test_app_secret_sahbi"
VERIFY_TOKEN = "test_verify_token_sahbi"
PAGE_ID = "page_sahbi_111"
PSID = "user_sahbi_222"


def _sign(raw: bytes, secret: str = APP_SECRET) -> str:
	digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return f"sha256={digest}"


def _configure_settings(**extra):
	doc = frappe.get_single("Sahbi LLM Settings")
	doc.facebook_enabled = 1
	doc.facebook_page_id = PAGE_ID
	doc.facebook_app_secret = APP_SECRET
	doc.facebook_verify_token = VERIFY_TOKEN
	doc.facebook_page_access_token = "PAGE_TOKEN"
	doc.graph_api_base = "https://graph.facebook.com/v26.0"
	for key, value in extra.items():
		doc.set(key, value)
	doc.save(ignore_permissions=True)
	frappe.db.commit()


class TestMessengerCrypto(FrappeTestCase):
	def test_signature_accept_reject(self):
		raw = b'{"object":"page"}'
		self.assertTrue(verify_webhook_signature(raw, _sign(raw), APP_SECRET))
		self.assertFalse(verify_webhook_signature(raw, _sign(raw, "wrong"), APP_SECRET))
		self.assertFalse(verify_webhook_signature(raw, None, APP_SECRET))
		self.assertFalse(verify_webhook_signature(raw, "sha256=abcd", APP_SECRET))

	def test_verify_token_constant_time(self):
		self.assertTrue(verify_token_match("abc", "abc"))
		self.assertFalse(verify_token_match("abc", "xyz"))
		self.assertFalse(verify_token_match(None, "abc"))

	def test_split_message(self):
		parts = split_message("x" * 2500, limit=2000)
		self.assertEqual(len(parts), 2)
		self.assertEqual(len(parts[0]), 2000)


class TestWebhookHandlers(FrappeTestCase):
	def setUp(self):
		_configure_settings()
		self._sent = []

		def fake_post(url, body, payload):
			self._sent.append(payload)
			return {"message_id": "mid.out"}

		set_http_post_for_tests(fake_post)

	def tearDown(self):
		set_http_post_for_tests(None)
		for doctype in ("Sahbi Webhook Event Log", "Sahbi Webhook Request", "Sahbi Integration Log"):
			for name in frappe.get_all(doctype, pluck="name"):
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
		frappe.db.commit()

	def _request(self, method: str, *, query=None, data=None, headers=None):
		builder = EnvironBuilder(
			method=method,
			path="/api/method/sahbi.api.facebook_webhook.webhook",
			query_string=query or {},
			data=data,
			headers=headers or {},
		)
		frappe.local.request = Request(builder.get_environ())
		frappe.local.request_ip = "203.0.113.10"
		return frappe.local.request

	def test_get_verification_success(self):
		from sahbi.api.facebook_webhook import webhook

		self._request(
			"GET",
			query={
				"hub.mode": "subscribe",
				"hub.verify_token": VERIFY_TOKEN,
				"hub.challenge": "1234567890",
			},
		)
		resp = webhook()
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.get_data(as_text=True), "1234567890")
		self.assertTrue(frappe.db.exists("Sahbi Webhook Request", {"reason": "verification_ok"}))

	def test_get_verification_reject(self):
		from sahbi.api.facebook_webhook import webhook

		self._request(
			"GET",
			query={
				"hub.mode": "subscribe",
				"hub.verify_token": "wrong",
				"hub.challenge": "123",
			},
		)
		resp = webhook()
		self.assertEqual(resp.status_code, 403)

	def test_post_signature_reject(self):
		from sahbi.api.facebook_webhook import webhook

		raw = json.dumps({"object": "page", "entry": []}).encode()
		self._request(
			"POST",
			data=raw,
			headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
		)
		with patch.object(frappe.request, "get_data", return_value=raw):
			resp = webhook()
		self.assertEqual(resp.status_code, 403)
		self.assertTrue(frappe.db.exists("Sahbi Webhook Request", {"reason": "invalid_signature"}))

	def test_post_signature_accept_and_enqueue(self):
		from sahbi.api import facebook_webhook as mod

		messaging = {
			"sender": {"id": PSID},
			"recipient": {"id": PAGE_ID},
			"timestamp": 1710000000000,
			"message": {"mid": "mid.sahbi.1", "text": "ازيك"},
		}
		payload = {"object": "page", "entry": [{"id": PAGE_ID, "messaging": [messaging]}]}
		raw = json.dumps(payload, separators=(",", ":")).encode()
		self._request(
			"POST",
			data=raw,
			headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(raw)},
		)
		enqueued = []

		def fake_enqueue(*args, **kwargs):
			enqueued.append(kwargs)

		with patch.object(frappe.request, "get_data", return_value=raw), patch.object(
			frappe, "enqueue", side_effect=fake_enqueue
		):
			resp = mod.webhook()

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.get_data(as_text=True), "EVENT_RECEIVED")
		self.assertEqual(len(enqueued), 1)
		self.assertTrue(frappe.db.exists("Sahbi Webhook Event Log", {"event_key": build_event_key(messaging)}))

	def test_duplicate_webhook_not_reenqueued(self):
		from sahbi.api import facebook_webhook as mod

		messaging = {
			"sender": {"id": PSID},
			"recipient": {"id": PAGE_ID},
			"timestamp": 1710000000001,
			"message": {"mid": "mid.sahbi.dup", "text": "ازيك"},
		}
		payload = {"object": "page", "entry": [{"id": PAGE_ID, "messaging": [messaging]}]}
		raw = json.dumps(payload, separators=(",", ":")).encode()
		self._request(
			"POST",
			data=raw,
			headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(raw)},
		)
		calls = []

		def fake_enqueue(*args, **kwargs):
			calls.append(1)

		with patch.object(frappe.request, "get_data", return_value=raw), patch.object(
			frappe, "enqueue", side_effect=fake_enqueue
		):
			mod.webhook()
			mod.webhook()
		self.assertEqual(len(calls), 1)

	def test_echo_ignored(self):
		ignore, reason = should_ignore_messaging_event(
			{"sender": {"id": PAGE_ID}, "message": {"mid": "m", "text": "x", "is_echo": True}},
			PAGE_ID,
		)
		self.assertTrue(ignore)
		self.assertEqual(reason, "echo")

	def test_disabled_facebook_is_logged_not_enqueued(self):
		from sahbi.api import facebook_webhook as mod

		_configure_settings(facebook_enabled=0)
		messaging = {
			"sender": {"id": PSID},
			"recipient": {"id": PAGE_ID},
			"timestamp": 1710000000002,
			"message": {"mid": "mid.sahbi.off", "text": "ازيك"},
		}
		payload = {"object": "page", "entry": [{"id": PAGE_ID, "messaging": [messaging]}]}
		raw = json.dumps(payload, separators=(",", ":")).encode()
		self._request(
			"POST",
			data=raw,
			headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(raw)},
		)
		calls = []
		with patch.object(frappe.request, "get_data", return_value=raw), patch.object(
			frappe, "enqueue", side_effect=lambda *a, **k: calls.append(1)
		):
			resp = mod.webhook()
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(calls, [])
		log = frappe.get_all(
			"Sahbi Webhook Event Log",
			filters={"event_key": build_event_key(messaging)},
			fields=["status", "notes"],
		)
		self.assertTrue(log)
		self.assertEqual(log[0].status, "Rejected")
		self.assertEqual(log[0].notes, "facebook_disabled")


class TestMessengerProcessing(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user("sahbi.facebook@example.com")
		self.workspace = make_workspace(user=self.user)
		_configure_settings(facebook_workspace=self.workspace.name)
		frappe.set_user(self.user)
		self._sent = []

		def fake_post(url, body, payload):
			self._sent.append(payload)
			return {"message_id": "mid.out"}

		set_http_post_for_tests(fake_post)

	def tearDown(self):
		set_http_post_for_tests(None)
		frappe.set_user("Administrator")
		if getattr(self, "workspace", None) and self.workspace.facebook_psid:
			frappe.db.set_value("Sahbi Workspace", self.workspace.name, "facebook_psid", "")

	def test_greeting_uses_sahbi_engine(self):
		event_key = "msg:mid.sahbi.hello"
		frappe.get_doc(
			{
				"doctype": "Sahbi Webhook Event Log",
				"event_key": event_key,
				"received_at": frappe.utils.now_datetime(),
				"status": "Received",
				"page_id": PAGE_ID,
			}
		).insert(ignore_permissions=True)
		process_messaging_event(
			PAGE_ID,
			{
				"sender": {"id": PSID},
				"recipient": {"id": PAGE_ID},
				"timestamp": 1710000000100,
				"message": {"mid": "mid.sahbi.hello", "text": "ازيك"},
			},
			event_key,
		)
		texts = [item.get("message", {}).get("text") for item in self._sent if item.get("message")]
		self.assertTrue(any(texts))
		joined = " ".join(t or "" for t in texts)
		self.assertTrue(any(word in joined for word in ("صاحبي", "هنا معاك", "قولّي", "عامل ايه")))
		self.assertEqual(
			frappe.db.get_value("Sahbi Workspace", self.workspace.name, "facebook_psid"),
			PSID,
		)
		self.assertEqual(
			frappe.db.get_value("Sahbi Webhook Event Log", {"event_key": event_key}, "status"),
			"Processed",
		)

	def test_unmapped_workspace_gets_egyptian_reply(self):
		_configure_settings(facebook_workspace="")
		process_messaging_event(
			PAGE_ID,
			{
				"sender": {"id": "unknown_psid"},
				"message": {"mid": "mid.sahbi.nomap", "text": "ازيك"},
			},
			"msg:mid.sahbi.nomap",
		)
		texts = [item.get("message", {}).get("text") for item in self._sent if item.get("message")]
		self.assertTrue(any("مش مربوط" in (t or "") for t in texts))

	def test_client_splits_long_replies(self):
		client = FacebookMessengerClient(page_access_token="TOK")
		client.send_text(PSID, "x" * 2500)
		self.assertEqual(len([item for item in self._sent if item.get("message")]), 2)


class TestLegalPages(FrappeTestCase):
	def test_terms_and_privacy_context(self):
		from frappe import _dict

		from sahbi.www._legal_context import build_legal_context
		from sahbi.www.privacy_policy import get_context as get_privacy_context
		from sahbi.www.terms_of_service import get_context as get_terms_context

		terms_ctx = get_terms_context(_dict())
		privacy_ctx = get_privacy_context(_dict())
		shared = build_legal_context(_dict())

		self.assertIn("Terms of Service", terms_ctx.title)
		self.assertIn("Privacy Policy", privacy_ctx.title)
		self.assertTrue(terms_ctx.no_cache)
		self.assertTrue(privacy_ctx.sitemap)
		self.assertIn("@", shared.contact_email)
		self.assertTrue(shared.last_updated)
