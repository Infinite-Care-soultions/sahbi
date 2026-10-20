# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import os

import frappe

DEFAULT_MODEL = "qwen2.5:1.5b"
DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 120


def get_llm_settings() -> dict:
	single = _single_settings()
	conf = getattr(frappe, "conf", None)
	return {
		"url": _first(
			single.get("url"),
			getattr(conf, "sahbi_ollama_url", None) if conf else None,
			os.environ.get("SAHBI_OLLAMA_URL"),
			DEFAULT_URL,
		).rstrip("/"),
		"model": _first(
			single.get("model"),
			getattr(conf, "sahbi_ollama_model", None) if conf else None,
			os.environ.get("SAHBI_OLLAMA_MODEL"),
			DEFAULT_MODEL,
		),
		"timeout": int(
			_first(
				single.get("timeout"),
				getattr(conf, "sahbi_ollama_timeout", None) if conf else None,
				os.environ.get("SAHBI_OLLAMA_TIMEOUT"),
				DEFAULT_TIMEOUT,
			)
		),
	}


def _single_settings() -> dict:
	try:
		if not getattr(frappe, "db", None) or not frappe.db.exists("DocType", "Sahbi LLM Settings"):
			return {}
		doc = frappe.get_cached_doc("Sahbi LLM Settings")
		return {
			"url": doc.ollama_url,
			"model": doc.ollama_model,
			"timeout": doc.timeout_seconds,
		}
	except Exception:
		return {}


def _first(*values):
	for value in values:
		if value not in (None, ""):
			return value
	return values[-1]
