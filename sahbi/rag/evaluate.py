# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import json
import time
from pathlib import Path

from sahbi.chat.local_query import parse_local_operation, parse_local_query
from sahbi.chat.normalize import fold_arabic
from sahbi.chat.service import _is_confirm, _is_deny, _is_thanks, is_ordinary_greeting

EVAL_PATH = Path(__file__).resolve().parent / "evaluation" / "egyptian_eval.json"


def load_eval_dataset() -> list[dict]:
	return json.loads(EVAL_PATH.read_text(encoding="utf-8"))


def classify_deterministic(text: str) -> dict:
	if _is_thanks(text) or is_ordinary_greeting(text):
		return {"route": "greeting", "intent": "ordinary_conversation"}
	if _is_confirm(text, allow_add_person=True):
		return {"route": "confirm", "intent": "ordinary_conversation"}
	if _is_deny(text):
		return {"route": "deny", "intent": "ordinary_conversation"}
	query = parse_local_query(text)
	if query:
		return {
			"route": "local_query",
			"intent": "financial_query",
			"query_kind": query.get("kind"),
			"person_name": query.get("person_name"),
			"search_terms": query.get("search_terms") or [],
			"needs_clarification": bool(query.get("needs_person")),
		}
	operation = parse_local_operation(text)
	if operation:
		return {
			"route": "local_operation",
			"intent": "financial_operation",
			"operation_type": operation.get("type"),
			"amount": operation.get("amount"),
			"person_name": operation.get("person_name"),
			"needs_clarification": False,
		}
	return {"route": "llm", "intent": None}


def score_case(case: dict, predicted: dict) -> dict:
	expected_person = fold_arabic(case.get("person_name") or "")
	got_person = fold_arabic(predicted.get("person_name") or "")
	amount_ok = True
	if case.get("amount"):
		amount_ok = _amount_eq(predicted.get("amount"), case["amount"])
	person_ok = True
	if case.get("person_name"):
		person_ok = expected_person == got_person or expected_person in got_person or got_person in expected_person
	elif predicted.get("route") == "local_operation" and predicted.get("person_name") and case.get("person_name") is None:
		person_ok = predicted.get("person_name") is None
	type_ok = True
	if case.get("operation_type"):
		type_ok = predicted.get("operation_type") == case["operation_type"]
	kind_ok = True
	if case.get("query_kind"):
		kind_ok = predicted.get("query_kind") == case["query_kind"]
	route_ok = predicted.get("route") == case.get("route")
	if case.get("route") == "llm" and predicted.get("route") == "llm":
		route_ok = True
		if predicted.get("intent") is None:
			type_ok = True
			kind_ok = True
			amount_ok = True
			person_ok = True
	return {
		"id": case["id"],
		"route_ok": route_ok,
		"type_ok": type_ok,
		"kind_ok": kind_ok,
		"amount_ok": amount_ok,
		"person_ok": person_ok,
		"pass": route_ok and type_ok and kind_ok and amount_ok and person_ok,
		"predicted": predicted,
	}


def run_deterministic_eval(cases: list[dict] | None = None) -> dict:
	cases = cases or load_eval_dataset()
	started = time.perf_counter()
	rows = [score_case(case, classify_deterministic(case["message"])) for case in cases]
	return _summary(rows, time.perf_counter() - started, len(cases))


def run_live_eval(mode: str, cases: list[dict] | None = None, limit: int | None = None) -> dict:
	from sahbi.llm.service import interpret_message

	cases = [case for case in (cases or load_eval_dataset()) if case.get("route") == "llm"]
	if limit:
		cases = cases[:limit]
	started = time.perf_counter()
	rows = []
	for case in cases:
		try:
			parsed = interpret_message(
				case["message"],
				use_rag=mode == "C",
				use_baseline=mode == "A",
			)
			predicted = {
				"route": "llm",
				"intent": parsed.get("intent"),
				"operation_type": (parsed.get("operation") or {}).get("type"),
				"amount": (parsed.get("operation") or {}).get("amount"),
				"person_name": (parsed.get("operation") or {}).get("person_name")
				or (parsed.get("query") or {}).get("person_name"),
				"query_kind": (parsed.get("query") or {}).get("kind"),
			}
		except Exception as exc:
			predicted = {"route": "error", "error": str(exc)}
		rows.append(score_case(case, predicted))
	return _summary(rows, time.perf_counter() - started, len(cases))


def _amount_eq(got, expected) -> bool:
	if got is None:
		return False
	try:
		return float(str(got).replace(",", ".")) == float(str(expected).replace(",", "."))
	except ValueError:
		return str(got) == str(expected)


def _summary(rows: list[dict], elapsed: float, total: int) -> dict:
	passed = sum(1 for row in rows if row["pass"])
	return {
		"total": total,
		"passed": passed,
		"failed": total - passed,
		"accuracy": (passed / total) if total else 0.0,
		"route_accuracy": (sum(1 for row in rows if row["route_ok"]) / total) if total else 0.0,
		"entity_accuracy": (
			sum(1 for row in rows if row["amount_ok"] and row["person_ok"] and row["type_ok"] and row["kind_ok"]) / total
			if total
			else 0.0
		),
		"seconds": elapsed,
		"failures": [row["id"] for row in rows if not row["pass"]],
		"rows": rows,
	}
