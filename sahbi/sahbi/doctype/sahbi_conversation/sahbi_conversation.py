# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sahbi.workspace import get_user_workspace


class SahbiConversation(Document):
	def before_insert(self):
		if not self.workspace and frappe.session.user != "Guest":
			self.workspace = get_user_workspace()
		if not self.user:
			self.user = frappe.db.get_value("Sahbi Workspace", self.workspace, "user") or frappe.session.user

	def validate(self):
		if self.workspace:
			owner = frappe.db.get_value("Sahbi Workspace", self.workspace, "user")
			if owner and self.user and owner != self.user and frappe.session.user != "Administrator":
				frappe.throw(_("Conversation user must own the workspace"))
