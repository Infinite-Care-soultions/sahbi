# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from frappe import _

from sahbi.llm.client import complete, inspect_ollama
from sahbi.llm.errors import SahbiLLMInvalidOutput
from sahbi.llm.prompts import build_baseline_messages, build_messages
from sahbi.llm.settings import get_llm_settings
from sahbi.llm.validate import parse_model_text, validate_extraction


def interpret_message(text: str, *, model: str | None = None, use_rag: bool = True, use_baseline: bool = False) -> dict:
	"""Extract structured intent from a user message.

	This function must not write financial documents or compute totals.
	"""
	if text is None or not str(text).strip():
		raise SahbiLLMInvalidOutput(_("Message is required"))

	user_text = str(text).strip()
	if use_baseline:
		messages = build_baseline_messages(user_text)
	elif use_rag:
		from sahbi.rag.context import build_rag_messages

		messages = build_rag_messages(user_text)
	else:
		messages = build_messages(user_text)
	raw = complete(messages, model=model)
	payload = parse_model_text(raw)
	parsed = validate_extraction(payload)
	parsed["model"] = model or get_llm_settings()["model"]
	parsed["raw_accepted"] = True
	return parsed


def llm_status() -> dict:
	return inspect_ollama()
