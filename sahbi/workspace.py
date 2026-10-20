# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _

SKIP_USERS = {"Guest"}
SAHBI_ROLE = "Sahbi User"


def ensure_sahbi_role() -> None:
	if frappe.db.exists("Role", SAHBI_ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": SAHBI_ROLE,
			"desk_access": 1,
		}
	).insert(ignore_permissions=True)


def ensure_workspace_for_user(doc=None, method=None, user=None):
	user = user or (doc.name if doc is not None else frappe.session.user)
	if not user or user in SKIP_USERS:
		return None

	existing = frappe.db.get_value("Sahbi Workspace", {"user": user}, "name")
	if existing:
		return existing

	title = user if user == "Administrator" else (doc.full_name if doc is not None else user)
	workspace = frappe.get_doc(
		{
			"doctype": "Sahbi Workspace",
			"user": user,
			"title": title or user,
			"is_default": 1,
		}
	)
	workspace.insert(ignore_permissions=True)
	return workspace.name


def ensure_workspaces_for_enabled_users() -> None:
	ensure_sahbi_role()
	users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
	for user in users:
		ensure_workspace_for_user(user=user)


def after_migrate() -> None:
	ensure_workspaces_for_enabled_users()


def get_user_workspace(user=None) -> str:
	user = user or frappe.session.user
	workspace = ensure_workspace_for_user(user=user)
	if not workspace:
		frappe.throw(_("No financial workspace is available for this user"))
	return workspace
