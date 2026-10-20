# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

ENTRY_KINDS = {"term", "example", "contrast"}
REQUIRED_KEYS = {"id", "kind", "text"}


def validate_knowledge_entry(row: dict) -> dict:
	if not isinstance(row, dict):
		raise ValueError("knowledge entry must be an object")
	missing = REQUIRED_KEYS - set(row)
	if missing:
		raise ValueError(f"knowledge entry missing {sorted(missing)}")
	if row["kind"] not in ENTRY_KINDS:
		raise ValueError(f"invalid knowledge kind: {row['kind']}")
	return {
		"id": str(row["id"]),
		"kind": row["kind"],
		"text": str(row["text"]).strip(),
		"intent": row.get("intent"),
		"operation_type": row.get("operation_type"),
		"query_kind": row.get("query_kind"),
		"notes": row.get("notes") or "",
		"contrast": row.get("contrast") or "",
		"clues": [str(item) for item in row.get("clues") or [] if item],
	}
