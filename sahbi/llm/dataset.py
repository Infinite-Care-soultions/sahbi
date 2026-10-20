# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import json
from pathlib import Path


def dataset_path() -> Path:
	return Path(__file__).resolve().parent / "egyptian_messages.json"


def load_message_dataset() -> list[dict]:
	return json.loads(dataset_path().read_text(encoding="utf-8"))
