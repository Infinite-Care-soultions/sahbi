# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from sahbi.engine.posting import apply_explicit_settlement, create_expense, create_income, record_payment
from sahbi.engine.utils import require_workspace, resolve_person, run_atomic
from sahbi.ledger import ALLOCATABLE_TYPES, DIRECTION_PAYABLE, DIRECTION_RECEIVABLE, get_entry_direction
from sahbi.money import ZERO, to_money


class AmbiguousSettlement(frappe.ValidationError):
	def __init__(self, message, candidates=None):
		super().__init__(message)
		self.candidates = candidates or []


def record_incoming_money(workspace, amount, **kwargs):
	return _record_transfer(workspace, amount, "Incoming", **kwargs)


def record_outgoing_money(workspace, amount, **kwargs):
	return _record_transfer(workspace, amount, "Outgoing", **kwargs)


def _record_transfer(
	workspace,
	amount,
	kind,
	*,
	person=None,
	person_name=None,
	description=None,
	transaction_date=None,
	currency="EGP",
	idempotency_key=None,
	settle_entry=None,
	allocations=None,
	create_person=False,
):
	workspace = require_workspace(workspace)
	person = resolve_person(workspace, person, person_name, create=create_person) if person or person_name else None
	direction = DIRECTION_RECEIVABLE if kind == "Incoming" else DIRECTION_PAYABLE

	def _do():
		if allocations:
			return {
				"status": "ok",
				"settled": True,
				"classification": "settlement",
				"payment": record_payment(
					workspace,
					amount,
					kind,
					allocations=allocations,
					person=person,
					description=description,
					payment_date=transaction_date,
					currency=currency,
					idempotency_key=idempotency_key,
				),
				"income": None,
				"expense": None,
			}

		target = settle_entry
		if not target:
			candidates = find_open_operations(workspace, person, direction)
			if len(candidates) > 1:
				raise AmbiguousSettlement(
					_("Several matching operations exist. Choose one explicitly."),
					candidates=candidates,
				)
			if len(candidates) == 1:
				target = candidates[0]["name"]

		if target:
			result = apply_explicit_settlement(
				workspace,
				amount,
				kind,
				target,
				person=person,
				description=description,
				transaction_date=transaction_date,
				currency=currency,
				idempotency_key=idempotency_key,
			)
			result["classification"] = "settlement"
			return result

		if kind == "Incoming":
			income = create_income(
				workspace,
				amount,
				person=person,
				description=description,
				transaction_date=transaction_date,
				currency=currency,
				idempotency_key=idempotency_key,
			)
			return {
				"status": "ok",
				"settled": False,
				"classification": "income",
				"income": income,
				"expense": None,
				"payment": None,
			}

		expense = create_expense(
			workspace,
			amount,
			person=person,
			description=description,
			transaction_date=transaction_date,
			currency=currency,
			idempotency_key=idempotency_key,
		)
		return {
			"status": "ok",
			"settled": False,
			"classification": "expense",
			"income": None,
			"expense": expense,
			"payment": None,
		}

	return run_atomic(_do)


def find_open_operations(workspace, person, direction) -> list[dict]:
	if not person:
		return []

	rows = frappe.get_all(
		"Sahbi Entry",
		filters={
			"workspace": workspace,
			"docstatus": 1,
			"person": person,
			"entry_type": ["in", list(ALLOCATABLE_TYPES)],
			"payment_status": ["in", ["Unpaid", "Partially Paid"]],
		},
		fields=["name", "entry_type", "direction", "amount", "outstanding_amount", "transaction_date"],
		order_by="transaction_date asc, creation asc",
	)
	matches = []
	for row in rows:
		entry_direction = row.direction or get_entry_direction(row)
		if entry_direction != direction:
			continue
		if to_money(row.outstanding_amount) <= ZERO:
			continue
		matches.append(
			{
				"name": row.name,
				"entry_type": row.entry_type,
				"direction": entry_direction,
				"amount": str(to_money(row.amount)),
				"outstanding_amount": str(to_money(row.outstanding_amount)),
				"transaction_date": str(row.transaction_date),
			}
		)
	return matches
