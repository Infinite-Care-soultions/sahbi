# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

from sahbi.engine.utils import money_out, require_workspace
from sahbi.ledger import DIRECTION_PAYABLE, DIRECTION_RECEIVABLE, get_entry_direction
from sahbi.money import ZERO, add_money, to_money

ACTIVITY_KINDS = {
	"income": ("Income", None),
	"expense": ("Expense", None),
	"sale": ("Sale", None),
	"purchase": ("Purchase", None),
	"loan_receivable": ("Loan", DIRECTION_RECEIVABLE),
	"loan_payable": ("Loan", DIRECTION_PAYABLE),
	"opening_balance": ("Opening Balance", None),
}

PAYMENT_KINDS = {
	"collections": "Incoming",
	"repayments": "Outgoing",
}

OUTSTANDING_KINDS = {
	"outstanding_receivable": DIRECTION_RECEIVABLE,
	"outstanding_payable": DIRECTION_PAYABLE,
}

DISTINGUISHING_TOKENS = ("نقل", "شحن", "توصيل", "مصنعية", "أجرة", "اجرة")
CASH_BANK_TERMS = {
	"كاش",
	"الكاش",
	"بنك",
	"البنك",
	"خزنة",
	"الخزنة",
	"فيزا",
	"كارت",
	"الكارت",
	"حساب بنكي",
	"رصيد الكاش",
	"رصيد البنك",
}
PROFIT_TERMS = {"ربح", "ارباح", "أرباح", "مكسب", "صافي الربح", "صافي الارباح"}


def get_income_expense_totals(workspace, from_date=None, to_date=None) -> dict:
	workspace = require_workspace(workspace)
	income = _sum_entries(workspace, ["Income"], from_date, to_date)
	expense = _sum_entries(workspace, ["Expense"], from_date, to_date)
	return {
		"workspace": workspace,
		"from_date": str(from_date) if from_date else None,
		"to_date": str(to_date) if to_date else None,
		"income": money_out(income),
		"expense": money_out(expense),
		"income_minus_expense": money_out(income - expense),
		"net": money_out(income - expense),
	}


def get_person_balances(workspace, person=None) -> dict:
	workspace = require_workspace(workspace)
	filters = {
		"workspace": workspace,
		"docstatus": 1,
		"entry_type": ["in", ["Sale", "Purchase", "Loan", "Opening Balance"]],
	}
	if person:
		filters["person"] = person

	rows = frappe.get_all(
		"Sahbi Entry",
		filters=filters,
		fields=[
			"name",
			"person",
			"entry_type",
			"direction",
			"amount",
			"outstanding_amount",
			"payment_status",
			"transaction_date",
		],
	)

	receivable = ZERO
	payable = ZERO
	open_entries = []
	for row in rows:
		direction = row.direction or get_entry_direction(row)
		outstanding = to_money(row.outstanding_amount)
		if direction == DIRECTION_RECEIVABLE:
			receivable = add_money(receivable, outstanding)
		elif direction == DIRECTION_PAYABLE:
			payable = add_money(payable, outstanding)
		if outstanding > ZERO:
			open_entries.append(
				{
					"name": row.name,
					"person": row.person,
					"entry_type": row.entry_type,
					"direction": direction,
					"amount": money_out(row.amount),
					"outstanding_amount": money_out(outstanding),
					"transaction_date": str(row.transaction_date),
				}
			)

	return {
		"workspace": workspace,
		"person": person,
		"receivable": money_out(receivable),
		"payable": money_out(payable),
		"net": money_out(receivable - payable),
		"open_entries": open_entries,
		"includes_carried_forward": True,
	}


def list_person_balances(workspace) -> list[dict]:
	workspace = require_workspace(workspace)
	people = frappe.get_all(
		"Sahbi Person",
		filters={"workspace": workspace},
		fields=["name", "person_name"],
		order_by="person_name asc",
	)
	rows = []
	for person in people:
		balances = get_person_balances(workspace, person.name)
		rows.append(
			{
				"person": person.name,
				"person_name": person.person_name,
				"receivable": balances["receivable"],
				"payable": balances["payable"],
			}
		)
	return rows


def get_person_statement(workspace, person) -> dict:
	workspace = require_workspace(workspace)
	balances = get_person_balances(workspace, person)
	if not person:
		return {**balances, "lines": []}

	entries = frappe.get_all(
		"Sahbi Entry",
		filters={"workspace": workspace, "person": person, "docstatus": 1},
		fields=[
			"name",
			"entry_type",
			"direction",
			"amount",
			"outstanding_amount",
			"payment_status",
			"transaction_date",
			"description",
			"creation",
		],
		order_by="transaction_date asc, creation asc",
	)
	payments = frappe.get_all(
		"Sahbi Payment",
		filters={"workspace": workspace, "person": person, "docstatus": 1},
		fields=["name", "payment_kind", "amount", "payment_date", "description", "creation"],
		order_by="payment_date asc, creation asc",
	)

	lines = []
	for row in entries:
		lines.append(
			{
				"kind": "entry",
				"name": row.name,
				"entry_type": row.entry_type,
				"direction": row.direction or get_entry_direction(row),
				"amount": money_out(row.amount),
				"outstanding_amount": money_out(row.outstanding_amount or 0),
				"payment_status": row.payment_status,
				"date": str(row.transaction_date),
				"description": row.description,
			}
		)
	for row in payments:
		lines.append(
			{
				"kind": "payment",
				"name": row.name,
				"payment_kind": row.payment_kind,
				"amount": money_out(row.amount),
				"date": str(row.payment_date),
				"description": row.description,
			}
		)
	lines.sort(key=lambda row: (row.get("date") or "", row.get("name") or ""))
	return {**balances, "lines": lines}


def get_period_report(workspace, from_date=None, to_date=None) -> dict:
	workspace = require_workspace(workspace)
	income = _sum_entries(workspace, ["Income"], from_date, to_date)
	expense = _sum_entries(workspace, ["Expense"], from_date, to_date)
	sales = _sum_entries(workspace, ["Sale"], from_date, to_date)
	purchases = _sum_entries(workspace, ["Purchase"], from_date, to_date)
	loans_receivable = _sum_entries(workspace, ["Loan"], from_date, to_date, direction=DIRECTION_RECEIVABLE)
	loans_payable = _sum_entries(workspace, ["Loan"], from_date, to_date, direction=DIRECTION_PAYABLE)
	openings = _sum_entries(workspace, ["Opening Balance"], from_date, to_date)
	collections = _sum_payments(workspace, "Incoming", from_date, to_date)
	disbursements = _sum_payments(workspace, "Outgoing", from_date, to_date)
	balances = get_person_balances(workspace)
	loan_receivable_outstanding = _sum_outstanding(workspace, ["Loan"], direction=DIRECTION_RECEIVABLE)
	loan_payable_outstanding = _sum_outstanding(workspace, ["Loan"], direction=DIRECTION_PAYABLE)
	opening_outstanding = _sum_outstanding(workspace, ["Opening Balance"])

	return {
		"workspace": workspace,
		"from_date": str(from_date) if from_date else None,
		"to_date": str(to_date) if to_date else None,
		"income": money_out(income),
		"expense": money_out(expense),
		"sales": money_out(sales),
		"purchases": money_out(purchases),
		"loan_receivable": money_out(loans_receivable),
		"loan_payable": money_out(loans_payable),
		"opening_balances": money_out(openings),
		"collections": money_out(collections),
		"repayments": money_out(disbursements),
		"disbursements": money_out(disbursements),
		"outstanding_receivable": balances["receivable"],
		"outstanding_payable": balances["payable"],
		"loan_outstanding_receivable": money_out(loan_receivable_outstanding),
		"loan_outstanding_payable": money_out(loan_payable_outstanding),
		"opening_outstanding": money_out(opening_outstanding),
		"includes_carried_forward": True,
		"claims_profit": False,
		"claims_cash": False,
	}


def run_financial_query(
	workspace,
	kind=None,
	search_terms=None,
	person=None,
	person_name=None,
	from_date=None,
	to_date=None,
) -> dict:
	workspace = require_workspace(workspace)
	terms = [str(term).strip() for term in (search_terms or []) if str(term).strip()]
	base = {
		"workspace": workspace,
		"kind": kind,
		"search_terms": terms,
		"person": person,
		"person_name": person_name,
		"from_date": str(from_date) if from_date else None,
		"to_date": str(to_date) if to_date else None,
		"claims_profit": False,
		"claims_cash": False,
		"includes_carried_forward": False,
	}

	if kind == "cash_or_bank" or _terms_are(terms, CASH_BANK_TERMS):
		return _limitation(base, "cash_or_bank")
	if kind == "profit" or _terms_are(terms, PROFIT_TERMS):
		return _limitation(base, "profit")
	if not kind:
		return _limitation(base, "unknown_kind")
	if kind == "search" and not terms:
		return _limitation(base, "need_search_terms")

	if kind == "income_expense":
		totals = get_income_expense_totals(workspace, from_date, to_date)
		return {
			**base,
			"status": "ok",
			"income": totals["income"],
			"expense": totals["expense"],
			"income_minus_expense": totals["income_minus_expense"],
			"total": None,
			"count": None,
			"by_type": {"Income": totals["income"], "Expense": totals["expense"]},
		}

	if kind == "period_report":
		report = get_period_report(workspace, from_date, to_date)
		report.update(base)
		report["kind"] = "period_report"
		report["status"] = "ok"
		report["total"] = None
		return report

	if kind == "person_balance":
		if person:
			statement = get_person_statement(workspace, person)
			people = []
		else:
			statement = get_person_balances(workspace, person)
			people = list_person_balances(workspace)
		return {
			**base,
			"status": "ok",
			"receivable": statement["receivable"],
			"payable": statement["payable"],
			"open_entries": statement["open_entries"],
			"lines": statement.get("lines") or [],
			"people": people,
			"includes_carried_forward": True,
			"total": None,
		}

	if kind in OUTSTANDING_KINDS:
		balances = get_person_balances(workspace, person)
		direction = OUTSTANDING_KINDS[kind]
		field = "receivable" if direction == DIRECTION_RECEIVABLE else "payable"
		total = balances[field]
		open_entries = [row for row in balances["open_entries"] if row["direction"] == direction]
		people = []
		if not person:
			people = [row for row in list_person_balances(workspace) if to_money(row[field]) > ZERO]
			people_total = ZERO
			for row in people:
				people_total = add_money(people_total, row[field])
			total = money_out(people_total)
			open_entries = [row for row in open_entries if row.get("person")]
		return {
			**base,
			"status": "ok",
			"direction": direction,
			"total": total,
			"count": len(open_entries),
			"open_entries": open_entries,
			"people": people,
			"includes_carried_forward": True,
		}

	if kind in PAYMENT_KINDS:
		rows = _list_payments(workspace, PAYMENT_KINDS[kind], from_date, to_date, person=person)
		total = ZERO
		for row in rows:
			total = add_money(total, row.amount)
		return {
			**base,
			"status": "ok",
			"payment_kind": PAYMENT_KINDS[kind],
			"total": money_out(total),
			"count": len(rows),
			"matches": [_serialize_payment(row) for row in rows],
		}

	if kind in ACTIVITY_KINDS or kind == "search":
		return _activity_or_search(base, workspace, kind, terms, person, from_date, to_date)

	return _limitation(base, "unknown_kind")


def _activity_or_search(base, workspace, kind, terms, person, from_date, to_date) -> dict:
	if kind in ACTIVITY_KINDS:
		entry_type, direction = ACTIVITY_KINDS[kind]
		rows = _list_entries(
			workspace,
			[entry_type],
			from_date,
			to_date,
			direction=direction,
			person=person,
		)
	else:
		rows = _list_entries(workspace, None, from_date, to_date, person=person)

	matched = [row for row in rows if description_matches(row.description, terms)]
	by_type_amounts = {}
	by_type_counts = {}
	total = ZERO
	paid_total = ZERO
	remaining_total = ZERO
	for row in matched:
		total = add_money(total, row.amount)
		remaining = to_money(row.outstanding_amount or 0)
		remaining_total = add_money(remaining_total, remaining)
		paid = row.paid_amount if getattr(row, "paid_amount", None) is not None else (to_money(row.amount) - remaining)
		paid_total = add_money(paid_total, paid)
		by_type_amounts[row.entry_type] = add_money(by_type_amounts.get(row.entry_type, ZERO), row.amount)
		by_type_counts[row.entry_type] = by_type_counts.get(row.entry_type, 0) + 1

	mixed = len(by_type_amounts) > 1
	return {
		**base,
		"status": "ok",
		"total": None if mixed else money_out(total),
		"paid_total": money_out(paid_total),
		"remaining_total": money_out(remaining_total),
		"count": len(matched),
		"by_type": {key: money_out(value) for key, value in by_type_amounts.items()},
		"by_type_count": by_type_counts,
		"mixed_types": mixed,
		"matches": [_serialize_entry(row) for row in matched],
	}


def description_matches(description: str | None, terms: list[str]) -> bool:
	text = description or ""
	if terms and not all(term in text for term in terms):
		return False
	if not terms:
		return True
	extra = [token for token in DISTINGUISHING_TOKENS if token in text and token not in terms]
	return not extra


def _limitation(base: dict, limitation: str) -> dict:
	return {
		**base,
		"status": "limitation",
		"limitation": limitation,
		"total": None,
		"count": 0,
		"claims_cash": limitation == "cash_or_bank",
		"claims_profit": False,
	}


def _terms_are(terms: list[str], allowed: set[str]) -> bool:
	if not terms:
		return False
	return all(term in allowed for term in terms)


def _date_filters(fieldname, from_date, to_date) -> dict:
	filters = {}
	from_date = getdate(from_date) if from_date else None
	to_date = getdate(to_date) if to_date else None
	if from_date and to_date:
		filters[fieldname] = ["between", [from_date, to_date]]
	elif from_date:
		filters[fieldname] = [">=", from_date]
	elif to_date:
		filters[fieldname] = ["<=", to_date]
	return filters


def _list_entries(workspace, entry_types, from_date=None, to_date=None, direction=None, person=None):
	filters = {
		"workspace": workspace,
		"docstatus": 1,
		**_date_filters("transaction_date", from_date, to_date),
	}
	if entry_types:
		filters["entry_type"] = ["in", entry_types]
	if direction:
		filters["direction"] = direction
	if person:
		filters["person"] = person
	return frappe.get_all(
		"Sahbi Entry",
		filters=filters,
		fields=[
			"name",
			"entry_type",
			"direction",
			"amount",
			"outstanding_amount",
			"paid_amount",
			"description",
			"person",
			"transaction_date",
			"payment_status",
		],
	)


def _list_payments(workspace, payment_kind, from_date=None, to_date=None, person=None):
	filters = {
		"workspace": workspace,
		"docstatus": 1,
		"payment_kind": payment_kind,
		**_date_filters("payment_date", from_date, to_date),
	}
	if person:
		filters["person"] = person
	return frappe.get_all(
		"Sahbi Payment",
		filters=filters,
		fields=["name", "amount", "payment_kind", "payment_date", "person", "description"],
	)


def _sum_entries(workspace, entry_types, from_date=None, to_date=None, direction=None, person=None):
	rows = _list_entries(workspace, entry_types, from_date, to_date, direction=direction, person=person)
	total = ZERO
	for row in rows:
		total = add_money(total, row.amount)
	return total


def _sum_payments(workspace, payment_kind, from_date=None, to_date=None, person=None):
	rows = _list_payments(workspace, payment_kind, from_date, to_date, person=person)
	total = ZERO
	for row in rows:
		total = add_money(total, row.amount)
	return total


def _sum_outstanding(workspace, entry_types, person=None, direction=None):
	rows = _list_entries(workspace, entry_types, direction=direction, person=person)
	total = ZERO
	for row in rows:
		total = add_money(total, row.outstanding_amount or 0)
	return total


def _serialize_entry(row) -> dict:
	return {
		"name": row.name,
		"entry_type": row.entry_type,
		"amount": money_out(row.amount),
		"outstanding_amount": money_out(row.outstanding_amount or 0),
		"paid_amount": money_out(
			row.paid_amount
			if getattr(row, "paid_amount", None) is not None
			else (to_money(row.amount) - to_money(row.outstanding_amount or 0))
		),
		"description": row.description,
		"person": row.person,
		"transaction_date": str(row.transaction_date),
	}


def _serialize_payment(row) -> dict:
	return {
		"name": row.name,
		"payment_kind": row.payment_kind,
		"amount": money_out(row.amount),
		"person": row.person,
		"description": row.description,
		"payment_date": str(row.payment_date),
	}
