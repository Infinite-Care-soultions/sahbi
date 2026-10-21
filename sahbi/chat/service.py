# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import json
import re

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from sahbi.chat import replies
from sahbi.chat.desk import HANDED_OFF_REPLY, can_ai_reply, touch_inbound
from sahbi.chat.dates import parse_date_expression
from sahbi.chat.local_query import (
	fold_arabic,
	looks_like_question,
	parse_local_operation,
	parse_local_operations,
	parse_local_query,
)
from sahbi.chat.normalize import clean_person_name
from sahbi.engine import (
	AmbiguousSettlement,
	cancel_entry,
	correct_entry,
	create_expense,
	create_income,
	create_loan,
	create_opening_balance,
	create_purchase,
	create_sale,
	record_incoming_money,
	record_outgoing_money,
	run_financial_query,
)
from sahbi.engine.utils import PersonNotFound, resolve_person
from sahbi.llm.errors import SahbiLLMInvalidOutput, SahbiLLMUnavailable
from sahbi.llm.service import interpret_message
from sahbi.money import to_money
from sahbi.permissions import assert_workspace_access
from sahbi.workspace import get_user_workspace

CONFIRM_WORDS = {
	"ايوه",
	"أيوه",
	"ايوة",
	"أيوة",
	"ايوا",
	"أيوا",
	"اه",
	"آه",
	"نعم",
	"تمام",
	"أكد",
	"اكد",
	"اكيد",
	"أكيد",
	"نفذ",
	"ماشي",
	"حاضر",
	"يلا",
	"صح",
	"اوك",
	"اوكي",
	"okay",
	"yes",
	"y",
	"ok",
}
ADD_PERSON_WORDS = {
	"ضيفه",
	"ضيفها",
	"ضيف",
	"اضيفه",
	"أضيفه",
	"اضيف",
	"أضيف",
	"ضيفوا",
	"زوده",
	"زود",
	"سجله",
	"سجل",
}
DENY_WORDS = {
	"لا",
	"لأ",
	"لاء",
	"لاه",
	"بلاش",
	"الغاء",
	"الغي",
	"إلغاء",
	"متضيفش",
	"cancel",
	"no",
}
FILLER_WORDS = {"يا", "صاحبي", "كده", "خلاص", "بقا", "بقى"}
INCOME_WORDS = {"دخل", "ايراد", "إيراد", "هدية"}
LOAN_WORDS = {"سلفة", "سلفه", "استلفت", "قرض"}
SETTLE_WORDS = {"تسديد", "سدد", "تحصيل", "قسط"}
GREETINGS = {
	"مساء الفل",
	"مساء الخير",
	"صباح الخير",
	"صباح الفل",
	"ازيك",
	"ازيك يا صاحبي",
	"ازاى",
	"ازاي",
	"اهلا",
	"أهلا",
	"اهلاً",
	"أهلاً",
	"السلام عليكم",
	"سلام",
	"هاي",
	"hello",
	"hi",
	"شكرا",
	"شكراً",
	"ميرسي",
	"عامل ايه",
	"عامل ايه النهاردة",
	"عامل ايه يا صاحبي",
	"اخبارك",
}
THANKS_WORDS = {"شكرا", "شكراً", "ميرسي"}
SELF_WORDS = {"انا", "أنا", "بنفسي"}
ATTENTION_PHRASES = {"ركز معايا", "ركز", "اسمع", "فهمت"}
EXPENSE_RECAT_WORDS = {"بند", "مصروف", "مصاريف", "تبع"}
VAGUE_AMOUNT_WORDS = {"كام", "بكام"}
MONEY_HINTS = (
	"جنيه",
	"صرف",
	"دخل",
	"اشتري",
	"بعت",
	"سلف",
	"كام",
	"دفعت",
	"حساب",
	"قسط",
	"سدد",
	"اداني",
	"عليا",
	"عليّ",
	"الغى",
	"الغي",
	"صحح",
)


def handle_message(text: str, conversation: str | None = None) -> dict:
	if not text or not str(text).strip():
		frappe.throw(_("Message is required"))
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)

	text = str(text).strip()
	workspace = get_user_workspace()
	conv = _get_or_create_conversation(workspace, conversation)
	touch_inbound(conv)
	allowed, _reason = can_ai_reply(conv)
	user_msg = _add_message(conv, "User", text, status="ignored" if not allowed else "ok")
	if not allowed:
		return {
			"conversation": conv.name,
			"status": "handed_off",
			"reply": HANDED_OFF_REPLY,
			"message": user_msg.name,
			"linked_entry": None,
			"linked_payment": None,
			"pending_kind": conv.pending_kind or "",
			"deliver": False,
		}

	try:
		if conv.pending_kind:
			return _continue_pending(conv, text, user_msg.name)
		return _start_turn(conv, text, user_msg.name)
	except SahbiLLMUnavailable:
		frappe.log_error(title="Sahbi LLM unavailable")
		return _reply(conv, replies.llm_down(), status="error")
	except SahbiLLMInvalidOutput:
		return _unknown_reply(conv)
	except AmbiguousSettlement as exc:
		return _ask_which_operation(conv, text, exc)
	except frappe.PermissionError:
		return _reply(conv, "مش مسموح تعمل العملية دي.", status="error")
	except Exception:
		frappe.log_error(title="Sahbi chat error")
		return _reply(conv, replies.error_generic(), status="error")


def get_conversation_history(conversation: str | None = None, limit: int | None = None) -> dict:
	workspace = get_user_workspace()
	conv = _get_or_create_conversation(workspace, conversation)
	_ensure_daily_greeting(conv)
	page_length = int(limit) if limit else 0
	rows = frappe.get_all(
		"Sahbi Chat Message",
		filters={"conversation": conv.name},
		fields=["name", "role", "content", "status", "creation", "linked_entry", "linked_payment"],
		order_by="creation asc",
		limit_page_length=page_length,
	)
	return {
		"conversation": conv.name,
		"workspace": conv.workspace,
		"pending_kind": conv.pending_kind or "",
		"messages": rows,
	}


def _start_turn(conv, text, user_message):
	if is_help_request(text):
		topic = help_topic(text)
		guide = replies.help_for_topic(topic) if topic else replies.help_guide()
		return _reply(conv, guide, status="conversation")
	if _is_thanks(text):
		return _reply(conv, replies.thanks(_friend_name()), status="conversation")
	if is_ordinary_greeting(text):
		return _reply(conv, _friend_reply(conv), status="conversation")
	if _is_attention(text):
		return _reply(conv, "تمام، قولّي العملية.", status="conversation")
	if fold_arabic(text) in VAGUE_AMOUNT_WORDS:
		return _reply(conv, "كام إيه؟ مصروف، دخل، ولا حساب مين؟", status="needs_clarification")

	local_query = parse_local_query(text)
	if local_query:
		return _handle_local_query(conv, local_query)

	local_operations = parse_local_operations(text)
	if len(local_operations) > 1:
		return _handle_multiple_operations(conv, text, local_operations, user_message)
	if local_operations:
		return _handle_operation(
			conv,
			text,
			{
				"intent": "financial_operation",
				"operation": local_operations[0],
				"query": {},
				"missing_fields": [],
				"is_ambiguous": False,
			},
			user_message,
		)

	interpretation = interpret_message(text)
	intent = interpretation.get("intent")
	if intent == "ordinary_conversation":
		return _reply(conv, _friend_reply(conv), status="conversation")
	if intent == "financial_query":
		return _handle_query(conv, interpretation)
	if intent == "financial_operation":
		if looks_like_question(text):
			return _handle_question_as_query(conv, text, interpretation)
		return _handle_operation(conv, text, interpretation, user_message)
	return _unknown_reply(conv)


QUESTION_OP_TO_KIND = {
	"purchase": "purchase",
	"sale": "sale",
	"expense": "expense",
	"income": "income",
	"incoming_money": "collections",
	"outgoing_money": "repayments",
}


def _handle_question_as_query(conv, text, interpretation):
	operation = interpretation.get("operation") or {}
	query = interpretation.get("query") or {}
	kind = query.get("kind") or QUESTION_OP_TO_KIND.get(operation.get("type"))
	if not kind:
		return _reply(conv, "ده سؤال. قول المبلغ لو هتسجّل عملية.", status="needs_clarification")
	return _handle_query(
		conv,
		{
			"intent": "financial_query",
			"query": {
				"kind": kind,
				"search_terms": query.get("search_terms") or [],
				"person_name": query.get("person_name") or operation.get("person_name"),
				"date_expression": query.get("date_expression") or operation.get("date_expression"),
			},
			"operation": {},
			"missing_fields": [],
		},
	)


def _handle_operation(conv, text, interpretation, user_message):
	operation = interpretation.get("operation") or {}
	if interpretation.get("missing_fields"):
		question = interpretation.get("clarification_question") or "ناقص معلومة مهمة. كمّل الجملة."
		_set_pending(
			conv,
			"Clarification",
			{"reason": "missing_fields", "interpretation": interpretation, "text": text},
		)
		return _reply(conv, replies.ask(question), status="needs_clarification", interpretation=interpretation)

	if operation.get("type") in {"correction", "cancellation"}:
		return _handle_mutate(conv, text, interpretation)

	if interpretation.get("is_ambiguous") and operation.get("type") in {"incoming_money", "outgoing_money"}:
		question = interpretation.get("clarification_question") or "ده دخل/مصروف ولا تسديد ولا سلفة؟"
		_set_pending(
			conv,
			"Clarification",
			{"reason": "direction_ambiguous", "interpretation": interpretation, "text": text},
		)
		return _reply(conv, replies.ask(question), status="needs_clarification", interpretation=interpretation)

	person, person_name, ask = _match_operation_person(conv, interpretation, text, user_message)
	if ask:
		return ask
	if operation.get("type") in {"loan_receivable", "loan_payable"} and not person_name:
		_set_pending(
			conv,
			"Clarification",
			{"reason": "missing_loan_person", "interpretation": interpretation, "text": text},
		)
		question = "السلفة دي لمين؟" if operation.get("type") == "loan_receivable" else "استلفت من مين؟"
		return _reply(conv, question, status="needs_clarification", interpretation=interpretation)
	if operation.get("type") == "incoming_money" and not person_name:
		_set_pending(
			conv,
			"Clarification",
			{"reason": "missing_payer", "interpretation": interpretation, "text": text},
		)
		return _reply(conv, "مين اللي دفع؟", status="needs_clarification", interpretation=interpretation)

	try:
		return _execute_operation(conv, interpretation, user_message, person=person, create_person=False)
	except AmbiguousSettlement as exc:
		return _ask_which_operation(conv, text, exc, interpretation)


def _match_operation_person(conv, interpretation, text, user_message):
	operation = interpretation.setdefault("operation", {})
	person_name = clean_person_name(operation.get("person_name") or "") or None
	if not person_name and conv.last_person and (
		operation.get("type") == "incoming_money" or operation.get("use_last_person")
	):
		person_name = frappe.db.get_value("Sahbi Person", conv.last_person, "person_name")
		if person_name:
			operation["person_name"] = person_name
			return conv.last_person, person_name, None
	if not person_name:
		return None, None, None
	operation["person_name"] = person_name
	matches = _match_people(conv.workspace, person_name)
	if len(matches) == 1:
		operation["person_name"] = matches[0]["person_name"]
		return matches[0]["name"], matches[0]["person_name"], None
	if len(matches) > 1:
		return None, person_name, _ask_which_person(conv, interpretation, matches, user_message=user_message)
	_set_pending(
		conv,
		"Clarification",
		{"reason": "unknown_person", "interpretation": interpretation, "text": text, "person_name": person_name},
	)
	return None, person_name, _reply(
		conv,
		replies.ask(f"{person_name} مش موجود. أضيفه؟"),
		status="needs_clarification",
		interpretation=interpretation,
	)


def _handle_mutate(conv, text, interpretation):
	operation = interpretation.get("operation") or {}
	target = _resolve_mutate_target(conv, operation)
	if not target:
		wanted = "مصروف" if operation.get("target_entry_type") == "Expense" else "عملية سابقة"
		return _reply(conv, f"مفيش {wanted} ألغيه.", status="error", interpretation=interpretation)

	if operation.get("type") == "cancellation":
		preview = cancel_entry(target, reason=text, confirm=False)
		_set_pending(conv, "Confirmation", {"action": "cancel_entry", "entry": target, "reason": text})
		return _reply(conv, replies.confirm_cancel(preview), status="needs_confirmation", interpretation=interpretation)

	preview = correct_entry(target, amount=operation.get("amount"), reason=text, confirm=False)
	_set_pending(
		conv,
		"Confirmation",
		{"action": "correct_entry", "entry": target, "amount": operation.get("amount"), "reason": text},
	)
	return _reply(conv, replies.confirm_correct(preview), status="needs_confirmation", interpretation=interpretation)


def _resolve_mutate_target(conv, operation):
	hint = operation.get("target_entry_type")
	amount = operation.get("amount")
	last = conv.last_entry
	if last and _entry_matches(last, hint, amount):
		return last
	found = _find_recent_entry(conv.workspace, hint, amount)
	if found:
		return found
	if last and _entry_matches(last, hint, None):
		return last
	if hint:
		found = _find_recent_entry(conv.workspace, hint, None)
		if found:
			return found
	if last and _entry_matches(last, None, None):
		return last
	return None


def _entry_matches(name, hint_type, amount) -> bool:
	row = frappe.db.get_value("Sahbi Entry", name, ["entry_type", "amount", "docstatus"], as_dict=True)
	if not row or row.docstatus != 1:
		return False
	if hint_type and row.entry_type != hint_type:
		return False
	if amount is not None and to_money(row.amount) != to_money(amount):
		return False
	return True


def _find_recent_entry(workspace, entry_type, amount):
	filters = {"workspace": workspace, "docstatus": 1}
	if entry_type:
		filters["entry_type"] = entry_type
	rows = frappe.get_all(
		"Sahbi Entry",
		filters=filters,
		fields=["name", "amount"],
		order_by="creation desc",
		limit_page_length=20,
	)
	for row in rows:
		if amount is None or to_money(row.amount) == to_money(amount):
			return row.name
	return None


def _handle_multiple_operations(conv, text, operations, user_message):
	saved = []
	pending_op = None
	last_entry = None
	last_person_name = None
	for index, operation in enumerate(operations):
		if not operation.get("person_name") and last_person_name and (
			operation.get("use_last_person") or operation.get("type") in {"incoming_money", "outgoing_money"}
		):
			operation["person_name"] = last_person_name
		if operation.get("type") in {"loan_receivable", "loan_payable"} and not operation.get("person_name"):
			pending_op = operation
			continue
		interpretation = {
			"intent": "financial_operation",
			"operation": operation,
			"query": {},
			"missing_fields": [],
			"is_ambiguous": False,
		}
		person, person_name, ask = _match_operation_person(conv, interpretation, text, user_message)
		if ask:
			if conv.pending_kind:
				payload = json.loads(conv.pending_payload or "{}")
				payload["queued_operations"] = operations[index + 1 :]
				_set_pending(conv, conv.pending_kind, payload)
			if saved:
				ask["reply"] = "\n".join([*saved, ask["reply"]])
			return ask
		try:
			result = _execute_operation(
				conv,
				interpretation,
				f"{user_message}:{index}",
				person=person,
				reply=False,
			)
		except AmbiguousSettlement as exc:
			return _ask_which_operation(conv, text, exc, interpretation)
		if result.get("status") != "ok":
			return _reply(conv, result.get("reply") or replies.not_saved(), status=result.get("status") or "error")
		saved.append(result["reply"])
		last_entry = result.get("linked_entry")
		if person_name:
			last_person_name = person_name
	if pending_op:
		interpretation = {
			"intent": "financial_operation",
			"operation": pending_op,
			"query": {},
			"missing_fields": [],
			"is_ambiguous": False,
		}
		_set_pending(
			conv,
			"Clarification",
			{"reason": "missing_loan_person", "interpretation": interpretation, "text": text},
		)
		question = "السلفة دي لمين؟" if pending_op.get("type") == "loan_receivable" else "استلفت من مين؟"
		body = "\n".join([*saved, question]) if saved else question
		return _reply(conv, body, status="needs_clarification", interpretation=interpretation, linked_entry=last_entry)
	_clear_pending(conv)
	return _reply(conv, "\n".join(saved), status="ok", linked_entry=last_entry)


def _recategorize_as_expense(conv, payload, text, user_message):
	original = payload.get("text") or ""
	operations = parse_local_operations(original)
	if len(operations) > 1:
		_clear_pending(conv)
		return _handle_multiple_operations(conv, original, operations, user_message)
	interpretation = payload.get("interpretation") or {}
	operation = interpretation.setdefault("operation", {})
	operation["type"] = "expense"
	operation["person_name"] = None
	from sahbi.chat.categorize_items.expense_items import is_expense_item

	folded = fold_arabic(text + " " + original)
	item = next((token for token in folded.split() if is_expense_item(token)), None)
	operation["description"] = item or "مصروف"
	if not operation.get("amount"):
		parsed = parse_local_operation(original)
		if parsed:
			operation["amount"] = parsed.get("amount")
			if parsed.get("description"):
				operation["description"] = parsed["description"]
	interpretation["is_ambiguous"] = False
	return _execute_operation(conv, interpretation, user_message)


def _execute_operation(conv, interpretation, user_message, person=None, create_person=False, reply=True):
	operation = interpretation.get("operation") or {}
	dates = parse_date_expression(operation.get("date_expression"))
	kwargs = {
		"person": person,
		"person_name": None if person else operation.get("person_name"),
		"description": operation.get("description"),
		"transaction_date": dates.get("transaction_date"),
		"idempotency_key": f"chat:{user_message}",
		"create_person": create_person,
	}
	op_type = operation.get("type")
	amount = operation.get("amount")
	result = None
	entry = None
	payment = None

	if op_type == "income":
		result = create_income(conv.workspace, amount, **kwargs)
		entry = result
	elif op_type == "expense":
		result = create_expense(conv.workspace, amount, **kwargs)
		entry = result
	elif op_type == "sale":
		result = create_sale(conv.workspace, amount, **kwargs)
		entry = result
	elif op_type == "purchase":
		result = create_purchase(conv.workspace, amount, **kwargs)
		entry = result
	elif op_type == "loan_receivable":
		result = create_loan(conv.workspace, amount, "Receivable", **kwargs)
		entry = result
	elif op_type == "loan_payable":
		result = create_loan(conv.workspace, amount, "Payable", **kwargs)
		entry = result
	elif op_type == "opening_receivable":
		result = create_opening_balance(conv.workspace, amount, "Receivable", **kwargs)
		entry = result
	elif op_type == "opening_payable":
		result = create_opening_balance(conv.workspace, amount, "Payable", **kwargs)
		entry = result
	elif op_type == "incoming_money":
		result = record_incoming_money(conv.workspace, amount, settle_entry=conv.last_entry if operation.get("previous_operation_references") and conv.last_entry else None, **kwargs)
		entry = (result.get("income") or (result.get("payment") or {}).get("entries") or [None])[0] if isinstance((result.get("payment") or {}).get("entries"), list) else result.get("income")
		if result.get("payment"):
			payment = result["payment"]
			if result["payment"].get("entries"):
				entry = result["payment"]["entries"][0]
	elif op_type == "outgoing_money":
		result = record_outgoing_money(
			conv.workspace,
			amount,
			settle_entry=conv.last_entry if operation.get("previous_operation_references") and conv.last_entry else None,
			**kwargs,
		)
		if result.get("expense"):
			entry = result["expense"]
		if result.get("payment"):
			payment = result["payment"]
			if result["payment"].get("entries"):
				entry = result["payment"]["entries"][0]
	else:
		return _reply(conv, replies.llm_confused(), status="error", interpretation=interpretation)

	if not _committed(result):
		if not reply:
			return {"status": "error", "reply": replies.not_saved(), "linked_entry": None}
		return _reply(conv, replies.not_saved(), status="error", interpretation=interpretation)

	if reply:
		_clear_pending(conv)
	_remember(conv, entry=entry, payment=payment, person=person)
	person_name = operation.get("person_name")
	if op_type in {"incoming_money", "outgoing_money"}:
		text = replies.saved_settlement(result, person_name)
	else:
		text = replies.saved_entry(entry, person_name)
	payload = {
		"status": "ok",
		"reply": text,
		"linked_entry": (entry or {}).get("name"),
		"linked_payment": (payment or {}).get("name"),
	}
	if not reply:
		return payload
	return _reply(
		conv,
		text,
		status="ok",
		interpretation=interpretation,
		linked_entry=payload["linked_entry"],
		linked_payment=payload["linked_payment"],
	)


def _committed(result) -> bool:
	if not result:
		return False
	if result.get("status") == "ok":
		name = result.get("name")
		if name and result.get("doctype") == "Sahbi Entry":
			return frappe.db.get_value("Sahbi Entry", name, "docstatus") == 1
		if name and result.get("doctype") == "Sahbi Payment":
			return frappe.db.get_value("Sahbi Payment", name, "docstatus") == 1
	if result.get("income") and frappe.db.get_value("Sahbi Entry", result["income"]["name"], "docstatus") == 1:
		return True
	if result.get("expense") and frappe.db.get_value("Sahbi Entry", result["expense"]["name"], "docstatus") == 1:
		return True
	payment = result.get("payment")
	if payment and frappe.db.get_value("Sahbi Payment", payment.get("name"), "docstatus") == 1:
		return True
	return False


def _handle_local_query(conv, query):
	if query.get("use_last_person") and conv.last_person:
		person_name = frappe.db.get_value("Sahbi Person", conv.last_person, "person_name")
		query["person_name"] = person_name
		query["needs_person"] = False
	if query.get("needs_person") and not query.get("person_name"):
		return _reply(conv, "حساب مين يا صاحبي؟ قول الاسم.", status="needs_clarification")
	return _handle_query(
		conv,
		{
			"intent": "financial_query",
			"query": query,
			"operation": {},
			"missing_fields": [],
		},
	)


def _handle_query(conv, interpretation):
	query = interpretation.get("query") or {}
	dates = parse_date_expression(query.get("date_expression"))
	person_name = clean_person_name(query.get("person_name") or "") or None
	if person_name:
		query["person_name"] = person_name
	person = query.get("person")
	if person_name and not person:
		matches = _match_people(conv.workspace, person_name)
		if not matches:
			return _reply(conv, f"مفيش حد اسمه {person_name} في الحساب.", status="ok", interpretation=interpretation)
		if len(matches) > 1:
			return _ask_which_person(conv, interpretation, matches, user_message=None)
		person = matches[0]["name"]
		query["person_name"] = matches[0]["person_name"]
		person_name = matches[0]["person_name"]

	result = run_financial_query(
		conv.workspace,
		kind=query.get("kind"),
		search_terms=query.get("search_terms") or [],
		person=person,
		person_name=person_name,
		from_date=dates.get("from_date"),
		to_date=dates.get("to_date"),
	)
	if person:
		_remember(conv, person=person)
	return _reply(conv, replies.query_result(result), status="ok", interpretation=interpretation)


def _continue_pending(conv, text, user_message):
	payload = json.loads(conv.pending_payload or "{}")
	if _is_new_topic(text, payload):
		_clear_pending(conv)
		return _start_turn(conv, text, user_message)
	normalized = _normalize(text)
	if conv.pending_kind == "Confirmation":
		if _is_confirm(text):
			return _execute_confirmation(conv, payload)
		if _is_deny(text):
			_clear_pending(conv)
			return _reply(conv, replies.denied(), status="ok")
		return _reply(conv, "قول أيوه أو لأ.", status="needs_confirmation")

	reason = payload.get("reason")
	if reason == "unknown_person":
		if _is_expense_recategorize(text):
			return _recategorize_as_expense(conv, payload, text, user_message)
		if _is_confirm(text, allow_add_person=True):
			interpretation = payload["interpretation"]
			result = _execute_operation(
				conv,
				interpretation,
				user_message,
				create_person=True,
			)
			queued = payload.get("queued_operations") or []
			if queued and result.get("status") == "ok":
				follow = _handle_multiple_operations(conv, payload.get("text") or text, queued, user_message)
				follow["reply"] = "\n".join(
					part for part in (result.get("reply"), follow.get("reply")) if part
				)
				return follow
			return result
		if _is_deny(text) or _starts_with_deny(text):
			_clear_pending(conv)
			return _reply(conv, "ماشي، ما سجلتش العملية.", status="ok")
		return _reply(conv, "أضيف الشخص؟ أيوه ولا لأ.", status="needs_clarification")

	if reason == "missing_loan_person":
		if _is_expense_recategorize(text):
			question = "ماشي، المصروف تحت بند المواصلات. السلفة لمين؟"
			if (payload.get("interpretation") or {}).get("operation", {}).get("type") == "loan_payable":
				question = "ماشي، المصروف تحت بند المواصلات. استلفت من مين؟"
			return _reply(conv, question, status="needs_clarification")
		if _is_deny(text) or _starts_with_deny(text):
			_clear_pending(conv)
			return _reply(conv, "ماشي، ما سجلتش السلفة.", status="ok")
		if _is_self(text):
			return _reply(conv, "السلفة باسم مين؟ قول اسم الشخص.", status="needs_clarification")
		interpretation = payload["interpretation"]
		operation = interpretation.setdefault("operation", {})
		operation["person_name"] = clean_person_name(text)
		return _handle_operation(conv, payload.get("text") or text, interpretation, user_message)

	if reason == "missing_payer":
		interpretation = payload["interpretation"]
		operation = interpretation.setdefault("operation", {})
		original = payload.get("text") or ""
		if _is_self(text):
			from sahbi.chat.categorize_items.expense_items import is_expense_item

			has_item = any(is_expense_item(token) for token in fold_arabic(original).split())
			operation["type"] = "expense" if has_item else "income"
			operation["person_name"] = None
			return _execute_operation(conv, interpretation, user_message)
		operation["person_name"] = clean_person_name(text)
		return _handle_operation(conv, original or text, interpretation, user_message)

	if reason == "direction_ambiguous":
		return _resolve_direction(conv, payload, normalized, user_message)

	if reason == "missing_fields":
		return _start_turn(conv, text, user_message)

	if reason == "choose_entry":
		return _choose_entry(conv, payload, text, user_message)

	if reason == "choose_person":
		return _choose_person(conv, payload, text)

	_clear_pending(conv)
	return _start_turn(conv, text, user_message)


def _resolve_direction(conv, payload, normalized, user_message):
	interpretation = payload["interpretation"]
	operation = interpretation.setdefault("operation", {})
	if any(word in normalized for word in INCOME_WORDS) or normalized in INCOME_WORDS:
		operation["type"] = "income"
	elif any(word in normalized for word in LOAN_WORDS):
		operation["type"] = "loan_payable" if operation.get("type") == "incoming_money" else "loan_receivable"
	elif any(word in normalized for word in SETTLE_WORDS):
		pass
	else:
		return _reply(conv, "قول: دخل، سلفة، ولا تسديد؟", status="needs_clarification")
	interpretation["is_ambiguous"] = False
	return _execute_operation(conv, interpretation, user_message)


def _is_new_topic(text, payload) -> bool:
	stripped = (text or "").strip()
	if not stripped or stripped.isdigit():
		return False
	if _is_confirm(text, allow_add_person=True) or _is_deny(text):
		return False
	candidates = payload.get("candidates") or []
	wanted = fold_arabic(stripped)
	direction_answers = _folded_set(INCOME_WORDS) | _folded_set(LOAN_WORDS) | _folded_set(SETTLE_WORDS)
	if wanted in direction_answers:
		return False
	if _is_self(text) or _is_expense_recategorize(text) or _starts_with_deny(text):
		return False
	for row in candidates:
		if row.get("name") == stripped:
			return False
		if fold_arabic(row.get("person_name") or "") == wanted:
			return False
	if parse_local_query(text) or parse_local_operations(text):
		return True
	return is_ordinary_greeting(text) or _is_thanks(text)


def _choose_entry(conv, payload, text, user_message):
	candidates = payload.get("candidates") or []
	match = next((row for row in candidates if row["name"] == text.strip()), None)
	if not match and text.strip().isdigit():
		index = int(text.strip()) - 1
		if 0 <= index < len(candidates):
			match = candidates[index]
	if not match:
		return _reply(conv, "اختار رقم العملية.", status="needs_clarification")
	interpretation = payload["interpretation"] or {}
	operation = interpretation.get("operation") or {}
	amount = operation.get("amount")
	if not amount:
		parsed = parse_local_operation(payload.get("text") or "")
		if parsed:
			operation.update(parsed)
			interpretation["operation"] = operation
			amount = parsed.get("amount")
	if not amount:
		return _reply(conv, "المبلغ ناقص. قول الجملة تاني.", status="error")
	settle = record_outgoing_money if operation.get("type") == "outgoing_money" else record_incoming_money
	result = settle(
		conv.workspace,
		amount,
		person_name=operation.get("person_name"),
		settle_entry=match["name"],
		idempotency_key=f"chat:{user_message}",
	)
	if not _committed(result):
		return _reply(conv, replies.not_saved(), status="error")
	_clear_pending(conv)
	entry = (result.get("payment") or {}).get("entries", [None])[0]
	_remember(conv, entry=entry, payment=result.get("payment"))
	return _reply(
		conv,
		replies.saved_settlement(result, interpretation["operation"].get("person_name")),
		status="ok",
		linked_entry=(entry or {}).get("name"),
		linked_payment=(result.get("payment") or {}).get("name"),
	)


def _execute_confirmation(conv, payload):
	action = payload.get("action")
	if action == "cancel_entry":
		result = cancel_entry(payload["entry"], reason=payload.get("reason") or "طلب المستخدم", confirm=True)
		if result.get("status") != "cancelled":
			return _reply(conv, replies.not_saved(), status="error")
		_clear_pending(conv)
		return _reply(conv, replies.cancelled(), status="ok", linked_entry=payload["entry"])
	if action == "correct_entry":
		result = correct_entry(
			payload["entry"],
			amount=payload.get("amount"),
			reason=payload.get("reason") or "طلب المستخدم",
			confirm=True,
		)
		if result.get("status") != "corrected":
			return _reply(conv, replies.not_saved(), status="error")
		_clear_pending(conv)
		_remember(conv, entry=result.get("replacement"))
		return _reply(
			conv,
			replies.corrected(result["replacement"]),
			status="ok",
			linked_entry=result["replacement"]["name"],
		)
	_clear_pending(conv)
	return _reply(conv, replies.denied(), status="ok")


def _match_people(workspace, person_name) -> list[dict]:
	wanted = fold_arabic(clean_person_name(person_name))
	if not wanted:
		return []
	rows = frappe.get_all(
		"Sahbi Person",
		filters={"workspace": workspace},
		fields=["name", "person_name", "normalized_name"],
	)
	matches = []
	wanted_tokens = wanted.split()
	for row in rows:
		normalized = fold_arabic(row.normalized_name or row.person_name)
		if normalized == wanted:
			matches.append(row)
		elif normalized.startswith(f"{wanted} "):
			matches.append(row)
		elif all(token in normalized.split() for token in wanted_tokens):
			matches.append(row)
	matches.sort(key=lambda row: (fold_arabic(row.person_name) != wanted, row.person_name or ""))
	return matches


def _ask_which_person(conv, interpretation, matches, user_message=None):
	_set_pending(
		conv,
		"Clarification",
		{
			"reason": "choose_person",
			"interpretation": interpretation,
			"candidates": matches,
			"user_message": user_message,
		},
	)
	hint = fold_arabic((interpretation.get("operation") or {}).get("person_name") or (interpretation.get("query") or {}).get("person_name") or "")
	title = f"في أكتر من {hint}." if hint else "في أكتر من شخص."
	lines = [f"{title} اختار رقم:"]
	for index, row in enumerate(matches, start=1):
		lines.append(f"{index} - {row.get('person_name')}")
	return _reply(conv, "\n".join(lines), status="needs_clarification", interpretation=interpretation)


def _choose_person(conv, payload, text):
	candidates = payload.get("candidates") or []
	folded = fold_arabic(text)
	match = next((row for row in candidates if fold_arabic(row.get("person_name")) == folded), None)
	number = re.match(r"^(\d+)", text.strip())
	if not match and number:
		index = int(number.group(1)) - 1
		if 0 <= index < len(candidates):
			match = candidates[index]
	if not match:
		return _reply(conv, "اختار الاسم أو رقمه.", status="needs_clarification")
	interpretation = payload["interpretation"]
	_clear_pending(conv)
	if interpretation.get("intent") == "financial_operation":
		interpretation.setdefault("operation", {})["person_name"] = match["person_name"]
		return _execute_operation(
			conv,
			interpretation,
			payload.get("user_message"),
			person=match["name"],
			create_person=False,
		)
	interpretation.setdefault("query", {})["person_name"] = match["person_name"]
	interpretation["query"]["person"] = match["name"]
	return _handle_query(conv, interpretation)


def _ask_which_operation(conv, text, exc: AmbiguousSettlement, interpretation=None):
	candidates = getattr(exc, "candidates", []) or []
	stored = interpretation or {}
	operation = dict(stored.get("operation") or {})
	if not operation.get("amount"):
		parsed = parse_local_operation(text)
		if parsed:
			operation.update(parsed)
	if not operation.get("type"):
		operation["type"] = "incoming_money"
	_set_pending(
		conv,
		"Clarification",
		{
			"reason": "choose_entry",
			"text": text,
			"interpretation": {
				"intent": stored.get("intent") or "financial_operation",
				"operation": operation,
				"query": stored.get("query") or {},
			},
			"candidates": candidates,
		},
	)
	lines = ["في أكتر من عملية. اختار رقم:"]
	for index, row in enumerate(candidates, start=1):
		label = replies.TYPE_AR.get(row.get("entry_type"), row.get("entry_type"))
		lines.append(f"{index}) {label} {row.get('outstanding_amount')} جنيه")
	return _reply(conv, "\n".join(lines), status="needs_clarification")


def _get_or_create_conversation(workspace, conversation=None):
	assert_workspace_access(workspace)
	if conversation:
		conv = frappe.get_doc("Sahbi Conversation", conversation)
		if conv.workspace != workspace and frappe.session.user != "Administrator":
			frappe.throw(_("You cannot access another user's workspace"), frappe.PermissionError)
		assert_workspace_access(conv.workspace)
		return conv
	name = frappe.db.get_value("Sahbi Conversation", {"workspace": workspace}, "name")
	if name:
		return frappe.get_doc("Sahbi Conversation", name)
	user = frappe.db.get_value("Sahbi Workspace", workspace, "user")
	conv = frappe.get_doc(
		{
			"doctype": "Sahbi Conversation",
			"workspace": workspace,
			"user": user,
		}
	)
	conv.insert()
	return conv


def _add_message(conv, role, content, status="ok", interpretation=None, linked_entry=None, linked_payment=None):
	doc = frappe.get_doc(
		{
			"doctype": "Sahbi Chat Message",
			"conversation": conv.name,
			"workspace": conv.workspace,
			"role": role,
			"content": content,
			"status": status,
			"interpretation": json.dumps(interpretation, ensure_ascii=False) if interpretation else None,
			"linked_entry": linked_entry,
			"linked_payment": linked_payment,
		}
	)
	doc.insert()
	return doc


def _reply(conv, content, status="ok", interpretation=None, linked_entry=None, linked_payment=None):
	message = _add_message(
		conv,
		"Sahbi",
		content,
		status=status,
		interpretation=interpretation,
		linked_entry=linked_entry,
		linked_payment=linked_payment,
	)
	return {
		"conversation": conv.name,
		"status": status,
		"reply": content,
		"message": message.name,
		"linked_entry": linked_entry,
		"linked_payment": linked_payment,
		"pending_kind": conv.pending_kind or "",
	}


def _set_pending(conv, kind, payload):
	conv.pending_kind = kind
	conv.pending_payload = json.dumps(payload, ensure_ascii=False)
	conv.save()


def _clear_pending(conv):
	conv.pending_kind = None
	conv.pending_payload = None
	conv.save()


def _remember(conv, entry=None, payment=None, person=None):
	if entry and entry.get("name"):
		conv.db_set("last_entry", entry["name"], update_modified=False)
	if payment and payment.get("name"):
		conv.db_set("last_payment", payment["name"], update_modified=False)
	if person:
		conv.db_set("last_person", person, update_modified=False)
	conv.reload()


def _friend_name() -> str | None:
	if frappe.session.user in {"Guest", "Administrator"}:
		return None
	name = frappe.db.get_value("User", frappe.session.user, "first_name")
	if not name or name in {"Guest", "Administrator", "Sahbi"}:
		return None
	return name


def _sahbi_spoke_today(conv) -> bool:
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Sahbi Chat Message",
		filters={"conversation": conv.name, "role": "Sahbi"},
		fields=["creation"],
		order_by="creation desc",
		limit_page_length=30,
	)
	return any(getdate(row.creation) == today for row in rows)


def _friend_reply(conv) -> str:
	return replies.greet(first_of_day=not _sahbi_spoke_today(conv), user_name=_friend_name())


def _ensure_daily_greeting(conv) -> None:
	if conv.pending_kind or _sahbi_spoke_today(conv):
		return
	_reply(conv, replies.greet(first_of_day=True, user_name=_friend_name()), status="conversation")


def _is_thanks(text: str) -> bool:
	folded = _normalize(text)
	if not folded or any(hint in folded for hint in MONEY_HINTS):
		return False
	for word in sorted(_folded_set(THANKS_WORDS), key=len, reverse=True):
		if folded == word or folded.startswith(word + " "):
			tail = folded[len(word) :].strip()
			return not tail or all(token in _folded_set(FILLER_WORDS) for token in tail.split())
	return False


HELP_EXACT = {
	"مساعده",
	"مساعدة",
	"help",
	"هيلب",
	"هلپ",
	"الدليل",
	"امثله",
	"أمثلة",
	"ازاي",
	"ازاى",
	"كيف",
}
HELP_PHRASES = (
	"ازاي استخدم",
	"ازاى استخدم",
	"مش عارف استخدم",
	"مش عارفه استخدم",
	"معرفش استخدم",
	"عايز مساعده",
	"عايزه مساعده",
	"عايز مساعدة",
	"عايزه مساعدة",
	"مش عارف استخدم التطبيق",
	"مش عارفه استخدم التطبيق",
	"اعرفها ازاي",
	"اعرفهم ازاي",
	"اعرف حساباتي",
	"اعرف حساباتى",
)
HOW_MARKERS = ("ازاي", "ازاى", "كيف", "بطريقه ايه", "ايه الطريقه")
HELP_ACTION_WORDS = ("اسجل", "سجل", "اتسجل", "اعمل", "ضيف", "اضيف", "اشوف", "وريني", "اعرف", "استخدم")
HELP_TOPICS = (
	("cancel", ("الغي", "الغاء", "صحح")),
	("settlement", ("سدد", "تسديد", "قسط", "تحصيل")),
	("loan", ("سلفه", "سلف", "قرض", "استلفت", "سلفت")),
	("sale", ("مبيعات", "بيع", "بعت", "بيعت")),
	("purchase", ("مشتريات", "شراء", "شري", "اشتري", "شرينا", "اتشري")),
	("expense", ("مصاريف", "مصروف", "صرف")),
	("income", ("ايراد", "دخل")),
	("people", ("حسابات الناس", "الناس", "مين ليا", "مين ليه")),
	("balance", ("رصيد", "كشف حساب", "كام عندي", "كام ليا")),
	("accounts", ("حساباتي", "حساباتى", "حسابات", "حسابي", "حساب")),
)


def is_help_request(text: str) -> bool:
	folded = _normalize(text)
	if not folded or re.search(r"\d", folded):
		return False
	if folded in _folded_set(HELP_EXACT):
		return True
	if any(phrase in folded for phrase in _folded_set(HELP_PHRASES)):
		return True
	if "مساعده" in folded or "help" in folded or "هيلب" in folded:
		return True
	if not _has_how_marker(folded):
		return False
	if help_topic(text):
		return True
	return any(word in folded for word in HELP_ACTION_WORDS) or any(
		token in folded for token in ("استخدم", "استخدام", "التطبيق", "البرنامج", "اعرفها", "اعرفهم")
	)


def help_topic(text: str) -> str | None:
	folded = _normalize(text)
	if not folded:
		return None
	for topic, words in HELP_TOPICS:
		if any(word in folded for word in words):
			return topic
	return None


def _has_how_marker(folded: str) -> bool:
	return any(marker in folded for marker in HOW_MARKERS)


def _unknown_reply(conv):
	if _consecutive_unknown_replies(conv) >= 1:
		return _reply(conv, replies.unknown_nudge_help(), status="error")
	return _reply(conv, replies.llm_confused(), status="error")


def _consecutive_unknown_replies(conv) -> int:
	rows = frappe.get_all(
		"Sahbi Chat Message",
		filters={"conversation": conv.name, "role": "Sahbi"},
		fields=["content", "status"],
		order_by="creation desc, name desc",
		limit_page_length=8,
	)
	streak = 0
	for row in rows:
		content = row.content or ""
		if row.status == "error" and (
			content == replies.llm_confused()
			or content == replies.unknown_nudge_help()
			or "اكتب: مساعدة" in content
			or "مش واضحة عليا" in content
		):
			streak += 1
			continue
		break
	return streak


def _is_self(text: str) -> bool:
	return fold_arabic(text) in _folded_set(SELF_WORDS)


def _is_attention(text: str) -> bool:
	folded = fold_arabic(text)
	return folded in _folded_set(ATTENTION_PHRASES)


def _is_expense_recategorize(text: str) -> bool:
	folded = fold_arabic(text)
	return any(word in folded for word in EXPENSE_RECAT_WORDS)


def _starts_with_deny(text: str) -> bool:
	tokens = fold_arabic(text).split()
	return bool(tokens) and tokens[0] in _folded_set(DENY_WORDS)


def is_ordinary_greeting(text: str) -> bool:
	normalized = _normalize(text)
	if not normalized or any(hint in normalized for hint in MONEY_HINTS):
		return False
	if re.search(r"\d", normalized):
		return False
	if normalized in GREETINGS:
		return True
	accepted = _folded_set(GREETINGS)
	for greeting in sorted(accepted, key=len, reverse=True):
		if normalized == greeting or normalized.startswith(greeting + " "):
			rest = normalized[len(greeting) :].strip()
			extra = _folded_set(FILLER_WORDS)
			return not rest or all(token in extra for token in rest.split())
	return False


def _normalize(text: str) -> str:
	return _fold_arabic(text)


def _fold_arabic(text: str) -> str:
	return fold_arabic(text)


def _folded_set(words) -> set[str]:
	return {_fold_arabic(word) for word in words}


def _matches_word_set(text: str, words) -> bool:
	folded = _fold_arabic(text)
	accepted = _folded_set(words)
	if folded in accepted:
		return True
	tokens = [token for token in folded.split() if token]
	if not tokens:
		return False
	extra = _folded_set(FILLER_WORDS)
	return any(token in accepted for token in tokens) and all(token in accepted | extra for token in tokens)


def _is_confirm(text: str, allow_add_person: bool = False) -> bool:
	words = set(CONFIRM_WORDS)
	if allow_add_person:
		words |= ADD_PERSON_WORDS
	return _matches_word_set(text, words)


def _is_deny(text: str) -> bool:
	return _matches_word_set(text, DENY_WORDS)
