# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sahbi.ledger import assert_allocation_fits, refresh_entry_balances, refresh_payment_balances
from sahbi.money import money_to_db, to_money
from sahbi.workspace import get_user_workspace


class SahbiPaymentAllocation(Document):
	def before_insert(self):
		if not self.workspace and frappe.session.user != "Guest":
			self.workspace = get_user_workspace()

	def validate(self):
		if not self.payment or not self.entry:
			frappe.throw(_("Payment and entry are required"))

		payment = frappe.get_doc("Sahbi Payment", self.payment)
		entry = frappe.get_doc("Sahbi Entry", self.entry)
		self.workspace = payment.workspace
		self.currency = payment.currency
		self.allocated_amount = money_to_db(to_money(self.allocated_amount))
		assert_allocation_fits(
			payment,
			entry,
			self.allocated_amount,
			ignore_allocation=self.name if not self.is_new() else None,
		)

	def on_submit(self):
		refresh_entry_balances(self.entry)
		refresh_payment_balances(self.payment)

	def on_cancel(self):
		refresh_entry_balances(self.entry)
		refresh_payment_balances(self.payment)

	def on_trash(self):
		if self.docstatus != 0:
			frappe.throw(_("Posted financial records cannot be deleted"))
