# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _

SYSTEM_ROLES = {"Administrator", "System Manager"}
STAFF_ROLES = SYSTEM_ROLES | {"Sahbi Support"}


def _is_system_user(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(SYSTEM_ROLES.intersection(frappe.get_roles(user)))


def _is_staff_user(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(STAFF_ROLES.intersection(frappe.get_roles(user)))


def user_workspaces(user: str) -> list[str]:
	return frappe.get_all("Sahbi Workspace", filters={"user": user, "disabled": 0}, pluck="name")


def _in_list_sql(doctype: str, fieldname: str, values: list[str]) -> str:
	if not values:
		return "1=0"
	escaped = ", ".join(frappe.db.escape(value) for value in values)
	return f"`tab{doctype}`.`{fieldname}` in ({escaped})"


def workspace_query(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if _is_system_user(user):
		return None
	return f"`tabSahbi Workspace`.`user` = {frappe.db.escape(user)}"


def person_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Person", user)


def entry_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Entry", user)


def payment_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Payment", user)


def allocation_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Payment Allocation", user)


def conversation_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Conversation", user, staff_sees_all=True)


def chat_message_query(user: str | None = None) -> str | None:
	return _workspace_field_query("Sahbi Chat Message", user, staff_sees_all=True)


def handoff_query(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if _is_staff_user(user):
		return None
	return "1=0"


def _workspace_field_query(doctype: str, user: str | None, staff_sees_all: bool = False) -> str | None:
	user = user or frappe.session.user
	if _is_system_user(user) or (staff_sees_all and _is_staff_user(user)):
		return None
	return _in_list_sql(doctype, "workspace", user_workspaces(user))


def has_workspace_permission(doc, ptype=None, user=None, debug=False):
	return _has_owner_permission(doc, user, owner_is_workspace=False)


def has_person_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user)


def has_entry_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user)


def has_payment_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user)


def has_allocation_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user)


def has_conversation_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user, staff_sees_all=True)


def has_chat_message_permission(doc, ptype=None, user=None, debug=False):
	return _has_doc_workspace_permission(doc, ptype, user, staff_sees_all=True)


def has_handoff_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	return _is_staff_user(user)


def validate_workspace_on_doc(doc, method=None):
	workspace = doc.get("workspace")
	if workspace:
		assert_workspace_access(workspace)


def _has_owner_permission(doc, user, owner_is_workspace=False):
	user = user or frappe.session.user
	if _is_system_user(user):
		return True
	if isinstance(doc, str):
		return False
	return doc.user == user


def assert_workspace_access(workspace: str, user: str | None = None) -> None:
	user = user or frappe.session.user
	if _is_system_user(user):
		return
	if not workspace:
		frappe.throw(_("Workspace is required"))
	owner = frappe.db.get_value("Sahbi Workspace", workspace, "user")
	if owner != user:
		frappe.throw(_("You cannot access another user's workspace"), frappe.PermissionError)


def _has_doc_workspace_permission(doc, ptype, user, staff_sees_all: bool = False):
	user = user or frappe.session.user
	if _is_system_user(user) or (staff_sees_all and _is_staff_user(user)):
		return True
	if isinstance(doc, str):
		return False
	workspace = doc.get("workspace")
	if not workspace:
		return ptype == "create"
	return frappe.db.get_value("Sahbi Workspace", workspace, "user") == user
