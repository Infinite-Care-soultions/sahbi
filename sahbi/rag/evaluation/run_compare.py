# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.rag.evaluate import run_deterministic_eval, run_live_eval


def main():
	deterministic = run_deterministic_eval()
	print("DETERMINISTIC", {k: deterministic[k] for k in ("total", "passed", "accuracy", "route_accuracy", "entity_accuracy", "seconds", "failures")})
	for mode in ("A", "B", "C"):
		live = run_live_eval(mode, limit=6)
		print(f"LIVE_{mode}", {k: live[k] for k in ("total", "passed", "accuracy", "seconds", "failures")})
