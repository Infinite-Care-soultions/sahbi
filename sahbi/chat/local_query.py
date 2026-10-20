# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import re

from sahbi.chat.normalize import fold_arabic, word_amount

__all__ = ["fold_arabic", "parse_account_query", "parse_local_query", "parse_local_operation"]

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
	"باقي",
)
POSTING_MARKERS = (
	"اشتريت",
	"اشتري",
	"بعت",
	"بيعت",
	"دفعت",
	"سلفت",
	"استلفت",
	"اداني",
	"سدد",
	"سجل",
	"اتسجل",
	"صرفت",
	"صرفنا",
	"دخل لي",
)
SALE_WORDS = ("بعت", "بيعت", "بعتها", "بعته", "بيعنا")
PURCHASE_WORDS = ("اشتريت", "اشتري", "شرينا")
PAY_WORDS = ("دفعت", "اتدفعت")
EXPENSE_WORDS = ("صرفت", "صرفنا")
INCOME_WORDS = ("دخل",)
RECEIVE_WORDS = ("اداني", "اخدت", "قبضت")
LOAN_GIVE_WORDS = ("سلفت",)
LOAN_TAKE_WORDS = ("استلفت",)
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
	"الف",
	"الفين",
	"الاف",
	"ميه",
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
	if not folded or _looks_like_posting(folded):
		return None
	if _has_posting_verb(folded) and not _looks_like_question(folded):
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
				"مين عليه",
				"حسابات الناس",
				"حسابات",
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


def parse_local_operation(text: str) -> dict | None:
	folded = fold_arabic(text)
	if not folded:
		return None
	if _looks_like_question(folded) and not _extract_amount(folded):
		return None
	if _has_multiple_money_actions(folded):
		return None
	op_type = _operation_type(folded)
	if not op_type:
		return None
	amount = _extract_amount(folded)
	if not amount:
		return None
	person_name = None
	if op_type not in {"income", "expense"}:
		person_name = _extract_operation_person(folded, amount)
	if not person_name and op_type in {"loan_receivable", "loan_payable", "opening_receivable", "opening_payable"}:
		person_name = _guess_subject_person(folded, amount)
	if op_type in {"loan_receivable", "loan_payable", "opening_receivable", "opening_payable"} and not person_name:
		return None
	return {
		"type": op_type,
		"amount": amount,
		"person_name": person_name,
		"description": _extract_description(folded, amount, person_name),
		"date_expression": _date_expression(folded),
		"previous_operation_references": [],
		"loan_direction": "receivable"
		if op_type in {"loan_receivable", "opening_receivable"}
		else "payable"
		if op_type in {"loan_payable", "opening_payable"}
		else None,
	}


def _looks_like_posting(folded: str) -> bool:
	if _looks_like_question(folded):
		return False
	has_amount = bool(_extract_amount(folded))
	if "حساب قديم" in folded and has_amount:
		return True
	return any(marker in folded for marker in POSTING_MARKERS) and has_amount


def _has_posting_verb(folded: str) -> bool:
	tokens = _split_wa(folded)
	return any(
		word in tokens
		for word in SALE_WORDS + PURCHASE_WORDS + PAY_WORDS + EXPENSE_WORDS + LOAN_GIVE_WORDS + LOAN_TAKE_WORDS + RECEIVE_WORDS
	)


def _looks_like_question(folded: str) -> bool:
	return "كام" in folded or "بكام" in folded


def _has_multiple_money_actions(folded: str) -> bool:
	tokens = _split_wa(folded)
	verbs = 0
	for group in (SALE_WORDS, PURCHASE_WORDS, PAY_WORDS, EXPENSE_WORDS, LOAN_GIVE_WORDS, LOAN_TAKE_WORDS, INCOME_WORDS):
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
	if any(word in tokens for word in SALE_WORDS):
		return "sale"
	if any(word in tokens for word in PURCHASE_WORDS):
		return "purchase"
	if any(word in tokens for word in PAY_WORDS):
		return "outgoing_money"
	if any(word in tokens for word in EXPENSE_WORDS):
		return "expense"
	if "دخل لي" in folded:
		return "income"
	return None


def _is_all_people_query(folded: str) -> bool:
	if "حساب قديم" in folded or "الحسابات القديمه" in folded:
		return False
	return any(token in folded for token in ("حسابات الناس", "كل الحسابات", "حسابات الكل")) or "حسابات" in folded.split()


def _is_who_receivable(folded: str) -> bool:
	return any(
		token in folded
		for token in ("مين ليه", "مين عليه", "مين لسه ليه", "مين لسه عليه", "ليه فلوس", "مين ليه فلوس")
	)


def _is_who_payable(folded: str) -> bool:
	return any(token in folded for token in ("مين عليا", "عليا لمين"))


def _is_who_query(folded: str) -> bool:
	return _is_who_receivable(folded) or _is_who_payable(folded)


def _query_kind(folded: str) -> tuple[str | None, list[str]]:
	if any(token in folded for token in ("بنك", "جيب", "خزنه", "خزينه")):
		return "cash_or_bank", []
	if any(token in folded for token in ("ربحت", "مكسب", "مكسبنا", "ربح")):
		return "profit", []
	if ("حساب قديم" in folded or "الحسابات القديمه" in folded) and "كام" in folded:
		return "opening_balance", []
	if "دخل والمصروف" in folded or "الدخل والمصروف" in folded:
		return "income_expense", []
	if "وريني شغل" in folded or "شغل الشهر" in folded:
		return "period_report", []
	if _is_who_receivable(folded):
		return "outstanding_receivable", []
	if _is_who_payable(folded):
		return "outstanding_payable", []
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
		return "purchase", _search_terms(folded, PURCHASE_WORDS)
	if any(word in folded.split() for word in EXPENSE_WORDS) and "كام" in folded:
		return "expense", _search_terms(folded, EXPENSE_WORDS)
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
		if bare in {"نقل", "خشب", "مطبخ", "غراء"} and bare not in goods:
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
	if "الشهر ده" in folded:
		return "الشهر ده"
	if "الفتره دي" in folded:
		return "الفترة دي"
	if "النهاردة" in folded or "النهارده" in folded:
		return "النهاردة"
	if "امبارح" in folded:
		return "امبارح"
	return None


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
			return _join_name_tokens(tokens[index + 1 :], skip, amount, stop_at={"من", "مع"})
		if token.startswith("ل") and len(token) > 2:
			return _join_name_tokens([token[1:], *tokens[index + 1 :]], skip, amount, stop_at={"من", "مع"})
		if token.startswith("من") and len(token) > 3:
			return _join_name_tokens([token[2:], *tokens[index + 1 :]], skip, amount)
	if "خد مني" in folded:
		return _guess_subject_person(folded, amount)
	return None


def _guess_subject_person(folded: str, amount: str | None) -> str | None:
	skip = _op_skip() | STOP_WORDS | {"خد", "مني", "اديت", "سلفه"}
	return _join_name_tokens(folded.split(), skip, amount)


def _op_skip() -> set[str]:
	return (
		OPERATION_SKIP
		| set(SALE_WORDS)
		| set(PURCHASE_WORDS)
		| set(PAY_WORDS)
		| set(RECEIVE_WORDS)
		| set(EXPENSE_WORDS)
		| set(INCOME_WORDS)
		| set(LOAN_GIVE_WORDS)
		| set(LOAN_TAKE_WORDS)
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
		if token in QUESTION_MARKERS:
			break
		if re.match(r"^\d", token):
			if amount and token.replace(",", ".") == amount:
				continue
			names.append(token)
			continue
		names.append(token)
		if len(names) >= 3:
			break
	return " ".join(names) if names else None


def _extract_description(folded: str, amount: str | None, person_name: str | None) -> str | None:
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
	return " ".join(tokens) if tokens else None
