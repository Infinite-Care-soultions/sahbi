# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import json
from pathlib import Path

from sahbi.chat.normalize import fold_arabic
from sahbi.rag.schema import validate_knowledge_entry

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"


def load_knowledge() -> list[dict]:
	rows = []
	for path in sorted(KNOWLEDGE_DIR.glob("*.json")):
		payload = json.loads(path.read_text(encoding="utf-8"))
		for raw in payload:
			entry = validate_knowledge_entry(raw)
			entry["normalized"] = fold_arabic(entry["text"] + " " + entry["notes"] + " " + " ".join(entry["clues"]))
			entry["source"] = path.name
			rows.append(entry)
	return rows
