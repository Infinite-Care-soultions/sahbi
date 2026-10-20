# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

import re

EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

NUMBER_WORDS = {
	"واحد": 1,
	"اتنين": 2,
	"اثنين": 2,
	"تلاته": 3,
	"ثلاثه": 3,
	"اربعه": 4,
	"خمسه": 5,
	"سته": 6,
	"سبعه": 7,
	"تمانيه": 8,
	"ثمانيه": 8,
	"تسعه": 9,
	"عشره": 10,
	"ميه": 100,
	"مائه": 100,
	"تلاتميه": 300,
	"تلتميه": 300,
	"الف": 1000,
	"الفين": 2000,
}

SCALE_WORDS = {
	"الاف": 1000,
	"الوف": 1000,
	"الاف": 1000,
}


def fold_arabic(text: str) -> str:
	value = (text or "").strip().translate(EASTERN_DIGITS)
	for src, dest in (
		("أ", "ا"),
		("إ", "ا"),
		("آ", "ا"),
		("ٱ", "ا"),
		("ة", "ه"),
		("ى", "ي"),
	):
		value = value.replace(src, dest)
	value = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", value)
	value = re.sub(r"(?<=\d),(?=\d{3}\b)", "", value)
	value = re.sub(r"[؟!،]+", " ", value)
	return re.sub(r"\s+", " ", value).casefold()


def word_amount(folded: str) -> str | None:
	tokens = [_bare_number_token(token) for token in folded.split()]
	for index, token in enumerate(tokens):
		if token in NUMBER_WORDS and index + 1 < len(tokens) and tokens[index + 1] in {"الاف", "الوف"}:
			return str(NUMBER_WORDS[token] * 1000)
		if token in NUMBER_WORDS:
			return str(NUMBER_WORDS[token])
	return None


def _bare_number_token(token: str) -> str:
	if token.startswith("ب") and token[1:] in NUMBER_WORDS:
		return token[1:]
	if token.startswith("ب") and token[1:] in {"الاف", "الوف", "الف", "الفين"}:
		return token[1:]
	return token
