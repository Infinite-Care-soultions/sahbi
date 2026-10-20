# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from sahbi.engine import (
	AmbiguousSettlement,
	cancel_entry,
	correct_entry,
	create_expense,
	create_income,
	create_loan,
	create_opening_balance,
	create_purchase,
	create_sale,
	get_income_expense_totals,
	get_period_report,
	get_person_balances,
	record_incoming_money,
	record_outgoing_money,
	record_payment,
)
from sahbi.money import to_money
from sahbi.tests.helpers import make_person, make_user, make_workspace


class TestSahbiFinancialEngine(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user(f"sahbi.engine.{frappe.generate_hash(length=8)}@example.com")
		self.workspace = make_workspace(self.user).name
		self.person = make_person(self.workspace, "محمد")

	def test_unpaid_sale(self):
		sale = create_sale(self.workspace, 5000, person=self.person.name)
		self.assertEqual(sale["payment_status"], "Unpaid")
		self.assertEqual(to_money(sale["outstanding_amount"]), to_money(5000))
		self.assertEqual(to_money(sale["paid_amount"]), to_money(0))

	def test_fully_paid_sale(self):
		sale = create_sale(self.workspace, 5000, person=self.person.name)
		payment = record_payment(
			self.workspace,
			5000,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 5000}],
		)
		self.assertEqual(payment["entries"][0]["payment_status"], "Fully Paid")
		self.assertEqual(to_money(payment["entries"][0]["outstanding_amount"]), to_money(0))

	def test_partial_payment(self):
		sale = create_sale(self.workspace, 5000, person=self.person.name)
		record_payment(
			self.workspace,
			2000,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 2000}],
		)
		balances = get_person_balances(self.workspace, self.person.name)
		self.assertEqual(to_money(balances["receivable"]), to_money(3000))
		sale_doc = frappe.get_doc("Sahbi Entry", sale["name"])
		self.assertEqual(sale_doc.payment_status, "Partially Paid")

	def test_multiple_payments_against_one_sale(self):
		sale = create_sale(self.workspace, 1000, person=self.person.name)
		record_payment(
			self.workspace,
			400,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 400}],
		)
		record_payment(
			self.workspace,
			600,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 600}],
		)
		sale_doc = frappe.get_doc("Sahbi Entry", sale["name"])
		self.assertEqual(sale_doc.payment_status, "Fully Paid")
		self.assertEqual(to_money(sale_doc.paid_amount), to_money(1000))

	def test_one_payment_allocated_across_multiple_sales(self):
		first = create_sale(self.workspace, 300, person=self.person.name)
		second = create_sale(self.workspace, 200, person=self.person.name)
		payment = record_payment(
			self.workspace,
			500,
			"Incoming",
			person=self.person.name,
			allocations=[
				{"entry": first["name"], "amount": 300},
				{"entry": second["name"], "amount": 200},
			],
		)
		self.assertEqual(len(payment["allocations"]), 2)
		self.assertEqual(to_money(payment["unallocated_amount"]), to_money(0))
		self.assertEqual(frappe.get_doc("Sahbi Entry", first["name"]).payment_status, "Fully Paid")
		self.assertEqual(frappe.get_doc("Sahbi Entry", second["name"]).payment_status, "Fully Paid")

	def test_purchase_with_installments(self):
		purchase = create_purchase(self.workspace, 900, person=self.person.name)
		record_payment(
			self.workspace,
			300,
			"Outgoing",
			allocations=[{"entry": purchase["name"], "amount": 300}],
		)
		record_payment(
			self.workspace,
			300,
			"Outgoing",
			allocations=[{"entry": purchase["name"], "amount": 300}],
		)
		purchase_doc = frappe.get_doc("Sahbi Entry", purchase["name"])
		self.assertEqual(purchase_doc.payment_status, "Partially Paid")
		self.assertEqual(to_money(purchase_doc.outstanding_amount), to_money(300))

	def test_loan_issued_and_partially_repaid(self):
		loan = create_loan(self.workspace, 2000, "Receivable", person=self.person.name)
		result = record_incoming_money(
			self.workspace,
			800,
			person=self.person.name,
			settle_entry=loan["name"],
		)
		self.assertTrue(result["settled"])
		self.assertIsNone(result["income"])
		loan_doc = frappe.get_doc("Sahbi Entry", loan["name"])
		self.assertEqual(to_money(loan_doc.outstanding_amount), to_money(1200))
		self.assertEqual(get_income_expense_totals(self.workspace)["income"], "0.00")

	def test_incoming_money_without_identifiable_prior_operation(self):
		result = record_incoming_money(self.workspace, 2000, person=self.person.name)
		self.assertEqual(result["classification"], "income")
		self.assertEqual(result["income"]["entry_type"], "Income")
		self.assertFalse(result["settled"])

	def test_incoming_money_settling_existing_sale(self):
		sale = create_sale(self.workspace, 1500, person=self.person.name)
		result = record_incoming_money(self.workspace, 1500, person=self.person.name)
		self.assertEqual(result["classification"], "settlement")
		self.assertTrue(result["settled"])
		self.assertIsNone(result["income"])
		self.assertEqual(frappe.get_doc("Sahbi Entry", sale["name"]).payment_status, "Fully Paid")
		self.assertEqual(get_income_expense_totals(self.workspace)["income"], "0.00")

	def test_outgoing_money_without_identifiable_prior_obligation(self):
		result = record_outgoing_money(self.workspace, 1000, person=self.person.name)
		self.assertEqual(result["classification"], "expense")
		self.assertEqual(result["expense"]["entry_type"], "Expense")

	def test_outgoing_money_settling_existing_purchase(self):
		purchase = create_purchase(self.workspace, 700, person=self.person.name)
		result = record_outgoing_money(self.workspace, 700, person=self.person.name)
		self.assertTrue(result["settled"])
		self.assertIsNone(result["expense"])
		self.assertEqual(frappe.get_doc("Sahbi Entry", purchase["name"]).payment_status, "Fully Paid")
		self.assertEqual(get_income_expense_totals(self.workspace)["expense"], "0.00")

	def test_optional_person_and_description(self):
		income = create_income(self.workspace, 50)
		expense = create_expense(self.workspace, 20, description="نقل")
		self.assertFalse(income["person"])
		self.assertFalse(income["description"])
		self.assertEqual(expense["description"], "نقل")
		self.assertFalse(expense["person"])

	def test_opening_balances(self):
		opening = create_opening_balance(
			self.workspace,
			1500,
			"Payable",
			person=self.person.name,
		)
		self.assertEqual(opening["entry_type"], "Opening Balance")
		self.assertNotEqual(opening["entry_type"], "Expense")
		totals = get_income_expense_totals(self.workspace)
		self.assertEqual(totals["income"], "0.00")
		self.assertEqual(totals["expense"], "0.00")
		balances = get_person_balances(self.workspace, self.person.name)
		self.assertEqual(to_money(balances["payable"]), to_money(1500))

	def test_cancelled_transactions_and_linked_payments(self):
		sale = create_sale(self.workspace, 400, person=self.person.name)
		payment = record_payment(
			self.workspace,
			400,
			"Incoming",
			allocations=[{"entry": sale["name"], "amount": 400}],
		)
		preview = cancel_entry(sale["name"], reason="entered by mistake")
		self.assertEqual(preview["status"], "needs_confirmation")
		self.assertEqual(frappe.get_doc("Sahbi Entry", sale["name"]).docstatus, 1)

		result = cancel_entry(sale["name"], reason="entered by mistake", confirm=True)
		self.assertEqual(result["status"], "cancelled")
		self.assertEqual(frappe.get_doc("Sahbi Entry", sale["name"]).docstatus, 2)
		self.assertEqual(frappe.get_doc("Sahbi Payment", payment["name"]).docstatus, 2)
		self.assertTrue(frappe.db.exists("Sahbi Entry", sale["name"]))
		self.assertTrue(frappe.db.exists("Sahbi Payment", payment["name"]))

		replacement_sale = create_sale(self.workspace, 450, person=self.person.name)
		correction_preview = correct_entry(replacement_sale["name"], amount=500, reason="wrong amount")
		self.assertEqual(correction_preview["status"], "needs_confirmation")
		self.assertEqual(frappe.get_doc("Sahbi Entry", replacement_sale["name"]).docstatus, 1)

		corrected = correct_entry(
			replacement_sale["name"],
			amount=500,
			reason="wrong amount",
			confirm=True,
		)
		self.assertEqual(corrected["status"], "corrected")
		self.assertEqual(to_money(corrected["replacement"]["amount"]), to_money(500))
		self.assertEqual(frappe.get_doc("Sahbi Entry", replacement_sale["name"]).docstatus, 2)
		self.assertEqual(
			frappe.get_doc("Sahbi Entry", replacement_sale["name"]).replaced_by,
			corrected["replacement"]["name"],
		)

	def test_repeated_technical_requests(self):
		first = create_income(self.workspace, 90, idempotency_key="income-1")
		second = create_income(self.workspace, 90, idempotency_key="income-1")
		self.assertEqual(first["name"], second["name"])
		self.assertTrue(second["replayed"])
		self.assertEqual(
			frappe.db.count("Sahbi Entry", {"workspace": self.workspace, "idempotency_key": "income-1"}),
			1,
		)

		sale = create_sale(self.workspace, 80, person=self.person.name, idempotency_key="sale-1")
		pay1 = record_payment(
			self.workspace,
			80,
			"Incoming",
			idempotency_key="pay-1",
			allocations=[{"entry": sale["name"], "amount": 80}],
		)
		pay2 = record_payment(
			self.workspace,
			80,
			"Incoming",
			idempotency_key="pay-1",
			allocations=[{"entry": sale["name"], "amount": 80}],
		)
		self.assertEqual(pay1["name"], pay2["name"])
		self.assertTrue(pay2["replayed"])

	def test_permission_boundaries_between_users(self):
		other_user = make_user(f"sahbi.engine.iso.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		create_income(other_workspace, 99)

		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			create_income(other_workspace, 10)
		with self.assertRaises(frappe.PermissionError):
			get_period_report(other_workspace)

		own = create_income(self.workspace, 15)
		self.assertEqual(own["workspace"], self.workspace)
		frappe.set_user("Administrator")

	def test_date_range_reports(self):
		today = nowdate()
		earlier = add_days(today, -10)
		create_income(self.workspace, 100, transaction_date=earlier)
		create_expense(self.workspace, 40, transaction_date=today)
		create_sale(self.workspace, 250, person=self.person.name, transaction_date=today)

		old = get_income_expense_totals(self.workspace, from_date=earlier, to_date=earlier)
		self.assertEqual(old["income"], "100.00")
		self.assertEqual(old["expense"], "0.00")

		recent = get_period_report(self.workspace, from_date=today, to_date=today)
		self.assertEqual(recent["income"], "0.00")
		self.assertEqual(recent["expense"], "40.00")
		self.assertEqual(recent["sales"], "250.00")
		self.assertEqual(recent["opening_balances"], "0.00")

	def test_ambiguous_incoming_requires_explicit_choice(self):
		create_sale(self.workspace, 100, person=self.person.name)
		create_loan(self.workspace, 100, "Receivable", person=self.person.name)
		with self.assertRaises(AmbiguousSettlement):
			record_incoming_money(self.workspace, 100, person=self.person.name)
