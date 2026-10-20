# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import inspect
from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from sahbi.chat.service import handle_message
from sahbi.engine import (
	cancel_entry,
	correct_entry,
	create_expense,
	create_income,
	create_loan,
	create_opening_balance,
	create_purchase,
	create_sale,
	get_income_expense_totals,
	get_person_balances,
	record_incoming_money,
	record_outgoing_money,
	record_payment,
	run_financial_query,
)
from sahbi.llm.errors import SahbiLLMInvalidOutput
from sahbi.llm.service import interpret_message
from sahbi.llm.validate import validate_extraction
from sahbi.money import add_money, to_money
from sahbi.tests.helpers import make_person, make_user, make_workspace


def _query(kind, **kwargs):
	return {
		"intent": "financial_query",
		"operation": {},
		"query": {"kind": kind, "search_terms": kwargs.get("search_terms", []), "person_name": kwargs.get("person_name"), "date_expression": kwargs.get("date_expression")},
		"missing_fields": [],
	}


def _op(**operation):
	return {
		"intent": "financial_operation",
		"operation": {
			"type": None,
			"amount": None,
			"person_name": None,
			"description": None,
			"date_expression": None,
			"previous_operation_references": [],
			"loan_direction": None,
			**operation,
		},
		"query": {"kind": None, "search_terms": [], "person_name": None, "date_expression": None},
		"missing_fields": [],
		"is_ambiguous": False,
	}


class TestSahbiAcceptance(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user(f"sahbi.accept.{frappe.generate_hash(length=8)}@example.com")
		self.workspace = make_workspace(self.user).name
		self.person = make_person(self.workspace, "محمد")
		self.other_user = make_user(f"sahbi.accept.iso.{frappe.generate_hash(length=8)}@example.com")
		self.other_workspace = make_workspace(self.other_user).name

	def test_01_users_cannot_access_another_workspace(self):
		own = create_income(self.workspace, 15)
		other = create_income(self.other_workspace, 99)
		frappe.set_user(self.user)
		visible = {row.name for row in frappe.get_list("Sahbi Entry", fields=["name"])}
		self.assertIn(own["name"], visible)
		self.assertNotIn(other["name"], visible)
		self.assertFalse(frappe.get_doc("Sahbi Entry", other["name"]).has_permission("read"))
		with self.assertRaises(frappe.PermissionError):
			create_income(self.other_workspace, 10)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			frappe.get_doc(
				{
					"doctype": "Sahbi Entry",
					"workspace": self.other_workspace,
					"entry_type": "Income",
					"amount": 5,
					"currency": "EGP",
				}
			).insert()
		frappe.set_user("Administrator")

	def test_02_server_side_permissions_and_guest(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			handle_message("ازيك")
		frappe.set_user(self.user)
		ws = frappe.get_doc("Sahbi Workspace", self.workspace)
		ws.user = self.other_user
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			ws.save()
		ws.reload()
		ws.user = self.other_user
		with self.assertRaises(frappe.ValidationError):
			ws.save(ignore_permissions=True)
		frappe.set_user("Administrator")

	def test_03_retries_do_not_duplicate(self):
		first = create_income(self.workspace, 90, idempotency_key="accept-income")
		second = create_income(self.workspace, 90, idempotency_key="accept-income")
		self.assertEqual(first["name"], second["name"])
		self.assertTrue(second["replayed"])
		self.assertEqual(
			frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "idempotency_key": "accept-income"}),
			1,
		)

	def test_04_payments_are_independent_records(self):
		sale = create_sale(self.workspace, 500, person=self.person.name)
		payment = record_payment(
			self.workspace,
			200,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 200}],
		)
		self.assertTrue(frappe.db.exists("Sahbi Payment", payment["name"]))
		self.assertNotEqual(payment["name"], sale["name"])
		self.assertEqual(payment["doctype"], "Sahbi Payment")
		self.assertEqual(len(payment["allocations"]), 1)

	def test_05_allocations_cannot_exceed_limits(self):
		sale = create_sale(self.workspace, 100, person=self.person.name)
		with self.assertRaises(frappe.ValidationError):
			record_payment(
				self.workspace,
				50,
				"Incoming",
				allocations=[{"entry": sale["name"], "amount": 51}],
			)
		record_payment(
			self.workspace,
			60,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 60}],
		)
		with self.assertRaises(frappe.ValidationError):
			record_payment(
				self.workspace,
				50,
				"Incoming",
				allocations=[{"entry": sale["name"], "amount": 50}],
			)

	def test_06_outstanding_balances_are_correct(self):
		create_opening_balance(self.workspace, 1000, "Receivable", person=self.person.name)
		sale = create_sale(self.workspace, 400, person=self.person.name)
		record_payment(
			self.workspace,
			100,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 100}],
		)
		balances = get_person_balances(self.workspace, self.person.name)
		self.assertEqual(to_money(balances["receivable"]), to_money(1300))
		self.assertTrue(balances["includes_carried_forward"])

	def test_07_settlements_are_not_new_income_or_expense(self):
		sale = create_sale(self.workspace, 300, person=self.person.name)
		purchase = create_purchase(self.workspace, 200, person=self.person.name)
		record_incoming_money(self.workspace, 80, person=self.person.name, settle_entry=sale["name"])
		record_outgoing_money(self.workspace, 50, person=self.person.name)
		totals = get_income_expense_totals(self.workspace)
		self.assertEqual(totals["income"], "0.00")
		self.assertEqual(totals["expense"], "0.00")
		self.assertEqual(run_financial_query(self.workspace, kind="collections")["total"], "80.00")
		self.assertEqual(run_financial_query(self.workspace, kind="repayments")["total"], "50.00")
		self.assertEqual(to_money(frappe.get_doc("Sahbi Entry", purchase["name"]).outstanding_amount), to_money(150))

	def test_08_loans_are_not_income_or_expense(self):
		create_loan(self.workspace, 700, "Receivable", person=self.person.name)
		totals = get_income_expense_totals(self.workspace)
		self.assertEqual(totals["income"], "0.00")
		self.assertEqual(totals["expense"], "0.00")
		self.assertEqual(run_financial_query(self.workspace, kind="loan_receivable")["total"], "700.00")

	def test_09_opening_balances_are_not_new_activity(self):
		create_opening_balance(self.workspace, 1500, "Payable", person=self.person.name)
		totals = get_income_expense_totals(self.workspace)
		self.assertEqual(totals["income"], "0.00")
		self.assertEqual(totals["expense"], "0.00")
		self.assertEqual(run_financial_query(self.workspace, kind="opening_balance")["total"], "1500.00")

	def test_10_posted_records_cannot_be_silently_deleted(self):
		entry = create_income(self.workspace, 25)
		doc = frappe.get_doc("Sahbi Entry", entry["name"])
		with self.assertRaises(frappe.ValidationError):
			doc.delete()
		self.assertTrue(frappe.db.exists("Sahbi Entry", entry["name"]))

	def test_11_corrections_require_confirmation(self):
		entry = create_income(self.workspace, 200)
		preview = correct_entry(entry["name"], amount=20, reason="غلط")
		self.assertEqual(preview["status"], "needs_confirmation")
		self.assertEqual(frappe.get_doc("Sahbi Entry", entry["name"]).docstatus, 1)
		self.assertEqual(to_money(frappe.get_doc("Sahbi Entry", entry["name"]).amount), to_money(200))
		done = correct_entry(entry["name"], amount=20, reason="غلط", confirm=True)
		self.assertEqual(done["status"], "corrected")
		self.assertEqual(frappe.get_doc("Sahbi Entry", entry["name"]).docstatus, 2)

	def test_12_cancellations_require_confirmation(self):
		entry = create_expense(self.workspace, 40)
		preview = cancel_entry(entry["name"], reason="غلط")
		self.assertEqual(preview["status"], "needs_confirmation")
		self.assertEqual(frappe.get_doc("Sahbi Entry", entry["name"]).docstatus, 1)
		done = cancel_entry(entry["name"], reason="غلط", confirm=True)
		self.assertEqual(done["status"], "cancelled")
		self.assertEqual(frappe.get_doc("Sahbi Entry", entry["name"]).docstatus, 2)
		self.assertTrue(frappe.db.exists("Sahbi Entry", entry["name"]))

	def test_13_linked_payments_are_handled_on_cancel(self):
		sale = create_sale(self.workspace, 100, person=self.person.name)
		payment = record_payment(
			self.workspace,
			40,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 40}],
		)
		cancel_entry(sale["name"], reason="غلط", confirm=True)
		self.assertEqual(frappe.get_doc("Sahbi Entry", sale["name"]).docstatus, 2)
		self.assertEqual(frappe.get_doc("Sahbi Payment", payment["name"]).docstatus, 2)

	def test_14_llm_output_cannot_bypass_validation(self):
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction({"intent": "financial_query", "sql": "select amount from `tabSahbi Entry`"})
		with self.assertRaises(SahbiLLMInvalidOutput):
			validate_extraction({"intent": "financial_query", "query": {"kind": "income"}, "totals": {"income": 9}})
		source = inspect.getsource(inspect.getmodule(interpret_message))
		self.assertNotIn("sahbi.engine", source)

	def test_15_llm_output_cannot_write_the_database(self):
		before = frappe.db.count("Sahbi Entry", {"workspace": self.workspace})
		with patch(
			"sahbi.llm.service.complete",
			return_value='{"intent":"financial_operation","operation":{"type":"sale","amount":"20000"}}',
		):
			parsed = interpret_message("بعت مطبخ بـ20000")
		self.assertEqual(parsed["operation"]["type"], "sale")
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), before)

	def test_16_invalid_amounts_and_dates_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			to_money("مجانا")
		with self.assertRaises(frappe.ValidationError):
			create_income(self.workspace, 0)
		with self.assertRaises(frappe.ValidationError):
			create_income(self.workspace, -10)
		with self.assertRaises(Exception):
			create_income(self.workspace, 10, transaction_date="not-a-date")
		create_income(self.workspace, 10, transaction_date=getdate("2026-01-15"))
		self.assertEqual(
			str(frappe.get_last_doc("Sahbi Entry", filters={"workspace": self.workspace}).transaction_date),
			"2026-01-15",
		)

	def test_17_money_uses_decimal_not_float(self):
		self.assertIsInstance(to_money("10.10"), Decimal)
		self.assertEqual(add_money("10.10", "10.20"), to_money("20.30"))
		self.assertNotEqual(0.1 + 0.2, 0.3)
		self.assertEqual(add_money("0.10", "0.20"), to_money("0.30"))
		sale = create_sale(self.workspace, "20.30", person=self.person.name)
		self.assertEqual(sale["amount"], "20.30")

	def test_18_failed_operations_do_not_claim_success(self):
		frappe.set_user(self.user)
		with patch("sahbi.chat.service.create_sale", side_effect=Exception("db down")):
			with patch("sahbi.chat.service.interpret_message", return_value=_op(type="sale", amount="20000.00")):
				result = handle_message("بعت مطبخ بـ20000")
		self.assertEqual(result["status"], "error")
		self.assertNotIn("اتسجل", result["reply"])
		self.assertEqual(frappe.db.count("Sahbi Entry", {"workspace": self.workspace}), 0)
		frappe.set_user("Administrator")

	def test_19_search_does_not_mix_unrelated_types(self):
		create_purchase(self.workspace, 5000, description="خشب")
		create_expense(self.workspace, 250, description="نقل الخشب")
		wood = run_financial_query(self.workspace, kind="purchase", search_terms=["خشب"])
		transport = run_financial_query(self.workspace, kind="expense", search_terms=["نقل", "خشب"])
		search = run_financial_query(self.workspace, kind="search", search_terms=["خشب"])
		self.assertEqual(wood["total"], "5000.00")
		self.assertEqual(transport["total"], "250.00")
		self.assertEqual(search["total"], "5000.00")
		self.assertFalse(search["mixed_types"])

	def test_20_cash_and_bank_are_not_fabricated(self):
		create_income(self.workspace, 999)
		cash = run_financial_query(self.workspace, kind="cash_or_bank")
		profit = run_financial_query(self.workspace, kind="profit")
		self.assertEqual(cash["status"], "limitation")
		self.assertIsNone(cash["total"])
		self.assertFalse(cash["claims_cash"] and cash["status"] == "ok")
		self.assertEqual(profit["status"], "limitation")
		self.assertIsNone(profit["total"])
		frappe.set_user(self.user)
		with patch("sahbi.chat.service.interpret_message", return_value=_query("cash_or_bank")):
			result = handle_message("معايا كام في البنك؟")
		self.assertNotRegex(result["reply"], r"\d+\.\d{2}")
		frappe.set_user("Administrator")
