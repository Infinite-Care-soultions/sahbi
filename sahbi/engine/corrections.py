# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from sahbi.engine.posting import _create_entry
from sahbi.engine.utils import money_out, require_workspace, run_atomic, serialize_entry, serialize_payment
from sahbi.money import to_money


def cancel_entry(name, *, reason=None, confirm=False):
	entry = frappe.get_doc("Sahbi Entry", name)
	require_workspace(entry.workspace)
	if entry.docstatus != 1:
		frappe.throw(_("Only a submitted entry can be cancelled"))

	allocations = frappe.get_all(
		"Sahbi Payment Allocation",
		filters={"entry": entry.name, "docstatus": 1},
		fields=["name", "payment", "allocated_amount"],
	)
	payment_names = list({row.payment for row in allocations})
	preview = {
		"action": "cancel",
		"entry": serialize_entry(entry),
		"current": serialize_entry(entry),
		"proposed": {"docstatus": 2, "cancellation_reason": reason},
		"linked_allocations": [row.name for row in allocations],
		"linked_payments": payment_names,
		"impact": _(
			"Linked allocations will be cancelled. Payments with no remaining allocations will also be cancelled."
		),
	}
	if not confirm:
		return {"status": "needs_confirmation", "preview": preview}

	def _do():
		cancelled_allocations = []
		cancelled_payments = []
		for row in allocations:
			allocation = frappe.get_doc("Sahbi Payment Allocation", row.name)
			if reason:
				allocation.cancellation_reason = reason
			allocation.cancel()
			cancelled_allocations.append(row.name)

		for payment_name in payment_names:
			payment = frappe.get_doc("Sahbi Payment", payment_name)
			still_open = frappe.db.exists(
				"Sahbi Payment Allocation",
				{"payment": payment_name, "docstatus": 1},
			)
			if still_open:
				continue
			if reason:
				payment.cancellation_reason = reason
			payment.cancel()
			cancelled_payments.append(payment_name)

		entry.reload()
		if reason:
			entry.cancellation_reason = reason
		entry.cancel()
		entry.reload()
		return {
			"status": "cancelled",
			"entry": serialize_entry(entry),
			"cancelled_allocations": cancelled_allocations,
			"cancelled_payments": cancelled_payments,
		}

	return run_atomic(_do)


def cancel_payment(name, *, reason=None, confirm=False):
	payment = frappe.get_doc("Sahbi Payment", name)
	require_workspace(payment.workspace)
	if payment.docstatus != 1:
		frappe.throw(_("Only a submitted payment can be cancelled"))

	allocations = frappe.get_all(
		"Sahbi Payment Allocation",
		filters={"payment": payment.name, "docstatus": 1},
		pluck="name",
	)
	preview = {
		"action": "cancel",
		"payment": serialize_payment(payment),
		"current": serialize_payment(payment),
		"proposed": {"docstatus": 2, "cancellation_reason": reason},
		"linked_allocations": allocations,
		"impact": _("Linked allocations will be cancelled and entry outstanding amounts will be restored."),
	}
	if not confirm:
		return {"status": "needs_confirmation", "preview": preview}

	def _do():
		if reason:
			payment.cancellation_reason = reason
		payment.cancel()
		payment.reload()
		entries = []
		for allocation_name in allocations:
			allocation = frappe.get_doc("Sahbi Payment Allocation", allocation_name)
			entries.append(serialize_entry(frappe.get_doc("Sahbi Entry", allocation.entry)))
		return {
			"status": "cancelled",
			"payment": serialize_payment(payment),
			"cancelled_allocations": allocations,
			"entries": entries,
		}

	return run_atomic(_do)


def correct_entry(
	name,
	*,
	amount=None,
	transaction_date=None,
	description=None,
	person=None,
	reason=None,
	confirm=False,
	idempotency_key=None,
):
	if not reason:
		frappe.throw(_("A reason is required to correct a posted entry"))

	original = frappe.get_doc("Sahbi Entry", name)
	require_workspace(original.workspace)
	if original.docstatus != 1:
		frappe.throw(_("Only a submitted entry can be corrected"))

	proposed_amount = to_money(amount) if amount is not None else to_money(original.amount)
	proposed = {
		"amount": money_out(proposed_amount),
		"transaction_date": str(transaction_date or original.transaction_date),
		"description": description if description is not None else original.description,
		"person": person if person is not None else original.person,
		"entry_type": original.entry_type,
		"direction": original.direction,
	}
	preview = {
		"action": "correct",
		"current": serialize_entry(original),
		"proposed": proposed,
		"reason": reason,
		"impact": _(
			"The original entry and its linked payments will be cancelled. A replacement entry will be posted."
		),
	}
	if not confirm:
		return {"status": "needs_confirmation", "preview": preview}

	def _do():
		cancelled = cancel_entry(original.name, reason=reason, confirm=True)
		replacement = _create_entry(
			original.workspace,
			original.entry_type,
			proposed_amount,
			direction=original.direction,
			person=proposed["person"],
			description=proposed["description"],
			transaction_date=proposed["transaction_date"],
			currency=original.currency,
			idempotency_key=idempotency_key,
		)
		frappe.db.set_value(
			"Sahbi Entry",
			replacement["name"],
			{"replaces": original.name},
			update_modified=False,
		)
		original.db_set("replaced_by", replacement["name"], update_modified=True)
		replacement_doc = frappe.get_doc("Sahbi Entry", replacement["name"])
		return {
			"status": "corrected",
			"original": serialize_entry(frappe.get_doc("Sahbi Entry", original.name)),
			"replacement": serialize_entry(replacement_doc),
			"cancelled": cancelled,
		}

	return run_atomic(_do)
