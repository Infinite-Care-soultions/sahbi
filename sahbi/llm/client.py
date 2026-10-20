# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import requests
from frappe import _

from sahbi.llm.errors import SahbiLLMUnavailable
from sahbi.llm.settings import get_llm_settings


def complete(messages: list[dict], *, model: str | None = None, timeout: int | None = None) -> str:
	settings = get_llm_settings()
	chosen_model = model or settings["model"]
	chosen_timeout = timeout if timeout is not None else settings["timeout"]
	url = f"{settings['url']}/api/chat"

	try:
		response = requests.post(
			url,
			json={
				"model": chosen_model,
				"messages": messages,
				"stream": False,
				"format": "json",
				"options": {"temperature": 0},
			},
			timeout=(5, chosen_timeout),
		)
	except requests.RequestException as exc:
		raise SahbiLLMUnavailable(_("Ollama is unavailable: {0}").format(exc)) from exc

	if response.status_code != 200:
		raise SahbiLLMUnavailable(
			_("Ollama returned HTTP {0}: {1}").format(response.status_code, response.text[:200])
		)

	try:
		payload = response.json()
		content = payload["message"]["content"]
	except (ValueError, KeyError, TypeError) as exc:
		raise SahbiLLMUnavailable(_("Ollama returned an unexpected response")) from exc

	if not content or not str(content).strip():
		raise SahbiLLMUnavailable(_("Ollama returned an empty response"))
	return str(content)


def inspect_ollama() -> dict:
	settings = get_llm_settings()
	try:
		response = requests.get(f"{settings['url']}/api/tags", timeout=5)
		response.raise_for_status()
		models = [row.get("name") for row in response.json().get("models", [])]
		return {
			"available": True,
			"url": settings["url"],
			"configured_model": settings["model"],
			"configured_model_present": settings["model"] in models,
			"models": models,
		}
	except requests.RequestException as exc:
		return {
			"available": False,
			"url": settings["url"],
			"configured_model": settings["model"],
			"configured_model_present": False,
			"models": [],
			"error": str(exc),
		}
