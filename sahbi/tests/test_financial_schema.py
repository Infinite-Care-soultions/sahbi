# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from sahbi.money import add_money, to_money
from sahbi.tests.helpers import (
	assert_rejected,
	make_allocation,
	make_entry,
	make_payment,
	make_person,
	make_user,
	make_workspace,
)


class TestSahbiFinancialSchema(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = make_user(f"sahbi.owner.{frappe.generate_hash(length=8)}@example.com")
		self.workspace = make_workspace(self.user).name

	def test_workspace_is_unique_per_user(self):
		assert_rejected(
			self,
			lambda: frappe.get_doc(
				{
					"doctype": "Sahbi Workspace",
					"user": self.user,
					"title": "Second",
					"is_default": 0,
				}
			).insert(),
		)

	def test_person_has_no_business_role_and_is_optional_on_entry(self):
		person = make_person(self.workspace, "محمد")
		self.assertFalse(person.meta.has_field("role"))
		self.assertFalse(person.meta.has_field("business_role"))
		entry = make_entry(self.workspace, "Income", 50, submit=True)
		self.assertFalse(entry.person)
		with_person = make_entry(self.workspace, "Expense", 20, person=person.name, submit=True)
		self.assertEqual(with_person.person, person.name)

	def test_person_name_unique_per_workspace_only(self):
		other_user = make_user(f"sahbi.other.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		make_person(self.workspace, "محمد")
		make_person(other_workspace, "محمد")
		assert_rejected(self, lambda: make_person(self.workspace, "  محمد "))

	def test_income_is_not_opening_balance_and_not_allocatable(self):
		income = make_entry(self.workspace, "Income", 200, submit=True)
		self.assertEqual(income.entry_type, "Income")
		self.assertEqual(income.payment_status, "Not Applicable")
		self.assertEqual(to_money(income.outstanding_amount), to_money(0))
		payment = make_payment(self.workspace, 200, "Incoming", submit=True)
		assert_rejected(self, lambda: make_allocation(payment, income, 200))

	def test_opening_balance_is_separate_classification(self):
		opening = make_entry(
			self.workspace,
			"Opening Balance",
			1500,
			direction="Payable",
			submit=True,
		)
		self.assertEqual(opening.entry_type, "Opening Balance")
		self.assertNotIn(opening.entry_type, {"Income", "Expense", "Sale", "Purchase", "Loan"})
		self.assertEqual(opening.payment_status, "Unpaid")
		self.assertEqual(to_money(opening.outstanding_amount), to_money(1500))

	def test_loan_requires_direction(self):
		assert_rejected(self, lambda: make_entry(self.workspace, "Loan", 2000))

		receivable = make_entry(self.workspace, "Loan", 2000, direction="Receivable", submit=True)
		self.assertEqual(receivable.direction, "Receivable")

	def test_sale_and_purchase_set_direction(self):
		sale = make_entry(self.workspace, "Sale", 5000, submit=True)
		purchase = make_entry(self.workspace, "Purchase", 800, submit=True)
		self.assertEqual(sale.direction, "Receivable")
		self.assertEqual(purchase.direction, "Payable")

	def test_idempotency_prevents_duplicate_entry_and_payment(self):
		make_entry(self.workspace, "Income", 90, idempotency_key="msg-1", submit=True)
		assert_rejected(
			self,
			lambda: make_entry(self.workspace, "Income", 90, idempotency_key="msg-1"),
		)
		make_payment(self.workspace, 40, "Outgoing", idempotency_key="pay-1", submit=True)
		assert_rejected(
			self,
			lambda: make_payment(self.workspace, 40, "Outgoing", idempotency_key="pay-1"),
		)

	def test_allocation_updates_outstanding_with_decimal_amounts(self):
		sale = make_entry(self.workspace, "Sale", "20.30", submit=True)
		payment = make_payment(self.workspace, "20.30", "Incoming", submit=True)
		make_allocation(payment, sale, "10.10", submit=True)
		make_allocation(payment, sale, "10.20", submit=True)

		sale.reload()
		payment.reload()
		self.assertEqual(to_money(sale.paid_amount), to_money("20.30"))
		self.assertEqual(to_money(sale.outstanding_amount), to_money(0))
		self.assertEqual(sale.payment_status, "Fully Paid")
		self.assertEqual(to_money(payment.unallocated_amount), to_money(0))
		self.assertEqual(add_money("10.10", "10.20"), to_money("20.30"))

	def test_allocation_cannot_exceed_payment_or_entry(self):
		sale = make_entry(self.workspace, "Sale", 100, submit=True)
		payment = make_payment(self.workspace, 60, "Incoming", submit=True)
		make_allocation(payment, sale, 60, submit=True)
		assert_rejected(self, lambda: make_allocation(payment, sale, 1, submit=True))

		second_payment = make_payment(self.workspace, 50, "Incoming", submit=True)
		assert_rejected(self, lambda: make_allocation(second_payment, sale, 50, submit=True))

	def test_allocation_rejects_direction_mismatch(self):
		sale = make_entry(self.workspace, "Sale", 100, submit=True)
		outgoing = make_payment(self.workspace, 100, "Outgoing", submit=True)
		assert_rejected(self, lambda: make_allocation(outgoing, sale, 100))

	def test_cross_workspace_allocation_is_rejected(self):
		other_user = make_user(f"sahbi.ws.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		sale = make_entry(self.workspace, "Sale", 100, submit=True)
		payment = make_payment(other_workspace, 100, "Incoming", submit=True)
		assert_rejected(self, lambda: make_allocation(payment, sale, 100))

	def test_person_must_belong_to_entry_workspace(self):
		other_user = make_user(f"sahbi.person.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		person = make_person(other_workspace, "أحمد")
		assert_rejected(self, lambda: make_entry(self.workspace, "Income", 10, person=person.name))

	def test_submitted_records_cannot_be_deleted(self):
		entry = make_entry(self.workspace, "Expense", 25, submit=True)
		assert_rejected(self, lambda: entry.delete())
		entry.reload()
		entry.cancel()
		self.assertTrue(frappe.db.exists("Sahbi Entry", entry.name))
		assert_rejected(self, lambda: frappe.delete_doc("Sahbi Entry", entry.name))

	def test_entry_cancel_blocked_while_allocation_exists(self):
		sale = make_entry(self.workspace, "Sale", 100, submit=True)
		payment = make_payment(self.workspace, 40, "Incoming", submit=True)
		allocation = make_allocation(payment, sale, 40, submit=True)
		assert_rejected(self, sale.cancel)
		allocation.cancel()
		sale.reload()
		sale.cancel()
		sale.reload()
		self.assertEqual(sale.docstatus, 2)
		self.assertTrue(frappe.db.exists("Sahbi Entry", sale.name))

	def test_payment_cancel_cancels_allocations_and_restores_outstanding(self):
		sale = make_entry(self.workspace, "Sale", 100, submit=True)
		payment = make_payment(self.workspace, 40, "Incoming", submit=True)
		allocation = make_allocation(payment, sale, 40, submit=True)
		payment.cancel()
		allocation.reload()
		sale.reload()
		self.assertEqual(allocation.docstatus, 2)
		self.assertEqual(to_money(sale.outstanding_amount), to_money(100))
		self.assertEqual(sale.payment_status, "Unpaid")
		self.assertTrue(frappe.db.exists("Sahbi Payment Allocation", allocation.name))

	def test_audit_reference_fields_exist(self):
		original = make_entry(self.workspace, "Income", 10, submit=True)
		replacement = make_entry(self.workspace, "Income", 12, replaces=original.name, submit=True)
		self.assertEqual(replacement.replaces, original.name)
		self.assertTrue(replacement.meta.has_field("reversal_of"))
		self.assertTrue(replacement.meta.has_field("replaced_by"))
		self.assertTrue(replacement.meta.has_field("cancellation_reason"))

	def test_users_cannot_read_another_workspace(self):
		other_user = make_user(f"sahbi.iso.{frappe.generate_hash(length=8)}@example.com")
		other_workspace = make_workspace(other_user).name
		own_entry = make_entry(self.workspace, "Income", 15, submit=True)
		other_entry = make_entry(other_workspace, "Income", 99, submit=True)

		frappe.set_user(self.user)
		visible = {row.name for row in frappe.get_list("Sahbi Entry", fields=["name"])}
		self.assertIn(own_entry.name, visible)
		self.assertNotIn(other_entry.name, visible)
		other_doc = frappe.get_doc("Sahbi Entry", other_entry.name)
		self.assertFalse(other_doc.has_permission("read"))
		frappe.set_user("Administrator")
