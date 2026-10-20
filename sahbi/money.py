# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import frappe
from frappe import _

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value) -> Decimal:
	if value is None or value == "":
		frappe.throw(_("Amount is required"))

	try:
		amount = Decimal(str(value))
	except (InvalidOperation, ValueError):
		frappe.throw(_("Invalid amount"))

	if not amount.is_finite():
		frappe.throw(_("Invalid amount"))

	return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def add_money(*values) -> Decimal:
	total = ZERO
	for value in values:
		total += to_money(value)
	return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_to_db(value) -> str:
	"""Return a 2-decimal string so Frappe does not accumulate raw floats."""
	return format(to_money(value), "f")
