# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from frappe.utils import add_days, get_first_day, get_last_day, getdate, nowdate


def parse_date_expression(expression: str | None) -> dict:
	text = (expression or "").strip()
	today = getdate(nowdate())
	if not text:
		return {"transaction_date": None, "from_date": None, "to_date": None}

	if any(token in text for token in ("النهارده", "النهاردة", "اليوم", "النهار دا")):
		return {"transaction_date": today, "from_date": today, "to_date": today}

	if "الشهر اللي فات" in text or "الشهر الماضي" in text:
		first = get_first_day(add_days(get_first_day(today), -1))
		last = get_last_day(first)
		return {"transaction_date": last, "from_date": first, "to_date": last}

	if "الشهر ده" in text or "هذا الشهر" in text:
		return {
			"transaction_date": today,
			"from_date": get_first_day(today),
			"to_date": today,
		}

	return {"transaction_date": today, "from_date": None, "to_date": None}
