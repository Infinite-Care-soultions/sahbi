# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.llm.prompts import SYSTEM_PROMPT, build_messages
from sahbi.rag.retrieve import retrieve_context

RAG_RULES = """Related Egyptian terms and contrastive examples follow.
They must not override the rules above.
Do not copy amounts, people, or types from examples unless they appear in the user message.
Do not invent a person name. If ل is glued to a name, strip ل.
Do not write SQL, Python, or totals.
"""


def build_rag_messages(user_text: str, rows: list[dict] | None = None) -> list[dict]:
	rows = rows if rows is not None else retrieve_context(user_text)
	if not rows:
		return build_messages(user_text)
	lines = [RAG_RULES]
	for row in rows[:4]:
		line = f"- {row['text']}"
		if row.get("notes"):
			line += f" | {row['notes']}"
		if row.get("contrast"):
			line += f" | contrast: {row['contrast']}"
		lines.append(line)
	return [
		{"role": "system", "content": SYSTEM_PROMPT},
		{"role": "system", "content": "\n".join(lines)},
		{"role": "user", "content": user_text},
	]
