# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sahbi.chat.local_query import parse_account_query, parse_local_operation
from sahbi.chat.service import _is_confirm, get_conversation_history, handle_message
from sahbi.chat.dates import parse_date_expression
from sahbi.engine import create_expense, create_income, create_purchase, create_sale
from sahbi.llm.errors import SahbiLLMUnavailable
from sahbi.tests.helpers import make_person, make_user, make_workspace


def _op(intent, **operation):
	payload = {
		"intent": intent,
		"operation": {
			"type": None,
			"amount": None,
			"person_name": None,
			"description": None,
			"date_expression": None,
			"previous_operation_references": [],
			"loan_direction": None,
		},
		"query": {"kind": None, "search_terms": [], "person_name": None, "date_expression": None},
		"missing_fields": [],
		"is_ambiguous": False,
		"ambiguity_reason": None,
		"clarification_question": None,
	}
	payload["operation"].update(operation)
	return payload


class TestSahbiChatWorkflow(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user(f"sahbi.chat.{frappe.generate_hash(length=8)}@example.com")
		self.workspace = make_workspace(self.user).name
		self.person = make_person(self.workspace, "محمد")
		frappe.set_user(self.user)

	def test_greeting_does_not_need_ollama(self):
		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("مساء الفل")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "conversation")
		self.assertIn("صاحبي", result["reply"])
		self.assertIn("عامل ايه النهاردة", result["reply"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), 0)

	def test_daily_greeting_starts_the_chat(self):
		history = get_conversation_history()
		contents = [row.content for row in history["messages"]]
		self.assertTrue(contents)
		self.assertIn("عامل ايه النهاردة", contents[0])
		self.assertEqual(history["messages"][0].role, "Sahbi")

		again = get_conversation_history(history["conversation"])
		checkins = [row.content for row in again["messages"] if "عامل ايه النهاردة" in (row.content or "")]
		self.assertEqual(len(checkins), 1)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			follow = handle_message("ازيك")
			mocked.assert_not_called()
		self.assertNotIn("عامل ايه النهاردة", follow["reply"])
		self.assertIn("أنا هنا معاك", follow["reply"])

	def test_person_account_questions_use_engine(self):
		self.assertEqual(parse_account_query("قولي حساب محمد")["person_name"], "محمد")
		self.assertEqual(parse_account_query("قولي حساب محمد حامد كام")["person_name"], "محمد حامد")
		self.assertEqual(parse_account_query("كشف حساب محمد حامد")["person_name"], "محمد حامد")
		self.assertEqual(parse_account_query("كشف محمد حامد")["person_name"], "محمد حامد")
		self.assertEqual(parse_account_query("تفاصيل حساب محمد")["person_name"], "محمد")
		self.assertIsNone(parse_account_query("اشتريت خشب بـ5000"))

		frappe.set_user("Administrator")
		create_sale(self.workspace, 400, person=self.person.name)
		hamed = make_person(self.workspace, "محمد حامد")
		create_sale(self.workspace, 150, person=hamed.name)
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("قولي حساب محمد")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "needs_clarification")
		self.assertIn("محمد حامد", result["reply"])
		self.assertIn("1 - محمد", result["reply"])

		chosen = handle_message("1")
		self.assertEqual(chosen["status"], "ok")
		self.assertIn("حساب محمد", chosen["reply"])
		self.assertIn("400.00", chosen["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			full = handle_message("قولي حساب محمد حامد كام")
			mocked.assert_not_called()
		self.assertIn("حساب محمد حامد", full["reply"])
		self.assertIn("150.00", full["reply"])
		self.assertNotIn("ضحكتني", full["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			statement = handle_message("كشف حساب محمد حامد")
			mocked.assert_not_called()
		self.assertIn("حساب محمد حامد", statement["reply"])
		self.assertIn("بعت له 150.00 جنيه", statement["reply"])
		self.assertNotIn("كشف محمد", statement["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			everyone = handle_message("وريني حسابات الناس")
			mocked.assert_not_called()
		self.assertEqual(everyone["status"], "ok")
		self.assertIn("حسابات الناس", everyone["reply"])
		self.assertIn("محمد حامد", everyone["reply"])
		self.assertNotIn("حسابات الناس في الحساب", everyone["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			who = handle_message("مين ليه فلوس عندي")
			mocked.assert_not_called()
		self.assertEqual(who["status"], "ok")
		self.assertIn("اللي ليه عندك", who["reply"])
		self.assertNotIn("تحصيل", who["reply"])

	def test_partial_person_name_auto_selects_single_match(self):
		frappe.set_user("Administrator")
		only = make_person(self.workspace, "سامي حامد")
		frappe.set_user(self.user)
		interpretation = _op(
			"financial_operation",
			type="outgoing_money",
			amount="200.00",
			person_name="سامي",
		)
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			result = handle_message("انا دفعت لسامي 200 جنية")
		self.assertEqual(result["status"], "ok")
		self.assertTrue(result["linked_entry"])
		self.assertEqual(frappe.db.get_value("Sahbi Entry", result["linked_entry"], "person"), only.name)
		self.assertNotIn("أضيفه", result["reply"])

	def test_partial_person_name_asks_when_several_match(self):
		frappe.set_user("Administrator")
		make_person(self.workspace, "محمد حامد")
		frappe.set_user(self.user)
		interpretation = _op(
			"financial_operation",
			type="outgoing_money",
			amount="200.00",
			person_name="محمد",
		)
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			asked = handle_message("انا دفعت لمحمد 200 جنية")
		self.assertEqual(asked["status"], "needs_clarification")
		self.assertIn("1 - محمد", asked["reply"])
		self.assertIn("محمد حامد", asked["reply"])
		self.assertNotIn("أضيفه", asked["reply"])

		picked = handle_message("2")
		self.assertEqual(picked["status"], "ok")
		self.assertTrue(picked["linked_entry"])
		self.assertEqual(
			frappe.db.get_value("Sahbi Person", frappe.db.get_value("Sahbi Entry", picked["linked_entry"], "person"), "person_name"),
			"محمد حامد",
		)

	def test_sale_to_name_after_laam_keeps_real_person(self):
		parsed = parse_local_operation("بيعت ب 500 جنية لاحمد حنفي")
		self.assertEqual(parsed["type"], "sale")
		self.assertEqual(parsed["amount"], "500")
		self.assertEqual(parsed["person_name"], "احمد حنفي")
		self.assertNotIn("لحيمه", parsed["person_name"])
		self.assertNotIn("لحيمة", parsed["person_name"])
		self.assertIsNone(parse_local_operation("محمد اداني 2000"))

		with patch("sahbi.chat.service.interpret_message") as mocked:
			asked = handle_message("بيعت ب 500 جنية لاحمد حنفي")
			mocked.assert_not_called()
		self.assertEqual(asked["status"], "needs_clarification")
		self.assertIn("احمد حنفي", asked["reply"])
		self.assertNotIn("لحيمة", asked["reply"])

		confirmed = handle_message("ضيفه")
		self.assertEqual(confirmed["status"], "ok")
		self.assertIn("احمد حنفي", confirmed["reply"])
		self.assertNotIn("لحيمة", confirmed["reply"])
		self.assertEqual(
			frappe.db.get_value(
				"Sahbi Person",
				frappe.db.get_value("Sahbi Entry", confirmed["linked_entry"], "person"),
				"person_name",
			),
			"احمد حنفي",
		)
		self.assertEqual(frappe.db.get_value("Sahbi Entry", confirmed["linked_entry"], "entry_type"), "Sale")

	def test_displays_user_and_sahbi_messages(self):
		with patch(
			"sahbi.chat.service.interpret_message",
			return_value={"intent": "ordinary_conversation", "operation": {}, "query": {}, "missing_fields": []},
		):
			result = handle_message("ازيك")
		history = get_conversation_history(result["conversation"])
		roles = [row.role for row in history["messages"]]
		contents = [row.content for row in history["messages"]]
		self.assertIn("User", roles)
		self.assertIn("Sahbi", roles)
		self.assertIn("ازيك", contents)
		self.assertTrue(any("صاحبي" in text for text in contents))

	def test_successful_sale_summary_only_after_commit(self):
		interpretation = _op(
			"financial_operation",
			type="sale",
			amount="20000.00",
			description="مطبخ",
		)
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			result = handle_message("بعت مطبخ بـ20000")
		self.assertEqual(result["status"], "ok")
		self.assertIn("20000.00", result["reply"])
		self.assertIn("اتسجل", result["reply"])
		self.assertTrue(result["linked_entry"])
		self.assertEqual(frappe.db.get_value("Sahbi Entry", result["linked_entry"], "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Sahbi Entry", result["linked_entry"], "workspace"), self.workspace)

	def test_add_person_accepts_egyptian_yes(self):
		for index, reply in enumerate(("ايوة", "ايوه", "ضيفه", "أضيفه"), start=1):
			interpretation = _op(
				"financial_operation",
				type="expense",
				amount="50.00",
				person_name=f"خالد {index}",
			)
			with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
				asked = handle_message(f"دفعت لخالد {index} 50")
			self.assertEqual(asked["status"], "needs_clarification", reply)
			self.assertIn("أضيف", asked["reply"])
			with patch("sahbi.chat.service.interpret_message") as mocked:
				confirmed = handle_message(reply)
				mocked.assert_not_called()
			self.assertEqual(confirmed["status"], "ok", reply)
			self.assertTrue(confirmed["linked_entry"], reply)
			self.assertNotIn("أضيف الشخص", confirmed["reply"])

		for yes in ("ايوة", "أيوه", "ايوه", "ماشي", "حاضر"):
			self.assertTrue(_is_confirm(yes), yes)
		self.assertTrue(_is_confirm("ضيفه", allow_add_person=True))
		self.assertFalse(_is_confirm("ضيفه"))

	def test_clarification_does_not_save(self):
		interpretation = _op(
			"financial_operation",
			type="incoming_money",
			amount="2000.00",
			person_name="محمد",
		)
		interpretation["is_ambiguous"] = True
		interpretation["clarification_question"] = "المبلغ ده دخل ولا سلفة من محمد؟"
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			result = handle_message("محمد اداني 2000")
		self.assertEqual(result["status"], "needs_clarification")
		self.assertFalse(result["linked_entry"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), 0)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			follow = handle_message("دخل")
			mocked.assert_not_called()
		self.assertEqual(follow["status"], "ok")
		self.assertTrue(follow["linked_entry"])
		self.assertEqual(frappe.db.get_value("Sahbi Entry", follow["linked_entry"], "entry_type"), "Income")

	def test_cancel_requires_confirmation_then_keeps_history(self):
		frappe.set_user("Administrator")
		sale = create_sale(self.workspace, 400, person=self.person.name)
		frappe.set_user(self.user)
		with patch(
			"sahbi.chat.service.interpret_message",
			return_value={"intent": "ordinary_conversation", "operation": {}, "query": {}, "missing_fields": []},
		):
			opened = handle_message("ازيك")
		conv = frappe.get_doc("Sahbi Conversation", opened["conversation"])
		conv.db_set("last_entry", sale["name"])

		cancel_intent = _op("financial_operation", type="cancellation")
		with patch("sahbi.chat.service.interpret_message", return_value=cancel_intent):
			preview = handle_message("الغي العملية")
		self.assertEqual(preview["status"], "needs_confirmation")
		self.assertEqual(frappe.db.get_value("Sahbi Entry", sale["name"], "docstatus"), 1)
		self.assertNotIn("اتلغت العملية", preview["reply"])

		confirmed = handle_message("أيوه")
		self.assertEqual(confirmed["status"], "ok")
		self.assertEqual(frappe.db.get_value("Sahbi Entry", sale["name"], "docstatus"), 2)
		self.assertTrue(frappe.db.exists("Sahbi Entry", sale["name"]))

	def test_query_uses_engine_totals(self):
		frappe.set_user("Administrator")
		create_income(self.workspace, 100)
		create_income(self.workspace, 50)
		frappe.set_user(self.user)
		query = {
			"intent": "financial_query",
			"operation": {},
			"query": {"kind": "income_expense", "search_terms": [], "person_name": None, "date_expression": None},
			"missing_fields": [],
			"is_ambiguous": False,
		}
		with patch("sahbi.chat.service.interpret_message", return_value=query):
			result = handle_message("الدخل كام؟")
		self.assertEqual(result["status"], "ok")
		self.assertIn("150.00", result["reply"])
		self.assertNotIn("ربح", result["reply"])

	def test_query_keeps_wood_and_transport_apart(self):
		frappe.set_user("Administrator")
		create_purchase(self.workspace, 5000, description="خشب")
		create_expense(self.workspace, 250, description="نقل الخشب")
		frappe.set_user(self.user)
		query = {
			"intent": "financial_query",
			"operation": {},
			"query": {"kind": "purchase", "search_terms": ["خشب"], "person_name": None, "date_expression": None},
			"missing_fields": [],
		}
		with patch("sahbi.chat.service.interpret_message", return_value=query):
			result = handle_message("اشتريت خشب بكام؟")
		self.assertEqual(result["status"], "ok")
		self.assertIn("5000.00", result["reply"])
		self.assertNotIn("250.00", result["reply"])

	def test_query_explains_cash_limitation(self):
		query = {
			"intent": "financial_query",
			"operation": {},
			"query": {"kind": "cash_or_bank", "search_terms": [], "person_name": None, "date_expression": None},
			"missing_fields": [],
		}
		with patch("sahbi.chat.service.interpret_message", return_value=query):
			result = handle_message("معايا كام في البنك؟")
		self.assertEqual(result["status"], "ok")
		self.assertIn("الكاش أو البنك", result["reply"])

	def test_date_expression_this_month(self):
		dates = parse_date_expression("الشهر ده")
		self.assertTrue(dates["from_date"])
		self.assertTrue(dates["to_date"])

	def test_llm_error_does_not_post(self):
		with patch("sahbi.chat.service.interpret_message", side_effect=SahbiLLMUnavailable("down")):
			result = handle_message("بعت مطبخ")
		self.assertEqual(result["status"], "error")
		self.assertIn("مقدرش", result["reply"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), 0)

	def test_users_cannot_use_another_conversation(self):
		with patch(
			"sahbi.chat.service.interpret_message",
			return_value={"intent": "ordinary_conversation", "operation": {}, "query": {}, "missing_fields": []},
		):
			mine = handle_message("ازيك")
		frappe.set_user("Administrator")
		other = make_user(f"sahbi.chat.iso.{frappe.generate_hash(length=8)}@example.com")
		make_workspace(other)
		frappe.set_user(other)
		with self.assertRaises(frappe.PermissionError):
			handle_message("ازيك", conversation=mine["conversation"])

	def test_missing_amount_asks_and_does_not_save(self):
		interpretation = _op("financial_operation", type="outgoing_money", person_name="محمد")
		interpretation["missing_fields"] = ["amount"]
		interpretation["clarification_question"] = "دفعت لمحمد كام؟"
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			result = handle_message("دفعت لمحمد")
		self.assertEqual(result["status"], "needs_clarification")
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), 0)
		self.assertEqual(frappe.db.count("Sahbi Payment", {"workspace": self.workspace}), 0)
