# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from sahbi.ledger import (
	CASH_TYPES,
	ENTRY_TYPES,
	PAYMENT_NOT_APPLICABLE,
	PAYMENT_UNPAID,
)
from sahbi.money import ZERO, money_to_db, to_money
from sahbi.workspace import get_user_workspace


class SahbiEntry(Document):
	def before_insert(self):
		if not self.workspace and frappe.session.user != "Guest":
			self.workspace = get_user_workspace()
		if not self.transaction_date:
			self.transaction_date = nowdate()

	def validate(self):
		self._normalize_optional_keys()
		self._validate_type_and_direction()
		self._validate_amount()
		self._validate_person()
		self._validate_audit_links()

	def before_submit(self):
		if self.entry_type in CASH_TYPES:
			self.payment_status = PAYMENT_NOT_APPLICABLE
			self.paid_amount = money_to_db(ZERO)
			self.outstanding_amount = money_to_db(ZERO)
		else:
			self.payment_status = PAYMENT_UNPAID
			self.paid_amount = money_to_db(ZERO)
			self.outstanding_amount = money_to_db(self.amount)

	def before_cancel(self):
		if frappe.db.exists("Sahbi Payment Allocation", {"entry": self.name, "docstatus": 1}):
			frappe.throw(_("Cancel linked payment allocations before cancelling this entry"))

	def on_trash(self):
		if self.docstatus != 0:
			frappe.throw(_("Posted financial records cannot be deleted"))

	def _normalize_optional_keys(self):
		if not self.idempotency_key:
			self.idempotency_key = None
		if self.idempotency_key:
			self.idempotency_key = self.idempotency_key.strip() or None

	def _validate_type_and_direction(self):
		if self.entry_type not in ENTRY_TYPES:
			frappe.throw(_("Invalid entry type"))

		if self.entry_type == "Sale":
			self.direction = "Receivable"
		elif self.entry_type == "Purchase":
			self.direction = "Payable"
		elif self.entry_type in CASH_TYPES:
			self.direction = None
		elif self.entry_type in {"Loan", "Opening Balance"} and self.direction not in {
			"Receivable",
			"Payable",
		}:
			frappe.throw(_("Direction is required for {0}").format(self.entry_type))

	def _validate_amount(self):
		amount = to_money(self.amount)
		if amount <= ZERO:
			frappe.throw(_("Amount must be greater than zero"))
		self.amount = money_to_db(amount)
		if not self.transaction_date:
			self.transaction_date = nowdate()
		self.transaction_date = getdate(self.transaction_date)

	def _validate_person(self):
		if not self.person:
			return
		person_workspace = frappe.db.get_value("Sahbi Person", self.person, "workspace")
		if person_workspace != self.workspace:
			frappe.throw(_("Person must belong to the same workspace"))

	def _validate_audit_links(self):
		for fieldname in ("reversal_of", "replaces"):
			link = self.get(fieldname)
			if not link:
				continue
			if link == self.name:
				frappe.throw(_("An entry cannot reference itself"))
			if frappe.db.get_value("Sahbi Entry", link, "workspace") != self.workspace:
				frappe.throw(_("Audit references must stay in the same workspace"))


def on_doctype_update():
	frappe.db.add_unique(
		"Sahbi Entry",
		["workspace", "idempotency_key"],
		constraint_name="unique_sahbi_entry_idempotency",
	)
