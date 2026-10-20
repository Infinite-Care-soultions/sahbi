# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from decimal import Decimal

from sahbi.money import ZERO, add_money, money_to_db, to_money

CASH_TYPES = {"Income", "Expense"}
ALLOCATABLE_TYPES = {"Sale", "Purchase", "Loan", "Opening Balance"}
ENTRY_TYPES = CASH_TYPES | ALLOCATABLE_TYPES

DIRECTION_RECEIVABLE = "Receivable"
DIRECTION_PAYABLE = "Payable"
KIND_INCOMING = "Incoming"
KIND_OUTGOING = "Outgoing"

PAYMENT_NOT_APPLICABLE = "Not Applicable"
PAYMENT_UNPAID = "Unpaid"
PAYMENT_PARTIAL = "Partially Paid"
PAYMENT_FULL = "Fully Paid"


def get_entry_direction(entry) -> str | None:
	if entry.entry_type == "Sale":
		return DIRECTION_RECEIVABLE
	if entry.entry_type == "Purchase":
		return DIRECTION_PAYABLE
	if entry.entry_type in {"Loan", "Opening Balance"}:
		return entry.direction
	return None


def payment_kind_for_direction(direction: str) -> str:
	if direction == DIRECTION_RECEIVABLE:
		return KIND_INCOMING
	if direction == DIRECTION_PAYABLE:
		return KIND_OUTGOING
	frappe.throw(_("Entry cannot receive a payment allocation"))


def get_submitted_allocation_total(fieldname: str, name: str, ignore: str | None = None) -> Decimal:
	filters = {fieldname: name, "docstatus": 1}
	rows = frappe.get_all(
		"Sahbi Payment Allocation",
		filters=filters,
		fields=["name", "allocated_amount"],
	)
	total = ZERO
	for row in rows:
		if ignore and row.name == ignore:
			continue
		total = add_money(total, row.allocated_amount)
	return total


def payment_status_for(amount, paid):
	amount = to_money(amount)
	paid = to_money(paid)
	if paid <= ZERO:
		return PAYMENT_UNPAID
	if paid < amount:
		return PAYMENT_PARTIAL
	return PAYMENT_FULL


def refresh_entry_balances(entry_name: str) -> None:
	entry = frappe.get_doc("Sahbi Entry", entry_name)
	if entry.entry_type in CASH_TYPES:
		entry.db_set(
			{
				"paid_amount": money_to_db(ZERO),
				"outstanding_amount": money_to_db(ZERO),
				"payment_status": PAYMENT_NOT_APPLICABLE,
			},
			update_modified=False,
		)
		return

	paid = get_submitted_allocation_total("entry", entry_name)
	outstanding = to_money(entry.amount) - paid
	if outstanding < ZERO:
		frappe.throw(_("Allocated amount would exceed the entry amount"))

	entry.db_set(
		{
			"paid_amount": money_to_db(paid),
			"outstanding_amount": money_to_db(outstanding),
			"payment_status": payment_status_for(entry.amount, paid),
		},
		update_modified=False,
	)


def refresh_payment_balances(payment_name: str) -> None:
	payment = frappe.get_doc("Sahbi Payment", payment_name)
	allocated = get_submitted_allocation_total("payment", payment_name)
	unallocated = to_money(payment.amount) - allocated
	if unallocated < ZERO:
		frappe.throw(_("Allocated amount would exceed the payment amount"))

	payment.db_set(
		{
			"allocated_amount": money_to_db(allocated),
			"unallocated_amount": money_to_db(unallocated),
		},
		update_modified=False,
	)


def assert_allocation_fits(payment, entry, allocated_amount, ignore_allocation=None) -> None:
	amount = to_money(allocated_amount)
	if amount <= ZERO:
		frappe.throw(_("Allocated amount must be greater than zero"))

	if payment.workspace != entry.workspace:
		frappe.throw(_("Payment and entry must belong to the same workspace"))

	if payment.docstatus != 1:
		frappe.throw(_("Allocate only against a submitted payment"))

	if entry.docstatus != 1:
		frappe.throw(_("Allocate only against a submitted entry"))

	if entry.entry_type not in ALLOCATABLE_TYPES:
		frappe.throw(_("This entry type cannot receive payment allocations"))

	direction = get_entry_direction(entry)
	expected_kind = payment_kind_for_direction(direction)
	if payment.payment_kind != expected_kind:
		frappe.throw(_("Payment direction does not match the entry"))

	payment_used = get_submitted_allocation_total("payment", payment.name, ignore=ignore_allocation)
	if add_money(payment_used, amount) > to_money(payment.amount):
		frappe.throw(_("Allocations cannot exceed the payment amount"))

	entry_used = get_submitted_allocation_total("entry", entry.name, ignore=ignore_allocation)
	if add_money(entry_used, amount) > to_money(entry.amount):
		frappe.throw(_("Allocations cannot exceed the entry amount"))
