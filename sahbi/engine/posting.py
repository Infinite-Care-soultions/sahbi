# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate

from sahbi.engine.utils import (
	catch_duplicate,
	get_by_idempotency,
	insert_and_submit,
	posted_entry,
	posted_payment,
	replayed_entry,
	replayed_payment,
	require_workspace,
	resolve_person,
	run_atomic,
	serialize_entry,
)
from sahbi.ledger import assert_allocation_fits
from sahbi.money import ZERO, to_money


def create_income(workspace, amount, **kwargs):
	return _create_entry(workspace, "Income", amount, **kwargs)


def create_expense(workspace, amount, **kwargs):
	return _create_entry(workspace, "Expense", amount, **kwargs)


def create_sale(workspace, amount, **kwargs):
	return _create_entry(workspace, "Sale", amount, **kwargs)


def create_purchase(workspace, amount, **kwargs):
	return _create_entry(workspace, "Purchase", amount, **kwargs)


def create_loan(workspace, amount, direction, **kwargs):
	if direction not in {"Receivable", "Payable"}:
		frappe.throw(_("Loan direction must be Receivable or Payable"))
	return _create_entry(workspace, "Loan", amount, direction=direction, **kwargs)


def create_opening_balance(workspace, amount, direction, **kwargs):
	if direction not in {"Receivable", "Payable"}:
		frappe.throw(_("Opening balance direction must be Receivable or Payable"))
	return _create_entry(workspace, "Opening Balance", amount, direction=direction, **kwargs)


def _create_entry(
	workspace,
	entry_type,
	amount,
	*,
	direction=None,
	person=None,
	person_name=None,
	description=None,
	transaction_date=None,
	currency="EGP",
	idempotency_key=None,
	replaces=None,
	reversal_of=None,
	create_person=False,
):
	workspace = require_workspace(workspace)
	existing = get_by_idempotency("Sahbi Entry", workspace, idempotency_key)
	if existing:
		return replayed_entry(existing)

	def _do():
		doc = frappe.get_doc(
			{
				"doctype": "Sahbi Entry",
				"workspace": workspace,
				"entry_type": entry_type,
				"direction": direction,
				"amount": to_money(amount),
				"currency": currency,
				"transaction_date": transaction_date or nowdate(),
				"person": resolve_person(workspace, person, person_name, create=create_person),
				"description": description,
				"idempotency_key": idempotency_key,
				"replaces": replaces,
				"reversal_of": reversal_of,
			}
		)
		try:
			insert_and_submit(doc)
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			replay = catch_duplicate("Sahbi Entry", workspace, idempotency_key, replayed_entry)
			if replay:
				return replay
			raise
		return posted_entry(doc)

	return run_atomic(_do)


def record_payment(
	workspace,
	amount,
	payment_kind,
	*,
	allocations=None,
	person=None,
	person_name=None,
	description=None,
	payment_date=None,
	currency="EGP",
	idempotency_key=None,
	create_person=False,
):
	workspace = require_workspace(workspace)
	if payment_kind not in {"Incoming", "Outgoing"}:
		frappe.throw(_("Payment kind must be Incoming or Outgoing"))

	existing = get_by_idempotency("Sahbi Payment", workspace, idempotency_key)
	if existing:
		return _payment_with_entries(existing, replayed=True)

	def _do():
		payment = frappe.get_doc(
			{
				"doctype": "Sahbi Payment",
				"workspace": workspace,
				"amount": to_money(amount),
				"currency": currency,
				"payment_kind": payment_kind,
				"payment_date": payment_date or nowdate(),
				"person": resolve_person(workspace, person, person_name, create=create_person),
				"description": description,
				"idempotency_key": idempotency_key,
			}
		)
		try:
			insert_and_submit(payment)
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			replay = get_by_idempotency("Sahbi Payment", workspace, idempotency_key)
			if replay:
				return _payment_with_entries(replay, replayed=True)
			raise

		posted_allocations = []
		for row in allocations or []:
			entry_name = row.get("entry") or row.get("entry_name")
			allocated = row.get("amount") or row.get("allocated_amount")
			if not entry_name:
				frappe.throw(_("Each allocation must include an entry"))
			entry = frappe.get_doc("Sahbi Entry", entry_name)
			if entry.workspace != workspace:
				frappe.throw(_("Allocation entry must belong to the same workspace"))
			assert_allocation_fits(payment, entry, allocated)
			allocation = frappe.get_doc(
				{
					"doctype": "Sahbi Payment Allocation",
					"workspace": workspace,
					"payment": payment.name,
					"entry": entry.name,
					"allocated_amount": to_money(allocated),
				}
			)
			insert_and_submit(allocation)
			posted_allocations.append(
				{
					"name": allocation.name,
					"entry": entry.name,
					"allocated_amount": str(to_money(allocated)),
				}
			)

		payment.reload()
		entries = []
		for row in posted_allocations:
			entry = frappe.get_doc("Sahbi Entry", row["entry"])
			entries.append(serialize_entry(entry))
		result = posted_payment(payment, {"allocations": posted_allocations, "entries": entries})
		return result

	return run_atomic(_do)


def _payment_with_entries(payment, replayed=False) -> dict:
	allocation_rows = frappe.get_all(
		"Sahbi Payment Allocation",
		filters={"payment": payment.name, "docstatus": 1},
		fields=["name", "entry", "allocated_amount"],
	)
	entries = [serialize_entry(frappe.get_doc("Sahbi Entry", row.entry)) for row in allocation_rows]
	payload = replayed_payment(payment) if replayed else posted_payment(payment)
	payload["allocations"] = [
		{
			"name": row.name,
			"entry": row.entry,
			"allocated_amount": str(to_money(row.allocated_amount)),
		}
		for row in allocation_rows
	]
	payload["entries"] = entries
	return payload


def apply_explicit_settlement(workspace, amount, payment_kind, entry_name, **kwargs):
	entry = frappe.get_doc("Sahbi Entry", entry_name)
	if entry.workspace != workspace:
		frappe.throw(_("Settlement entry must belong to the same workspace"))
	if entry.docstatus != 1:
		frappe.throw(_("Settlement entry must be submitted"))

	outstanding = to_money(entry.outstanding_amount)
	pay_amount = to_money(amount)
	if outstanding <= ZERO:
		frappe.throw(_("This operation has no outstanding amount"))

	allocated = pay_amount if pay_amount <= outstanding else outstanding
	leftover = pay_amount - allocated

	result = {
		"status": "ok",
		"settled": False,
		"income": None,
		"expense": None,
		"payment": None,
	}
	if allocated > ZERO:
		result["payment"] = record_payment(
			workspace,
			allocated,
			payment_kind,
			allocations=[{"entry": entry.name, "amount": allocated}],
			person=kwargs.get("person") or entry.person,
			description=kwargs.get("description"),
			payment_date=kwargs.get("transaction_date") or kwargs.get("payment_date"),
			currency=kwargs.get("currency", "EGP"),
			idempotency_key=kwargs.get("idempotency_key"),
		)
		result["settled"] = True

	if leftover > ZERO:
		remainder_kwargs = {
			"person": kwargs.get("person") or entry.person,
			"description": kwargs.get("description"),
			"transaction_date": kwargs.get("transaction_date"),
			"currency": kwargs.get("currency", "EGP"),
		}
		if kwargs.get("idempotency_key"):
			remainder_kwargs["idempotency_key"] = f"{kwargs['idempotency_key']}-remainder"
		if payment_kind == "Incoming":
			result["income"] = create_income(workspace, leftover, **remainder_kwargs)
		else:
			result["expense"] = create_expense(workspace, leftover, **remainder_kwargs)

	return result
