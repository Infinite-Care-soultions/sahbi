# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SahbiChatMessage(Document):
	def validate(self):
		if self.conversation and not self.workspace:
			self.workspace = frappe.db.get_value("Sahbi Conversation", self.conversation, "workspace")
		if self.conversation:
			conv_workspace = frappe.db.get_value("Sahbi Conversation", self.conversation, "workspace")
			if conv_workspace and self.workspace != conv_workspace:
				frappe.throw(_("Message workspace must match the conversation"))
