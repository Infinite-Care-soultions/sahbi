# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_first_day, get_last_day, nowdate

from sahbi.engine import (
	cancel_entry,
	create_expense,
	create_income,
	create_loan,
	create_opening_balance,
	create_purchase,
	create_sale,
	record_incoming_money,
	record_outgoing_money,
	record_payment,
	run_financial_query,
)
from sahbi.engine.reports import description_matches
from sahbi.money import to_money
from sahbi.tests.helpers import make_person, make_user, make_workspace


class TestSahbiFinancialReports(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user(f"sahbi.reports.{frappe.generate_hash(length=8)}@example.com")
		self.workspace = make_workspace(self.user).name
		self.person = make_person(self.workspace, "محمد")
		self.today = nowdate()
		self.last_month = str(get_first_day(add_days(get_first_day(self.today), -1)))
		self.last_month_end = str(get_last_day(self.last_month))

	def _query(self, kind, **kwargs):
		return run_financial_query(self.workspace, kind=kind, **kwargs)

	def test_period_filters_use_transaction_dates(self):
		create_expense(self.workspace, 80, description="بنزين", transaction_date=self.last_month)
		create_expense(self.workspace, 30, description="بنزين", transaction_date=self.today)
		create_income(self.workspace, 200, transaction_date=self.last_month)

		this_month = self._query("expense", from_date=self.today, to_date=self.today)
		last_month = self._query("income", from_date=self.last_month, to_date=self.last_month_end)

		self.assertEqual(this_month["total"], "30.00")
		self.assertEqual(last_month["total"], "200.00")
		self.assertEqual(this_month["from_date"], self.today)

	def test_wood_purchase_excludes_wood_transport(self):
		create_purchase(self.workspace, 5000, description="خشب")
		create_expense(self.workspace, 250, description="نقل الخشب")

		wood = self._query("purchase", search_terms=["خشب"])
		transport = self._query("expense", search_terms=["نقل", "خشب"])
		search = self._query("search", search_terms=["خشب"])

		self.assertEqual(wood["total"], "5000.00")
		self.assertEqual(wood["count"], 1)
		self.assertEqual(transport["total"], "250.00")
		self.assertEqual(transport["count"], 1)
		self.assertEqual(search["total"], "5000.00")
		self.assertNotIn("Expense", search["by_type"])

	def test_description_matching_keeps_semantic_tokens(self):
		self.assertTrue(description_matches("خشب زان", ["خشب"]))
		self.assertFalse(description_matches("نقل الخشب", ["خشب"]))
		self.assertTrue(description_matches("نقل الخشب", ["نقل", "خشب"]))

	def test_settlements_are_not_income_or_expense(self):
		sale = create_sale(self.workspace, 1500, person=self.person.name)
		purchase = create_purchase(self.workspace, 700, person=self.person.name)
		record_incoming_money(self.workspace, 400, person=self.person.name, settle_entry=sale["name"])
		record_outgoing_money(self.workspace, 200, person=self.person.name)

		income = self._query("income")
		expense = self._query("expense")
		collections = self._query("collections", person=self.person.name)
		repayments = self._query("repayments", person=self.person.name)
		sales = self._query("sale")
		purchases = self._query("purchase")

		self.assertEqual(income["total"], "0.00")
		self.assertEqual(expense["total"], "0.00")
		self.assertEqual(collections["total"], "400.00")
		self.assertEqual(repayments["total"], "200.00")
		self.assertEqual(sales["total"], "1500.00")
		self.assertEqual(purchases["total"], "700.00")
		self.assertEqual(frappe.get_doc("Sahbi Entry", sale["name"]).payment_status, "Partially Paid")
		self.assertEqual(to_money(frappe.get_doc("Sahbi Entry", purchase["name"]).outstanding_amount), to_money(500))

	def test_cancellations_leave_totals(self):
		expense = create_expense(self.workspace, 90, description="انتقال")
		sale = create_sale(self.workspace, 300, person=self.person.name)
		payment = record_payment(
			self.workspace,
			100,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 100}],
		)
		cancel_entry(expense["name"], reason="غلط", confirm=True)
		cancel_entry(sale["name"], reason="غلط", confirm=True)

		self.assertEqual(self._query("expense")["total"], "0.00")
		self.assertEqual(self._query("sale")["total"], "0.00")
		self.assertEqual(self._query("collections")["total"], "0.00")
		self.assertEqual(frappe.get_doc("Sahbi Entry", expense["name"]).docstatus, 2)
		self.assertEqual(frappe.get_doc("Sahbi Payment", payment["name"]).docstatus, 2)

	def test_outstanding_includes_opening_and_unpaid(self):
		create_opening_balance(self.workspace, 2000, "Receivable", person=self.person.name)
		create_sale(self.workspace, 500, person=self.person.name, transaction_date=self.last_month)
		create_income(self.workspace, 80, transaction_date=self.today)

		result = self._query("outstanding_receivable", person=self.person.name)
		self.assertEqual(result["total"], "2500.00")
		self.assertTrue(result["includes_carried_forward"])
		self.assertGreaterEqual(result["count"], 2)

	def test_person_statement_lists_sales_purchases_and_payments(self):
		sale = create_sale(self.workspace, 400, person=self.person.name)
		create_purchase(self.workspace, 80, person=self.person.name)
		record_payment(
			self.workspace,
			100,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 100}],
		)
		result = self._query("person_balance", person=self.person.name, person_name="محمد")
		kinds = {(row.get("kind"), row.get("entry_type") or row.get("payment_kind")) for row in result["lines"]}
		self.assertIn(("entry", "Sale"), kinds)
		self.assertIn(("entry", "Purchase"), kinds)
		self.assertIn(("payment", "Incoming"), kinds)
		self.assertEqual(result["receivable"], "300.00")
		self.assertEqual(result["payable"], "80.00")

	def test_person_payable_is_separate_from_receivable(self):
		create_opening_balance(self.workspace, 1500, "Payable", person=self.person.name)
		create_loan(self.workspace, 400, "Receivable", person=self.person.name)
		owed = self._query("outstanding_payable", person=self.person.name)
		due = self._query("outstanding_receivable", person=self.person.name)
		both = self._query("person_balance", person=self.person.name)
		self.assertEqual(owed["total"], "1500.00")
		self.assertEqual(due["total"], "400.00")
		self.assertEqual(both["payable"], "1500.00")
		self.assertEqual(both["receivable"], "400.00")

	def test_worker_loans_are_not_expenses(self):
		create_loan(self.workspace, 1000, "Receivable", person=self.person.name, description="سلفة عامل")
		create_expense(self.workspace, 50, description="سلفة غلط")
		loans = self._query("loan_receivable")
		expenses = self._query("expense")
		self.assertEqual(loans["total"], "1000.00")
		self.assertEqual(expenses["total"], "50.00")

	def test_period_report_keeps_types_apart(self):
		create_income(self.workspace, 100)
		create_expense(self.workspace, 20)
		sale = create_sale(self.workspace, 300, person=self.person.name)
		create_purchase(self.workspace, 40, person=self.person.name)
		create_loan(self.workspace, 70, "Receivable", person=self.person.name)
		create_opening_balance(self.workspace, 15, "Payable", person=self.person.name)
		record_payment(
			self.workspace,
			50,
			"Incoming",
			person=self.person.name,
			allocations=[{"entry": sale["name"], "amount": 50}],
		)

		report = self._query("period_report")
		self.assertEqual(report["income"], "100.00")
		self.assertEqual(report["expense"], "20.00")
		self.assertEqual(report["sales"], "300.00")
		self.assertEqual(report["purchases"], "40.00")
		self.assertEqual(report["loan_receivable"], "70.00")
		self.assertEqual(report["opening_balances"], "15.00")
		self.assertEqual(report["collections"], "50.00")
		self.assertFalse(report["claims_profit"])
		self.assertFalse(report["claims_cash"])

	def test_cash_bank_and_profit_are_limitations(self):
		create_income(self.workspace, 999)
		cash = self._query("cash_or_bank")
		profit = self._query("profit")
		cash_terms = self._query("search", search_terms=["كاش"])
		self.assertEqual(cash["status"], "limitation")
		self.assertEqual(cash["limitation"], "cash_or_bank")
		self.assertIsNone(cash["total"])
		self.assertEqual(profit["limitation"], "profit")
		self.assertEqual(cash_terms["limitation"], "cash_or_bank")

	def test_empty_search_is_a_limitation(self):
		result = self._query("search")
		self.assertEqual(result["status"], "limitation")
		self.assertEqual(result["limitation"], "need_search_terms")

	def test_other_workspace_is_hidden(self):
		other_user = make_user(f"sahbi.reports.iso.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		create_income(other_workspace, 99)
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			run_financial_query(other_workspace, kind="income")
		own = run_financial_query(self.workspace, kind="income")
		self.assertEqual(own["total"], "0.00")
		frappe.set_user("Administrator")
