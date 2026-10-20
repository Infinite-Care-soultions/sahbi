# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.chat.normalize import fold_arabic


def lexical_score(message: str, entry: dict) -> float:
	folded = fold_arabic(message)
	if not folded:
		return 0.0
	haystack = entry.get("normalized") or fold_arabic(entry.get("text") or "")
	tokens = [token for token in folded.split() if len(token) > 1]
	if not tokens:
		return 0.0
	hits = sum(1 for token in tokens if token in haystack)
	clue_hits = sum(1 for clue in entry.get("clues") or [] if fold_arabic(clue) in folded)
	bonus = 0.5 if fold_arabic(entry.get("text") or "")[:12] in folded else 0.0
	return (hits / len(tokens)) + clue_hits + bonus
