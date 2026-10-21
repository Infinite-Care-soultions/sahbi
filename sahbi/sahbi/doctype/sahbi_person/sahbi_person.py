# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from sahbi.chat.normalize import clean_person_name
from sahbi.workspace import get_user_workspace


def normalize_person_name(name: str) -> str:
	collapsed = re.sub(r"\s+", " ", clean_person_name(name or "").strip())
	return collapsed.casefold()


class SahbiPerson(Document):
	def before_validate(self):
		if not self.workspace and frappe.session.user != "Guest":
			self.workspace = get_user_workspace()

	def validate(self):
		if not self.person_name or not self.person_name.strip():
			frappe.throw(_("Person name is required"))
		self.person_name = clean_person_name(self.person_name)
		self.person_name = re.sub(r"\s+", " ", self.person_name.strip())
		self.normalized_name = normalize_person_name(self.person_name)
		if not self.normalized_name:
			frappe.throw(_("Person name is required"))

	def on_trash(self):
		if frappe.db.exists("Sahbi Entry", {"person": self.name}) or frappe.db.exists(
			"Sahbi Payment", {"person": self.name}
		):
			frappe.throw(_("Cannot delete a person who appears in financial history"))


def repair_glued_person_names() -> int:
	changed = 0
	for name in frappe.get_all("Sahbi Person", pluck="name"):
		doc = frappe.get_doc("Sahbi Person", name)
		cleaned = clean_person_name(doc.person_name)
		if cleaned == doc.person_name:
			continue
		existing = frappe.db.get_value(
			"Sahbi Person",
			{"workspace": doc.workspace, "normalized_name": normalize_person_name(cleaned), "name": ["!=", doc.name]},
			"name",
		)
		if existing:
			continue
		doc.person_name = cleaned
		doc.save(ignore_permissions=True)
		changed += 1
	return changed


def on_doctype_update():
	frappe.db.add_unique(
		"Sahbi Person",
		["workspace", "normalized_name"],
		constraint_name="unique_sahbi_person_workspace_name",
	)
