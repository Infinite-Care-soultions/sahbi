# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.rag.embeddings import cosine, embed_text
from sahbi.rag.lexical import lexical_score
from sahbi.rag.loader import load_knowledge

_KNOWLEDGE: list[dict] | None = None


def knowledge_rows() -> list[dict]:
	global _KNOWLEDGE
	if _KNOWLEDGE is None:
		_KNOWLEDGE = load_knowledge()
	return _KNOWLEDGE


def retrieve_context(text: str, limit: int = 4) -> list[dict]:
	"""Return bounded knowledge rows. Failure returns an empty list."""
	try:
		return _retrieve(text, limit=limit)
	except Exception:
		return []


def _embeddings_enabled() -> bool:
	try:
		import frappe

		return bool(getattr(getattr(frappe, "conf", None), "sahbi_rag_embeddings", False))
	except Exception:
		return False


def _retrieve(text: str, limit: int) -> list[dict]:
	if not (text or "").strip():
		return []
	message_vec = embed_text(text) if _embeddings_enabled() else None
	ranked = []
	seen = set()
	for entry in knowledge_rows():
		if entry["id"] in seen:
			continue
		score = lexical_score(text, entry)
		if message_vec:
			entry_vec = embed_text(entry["text"])
			if entry_vec:
				score += cosine(message_vec, entry_vec)
		if score <= 0:
			continue
		seen.add(entry["id"])
		ranked.append((score, entry))
	ranked.sort(key=lambda item: item[0], reverse=True)
	return [entry for _score, entry in ranked[:limit]]
