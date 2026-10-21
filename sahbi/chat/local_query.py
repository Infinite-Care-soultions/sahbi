# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import re

from sahbi.chat.normalize import clean_person_name, fold_arabic, word_amount
from sahbi.chat.categorize_items.expense_items import EXPENSE_ITEMS, is_expense_item
__all__ = [
	"fold_arabic",
	"looks_like_question",
	"parse_account_query",
	"parse_local_query",
	"parse_local_operation",
	"parse_local_operations",
]

ACCOUNT_MARKERS = (
	"حساب",
	"حسابه",
	"حسابها",
	"كشف حساب",
	"كشف",
	"تفاصيل حساب",
	"تفاصيل",
	"لسه ليه",
	"ليه كام",
	"عليه كام",
	"عليا كام",
	"متبقي",
	"المتبقي",
	"باقي عليه",
	"الباقي عليه",
)
POSTING_MARKERS = (
	"اشتريت",
	"اشتري",
	"اشترينا",
	"بعت",
	"بيعت",
	"دفعت",
	"دفع",
	"سلفت",
	"استلفت",
	"اداني",
	"سدد",
	"رجعلي",
	"رجع",
	"سجل",
	"اتسجل",
	"صرفت",
	"صرفنا",
	"حطيت",
	"حطينا",
	"فلوت",
	"فليت",
	"فلت",
	"عبيت",
	"عبينا",
	"جبت",
	"جبنا",
	"اتشريت",
	"اتشري",
	"مصروف",
	"مصاريف",
	"دخل لي",
	"دخل",
	"سلف",
	"سلفه",
)
SALE_WORDS = ( "بعت", "بيعت", "بعتها", "بعته", "بيعنا", "بعنا",
    # Past tense variants (I/we/he/she/they sold)
    "بعتوا", "باعوا", "باع", "باعت", "باعو", "بعتلك", "بعتلكم",
    "بعتلهم", "بعتوه", "بعتيه", "باعتها", "باعته", "باعوها",
    # "Sold" passive / state
    "مباع", "مبيوع", "مباعة", "مبيوعة", "اتباع", "اتبيعت", "اتبعو",
    # Noun forms (sale / selling)
    "بيع", "بيوع", "مبيعات", "بيعناها", "البيع", "للبيع", "بيعه",
    # Imperative / offers (sell it!)
    "بيعلي", "بيعوه", "بيعوها", "بيعيهم",
    # Common deal phrases
    "تم البيع", "اتبيع", "اتباعت", "خلصان", "مباعه",)
PURCHASE_WORDS = ("اشتريت", "اشتري", "اشترينا", "شرينا", "اتشريت", "اتشري")
PAY_WORDS = ("دفعت", "اتدفعت")
EXPENSE_WORDS = ("صرفت", "صرفنا", "حطيت", "حطينا", "فلوت", "فليت", "فلت", "عبيت", "عبينا")
EXPENSE_GET_WORDS = ("جبت", "جبنا", "اتشريت", "اتشري")
EXPENSE_NOUNS = ("مصروف", "مصاريف")
INCOME_WORDS = ("دخل",)
RECEIVE_WORDS = ("اداني", "اخدت", "قبضت" ,"قبضنا" )
LOAN_GIVE_WORDS = ("سلفت",)
LOAN_TAKE_WORDS = ("استلفت",)
LOAN_NOUN_WORDS = ("سلفه", "سلف")
SETTLE_IN_WORDS = ("سدد", "دفع", "دفعلي", "رجعلي", "رجع", "رجعت", "قسط", "قسطلي")
LAST_PERSON_MARKERS = ("ليه", "له", "ليها", "ليهم", "لها", "لنفسو", "لنفسه")
POSTING_VERB_WORDS = (
	SALE_WORDS
	+ PURCHASE_WORDS
	+ PAY_WORDS
	+ EXPENSE_WORDS
	+ EXPENSE_GET_WORDS
	+ LOAN_GIVE_WORDS
	+ LOAN_TAKE_WORDS
	+ LOAN_NOUN_WORDS
	+ RECEIVE_WORDS
	+ SETTLE_IN_WORDS
	+ INCOME_WORDS
)
PERSON_LINKED_TYPES = {
	"purchase",
	"sale",
	"loan_receivable",
	"loan_payable",
	"opening_receivable",
	"opening_payable",
	"incoming_money",
	"outgoing_money",
}
ALLOCATABLE_TYPES = {
	"purchase",
	"sale",
	"loan_receivable",
	"loan_payable",
	"opening_receivable",
	"opening_payable",
}
GOODS_STOP = {
	"خشب",
	"مطبخ",
	"غراء",
	"كرسي",
	"دولاب",
	"باب",
	"شباك",
	"نقل",
}
CANCEL_WORDS = ("الغي", "الغاء", "الغى", "الغيها", "الغيته", "الغيه")
CANCEL_ENTRY_TYPES = {
	"مصروف": "Expense",
	"المصروف": "Expense",
	"دخل": "Income",
	"الدخل": "Income",
	"بيع": "Sale",
	"البيع": "Sale",
	"شراء": "Purchase",
	"الشراء": "Purchase",
	"سلفه": "Loan",
	"السلفه": "Loan",
	"سلف": "Loan",
	"السلف": "Loan",
}
QUESTION_MARKERS = ("كام", "بكام")
GLUED_PREP_STOP = {"لسه", "لكن", "لل", "لي", "لك", "لو", "لما", "ليه", "لان", "لانك"}
OPERATION_SKIP = {
	"جنيه",
	"جني",
	"ج",
	"ب",
	"انا",
	"اليوم",
	"النهاردة",
	"النهارده",
	"امبارح",
	"كده",
	"يا",
	"من",
	"علي",
	"على",
	"حساب",
	"قديم",
	"قديه",
	"سلفه",
	"السلفه",
	"سلف",
	"السلف",
	"الف",
	"الفين",
	"الاف",
	"ميه",
	"عايز",
	"عايزه",
	"اضيف",
	"اضيفه",
	"سجل",
	"صح",
	"كدة",
}
STOP_WORDS = {
	"قولي",
	"قوليلي",
	"قول",
	"قلي",
	"لي",
	"كشف",
	"كشوف",
	"بيان",
	"تفاصيل",
	"حساب",
	"حسابه",
	"حسابها",
	"كام",
	"بكام",
	"النهاردة",
	"النهارده",
	"بتاع",
	"بتاعه",
	"بتاعت",
	"يا",
	"عايز",
	"عايزه",
	"عاوز",
	"اعرف",
	"وريني",
	"شوف",
	"مين",
	"ليا",
	"ليه",
	"فلوس",
	"عنده",
	"عندي",
	"عند",
	"عليا",
	"عليه",
	"حساباتي",
	"حساباتى",
	"حسابات",
	"حسابي",
	"البيوع",
	"مبيعات",
	"المبيعات",
	"المشتريات",
	"مشتريات",
	"الدخل",
	"الشهر",
	"ايه",
	"هو",
	"هي",
	"في",
	"من",
	"على",
	"علي",
	"لسه",
	"ليه",
	"عليا",
	"عليه",
	"انا",
	"أنا",
	"قديم",
	"قديه",
	"كده",
	"بقا",
	"بقى",
	"بخصوص",
	"عن",
	"الشهر",
	"ده",
	"فات",
	"الماضي",
	"الفتره",
	"دي",
	"عندي",
	"فلوس",
	"مين",
	"شغل",
	"الحسابات",
	"حسابات",
	"الناس",
	"الكل",
	"القديمه",
	"حصلت",
	"تحصيل",
	"العمال",
	"عمال",
	"معايا",
	"البنك",
	"الجيب",
	"مصاريف",
	"المصاريف",
	"المصروف",
	"مصروف",
	"الصرف",
	"مشتريات",
	"المشتريات",
	"الشراء",
	"اعرض",
	"اظهر",
	"عرض",
	"كدة",
	"باقي",
	"فاضل",
	"فلوسي",
	"لو",
	"ازاي",
	"ازاى",
	"اعرفها",
	"اعرفهم",
	"اضيف",
	"اضيفه",
	"صح",
	"كان",
}
PERSON_QUERY_KINDS = {
	"person_balance",
	"outstanding_receivable",
	"outstanding_payable",
	"collections",
	"repayments",
}


def parse_account_query(text: str) -> dict | None:
	return parse_local_query(text)


def parse_local_query(text: str) -> dict | None:
	folded = fold_arabic(text)
	if not folded or _looks_like_posting(folded) or _is_cancellation(folded):
		return None
	if (
		_has_posting_verb(folded)
		and not _looks_like_question(folded)
		and not _is_listing_query(folded)
	):
		return None
	if (
		not _looks_like_question(folded)
		and not any(marker in folded for marker in ACCOUNT_MARKERS)
		and not any(
			token in folded
			for token in (
				"وريني شغل",
				"شغل الشهر",
				"الدخل والمصروف",
				"دخل والمصروف",
				"مين لسه",
				"مين ليه",
				"مين ليا",
				"مين عليه",
				"حسابات الناس",
				"حسابات",
				"حساباتي",
				"حساباتى",
				"وريني",
				"البيوع",
				"مبيعات",
				"المبيعات",
				"الدخل",
				"دخل",
				"مصاريف",
				"المصاريف",
				"المصروف",
				"مشتريات",
				"المشتريات",
				"اعرض",
				"معايا",
				"صرفت",
			)
		)
	):
		return None

	kind, terms = _query_kind(folded)
	if not kind:
		return None

	all_people = _is_all_people_query(folded)
	who = _is_who_query(folded)
	person_name = None
	if kind in PERSON_QUERY_KINDS and not all_people and not who:
		person_name = _extract_person_name(folded)
	if kind == "loan_receivable" and "عمال" in folded:
		person_name = None
	return {
		"kind": kind,
		"search_terms": terms,
		"person_name": person_name,
		"date_expression": _date_expression(folded),
		"use_last_person": person_name is None and ("حسابه" in folded or "حسابها" in folded) and not all_people and not who,
		"needs_person": person_name is None
		and kind in {"person_balance", "outstanding_receivable", "outstanding_payable"}
		and not all_people
		and not who,
	}


def parse_local_operations(text: str) -> list[dict]:
	folded = fold_arabic(text)
	if not folded:
		return []
	clauses = _split_compound_clauses(folded)
	if len(clauses) >= 2:
		operations = _operations_from_clauses(clauses)
		if len(operations) >= 2:
			return operations
	chunks = _amount_chunks(folded)
	if len(chunks) >= 2:
		operations = []
		for label, amount in chunks:
			operation = _operation_from_chunk(label, amount, multi=True)
			if operation:
				operations.append(operation)
		return _link_compound_operations(operations)
	operation = parse_local_operation(text)
	return [operation] if operation else []


def parse_local_operation(text: str) -> dict | None:
	folded = fold_arabic(text)
	if not folded:
		return None
	if len(_amount_chunks(folded)) >= 2:
		return None
	if _looks_like_question(folded) and not _extract_amount(folded):
		return None
	if _has_multiple_money_actions(folded):
		return None
	if _is_cancellation(folded):
		return _cancellation_operation(folded)
	op_type = _operation_type(folded)
	if not op_type:
		return None
	amount = _extract_amount(folded)
	if not amount:
		return None
	person_name = None
	if op_type not in {"income", "expense"}:
		person_name = _extract_operation_person(folded, amount)
	if not person_name and op_type in {"loan_receivable", "loan_payable", "opening_receivable", "opening_payable", "incoming_money"}:
		person_name = _guess_subject_person(folded, amount)
	if _not_a_person_name(person_name):
		person_name = None
	return _operation_payload(op_type, amount, person_name, folded)


def _operation_payload(op_type: str, amount: str, person_name: str | None, folded: str) -> dict:
	return {
		"type": op_type,
		"amount": amount,
		"person_name": person_name,
		"description": _extract_description(folded, amount, person_name),
		"date_expression": _date_expression(folded),
		"previous_operation_references": ["السلفة"] if op_type == "incoming_money" and ("سلفه" in folded or "السلف" in folded) else [],
		"use_last_person": _uses_last_person(folded) and not person_name,
		"loan_direction": "receivable"
		if op_type in {"loan_receivable", "opening_receivable"}
		else "payable"
		if op_type in {"loan_payable", "opening_payable"}
		else None,
	}


def _operation_from_chunk(label: str, amount: str, multi: bool = False) -> dict | None:
	folded = fold_arabic(f"{label} {amount}".strip())
	op_type = _operation_type(folded)
	if not op_type and (_has_expense_item(folded) or (multi and fold_arabic(label))):
		op_type = "expense"
	if not op_type:
		return None
	person_name = None
	if op_type not in {"income", "expense"}:
		person_name = _extract_operation_person(folded, amount)
	if not person_name and op_type in {"loan_receivable", "loan_payable", "opening_receivable", "opening_payable", "incoming_money"}:
		person_name = _guess_subject_person(folded, amount)
	if _not_a_person_name(person_name):
		person_name = None
	if multi and _has_expense_item(folded) and op_type not in PERSON_LINKED_TYPES:
		person_name = None
	if op_type in {"loan_receivable", "loan_payable"} and (_has_expense_item(folded) or _looks_like_expense_label(label)) and not person_name:
		op_type = "expense"
		person_name = None
	return _operation_payload(op_type, amount, person_name, folded)


def _looks_like_expense_label(label: str) -> bool:
	folded = fold_arabic(label)
	return _has_expense_item(folded) or any(token in EXPENSE_NOUNS for token in folded.split())


def _not_a_person_name(name: str | None) -> bool:
	if not name:
		return True
	folded = fold_arabic(name)
	if not folded or folded in {"صح", "انا", "كده", "كدة", "كان", "كام"}:
		return True
	return all(_bare_expense_item(token) or token.isdigit() or token in STOP_WORDS for token in folded.split())


def _is_cancellation(folded: str) -> bool:
	tokens = folded.split()
	return any(token in CANCEL_WORDS or token.startswith("الغي") for token in tokens)


def _cancellation_operation(folded: str) -> dict:
	tokens = folded.split()
	hint = next((CANCEL_ENTRY_TYPES[token] for token in tokens if token in CANCEL_ENTRY_TYPES), None)
	return {
		"type": "cancellation",
		"amount": _extract_amount(folded),
		"person_name": None,
		"description": None,
		"date_expression": None,
		"previous_operation_references": [],
		"loan_direction": None,
		"target_entry_type": hint,
	}


def _looks_like_posting(folded: str) -> bool:
	if _looks_like_question(folded):
		return False
	has_amount = bool(_extract_amount(folded))
	if "حساب قديم" in folded and has_amount:
		return True
	if _is_loan_noun_posting(folded) and has_amount:
		return True
	return any(marker in folded for marker in POSTING_MARKERS) and has_amount


def _has_posting_verb(folded: str) -> bool:
	tokens = _split_wa(folded)
	return any(
		word in tokens
		for word in SALE_WORDS + PURCHASE_WORDS + PAY_WORDS + EXPENSE_WORDS + EXPENSE_GET_WORDS + LOAN_GIVE_WORDS + LOAN_TAKE_WORDS + LOAN_NOUN_WORDS + RECEIVE_WORDS + SETTLE_IN_WORDS
	)


def looks_like_question(text: str) -> bool:
	return _looks_like_question(fold_arabic(text or ""))


def _looks_like_question(folded: str) -> bool:
	return "كام" in folded or "بكام" in folded


def _has_multiple_money_actions(folded: str) -> bool:
	tokens = _split_wa(folded)
	verbs = 0
	for group in (SALE_WORDS, PURCHASE_WORDS, PAY_WORDS, EXPENSE_WORDS, LOAN_GIVE_WORDS, LOAN_TAKE_WORDS, LOAN_NOUN_WORDS, INCOME_WORDS):
		if any(word in tokens for word in group):
			verbs += 1
	return verbs >= 2


def _split_wa(folded: str) -> list[str]:
	tokens = []
	for token in folded.split():
		if token.startswith("و") and len(token) > 2:
			tokens.append(token[1:])
		else:
			tokens.append(token)
	return tokens


def _operation_type(folded: str) -> str | None:
	if "حساب قديم" in folded:
		if any(token in folded for token in ("عليا", "انا علي")):
			return "opening_payable"
		return "opening_receivable"
	tokens = folded.split()
	if "خد مني" in folded or (("اديت" in tokens or "سلفت" in tokens) and "سلفه" in folded):
		return "loan_receivable"
	if any(word in tokens for word in LOAN_GIVE_WORDS) or "اديت" in tokens:
		return "loan_receivable"
	if any(word in tokens for word in LOAN_TAKE_WORDS):
		return "loan_payable"
	if _is_loan_noun_posting(folded):
		return "loan_payable" if _loan_taken_from_person(folded) else "loan_receivable"
	if any(word in tokens for word in SETTLE_IN_WORDS):
		return "incoming_money"
	if any(word in tokens for word in SALE_WORDS):
		return "sale"
	if any(word in tokens for word in ("جبت", "جبنا")):
		return "incoming_money" if _loan_taken_from_person(folded) else "expense"
	if any(word in tokens for word in PURCHASE_WORDS) and _has_supplier_person(folded):
		return "purchase"
	if _has_expense_item(folded) and any(word in tokens for word in PURCHASE_WORDS + EXPENSE_GET_WORDS):
		return "expense"
	if any(word in tokens for word in PURCHASE_WORDS):
		return "purchase"
	if any(word in tokens for word in PAY_WORDS):
		return "outgoing_money"
	if any(word in tokens for word in EXPENSE_WORDS + EXPENSE_NOUNS):
		return "expense"
	if "دخل لي" in folded or any(word in tokens for word in INCOME_WORDS):
		return "income"
	if _has_expense_item(folded):
		return "expense"
	return None


def _has_expense_item(folded: str) -> bool:
	return any(is_expense_item(token) or _bare_expense_item(token) for token in _split_wa(folded))


def _expense_item_terms(folded: str) -> list[str]:
	terms = []
	for token in folded.split():
		item = _bare_expense_item(token)
		if item and item not in terms:
			terms.append(item)
	return terms


def _bare_expense_item(token: str) -> str | None:
	if token in EXPENSE_ITEMS:
		return token[2:] if token.startswith("ال") and token[2:] in EXPENSE_ITEMS else token
	if token.startswith("ال") and token[2:] in EXPENSE_ITEMS:
		return token[2:]
	return None


def _is_loan_noun_posting(folded: str) -> bool:
	tokens = folded.split()
	if not any(token in LOAN_NOUN_WORDS for token in tokens):
		return False
	if tokens[0] in LOAN_NOUN_WORDS:
		return True
	return "من السلفه" not in folded and "من السلف" not in folded


def _loan_taken_from_person(folded: str) -> bool:
	tokens = folded.split()
	skip = {"سلفه", "السلفه", "سلف", "السلف"}
	for index, token in enumerate(tokens):
		if token == "من" and index + 1 < len(tokens) and tokens[index + 1] not in skip:
			return True
		if token.startswith("من") and len(token) > 3 and token[2:] not in skip:
			return True
	return False


def _is_all_people_query(folded: str) -> bool:
	if "حساب قديم" in folded or "الحسابات القديمه" in folded:
		return False
	return any(
		token in folded
		for token in (
			"حسابات الناس",
			"كل الحسابات",
			"حسابات الكل",
			"حساباتي",
			"حساباتى",
			"حسابي",
			"اعرض الحساب",
			"عرض الحساب",
			"وريني الحساب",
			"شوف الحساب",
		)
	) or folded in {"الحساب", "الحسابات"} or "حسابات" in folded.split()


def _is_who_payable(folded: str) -> bool:
	return any(
		token in folded
		for token in ("مين ليه فلوس عندي", "ليه فلوس عندي", "مين عليا", "عليا لمين")
	)


def _is_who_receivable(folded: str) -> bool:
	if _is_who_payable(folded):
		return False
	if "مين ليا" in folded or ("ليا" in folded and "عنده" in folded) or "ليك عنده" in folded:
		return True
	return any(
		token in folded
		for token in ("مين ليه", "مين عليه", "مين لسه ليه", "مين لسه عليه", "ليه فلوس", "مين ليه فلوس")
	)


def _is_who_query(folded: str) -> bool:
	return _is_who_receivable(folded) or _is_who_payable(folded)


def _is_cash_on_hand(folded: str) -> bool:
	pocket = any(token in folded for token in ("معايا", "جيبي", "الجيب", "معاي"))
	if not pocket:
		return False
	return any(token in folded for token in ("فلوس", "باقي", "فاضل", "كام", "كان", "جنيه", "جني", "كاش", "رصيد"))


def _is_listing_query(folded: str) -> bool:
	return any(
		token in folded
		for token in (
			"وريني",
			"الشهر",
			"المبيعات",
			"مبيعات",
			"البيوع",
			"المشتريات",
			"المصاريف",
			"الدخل",
			"حساباتي",
			"حساباتى",
		)
	)


def _is_expense_topic(folded: str) -> bool:
	if "دخل والمصروف" in folded or "الدخل والمصروف" in folded:
		return False
	tokens = folded.split()
	return any(token in {"مصاريف", "المصاريف", "المصروف", "مصروف", "الصرف", "صرفت"} for token in tokens)


def _is_purchase_topic(folded: str) -> bool:
	tokens = folded.split()
	return any(token in {"مشتريات", "المشتريات", "مشترياتي"} for token in tokens)


def _is_sale_topic(folded: str) -> bool:
	tokens = folded.split()
	return any(token in {"بيع", "البيوع", "مبيعات", "المبيعات", "بيوع"} for token in tokens)


def _is_income_topic(folded: str) -> bool:
	tokens = folded.split()
	return any(token in {"دخل", "الدخل", "ايراد", "الايراد"} for token in tokens)


def _query_kind(folded: str) -> tuple[str | None, list[str]]:
	if any(token in folded for token in ("بنك", "جيب", "خزنه", "خزينه")):
		return "cash_or_bank", []
	if _is_cash_on_hand(folded):
		return "cash_or_bank", []
	if any(token in folded for token in ("ربحت", "مكسب", "مكسبنا", "ربح")):
		return "profit", []
	if ("حساب قديم" in folded or "الحسابات القديمه" in folded) and "كام" in folded:
		return "opening_balance", []
	if "دخل والمصروف" in folded or "الدخل والمصروف" in folded:
		return "income_expense", []
	if _is_expense_topic(folded):
		return "expense", _expense_item_terms(folded)
	if _is_purchase_topic(folded):
		return "purchase", []
	if _is_sale_topic(folded):
		return "sale", []
	if _is_income_topic(folded):
		return "income", []
	if "ليا عند" in folded or "ليك عند" in folded:
		return "outstanding_receivable", []
	if _has_expense_item(folded) and _looks_like_question(folded):
		tokens = folded.split()
		if not any(word in tokens for word in EXPENSE_WORDS + EXPENSE_GET_WORDS + PURCHASE_WORDS + SALE_WORDS):
			return "expense", _expense_item_terms(folded)
	if "وريني شغل" in folded or "شغل الشهر" in folded:
		return "period_report", []
	if _is_who_payable(folded):
		return "outstanding_payable", []
	if _is_who_receivable(folded):
		return "outstanding_receivable", []
	if _is_all_people_query(folded):
		return "person_balance", []
	if "حصلت" in folded or "تحصيل" in folded:
		return "collections", []
	if ("دفعت" in folded or "سددت" in folded) and "كام" in folded:
		return "repayments", []
	if any(token in folded for token in ("لسه ليه", "ليه كام", "ليه عندي", "لسه عليه", "مين لسه عليه", "مين ليه", "ليه فلوس")):
		return "outstanding_receivable", []
	if folded.split()[:2] == ["عليه", "كام"] or "عليه كام" == folded:
		return "outstanding_payable", []
	if any(token in folded for token in ("عليا ل", "انا علي", "علي ل", "عليا كام")):
		return "outstanding_payable", []
	if "استلفت" in folded and "كام" in folded:
		return "loan_payable", []
	if "سلفت" in folded and "كام" in folded:
		return "loan_receivable", []
	if any(word in folded.split() for word in SALE_WORDS) and ("كام" in folded or "بكام" in folded):
		return "sale", _search_terms(folded, SALE_WORDS)
	if any(word in folded.split() for word in PURCHASE_WORDS) and ("كام" in folded or "بكام" in folded):
		if _has_expense_item(folded):
			return "expense", _search_terms(folded, PURCHASE_WORDS + EXPENSE_GET_WORDS)
		return "purchase", _search_terms(folded, PURCHASE_WORDS)
	if any(word in folded.split() for word in EXPENSE_WORDS + EXPENSE_GET_WORDS) and "كام" in folded:
		return "expense", _search_terms(folded, EXPENSE_WORDS + EXPENSE_GET_WORDS)
	if "دخل" in folded and "كام" in folded:
		return "income", []
	if any(marker in folded for marker in ACCOUNT_MARKERS):
		if any(token in folded for token in ("لسه ليه", "ليه كام", "ليه عندي")):
			return "outstanding_receivable", []
		if any(token in folded for token in ("عليا ل", "انا علي", "علي ل", "عليه كام")):
			return "outstanding_payable", []
		return "person_balance", []
	return None, []


def _search_terms(folded: str, verbs) -> list[str]:
	skip = STOP_WORDS | set(verbs) | OPERATION_SKIP | set(QUESTION_MARKERS)
	goods = []
	for token in folded.split():
		bare = token[2:] if token.startswith("ال") and len(token) > 3 else token
		if bare in {"نقل", "خشب", "مطبخ", "غراء", "بنزين", "جاز", "غاز", "وقود", "سولار", "اكل", "لحم", "لحمه", "فراخ"} and bare not in goods:
			goods.append(bare)
	if goods:
		return goods
	terms = []
	for token in folded.split():
		if token in skip or token.isdigit() or len(token) < 3:
			continue
		terms.append(token)
	return terms[:2]


def _date_expression(folded: str) -> str | None:
	if "الشهر اللي فات" in folded or "الشهر الماضي" in folded:
		return "الشهر اللي فات"
	if "الشهر ده" in folded or ("الشهر" in folded and "فات" not in folded and "الماضي" not in folded):
		return "الشهر ده"
	if "الفتره دي" in folded:
		return "الفترة دي"
	if "النهاردة" in folded or "النهارده" in folded:
		return "النهاردة"
	if "امبارح" in folded:
		return "امبارح"
	return None


def _uses_last_person(folded: str) -> bool:
	tokens = folded.split()
	return any(token in LAST_PERSON_MARKERS for token in tokens)


def _has_supplier_person(folded: str) -> bool:
	return not _not_a_person_name(_extract_operation_person(folded))


def _split_compound_clauses(folded: str) -> list[str]:
	tokens = _split_wa(folded)
	clauses = []
	current = []
	for token in tokens:
		if token in POSTING_VERB_WORDS and current and _extract_amount(" ".join(current)):
			clauses.append(" ".join(current))
			current = [token]
		else:
			current.append(token)
	if current:
		clauses.append(" ".join(current))
	return clauses


def _operations_from_clauses(clauses: list[str]) -> list[dict]:
	operations = []
	for clause in clauses:
		operation = parse_local_operation(clause)
		if operation:
			operations.append(operation)
	return _link_compound_operations(operations)


def _link_compound_operations(operations: list[dict]) -> list[dict]:
	last_person = None
	last_allocatable = None
	for operation in operations:
		if not operation.get("person_name") and last_person and (
			operation.get("use_last_person") or operation.get("type") in {"incoming_money", "outgoing_money"}
		):
			operation["person_name"] = last_person
		if operation.get("person_name"):
			last_person = operation["person_name"]
		if (
			operation.get("type") in {"incoming_money", "outgoing_money"}
			and last_allocatable
			and not operation.get("previous_operation_references")
		):
			operation["previous_operation_references"] = [last_allocatable]
		if operation.get("type") in ALLOCATABLE_TYPES:
			last_allocatable = operation["type"]
	return operations


def _amount_chunks(folded: str) -> list[tuple[str, str]]:
	tokens = []
	for token in _split_wa(folded):
		if token.startswith("ب") and len(token) > 1 and token[1].isdigit():
			tokens.append("ب")
			tokens.append(token[1:])
		else:
			tokens.append(token)
	chunks = []
	current = []
	for token in tokens:
		if re.match(r"^\d+(?:[.,]\d+)?$", token):
			label = " ".join(part for part in current if part not in {"ب"}).strip()
			if label:
				chunks.append((label, _format_amount(token)))
			current = []
		else:
			current.append(token)
	return chunks


def _extract_amount(folded: str) -> str | None:
	match = re.search(r"ب\s*(\d+(?:[.,]\d+)?)", folded)
	if match:
		return _format_amount(match.group(1))
	match = re.search(r"(\d+(?:[.,]\d+)?)\s*جني", folded)
	if match:
		return _format_amount(match.group(1))
	words = word_amount(folded)
	if words:
		return words
	numbers = re.findall(r"\d+(?:[.,]\d+)?", folded)
	if not numbers:
		return None
	raw = numbers[-1]
	if "," in raw and "." not in raw and len(raw.split(",")[-1]) == 3:
		raw = raw.replace(",", "")
	return _format_amount(raw)


def _format_amount(raw: str) -> str:
	return raw.replace(",", ".")


def _extract_operation_person(folded: str, amount: str | None = None) -> str | None:
	tokens = folded.split()
	skip = _op_skip()
	for index, token in enumerate(tokens):
		if token in GLUED_PREP_STOP:
			continue
		if token in {"من", "مع", "ل"} and index + 1 < len(tokens):
			nxt = tokens[index + 1]
			if nxt in {"حساب", "السلفه", "السلف", "سلفه"}:
				continue
			return _join_name_tokens(
				tokens[index + 1 :],
				skip,
				amount,
				stop_at={"من", "مع", "ب"} | set(POSTING_VERB_WORDS),
			)
		if token.startswith("ل") and len(token) > 2:
			return _join_name_tokens(
				[token[1:], *tokens[index + 1 :]],
				skip,
				amount,
				stop_at={"من", "مع", "ب"} | set(POSTING_VERB_WORDS),
			)
		if token.startswith("من") and len(token) > 3:
			return _join_name_tokens([token[2:], *tokens[index + 1 :]], skip, amount)
	if "خد مني" in folded:
		return _guess_subject_person(folded, amount)
	return None


def _guess_subject_person(folded: str, amount: str | None) -> str | None:
	skip = _op_skip() | STOP_WORDS | set(SETTLE_IN_WORDS) | {"خد", "مني", "اديت", "سلفه", "حساب"}
	return _join_name_tokens(folded.split(), skip, amount)


def _op_skip() -> set[str]:
	return (
		OPERATION_SKIP
		| set(SALE_WORDS)
		| set(PURCHASE_WORDS)
		| set(PAY_WORDS)
		| set(RECEIVE_WORDS)
		| set(EXPENSE_WORDS)
		| set(EXPENSE_GET_WORDS)
		| set(EXPENSE_NOUNS)
		| set(INCOME_WORDS)
		| set(LOAN_GIVE_WORDS)
		| set(LOAN_TAKE_WORDS)
		| set(SETTLE_IN_WORDS)
	)


def _join_name_tokens(tokens: list[str], skip: set[str], amount: str | None = None, stop_at: set[str] | None = None) -> str | None:
	names = []
	for token in tokens:
		if stop_at and token in stop_at and names:
			break
		if token in skip:
			continue
		if amount and token.replace(",", ".") == amount:
			continue
		if token in QUESTION_MARKERS or token in {"صح", "كان"}:
			break
		if is_expense_item(token) or _bare_expense_item(token) or token in GOODS_STOP:
			if names:
				break
			continue
		if re.match(r"^\d", token):
			if amount and _format_amount(token.replace(",", ".")) == amount:
				continue
			if names and len(token) <= 2:
				names.append(token)
			continue
		names.append(token)
		if len(names) >= 3:
			break
	return clean_person_name(" ".join(names)) if names else None


def _extract_description(folded: str, amount: str | None, person_name: str | None) -> str | None:
	items = [item for token in folded.split() if (item := _bare_expense_item(token))]
	if items:
		return items[0]
	skip = _op_skip() | STOP_WORDS
	person_parts = set((person_name or "").split())
	tokens = []
	for token in folded.split():
		if token in skip or token in person_parts:
			continue
		if amount and token.replace(",", ".") == amount:
			continue
		if re.match(r"^\d", token) or (token.startswith("ب") and token[1:2].isdigit()):
			continue
		if token in {"حساب", "قديم"}:
			continue
		tokens.append(token)
	return " ".join(tokens[:3]) if tokens else None


def _extract_person_name(folded: str) -> str | None:
	tokens = []
	for token in folded.split():
		if not token or token in STOP_WORDS or token.isdigit():
			continue
		if token.startswith("ل") and len(token) > 2 and token not in GLUED_PREP_STOP:
			token = token[1:]
		tokens.append(token)
	return clean_person_name(" ".join(tokens)) if tokens else None
