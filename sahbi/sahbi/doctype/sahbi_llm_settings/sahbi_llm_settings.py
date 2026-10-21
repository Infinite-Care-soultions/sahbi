# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from sahbi.llm.client import inspect_ollama
from sahbi.llm.settings import DEFAULT_MODEL, DEFAULT_TIMEOUT, DEFAULT_URL


class SahbiLLMSettings(Document):
	def validate(self):
		self.ollama_url = (self.ollama_url or DEFAULT_URL).strip().rstrip("/")
		self.ollama_model = (self.ollama_model or DEFAULT_MODEL).strip()
		if not self.ollama_url:
			frappe.throw(_("Ollama URL is required"))
		if not self.ollama_model:
			frappe.throw(_("Model is required"))
		timeout = int(self.timeout_seconds or DEFAULT_TIMEOUT)
		if timeout < 1:
			frappe.throw(_("Timeout must be at least 1 second"))
		self.timeout_seconds = timeout
		raw_delay = getattr(self, "reply_delay_seconds", None)
		if raw_delay in (None, ""):
			self.reply_delay_seconds = 10
		else:
			delay = int(raw_delay)
			if delay < 0:
				frappe.throw(_("Reply delay cannot be negative"))
			if delay > 60:
				frappe.throw(_("Reply delay cannot be more than 60 seconds"))
			self.reply_delay_seconds = delay


@frappe.whitelist()
def test_llm_connection():
	if not frappe.has_permission("Sahbi LLM Settings", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return inspect_ollama()
