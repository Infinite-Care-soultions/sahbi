# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from collections.abc import Callable
from typing import TypeVar

import frappe
from frappe import _

from sahbi.money import money_to_db
from sahbi.permissions import assert_workspace_access
from sahbi.chat.normalize import clean_person_name
from sahbi.sahbi.doctype.sahbi_person.sahbi_person import normalize_person_name


class PersonNotFound(frappe.ValidationError):
	def __init__(self, person_name):
		self.person_name = person_name
		super().__init__(_("Person {0} was not found").format(person_name))

T = TypeVar("T")
SAVE_POINT = "sahbi_engine"


def atomic(fn: Callable[[], T]) -> T:
	frappe.db.savepoint(SAVE_POINT)
	try:
		result = fn()
	except Exception:
		frappe.db.rollback(save_point=SAVE_POINT)
		raise
	frappe.db.release_savepoint(SAVE_POINT)
	return result


def run_atomic(fn: Callable[[], T]) -> T:
	if frappe.flags.get("sahbi_in_engine"):
		return fn()
	frappe.flags.sahbi_in_engine = True
	try:
		return atomic(fn)
	finally:
		frappe.flags.sahbi_in_engine = False


def money_out(value) -> str:
	return money_to_db(value)


def resolve_person(workspace: str, person=None, person_name=None, create=False):
	if person:
		person_workspace = frappe.db.get_value("Sahbi Person", person, "workspace")
		if person_workspace != workspace:
			frappe.throw(_("Person must belong to the same workspace"))
		return person
	if not person_name:
		return None

	person_name = clean_person_name(person_name)
	normalized = normalize_person_name(person_name)
	existing = frappe.db.get_value(
		"Sahbi Person",
		{"workspace": workspace, "normalized_name": normalized},
		"name",
	)
	if existing:
		return existing
	if not create:
		raise PersonNotFound(person_name)

	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Person",
			"workspace": workspace,
			"person_name": person_name,
		}
	)
	doc.insert()
	return doc.name


def get_by_idempotency(doctype: str, workspace: str, key: str | None):
	if not key:
		return None
	name = frappe.db.get_value(
		doctype,
		{"workspace": workspace, "idempotency_key": key.strip(), "docstatus": ["!=", 2]},
		"name",
	)
	if not name:
		return None
	return frappe.get_doc(doctype, name)


def serialize_entry(doc) -> dict:
	return {
		"doctype": "Sahbi Entry",
		"name": doc.name,
		"workspace": doc.workspace,
		"entry_type": doc.entry_type,
		"direction": doc.direction,
		"amount": money_out(doc.amount),
		"paid_amount": money_out(doc.paid_amount or 0),
		"outstanding_amount": money_out(doc.outstanding_amount or 0),
		"payment_status": doc.payment_status,
		"transaction_date": str(doc.transaction_date),
		"person": doc.person,
		"description": doc.description,
		"docstatus": doc.docstatus,
		"replaces": doc.replaces,
		"replaced_by": doc.replaced_by,
		"reversal_of": doc.reversal_of,
	}


def serialize_payment(doc) -> dict:
	return {
		"doctype": "Sahbi Payment",
		"name": doc.name,
		"workspace": doc.workspace,
		"payment_kind": doc.payment_kind,
		"amount": money_out(doc.amount),
		"allocated_amount": money_out(doc.allocated_amount or 0),
		"unallocated_amount": money_out(doc.unallocated_amount or 0),
		"payment_date": str(doc.payment_date),
		"person": doc.person,
		"description": doc.description,
		"docstatus": doc.docstatus,
	}


def require_workspace(workspace: str) -> str:
	if not workspace:
		frappe.throw(_("Workspace is required"))
	if not frappe.db.exists("Sahbi Workspace", workspace):
		frappe.throw(_("Workspace {0} was not found").format(workspace))
	assert_workspace_access(workspace)
	return workspace


def replayed_entry(doc) -> dict:
	result = serialize_entry(doc)
	result["status"] = "ok"
	result["replayed"] = True
	return result


def replayed_payment(doc) -> dict:
	result = serialize_payment(doc)
	result["status"] = "ok"
	result["replayed"] = True
	return result


def insert_and_submit(doc):
	doc.insert()
	doc.submit()
	return doc


def posted_entry(doc, extra=None) -> dict:
	result = serialize_entry(doc)
	result["status"] = "ok"
	result["replayed"] = False
	if extra:
		result.update(extra)
	return result


def posted_payment(doc, extra=None) -> dict:
	result = serialize_payment(doc)
	result["status"] = "ok"
	result["replayed"] = False
	if extra:
		result.update(extra)
	return result


def catch_duplicate(doctype, workspace, key, serializer):
	existing = get_by_idempotency(doctype, workspace, key)
	if existing:
		return serializer(existing)
	return None
