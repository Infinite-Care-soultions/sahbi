# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from sahbi.chat.local_query import parse_account_query, parse_local_operation, parse_local_operations, parse_local_query
from sahbi.chat.replies import help_for_topic, help_guide
from sahbi.chat.service import (
	_is_confirm,
	get_conversation_history,
	handle_message,
	help_topic,
	is_help_request,
)
from sahbi.chat.dates import parse_date_expression
from sahbi.engine import (
	create_expense,
	create_income,
	create_loan,
	create_purchase,
	create_sale,
	record_outgoing_money,
)
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
		self.assertEqual(parse_account_query("تفاصيل المصاريف")["kind"], "expense")
		self.assertIsNone(parse_account_query("تفاصيل المصاريف")["person_name"])
		self.assertIsNone(parse_account_query("اشتريت خشب بـ5000"))

		frappe.set_user("Administrator")
		create_sale(self.workspace, 400, person=self.person.name)
		hamed = make_person(self.workspace, "محمد حامد")
		create_sale(self.workspace, 150, person=hamed.name)
		supplier = make_person(self.workspace, "احمد المورد")
		create_purchase(self.workspace, 250, person=supplier.name)
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
		self.assertIn("ليك عنده", everyone["reply"])
		self.assertNotIn("ليه عندك", everyone["reply"])
		self.assertNotIn("حسابات الناس في الحساب", everyone["reply"])

		frappe.set_user("Administrator")
		create_purchase(self.workspace, 5500, description="خشب")
		frappe.set_user(self.user)
		with patch("sahbi.chat.service.interpret_message") as mocked:
			who = handle_message("مين ليه فلوس عندي")
			mocked.assert_not_called()
		self.assertEqual(who["status"], "ok")
		self.assertIn("اللي عليك لهم", who["reply"])
		self.assertIn("احمد المورد", who["reply"])
		self.assertIn("250.00", who["reply"])
		self.assertIn("الإجمالي: 250.00", who["reply"])
		self.assertNotIn("5500.00", who["reply"])
		self.assertNotIn("5750.00", who["reply"])
		self.assertNotIn("اللي ليك عندهم", who["reply"])
		self.assertNotIn("تحصيل", who["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			owed = handle_message("مين ليا فلوس عنده")
			mocked.assert_not_called()
		self.assertEqual(owed["status"], "ok")
		self.assertIn("اللي ليك عندهم", owed["reply"])
		self.assertIn("محمد حامد", owed["reply"])
		self.assertIn("150.00", owed["reply"])
		self.assertNotIn("تحصيل", owed["reply"])
		self.assertNotIn("اللي عليك لهم", owed["reply"])

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

	def test_loan_noun_to_person_is_receivable(self):
		parsed = parse_local_operation("سلفه لامونيوس ب 500 جنيه")
		self.assertEqual(parsed["type"], "loan_receivable")
		self.assertEqual(parsed["amount"], "500")
		self.assertEqual(parsed["person_name"], "امونيوس")

		with patch("sahbi.chat.service.interpret_message") as mocked:
			asked = handle_message("سلفه لامونيوس ب 500 جنيه")
			mocked.assert_not_called()
		self.assertEqual(asked["status"], "needs_clarification")
		self.assertIn("امونيوس", asked["reply"])
		self.assertNotIn("حسابات الناس", asked["reply"])

		confirmed = handle_message("ضيفه")
		self.assertEqual(confirmed["status"], "ok")
		self.assertIn("سلفة", confirmed["reply"])
		self.assertIn("500", confirmed["reply"])
		self.assertIn("امونيوس", confirmed["reply"])
		entry = frappe.get_doc("Sahbi Entry", confirmed["linked_entry"])
		self.assertEqual(entry.entry_type, "Loan")
		self.assertEqual(entry.direction, "Receivable")
		self.assertEqual(float(entry.amount), 500)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			people = handle_message("وريني حسابات الناس")
			mocked.assert_not_called()
		self.assertIn("امونيوس", people["reply"])
		self.assertIn("ليك عنده 500", people["reply"])
		self.assertNotIn("ليه عندك", people["reply"])

	def test_choose_loan_number_settles_selected_entry(self):
		frappe.set_user("Administrator")
		person = make_person(self.workspace, "مينا")
		first = create_loan(self.workspace, 500, "Receivable", person=person.name)
		second = create_loan(self.workspace, 500, "Receivable", person=person.name)
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			asked = handle_message("مينا دفع 200")
			mocked.assert_not_called()
		self.assertEqual(asked["status"], "needs_clarification")
		self.assertIn("أكتر من عملية", asked["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			picked = handle_message("1")
			mocked.assert_not_called()
		self.assertEqual(picked["status"], "ok")
		self.assertIn("200", picked["reply"])
		self.assertIn("300", picked["reply"])
		first_doc = frappe.get_doc("Sahbi Entry", first["name"])
		second_doc = frappe.get_doc("Sahbi Entry", second["name"])
		self.assertEqual(float(first_doc.outstanding_amount), 300)
		self.assertEqual(float(second_doc.outstanding_amount), 500)

	def test_people_list_cancels_pending_entry_choice(self):
		frappe.set_user("Administrator")
		person = make_person(self.workspace, "مينا")
		create_loan(self.workspace, 500, "Receivable", person=person.name)
		create_loan(self.workspace, 500, "Receivable", person=person.name)
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			asked = handle_message("مينا دفع 200")
			mocked.assert_not_called()
		self.assertEqual(asked["status"], "needs_clarification")

		with patch("sahbi.chat.service.interpret_message") as mocked:
			people = handle_message("وريني حسابات الناس")
			mocked.assert_not_called()
		self.assertEqual(people["status"], "ok")
		self.assertIn("حسابات الناس", people["reply"])
		self.assertIn("مينا", people["reply"])
		self.assertNotIn("اختار رقم العملية", people["reply"])

	def test_person_dafaa_settles_receivable_loan(self):
		frappe.set_user("Administrator")
		person = make_person(self.workspace, "مينا")
		posted = create_loan(self.workspace, 500, "Receivable", person=person.name)
		loan = frappe.get_doc("Sahbi Entry", posted["name"])
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("مينا دفع 200")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertIn("200", result["reply"])
		self.assertIn("مينا", result["reply"])
		self.assertIn("300", result["reply"])
		loan.reload()
		self.assertEqual(float(loan.outstanding_amount), 300)

	def test_person_saddad_settles_receivable_loan(self):
		frappe.set_user("Administrator")
		person = make_person(self.workspace, "مينا")
		posted = create_loan(self.workspace, 500, "Receivable", person=person.name)
		loan = frappe.get_doc("Sahbi Entry", posted["name"])
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("مينا سدد 200")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertIn("200", result["reply"])
		self.assertIn("مينا", result["reply"])
		self.assertIn("300", result["reply"])
		loan.reload()
		self.assertEqual(float(loan.outstanding_amount), 300)
		self.assertEqual(loan.payment_status, "Partially Paid")

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
			self.assertEqual(asked["status"], "needs_clarification", asked)
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

	def test_pay_after_person_account_settles_not_expense(self):
		frappe.set_user("Administrator")
		person = make_person(self.workspace, "امونيوس")
		first = create_loan(self.workspace, 500, "Receivable", person=person.name)
		second = create_loan(self.workspace, 500, "Receivable", person=person.name)
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			account = handle_message("حساب امونيوس")
			mocked.assert_not_called()
		self.assertIn("امونيوس", account["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			paid = handle_message("دفع 700")
			mocked.assert_not_called()
		self.assertNotIn("مصروف", paid["reply"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Expense"}), 0)
		if paid["status"] == "needs_clarification":
			self.assertIn("أكتر من عملية", paid["reply"])
			picked = handle_message("1")
			self.assertEqual(picked["status"], "ok")
			self.assertNotIn("مصروف", picked["reply"])
		else:
			self.assertEqual(paid["status"], "ok")
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Expense"}), 0)
		self.assertTrue(
			float(frappe.db.get_value("Sahbi Entry", first["name"], "outstanding_amount")) < 500
			or float(frappe.db.get_value("Sahbi Entry", second["name"], "outstanding_amount")) < 500
		)

	def test_cancel_expense_phrases_are_local(self):
		frappe.set_user("Administrator")
		expense = create_expense(self.workspace, 700, description="غلط")
		frappe.set_user(self.user)
		with patch(
			"sahbi.chat.service.interpret_message",
			return_value={"intent": "ordinary_conversation", "operation": {}, "query": {}, "missing_fields": []},
		):
			opened = handle_message("ازيك")
		conv = frappe.get_doc("Sahbi Conversation", opened["conversation"])
		conv.db_set("last_entry", expense["name"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			preview = handle_message("الغي المصروف")
			mocked.assert_not_called()
		self.assertEqual(preview["status"], "needs_confirmation")
		self.assertIn("مصروف", preview["reply"])
		self.assertIn("700", preview["reply"])
		self.assertEqual(frappe.db.get_value("Sahbi Entry", expense["name"], "docstatus"), 1)

		confirmed = handle_message("أيوه")
		self.assertEqual(confirmed["status"], "ok")
		self.assertEqual(frappe.db.get_value("Sahbi Entry", expense["name"], "docstatus"), 2)
		self.assertIn("اتلغت", confirmed["reply"])

		frappe.set_user("Administrator")
		other = create_expense(self.workspace, 700, description="تاني")
		frappe.set_user(self.user)
		with patch("sahbi.chat.service.interpret_message") as mocked:
			again = handle_message("الغاء المصروف 700")
			mocked.assert_not_called()
		self.assertEqual(again["status"], "needs_confirmation")
		self.assertIn("700", again["reply"])
		handle_message("أيوه")
		self.assertEqual(frappe.db.get_value("Sahbi Entry", other["name"], "docstatus"), 2)

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

	def test_expense_details_are_not_a_person(self):
		frappe.set_user("Administrator")
		create_expense(self.workspace, 400, description="مصروف بنزين")
		create_expense(self.workspace, 700, description="أكل")
		create_expense(self.workspace, 200)
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			month = handle_message("مصاريف الشهر")
			mocked.assert_not_called()
		self.assertEqual(month["status"], "ok")
		self.assertIn("1300.00", month["reply"])
		self.assertNotIn("الدخل", month["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			details = handle_message("تفاصيل المصاريف")
			mocked.assert_not_called()
		self.assertEqual(details["status"], "ok")
		self.assertIn("بنزين", details["reply"])
		self.assertIn("أكل", details["reply"])
		self.assertIn("400.00", details["reply"])
		self.assertIn("700.00", details["reply"])
		self.assertIn("200.00", details["reply"])
		self.assertRegex(details["reply"], r"مصروف: 200.00")
		self.assertNotIn("مصروف بنزين", details["reply"])
		self.assertNotIn("مفيش حد اسمه", details["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			gas = handle_message("كام مصروف البنزين")
			mocked.assert_not_called()
		self.assertEqual(gas["status"], "ok")
		self.assertIn("بنزين", gas["reply"])
		self.assertIn("400.00", gas["reply"])
		self.assertNotIn("700.00", gas["reply"])
		self.assertNotIn("أكل", gas["reply"])
		self.assertNotRegex(gas["reply"], r"مصروف: 200.00")

	def test_put_gas_saves_expense_description(self):
		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("حطيت بنزين ب 500")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertTrue(result["linked_entry"])
		entry = frappe.get_doc("Sahbi Entry", result["linked_entry"])
		self.assertEqual(entry.entry_type, "Expense")
		self.assertEqual(float(entry.amount), 500)
		self.assertEqual(entry.description, "بنزين")
		self.assertIn("بنزين", result["reply"])

		for phrase in ("فلوت بنزين ب 80", "اتشريت بنزين ب 90", "جبت بنزين ب 70"):
			with patch("sahbi.chat.service.interpret_message") as mocked:
				saved = handle_message(phrase)
				mocked.assert_not_called()
			self.assertEqual(saved["status"], "ok", phrase)
			doc = frappe.get_doc("Sahbi Entry", saved["linked_entry"])
			self.assertEqual(doc.entry_type, "Expense", phrase)
			self.assertEqual(doc.description, "بنزين", phrase)

	def test_got_meat_saves_expense(self):
		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("جبت لحمه ب 800")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertNotIn("قولّي اللي على بالك", result["reply"])
		entry = frappe.get_doc("Sahbi Entry", result["linked_entry"])
		self.assertEqual(entry.entry_type, "Expense")
		self.assertEqual(float(entry.amount), 800)
		self.assertEqual(entry.description, "لحمه")
		self.assertIn("لحمه", result["reply"])

	def test_month_purchases_show_paid_and_remaining(self):
		self.assertEqual(parse_local_query("مشتريات الشهر")["kind"], "purchase")
		self.assertEqual(parse_local_query("مشتريات الشهر")["date_expression"], "الشهر ده")

		frappe.set_user("Administrator")
		wood = create_purchase(self.workspace, 5000, description="خشب")
		create_purchase(self.workspace, 700, description="غراء")
		record_outgoing_money(self.workspace, 2000, settle_entry=wood["name"])
		frappe.set_user(self.user)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("مشتريات الشهر")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertIn("خشب", result["reply"])
		self.assertIn("غراء", result["reply"])
		self.assertIn("5000.00", result["reply"])
		self.assertIn("مدفوع 2000.00", result["reply"])
		self.assertIn("باقي 3000.00", result["reply"])
		self.assertIn("700.00", result["reply"])
		self.assertIn("الإجمالي: 5700.00", result["reply"])
		self.assertIn("المدفوع: 2000.00", result["reply"])
		self.assertIn("المتبقي: 3700.00", result["reply"])
		self.assertNotIn("الدخل", result["reply"])

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

	def test_how_much_wood_purchase_does_not_post(self):
		frappe.set_user("Administrator")
		create_purchase(self.workspace, 700, description="خشب")
		frappe.set_user(self.user)
		before = frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Purchase"})

		with patch("sahbi.chat.service.interpret_message") as mocked:
			first = handle_message("اشتريت بكام خشب")
			mocked.assert_not_called()
		self.assertEqual(first["status"], "ok")
		self.assertIn("700.00", first["reply"])
		self.assertNotIn("اتسجل", first["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			second = handle_message("اشترينا بكام خشب")
			mocked.assert_not_called()
		self.assertEqual(second["status"], "ok")
		self.assertIn("700.00", second["reply"])
		self.assertNotIn("اتسجل", second["reply"])
		self.assertNotIn("5000", second["reply"])
		self.assertEqual(
			frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Purchase"}),
			before,
		)

	def test_how_much_question_never_posts_from_llm(self):
		frappe.set_user("Administrator")
		create_purchase(self.workspace, 700, description="خشب")
		frappe.set_user(self.user)
		before = frappe.db.count("Sahbi Entry", {"workspace": self.workspace})
		interpretation = _op("financial_operation", type="purchase", amount="5000.00")
		with patch("sahbi.chat.service.interpret_message", return_value=interpretation):
			result = handle_message("بكام الخشب؟")
		self.assertEqual(result["status"], "ok")
		self.assertIn("700.00", result["reply"])
		self.assertNotIn("اتسجل", result["reply"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), before)

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

	def test_help_guide_examples_parse(self):
		missing = []
		for text in _help_example_phrases():
			query = parse_local_query(text)
			operation = parse_local_operation(text)
			if not query and not operation:
				missing.append(text)
		self.assertFalse(missing, missing)
		self.assertEqual(parse_local_query("وريني حساباتي")["kind"], "person_balance")
		self.assertTrue(parse_local_query("وريني حساباتي").get("person_name") in (None, ""))
		self.assertEqual(parse_local_operation("دخل 500 من شغل النهارده")["type"], "income")
		self.assertEqual(parse_local_query("وريني البيوع")["kind"], "sale")
		self.assertEqual(parse_local_query("مبيعات الشهر")["kind"], "sale")
		self.assertEqual(parse_local_query("دخل الشهر")["kind"], "income")
		self.assertEqual(parse_local_query("كام ليا عند محمد")["kind"], "outstanding_receivable")
		self.assertEqual(parse_local_query("كام ليا عند محمد")["person_name"], "محمد")

	def test_help_request_shows_examples(self):
		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("مساعدة")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "conversation")
		self.assertIn("وريني حساباتي", result["reply"])
		self.assertIn("صرفت 200 بنزين", result["reply"])
		self.assertIn("سلفت محمد 300", result["reply"])

	def test_help_guide_examples_run_in_chat(self):
		frappe.set_user("Administrator")
		ahmed = make_person(self.workspace, "أحمد")
		create_expense(self.workspace, 80, description="بنزين")
		create_loan(self.workspace, 300, "Receivable", person=self.person.name)
		create_loan(self.workspace, 200, "Payable", person=ahmed.name)
		frappe.set_user(self.user)
		failed = []
		with patch("sahbi.chat.service.interpret_message") as mocked:
			for text in _help_example_phrases():
				result = handle_message(text)
				if mocked.called:
					failed.append(f"llm:{text}")
					mocked.reset_mock()
					continue
				if result["status"] not in {"ok", "needs_clarification", "needs_confirmation"}:
					failed.append(f"{result['status']}:{text}:{result['reply']}")
				_reset_chat_pending()
		self.assertFalse(failed, failed)
		with patch("sahbi.chat.service.interpret_message") as mocked:
			accounts = handle_message("وريني حساباتي")
			income = handle_message("دخل 500 من شغل النهارده")
			sales = handle_message("وريني البيوع")
			mocked.assert_not_called()
		self.assertEqual(accounts["status"], "ok")
		self.assertNotIn("مفيش حد اسمه", accounts["reply"])
		self.assertEqual(income["status"], "ok")
		self.assertIn("دخل", income["reply"])
		self.assertEqual(sales["status"], "ok")

	def test_how_to_ask_accounts_is_help(self):
		self.assertTrue(is_help_request("لو عايزه اعرف حساباتي اعرفها ازاي"))
		self.assertTrue(is_help_request("مش عارف استخدم التطبيق"))
		self.assertEqual(help_topic("لو عايزه اعرف حساباتي اعرفها ازاي"), "accounts")
		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("لو عايزه اعرف حساباتي اعرفها ازاي")
			mocked.assert_not_called()
		self.assertIn("حساب محمد", result["reply"])
		self.assertIn("مين ليا فلوس عنده", result["reply"])

	def test_how_to_record_topics_return_matching_examples(self):
		cases = {
			"ازاى اسجل مصروف": ("expense", "صرفت 200 بنزين"),
			"ازاي اسجل بيع": ("sale", "بعت كرسي ب 800"),
			"اسجل بيع ازاي": ("sale", "بعت كرسي ب 800"),
			"ازاي اسجل مشتريات": ("purchase", "اشتريت خشب ب 2000"),
			"ازاي اسجل شري": ("purchase", "اشتريت خشب ب 2000"),
			"اسجل ازاي شري": ("purchase", "اشتريت خشب ب 2000"),
			"ازاي اسجل سلفة": ("loan", "سلفت محمد 300"),
			"ازاي اشوف حساباتي": ("accounts", "وريني حساباتي"),
		}
		for text, (topic, example) in cases.items():
			self.assertEqual(help_topic(text), topic, text)
			self.assertTrue(is_help_request(text), text)
			with patch("sahbi.chat.service.interpret_message") as mocked:
				result = handle_message(text)
				mocked.assert_not_called()
			self.assertIn(example, result["reply"], text)
			self.assertNotIn("أهو دليل سريع", result["reply"], text)

	def test_second_unknown_message_nudges_help(self):
		unknown = {
			"intent": "unknown",
			"operation": {},
			"query": {},
			"missing_fields": [],
			"is_ambiguous": False,
		}
		with patch("sahbi.chat.service.interpret_message", return_value=unknown):
			first = handle_message("بلابل كده")
			second = handle_message("همممم مش فاهم")
		self.assertEqual(first["status"], "error")
		self.assertIn("مش واضحة", first["reply"])
		self.assertNotIn("اكتب: مساعدة", first["reply"])
		self.assertIn("مساعدة", second["reply"])

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

	def test_purchase_and_pay_in_same_line(self):
		ops = parse_local_operations("اشتريت من محمد خشب ب 700 ودفعت ليه 200")
		self.assertEqual(len(ops), 2, ops)
		self.assertEqual(ops[0]["type"], "purchase")
		self.assertEqual(ops[0]["amount"], "700")
		self.assertEqual(ops[0]["person_name"], "محمد")
		self.assertEqual(ops[1]["type"], "outgoing_money")
		self.assertEqual(ops[1]["amount"], "200")
		self.assertEqual(ops[1]["person_name"], "محمد")
		word_ops = parse_local_operations("اشتريت خشب بخمسة آلاف ودفعت ألفين")
		self.assertEqual(len(word_ops), 2, word_ops)
		self.assertEqual(word_ops[0]["type"], "purchase")
		self.assertEqual(word_ops[0]["amount"], "5000")
		self.assertEqual(word_ops[1]["type"], "outgoing_money")
		self.assertEqual(word_ops[1]["amount"], "2000")

		with patch("sahbi.chat.service.interpret_message") as mocked:
			result = handle_message("اشتريت من محمد خشب ب 700 ودفعت ليه 200")
			mocked.assert_not_called()
		self.assertEqual(result["status"], "ok")
		self.assertIn("700", result["reply"])
		self.assertIn("200", result["reply"])
		self.assertNotIn("مفيش حد اسمه", result["reply"])
		purchase = frappe.get_all(
			"Sahbi Entry",
			filters={"workspace": self.workspace, "entry_type": "Purchase", "docstatus": 1},
			fields=["name", "amount", "outstanding_amount", "person"],
			limit_page_length=1,
		)
		self.assertTrue(purchase)
		self.assertEqual(float(purchase[0].amount), 700)
		self.assertEqual(float(purchase[0].outstanding_amount), 500)
		self.assertEqual(
			frappe.db.count("Sahbi Payment", {"workspace": self.workspace, "docstatus": 1}),
			1,
		)

	def test_live_facebook_thread_cases(self):
		ops = parse_local_operations("سلف ١٠٠٠ موصلات ٨٥ وداخلي ٥")
		self.assertEqual(len(ops), 3, ops)
		self.assertEqual(ops[0]["type"], "loan_receivable")
		self.assertEqual(ops[0]["amount"], "1000")
		self.assertFalse(ops[0].get("person_name"))
		self.assertEqual(ops[1]["type"], "expense")
		self.assertEqual(ops[1]["amount"], "85")
		self.assertEqual(ops[2]["type"], "expense")
		self.assertEqual(ops[2]["amount"], "5")
		self.assertEqual(parse_local_operation("موصلات ٥")["type"], "expense")
		self.assertEqual(parse_local_operation("موصلات ٥")["amount"], "5")
		self.assertEqual(parse_local_operation("أنا استلفت ١٠٠٠ صح")["type"], "loan_payable")
		self.assertFalse(parse_local_operation("أنا استلفت ١٠٠٠ صح").get("person_name"))
		self.assertEqual(parse_local_query("اعرض الحساب")["kind"], "person_balance")
		self.assertFalse(parse_local_query("اعرض الحساب").get("needs_person"))
		self.assertEqual(parse_local_query("كدة باقي معايا كان")["kind"], "cash_or_bank")
		self.assertEqual(parse_local_query("فاضل كان فلوس معايا")["kind"], "cash_or_bank")
		self.assertEqual(parse_local_query("صرفت كام")["kind"], "expense")
		self.assertTrue(is_help_request("لو عايزه اعرف حساباتي اعرفها ازاي"))

		with patch("sahbi.chat.service.interpret_message") as mocked:
			compound = handle_message("سلف ١٠٠٠ موصلات ٨٥ وداخلي ٥")
			mocked.assert_not_called()
		self.assertEqual(compound["status"], "needs_clarification")
		self.assertIn("85", compound["reply"])
		self.assertIn("5", compound["reply"])
		self.assertIn("لمين", compound["reply"])
		self.assertNotIn("أضيفه", compound["reply"])
		self.assertEqual(
			frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Expense"}),
			2,
		)

		with patch("sahbi.chat.service.interpret_message") as mocked:
			recat = handle_message("لا تبع بند الموصلات برضو")
			mocked.assert_not_called()
		self.assertEqual(recat["status"], "needs_clarification")
		self.assertIn("لمين", recat["reply"])
		self.assertNotIn("أضيف الشخص", recat["reply"])
		self.assertEqual(
			frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "entry_type": "Expense"}),
			2,
		)

		_reset_chat_pending()
		with patch("sahbi.chat.service.interpret_message") as mocked:
			bare = handle_message("موصلات ٥")
			mocked.assert_not_called()
		self.assertEqual(bare["status"], "ok")
		self.assertIn("مصروف", bare["reply"])
		self.assertNotIn("مين اللي دفع", bare["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			borrowed = handle_message("أنا استلفت ١٠٠٠ صح")
			mocked.assert_not_called()
		self.assertEqual(borrowed["status"], "needs_clarification")
		self.assertIn("من مين", borrowed["reply"])
		self.assertNotIn("مساء الفل", borrowed["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			show = handle_message("اعرض الحساب")
			mocked.assert_not_called()
		self.assertEqual(show["status"], "ok")
		self.assertNotIn("مفيش حد اسمه", show["reply"])

		with patch("sahbi.chat.service.interpret_message") as mocked:
			cash = handle_message("كدة باقي معايا كان")
			help_ask = handle_message("لو عايزه اعرف حساباتي اعرفها ازاي")
			spent = handle_message("صرفت كام")
			focus = handle_message("ركز معايا")
			mocked.assert_not_called()
		self.assertEqual(cash["status"], "ok")
		self.assertNotIn("مفيش حد اسمه", cash["reply"])
		self.assertIn("حساباتي", help_ask["reply"])
		self.assertNotIn("مفيش حد اسمه", help_ask["reply"])
		self.assertEqual(spent["status"], "ok")
		self.assertNotIn("مساء الفل", focus["reply"])


def _help_example_phrases():
	topics = (
		"expense",
		"sale",
		"purchase",
		"income",
		"loan",
		"settlement",
		"cancel",
		"accounts",
		"balance",
		"people",
	)
	seen = []
	for text in (help_guide(), *(help_for_topic(topic) for topic in topics)):
		for line in text.splitlines():
			if not line.startswith("• "):
				continue
			example = line[2:].strip()
			if example and example not in seen:
				seen.append(example)
	return seen


def _reset_chat_pending():
	history = get_conversation_history()
	name = history.get("conversation")
	if not name:
		return
	frappe.db.set_value("Sahbi Conversation", name, {"pending_kind": None, "pending_payload": None})
