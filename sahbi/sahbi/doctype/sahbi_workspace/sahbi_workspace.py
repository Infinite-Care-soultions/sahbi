# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sahbi.permissions import _is_system_user


class SahbiWorkspace(Document):
	def validate(self):
		if self.is_default and self.user:
			others = frappe.get_all(
				"Sahbi Workspace",
				filters={"user": self.user, "is_default": 1, "name": ["!=", self.name or ""]},
				pluck="name",
			)
			if others:
				frappe.throw(_("A user can have only one default workspace in the MVP"))
		self._prevent_owner_reassignment()

	def _prevent_owner_reassignment(self):
		if self.is_new() or not self.user:
			return
		original = frappe.db.get_value("Sahbi Workspace", self.name, "user")
		if original and original != self.user:
			if not _is_system_user(frappe.session.user):
				frappe.throw(_("Workspace owner cannot be changed"))

	def on_trash(self):
		linked = (
			frappe.db.exists("Sahbi Entry", {"workspace": self.name})
			or frappe.db.exists("Sahbi Payment", {"workspace": self.name})
			or frappe.db.exists("Sahbi Person", {"workspace": self.name})
		)
		if linked:
			frappe.throw(_("Cannot delete a workspace that has financial history"))


def on_doctype_update():
	frappe.db.add_unique("Sahbi Workspace", ["user"], constraint_name="unique_sahbi_workspace_user")
