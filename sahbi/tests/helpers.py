# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate

from sahbi.workspace import ensure_sahbi_role, ensure_workspace_for_user


def make_user(email: str) -> str:
	ensure_sahbi_role()
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Sahbi",
				"last_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
	user.add_roles("Sahbi User")
	return user.name


def make_workspace(user: str | None = None, title: str | None = None):
	user = user or frappe.session.user
	name = ensure_workspace_for_user(user=user)
	workspace = frappe.get_doc("Sahbi Workspace", name)
	if title and workspace.title != title:
		workspace.title = title
		workspace.save(ignore_permissions=True)
	return workspace


def make_person(workspace, person_name="محمد", **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Person",
			"workspace": workspace,
			"person_name": person_name,
			**kwargs,
		}
	)
	doc.insert()
	return doc


def make_entry(workspace, entry_type="Income", amount=100, submit=False, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Entry",
			"workspace": workspace,
			"entry_type": entry_type,
			"amount": amount,
			"currency": "EGP",
			"transaction_date": kwargs.pop("transaction_date", nowdate()),
			**kwargs,
		}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


def make_payment(workspace, amount=100, payment_kind="Incoming", submit=False, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Payment",
			"workspace": workspace,
			"amount": amount,
			"currency": "EGP",
			"payment_kind": payment_kind,
			"payment_date": kwargs.pop("payment_date", nowdate()),
			**kwargs,
		}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


def make_allocation(payment, entry, allocated_amount, submit=False):
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Payment Allocation",
			"workspace": payment.workspace,
			"payment": payment.name,
			"entry": entry.name,
			"allocated_amount": allocated_amount,
		}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


def assert_rejected(test_case, fn):
	try:
		fn()
	except Exception:
		return
	test_case.fail("Expected the operation to be rejected")
