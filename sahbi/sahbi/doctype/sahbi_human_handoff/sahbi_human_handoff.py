# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SahbiHumanHandoff(Document):
	def before_insert(self):
		if self.conversation and not self.workspace:
			self.workspace = frappe.db.get_value("Sahbi Conversation", self.conversation, "workspace")
		if not self.created_at:
			self.created_at = frappe.utils.now_datetime()

	def validate(self):
		if self.conversation and not self.workspace:
			self.workspace = frappe.db.get_value("Sahbi Conversation", self.conversation, "workspace")
