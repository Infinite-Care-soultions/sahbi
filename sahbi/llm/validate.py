# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import json
import re

from frappe import _

from sahbi.llm.errors import SahbiLLMInvalidOutput
from sahbi.llm.schema import (
	ALLOWED_OPERATION_KEYS,
	ALLOWED_QUERY_KEYS,
	ALLOWED_ROOT_KEYS,
	FORBIDDEN_KEYS,
	INTENTS,
	OPERATION_TYPES,
	QUERY_KINDS,
)
from sahbi.money import to_money


def parse_model_text(text: str) -> dict:
	if text is None or not str(text).strip():
		raise SahbiLLMInvalidOutput(_("The model returned empty output"))
	cleaned = _strip_fences(str(text).strip())
	try:
		payload = json.loads(cleaned)
	except json.JSONDecodeError as exc:
		raise SahbiLLMInvalidOutput(_("The model returned invalid JSON")) from exc
	if not isinstance(payload, dict):
		raise SahbiLLMInvalidOutput(_("The model returned invalid JSON"))
	return payload


def validate_extraction(payload: dict) -> dict:
	if not isinstance(payload, dict):
		raise SahbiLLMInvalidOutput(_("The model returned invalid JSON"))
	_reject_forbidden(payload)

	intent = payload.get("intent")
	if intent not in INTENTS:
		raise SahbiLLMInvalidOutput(_("Invalid intent"))

	operation = _clean_operation(payload.get("operation"))
	query = _clean_query(payload.get("query"))
	missing = _string_list(payload.get("missing_fields"))
	is_ambiguous = bool(payload.get("is_ambiguous"))
	ambiguity_reason = _optional_text(payload.get("ambiguity_reason"))
	clarification = _optional_text(payload.get("clarification_question"))

	if intent == "ordinary_conversation":
		operation = _empty_operation()
		query = _empty_query()

	if intent == "financial_operation" and not operation.get("type") and "type" not in missing:
		missing.append("type")

	if intent == "financial_query" and not query.get("kind") and "kind" not in missing:
		missing.append("kind")

	if (
		intent == "financial_operation"
		and operation.get("type")
		and operation["type"] not in {"correction", "cancellation"}
		and operation.get("amount") is None
		and "amount" not in missing
	):
		missing.append("amount")

	return {
		"intent": intent,
		"operation": operation,
		"query": query,
		"missing_fields": missing,
		"is_ambiguous": is_ambiguous,
		"ambiguity_reason": ambiguity_reason,
		"clarification_question": clarification,
	}


def _reject_forbidden(payload: dict) -> None:
	stack = [payload]
	while stack:
		current = stack.pop()
		if not isinstance(current, dict):
			continue
		for key, value in current.items():
			if key in FORBIDDEN_KEYS and value not in (None, "", [], {}):
				raise SahbiLLMInvalidOutput(_("The model returned a forbidden field: {0}").format(key))
			if isinstance(value, dict):
				stack.append(value)


def _clean_operation(raw) -> dict:
	data = raw if isinstance(raw, dict) else {}
	cleaned = _empty_operation()
	for key in ALLOWED_OPERATION_KEYS:
		if key not in data:
			continue
		if key == "type":
			cleaned["type"] = _enum(data.get("type"), OPERATION_TYPES)
		elif key == "amount":
			cleaned["amount"] = _optional_amount(data.get("amount"))
		elif key == "previous_operation_references":
			cleaned[key] = _string_list(data.get(key))
		elif key == "loan_direction":
			direction = _optional_text(data.get(key))
			if direction and direction not in {"receivable", "payable"}:
				raise SahbiLLMInvalidOutput(_("Invalid loan direction"))
			cleaned[key] = direction
		else:
			cleaned[key] = _optional_text(data.get(key))
	return cleaned


def _clean_query(raw) -> dict:
	data = raw if isinstance(raw, dict) else {}
	cleaned = _empty_query()
	for key in ALLOWED_QUERY_KEYS:
		if key not in data:
			continue
		if key == "kind":
			cleaned["kind"] = _enum(data.get("kind"), QUERY_KINDS)
		elif key == "search_terms":
			cleaned[key] = _string_list(data.get(key))
		else:
			cleaned[key] = _optional_text(data.get(key))
	return cleaned


def _empty_operation() -> dict:
	return {
		"type": None,
		"amount": None,
		"person_name": None,
		"description": None,
		"date_expression": None,
		"previous_operation_references": [],
		"loan_direction": None,
	}


def _empty_query() -> dict:
	return {
		"kind": None,
		"search_terms": [],
		"person_name": None,
		"date_expression": None,
	}


NULL_TOKENS = {None, "", "null", "none", "nil", "undefined"}


def _enum(value, allowed):
	if isinstance(value, str):
		value = value.strip()
	if value in NULL_TOKENS:
		return None
	if value not in allowed:
		raise SahbiLLMInvalidOutput(_("Invalid value: {0}").format(value))
	return value


def _optional_text(value):
	if isinstance(value, str):
		value = value.strip()
	if value in NULL_TOKENS:
		return None
	text = str(value).strip()
	return text or None


def _string_list(value) -> list[str]:
	if not value:
		return []
	if not isinstance(value, list):
		raise SahbiLLMInvalidOutput(_("Expected a list"))
	items = []
	for item in value:
		text = _optional_text(item)
		if text:
			items.append(text)
	return items


def _optional_amount(value):
	if isinstance(value, str):
		value = value.strip()
	if value in NULL_TOKENS:
		return None
	try:
		amount = to_money(value)
	except Exception as exc:
		raise SahbiLLMInvalidOutput(_("Invalid amount")) from exc
	if amount <= 0:
		raise SahbiLLMInvalidOutput(_("Amount must be greater than zero"))
	return format(amount, "f")


def _strip_fences(text: str) -> str:
	fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
	if fenced:
		return fenced.group(1).strip()
	start = text.find("{")
	end = text.rfind("}")
	if start != -1 and end != -1 and end > start:
		return text[start : end + 1]
	return text
