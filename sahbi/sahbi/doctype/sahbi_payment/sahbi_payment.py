# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from sahbi.money import ZERO, money_to_db, to_money
from sahbi.workspace import get_user_workspace


class SahbiPayment(Document):
	def before_insert(self):
		if not self.workspace and frappe.session.user != "Guest":
			self.workspace = get_user_workspace()
		if not self.payment_date:
			self.payment_date = nowdate()

	def validate(self):
		if not self.idempotency_key:
			self.idempotency_key = None
		if self.idempotency_key:
			self.idempotency_key = self.idempotency_key.strip() or None

		amount = to_money(self.amount)
		if amount <= ZERO:
			frappe.throw(_("Amount must be greater than zero"))
		self.amount = money_to_db(amount)

		if not self.payment_date:
			self.payment_date = nowdate()
		self.payment_date = getdate(self.payment_date)

		if self.payment_kind not in {"Incoming", "Outgoing"}:
			frappe.throw(_("Payment kind must be Incoming or Outgoing"))

		if self.person:
			person_workspace = frappe.db.get_value("Sahbi Person", self.person, "workspace")
			if person_workspace != self.workspace:
				frappe.throw(_("Person must belong to the same workspace"))

	def before_submit(self):
		self.allocated_amount = money_to_db(ZERO)
		self.unallocated_amount = money_to_db(self.amount)

	def on_cancel(self):
		allocations = frappe.get_all(
			"Sahbi Payment Allocation",
			filters={"payment": self.name, "docstatus": 1},
			pluck="name",
		)
		for name in allocations:
			frappe.get_doc("Sahbi Payment Allocation", name).cancel()

	def on_trash(self):
		if self.docstatus != 0:
			frappe.throw(_("Posted financial records cannot be deleted"))


def on_doctype_update():
	frappe.db.add_unique(
		"Sahbi Payment",
		["workspace", "idempotency_key"],
		constraint_name="unique_sahbi_payment_idempotency",
	)
