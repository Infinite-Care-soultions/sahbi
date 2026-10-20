# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import inspect
import json
from unittest.mock import patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from sahbi.llm import interpret_message, llm_status
from sahbi.llm.dataset import load_message_dataset
from sahbi.llm.errors import SahbiLLMInvalidOutput, SahbiLLMUnavailable
from sahbi.llm.service import interpret_message as interpret_message_direct
from sahbi.llm.settings import DEFAULT_MODEL, get_llm_settings
from sahbi.llm.validate import parse_model_text, validate_extraction
from sahbi.tests.helpers import make_user, make_workspace


def _dump(expected: dict) -> str:
	return json.dumps(expected, ensure_ascii=False)


class TestSahbiLLMService(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_dataset_covers_required_egyptian_examples(self):
		dataset = load_message_dataset()
		messages = {row["message"] for row in dataset}
		for required in (
			"اشتريت خشب بـ5000",
			"بعت مطبخ بـ20000",
			"محمد اداني 2000",
			"محمد سدد 2000 من حساب الخشب",
			"سلفت أحمد 1000",
			"أحمد رجع 300 من السلفة",
			"صرفنا كام على نقل الخشب؟",
		):
			self.assertIn(required, messages)
		self.assertGreaterEqual(len(dataset), 10)
		intents = {row["expected"]["intent"] for row in dataset}
		self.assertEqual(
			intents,
			{"financial_operation", "financial_query", "ordinary_conversation"},
		)

	def test_dataset_cases_pass_through_mocked_model(self):
		for row in load_message_dataset():
			with patch("sahbi.llm.service.complete", return_value=_dump(row["expected"])):
				parsed = interpret_message(row["message"])
			for key, value in row["expected"].items():
				self.assertEqual(parsed[key], value, msg=row["id"])
			self.assertEqual(parsed["model"], DEFAULT_MODEL)
			self.assertTrue(parsed["raw_accepted"])

	def test_invalid_json_is_safe(self):
		with patch("sahbi.llm.service.complete", return_value="this is not json"):
			with self.assertRaises(SahbiLLMInvalidOutput):
				interpret_message("اشتريت خشب")

	def test_markdown_fenced_json_is_accepted(self):
		payload = {
			"intent": "ordinary_conversation",
			"operation": {},
			"query": {},
			"missing_fields": [],
			"is_ambiguous": False,
		}
		with patch(
			"sahbi.llm.service.complete",
			return_value=f"```json\n{_dump(payload)}\n```",
		):
			parsed = interpret_message("شكرا")
		self.assertEqual(parsed["intent"], "ordinary_conversation")
		self.assertIsNone(parsed["operation"]["type"])

	def test_string_null_is_treated_as_missing(self):
		parsed = validate_extraction(
			{
				"intent": "ordinary_conversation",
				"operation": {"type": "null", "amount": "null", "person_name": "none"},
				"query": {"kind": "null"},
			}
		)
		self.assertEqual(parsed["intent"], "ordinary_conversation")
		self.assertIsNone(parsed["operation"]["type"])
		self.assertIsNone(parsed["query"]["kind"])

	def test_invalid_amount_is_rejected(self):
		payload = {
			"intent": "financial_operation",
			"operation": {"type": "sale", "amount": "مجانا"},
		}
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction(payload)

	def test_forbidden_sql_and_python_are_rejected(self):
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction(
				{
					"intent": "financial_query",
					"sql": "select sum(amount) from tabSahbi Entry",
				}
			)
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction(
				{
					"intent": "financial_query",
					"python": "frappe.db.sql('delete from tabSahbi Entry')",
				}
			)

	def test_model_totals_are_ignored_and_not_used(self):
		payload = {
			"intent": "financial_query",
			"query": {"kind": "income_expense"},
			"totals": {"income": 999},
		}
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction(payload)

	def test_ollama_unavailable_is_reported(self):
		with patch(
			"sahbi.llm.client.requests.post",
			side_effect=requests.ConnectionError("down"),
		):
			with self.assertRaises(SahbiLLMUnavailable):
				interpret_message_direct("ازيك")

	def test_model_name_is_configurable(self):
		settings = frappe.get_single("Sahbi LLM Settings")
		original = settings.ollama_model
		settings.ollama_model = "qwen2.5:7b"
		settings.save()
		self.assertEqual(get_llm_settings()["model"], "qwen2.5:7b")
		settings.ollama_model = original or DEFAULT_MODEL
		settings.save()

		with patch("sahbi.llm.client.requests.post") as mocked:
			mocked.return_value.status_code = 200
			mocked.return_value.json.return_value = {
				"message": {"content": _dump({"intent": "ordinary_conversation"})}
			}
			interpret_message("ازيك", model="custom-qwen")
			sent = mocked.call_args.kwargs["json"]
			self.assertEqual(sent["model"], "custom-qwen")
			self.assertEqual(sent["format"], "json")

	def test_interpret_does_not_write_financial_documents(self):
		user = make_user(f"sahbi.llm.{frappe.generate_hash(length=8)}@example.com")
		workspace = make_workspace(user).name
		before = frappe.db.count("Sahbi Entry", {"workspace": workspace})
		payload = {
			"intent": "financial_operation",
			"operation": {"type": "sale", "amount": "20000", "description": "مطبخ"},
		}
		with patch("sahbi.llm.service.complete", return_value=_dump(payload)):
			parsed = interpret_message("بعت مطبخ بـ20000")
		after = frappe.db.count("Sahbi Entry", {"workspace": workspace})
		self.assertEqual(before, after)
		self.assertEqual(parsed["operation"]["type"], "sale")

	def test_service_module_does_not_import_the_posting_engine(self):
		source = inspect.getsource(inspect.getmodule(interpret_message_direct))
		self.assertNotIn("sahbi.engine", source)
		self.assertNotIn("create_income", source)
		self.assertNotIn("frappe.db.sql", source)

	def test_llm_status_reports_clear_failure(self):
		with patch(
			"sahbi.llm.client.requests.get",
			side_effect=requests.ConnectionError("refused"),
		):
			status = llm_status()
		self.assertFalse(status["available"])
		self.assertIn("error", status)
		self.assertEqual(status["configured_model"], DEFAULT_MODEL)

	def test_empty_message_is_rejected(self):
		with self.assertRaises(SahbiLLMInvalidOutput):
			interpret_message("   ")

	def test_parse_model_text_rejects_non_objects(self):
		with self.assertRaises(SahbiLLMInvalidOutput):
			parse_model_text("[1,2,3]")

	def test_desk_workspace_lists_sahbi_doctypes(self):
		workspace = frappe.get_doc("Workspace", "Sahbi")
		self.assertTrue(workspace.public)
		self.assertFalse(workspace.is_hidden)
		link_tos = {row.link_to for row in workspace.links if row.type == "Link"}
		for doctype in (
			"Sahbi Workspace",
			"Sahbi Person",
			"Sahbi Entry",
			"Sahbi Payment",
			"Sahbi Payment Allocation",
			"Sahbi Conversation",
			"Sahbi Chat Message",
			"Sahbi LLM Settings",
		):
			self.assertIn(doctype, link_tos)
		self.assertTrue(frappe.get_meta("Sahbi LLM Settings").issingle)
		self.assertTrue(any(row.type == "Page" and row.link_to == "sahbi-chat" for row in workspace.shortcuts))
		self.assertTrue(
			any(row.type == "DocType" and row.link_to == "Sahbi LLM Settings" for row in workspace.shortcuts)
		)
