# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import frappe


class SahbiLLMError(frappe.ValidationError):
	pass


class SahbiLLMUnavailable(SahbiLLMError):
	pass


class SahbiLLMInvalidOutput(SahbiLLMError):
	pass
