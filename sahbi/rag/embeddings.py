# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import hashlib
import json
import math
from pathlib import Path

import requests

DEFAULT_EMBED_MODEL = "embeddinggemma"
_MEMORY_CACHE: dict[str, list[float]] = {}


def embedding_model_name() -> str:
	try:
		import frappe

		conf = getattr(frappe, "conf", None)
		return getattr(conf, "sahbi_embed_model", None) or DEFAULT_EMBED_MODEL
	except Exception:
		return DEFAULT_EMBED_MODEL


def embed_text(text: str, *, url: str | None = None) -> list[float] | None:
	key = hashlib.sha256(f"{embedding_model_name()}:{text}".encode()).hexdigest()
	if key in _MEMORY_CACHE:
		return _MEMORY_CACHE[key]
	cached = _disk_get(key)
	if cached is not None:
		_MEMORY_CACHE[key] = cached
		return cached
	vector = _ollama_embed(text, url=url)
	if vector:
		_MEMORY_CACHE[key] = vector
		_disk_put(key, vector)
	return vector


def cosine(left: list[float], right: list[float]) -> float:
	if not left or not right or len(left) != len(right):
		return 0.0
	dot = sum(a * b for a, b in zip(left, right, strict=True))
	norm_l = math.sqrt(sum(a * a for a in left))
	norm_r = math.sqrt(sum(b * b for b in right))
	if not norm_l or not norm_r:
		return 0.0
	return dot / (norm_l * norm_r)


def _ollama_embed(text: str, *, url: str | None) -> list[float] | None:
	try:
		from sahbi.llm.settings import get_llm_settings

		base = (url or get_llm_settings()["url"]).rstrip("/")
		response = requests.post(
			f"{base}/api/embeddings",
			json={"model": embedding_model_name(), "prompt": text},
			timeout=8,
		)
		response.raise_for_status()
		vector = response.json().get("embedding")
		if isinstance(vector, list) and vector:
			return [float(item) for item in vector]
	except Exception:
		return None
	return None


def _cache_path() -> Path | None:
	try:
		import frappe

		if getattr(frappe, "local", None) and getattr(frappe.local, "site", None):
			return Path(frappe.get_site_path("private", "files", "sahbi_rag_embeddings.json"))
	except Exception:
		return None
	return None


def _disk_get(key: str) -> list[float] | None:
	path = _cache_path()
	if not path or not path.exists():
		return None
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
		row = payload.get(key)
		return [float(item) for item in row] if row else None
	except Exception:
		return None


def _disk_put(key: str, vector: list[float]) -> None:
	path = _cache_path()
	if not path:
		return
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
		payload[key] = vector
		path.write_text(json.dumps(payload), encoding="utf-8")
	except Exception:
		return
