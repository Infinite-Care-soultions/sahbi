# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from frappe.utils import now_datetime

TYPE_AR = {
	"Income": "دخل",
	"Expense": "مصروف",
	"Sale": "بيع",
	"Purchase": "شراء",
	"Loan": "سلفة",
	"Opening Balance": "حساب قديم",
}

KIND_AR = {
	"Incoming": "تحصيل",
	"Outgoing": "صرف",
}


def time_hello() -> str:
	hour = now_datetime().hour
	if hour < 12:
		return "صباح الفل"
	if hour < 17:
		return "أهلاً"
	return "مساء الفل"


def greet(first_of_day: bool = True, user_name: str | None = None) -> str:
	hello = time_hello()
	name = f" يا {user_name}" if user_name else ""
	if first_of_day:
		return f"{hello}{name}. أنا صاحبي، صاحبك. عامل ايه النهاردة؟"
	return f"{hello}{name}، أنا هنا معاك. قولّي اللي على بالك."


def thanks(user_name: str | None = None) -> str:
	name = f" يا {user_name}" if user_name else ""
	return f"العفو{name}. أنا موجود، أي وقت."


def saved_entry(entry: dict, person_name=None) -> str:
	label = TYPE_AR.get(entry.get("entry_type"), entry.get("entry_type"))
	amount = entry.get("amount")
	status = entry.get("payment_status")
	parts = [f"اتسجل {label} بمبلغ {amount} جنيه"]
	if person_name:
		parts.append(f"مع {person_name}")
	if status and status not in {"Not Applicable"}:
		parts.append(f"والحالة {status_ar(status)}")
	return "، ".join(parts) + "."


def saved_settlement(result: dict, person_name=None) -> str:
	if result.get("classification") == "income" and result.get("income"):
		return saved_entry(result["income"], person_name)
	if result.get("classification") == "expense" and result.get("expense"):
		return saved_entry(result["expense"], person_name)
	payment = result.get("payment") or {}
	entries = payment.get("entries") or []
	amount = payment.get("amount")
	kind = KIND_AR.get(payment.get("payment_kind"), "دفعة")
	if entries:
		first = entries[0]
		return (
			f"اتسجلت {kind} بمبلغ {amount} جنيه"
			+ (f" مع {person_name}" if person_name else "")
			+ f" على {TYPE_AR.get(first.get('entry_type'), 'العملية')}."
			+ f" المتبقي {first.get('outstanding_amount')} جنيه."
		)
	return f"اتسجلت {kind} بمبلغ {amount} جنيه."


TYPE_QUERY_AR = {
	"Income": "دخل",
	"Expense": "صرف",
	"Sale": "بيع",
	"Purchase": "شراء",
	"Loan": "سلف",
	"Opening Balance": "حساب قديم",
}

LIMITATION_AR = {
	"cash_or_bank": "صاحبي مش بيسجل رصيد الكاش أو البنك، فمقدرش أجاوب على السؤال ده من الحساب.",
	"profit": "البيانات المسجلة مش كافية أحسب ربح صافي. أقدر أقولك الدخل والصرف والبيع والشراء، من غير ما أسميه ربح.",
	"need_search_terms": "مش واضح بتدور على إيه بالظبط.",
	"unknown_kind": "ما قدرتش أحدد نوع السؤال من البيانات المسجلة.",
}


def query_result(result: dict) -> str:
	if result.get("status") == "limitation":
		return LIMITATION_AR.get(result.get("limitation"), LIMITATION_AR["unknown_kind"])

	kind = result.get("kind")
	if kind == "income_expense":
		return query_income_expense(result)
	if kind == "period_report":
		return query_period(result)
	if kind == "person_balance":
		return query_person(result, result.get("person_name"))
	if kind in {"outstanding_receivable", "outstanding_payable"}:
		return query_outstanding(result)
	if kind in {"collections", "repayments"}:
		return query_payments(result)
	return query_activity(result)


def query_income_expense(totals: dict) -> str:
	return (
		f"من {totals.get('from_date') or 'البداية'} لـ {totals.get('to_date') or 'دلوقتي'}:"
		f" الدخل {totals['income']} جنيه، والصرف {totals['expense']} جنيه."
		f" الفرق بين الدخل والصرف {totals.get('income_minus_expense') or totals.get('net')} جنيه."
	)


def query_person(balances: dict, person_name=None) -> str:
	if not person_name:
		return query_all_people(balances)
	name = person_name
	lines = []
	for row in balances.get("lines") or []:
		text = _statement_line(row)
		if text:
			lines.append(text)
	header = f"كشف حساب {name}:"
	if not lines:
		body = "مفيش عمليات مسجلة معاه لسه."
	else:
		body = "\n".join(f"{index} - {text}" for index, text in enumerate(lines, start=1))
	return (
		f"{header}\n"
		f"{body}\n"
		f"الإجمالي: ليه عندك {balances['receivable']} جنيه، وعليك له {balances['payable']} جنيه."
	)


def _statement_line(row: dict) -> str | None:
	amount = row.get("amount")
	if row.get("kind") == "payment":
		if row.get("payment_kind") == "Incoming":
			return f"قبضت منه {amount} جنيه"
		if row.get("payment_kind") == "Outgoing":
			return f"دفعت له {amount} جنيه"
		return f"دفعة {amount} جنيه"

	entry_type = row.get("entry_type")
	label = {
		"Sale": f"بعت له {amount} جنيه",
		"Purchase": f"اشتريت منه {amount} جنيه",
		"Income": f"دخل منه {amount} جنيه",
		"Expense": f"مصروف له {amount} جنيه",
		"Loan": (
			f"سلفت له {amount} جنيه"
			if row.get("direction") == "Receivable"
			else f"استلفت منه {amount} جنيه"
		),
		"Opening Balance": (
			f"حساب قديم ليه {amount} جنيه"
			if row.get("direction") == "Receivable"
			else f"حساب قديم عليك {amount} جنيه"
		),
	}.get(entry_type)
	if not label:
		return None
	outstanding = row.get("outstanding_amount")
	if entry_type in {"Sale", "Purchase", "Loan", "Opening Balance"} and outstanding not in {None, "0.00"}:
		return f"{label} — لسه {outstanding}"
	if entry_type in {"Sale", "Purchase", "Loan", "Opening Balance"} and row.get("payment_status") == "Fully Paid":
		return f"{label} — اتدفعت"
	return label


def query_period(report: dict) -> str:
	return (
		f"ملخص الفترة: دخل {report['income']}، صرف {report['expense']}،"
		f" بيع {report['sales']}، شراء {report['purchases']}،"
		f" سلف للناس {report['loan_receivable']}، سلف عليك {report['loan_payable']}،"
		f" حساب قديم {report['opening_balances']}،"
		f" تحصيل {report['collections']}، دفعات {report.get('repayments') or report['disbursements']}."
		f" المتبقي ليك دلوقتي {report['outstanding_receivable']}،"
		f" وعليك {report['outstanding_payable']}."
		" التحصيل والدفعات مش دخل أو صرف جديد. ومش رصيد كاش أو بنك."
	)


def query_all_people(result: dict) -> str:
	rows = result.get("people") or []
	if not rows:
		return "مفيش ناس متسجلين في الحساب."
	lines = [
		f"{index} - {row['person_name']}: ليه عندك {row['receivable']} جنيه، وعليك له {row['payable']} جنيه."
		for index, row in enumerate(rows, start=1)
	]
	return "حسابات الناس:\n" + "\n".join(lines)


def query_outstanding(result: dict) -> str:
	if not result.get("person_name"):
		return query_who_owes(result)
	name = result.get("person_name")
	if result.get("kind") == "outstanding_receivable":
		return (
			f"{name} لسه ليه {result['total']} جنيه."
			" الرقم شامل الحساب القديم وأي عملية لسه متتسددتش."
		)
	return (
		f"أنت عليك لـ {name} {result['total']} جنيه."
		" الرقم شامل الحساب القديم وأي عملية لسه متتسددتش."
	)


def query_who_owes(result: dict) -> str:
	rows = result.get("people") or []
	receivable = result.get("kind") == "outstanding_receivable"
	if not rows:
		return "مفيش حد ليه عندك فلوس دلوقتي." if receivable else "مفيش حد عليك له فلوس دلوقتي."
	field = "receivable" if receivable else "payable"
	header = "اللي ليه عندك:" if receivable else "اللي عليك لهم:"
	lines = [f"{index} - {row['person_name']}: {row[field]} جنيه" for index, row in enumerate(rows, start=1)]
	return f"{header}\n" + "\n".join(lines) + f"\nالإجمالي: {result['total']} جنيه."


def query_payments(result: dict) -> str:
	label = "تحصيل" if result.get("kind") == "collections" else "دفعات"
	person = f" مع {result['person_name']}" if result.get("person_name") else ""
	period = _period(result)
	if not result.get("count"):
		return f"مفيش {label} مسجلة{person}{period}."
	return f"{label}{person}{period}: {result['total']} جنيه."


def query_activity(result: dict) -> str:
	terms = " ".join(result.get("search_terms") or [])
	about = f" عن {terms}" if terms else ""
	period = _period(result)
	if not result.get("count"):
		return f"مفيش بيانات كافية{about}{period}."
	if result.get("mixed_types"):
		parts = [
			f"{TYPE_QUERY_AR.get(entry_type, entry_type)} {amount}"
			for entry_type, amount in (result.get("by_type") or {}).items()
		]
		return (
			f"لقيت {result['count']} عملية{about}{period}: "
			+ "، ".join(parts)
			+ " جنيه. مش هجمع الأنواع دي مع بعض."
		)
	label = {
		"income": "الدخل",
		"expense": "الصرف",
		"sale": "البيع",
		"purchase": "الشراء",
		"loan_receivable": "السلف للناس",
		"loan_payable": "السلف عليك",
		"opening_balance": "الحساب القديم",
		"search": "الإجمالي",
	}.get(result.get("kind"), "الإجمالي")
	return f"{label}{about}{period}: {result['total']} جنيه."


def query_search(total: str, count: int, terms: list[str]) -> str:
	return query_activity({"kind": "search", "total": total, "count": count, "search_terms": terms})


def _period(result: dict) -> str:
	if result.get("from_date") or result.get("to_date"):
		return f" من {result.get('from_date') or 'البداية'} لـ {result.get('to_date') or 'دلوقتي'}"
	return ""


def ask(question: str) -> str:
	return question


def confirm_cancel(preview: dict) -> str:
	entry = preview.get("preview", {}).get("entry") or {}
	return (
		f"هلغي {TYPE_AR.get(entry.get('entry_type'), 'العملية')}"
		f" بمبلغ {entry.get('amount')} جنيه. لو العمليات المرتبطة هتتلغي كمان."
		" أكّد بـ أيوه أو لأ."
	)


def confirm_correct(preview: dict) -> str:
	proposed = preview.get("preview", {}).get("proposed") or {}
	return (
		f"هصحح العملية لمبلغ {proposed.get('amount')} جنيه."
		" أكّد بـ أيوه أو لأ."
	)


def cancelled() -> str:
	return "اتلغت العملية، والسجل لسه موجود في الأرشيف."


def corrected(replacement: dict) -> str:
	return f"اتسجلت العملية المصححة بمبلغ {replacement.get('amount')} جنيه."


def not_saved() -> str:
	return "العملية متنفذتش."


def error_generic() -> str:
	return "حصلت مشكلة وأنا بسجل. العملية متنفذتش."


def llm_down() -> str:
	return "مقدرش أوصل للمساعد دلوقتي. جرب كمان شوية."


def llm_confused() -> str:
	return "ضحكتني، الجملة مش واضحة عليا. قولها تاني بهدوء؟"


def denied() -> str:
	return "ماشي، ملغيتش حاجة."


def status_ar(status: str) -> str:
	return {
		"Unpaid": "لسه متدفعتش",
		"Partially Paid": "اتدفع جزء",
		"Fully Paid": "اتدفعت بالكامل",
	}.get(status, status)
