# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Create a Sahbi user + workspace from Facebook Messenger when the PSID is new."""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe.utils import validate_email_address
from frappe.utils.password import update_password

from sahbi.chat import replies
from sahbi.chat.normalize import fold_arabic
from sahbi.workspace import ensure_sahbi_role, ensure_workspace_for_user

CACHE_TTL = 45 * 60
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

YES_WORDS = {
	"ايوه",
	"أيوه",
	"ايوة",
	"أيوة",
	"ايوا",
	"أيوا",
	"اه",
	"آه",
	"نعم",
	"تمام",
	"ماشي",
	"حاضر",
	"يلا",
	"اوك",
	"اوكي",
	"ok",
	"okay",
	"yes",
	"y",
}
NO_WORDS = {
	"لا",
	"لأ",
	"لاء",
	"بلاش",
	"الغاء",
	"الغي",
	"إلغاء",
	"cancel",
	"no",
}
CREATE_WORDS = {
	"اعمل حساب",
	"اعمل الحساب",
	"حساب جديد",
	"سجلني",
	"سجل",
	"عايز حساب",
	"عاوز حساب",
	"اعمل اكونت",
	"signup",
	"sign up",
	"register",
}
HAS_ACCOUNT_WORDS = {
	"عندي حساب",
	"عندى حساب",
	"مسجل",
	"عندي اكونت",
	"already",
}


def handle_unmapped_sender(psid: str, text: str) -> str:
	state = _get_state(psid) or {"step": "start"}
	step = state.get("step") or "start"
	text = (text or "").strip()

	if step == "start":
		return _step_start(psid, text, state)
	if step == "name":
		return _step_name(psid, text, state)
	if step == "email":
		return _step_email(psid, text, state)
	if step == "confirm":
		return _step_confirm(psid, text, state)
	_clear_state(psid)
	return replies.facebook_signup_invite()


def _step_start(psid: str, text: str, state: dict[str, Any]) -> str:
	folded = fold_arabic(text)
	if _is_no(folded):
		_clear_state(psid)
		return replies.facebook_signup_cancelled()
	if _has_account(folded):
		_set_state(psid, {"step": "start"})
		return replies.facebook_signup_has_account()
	if text and (_is_yes(folded) or _wants_create(folded)):
		state.update(step="name")
		_set_state(psid, state)
		return replies.facebook_signup_ask_name()
	_set_state(psid, {"step": "start"})
	return replies.facebook_signup_invite()


def _step_name(psid: str, text: str, state: dict[str, Any]) -> str:
	folded = fold_arabic(text)
	if _is_no(folded):
		_clear_state(psid)
		return replies.facebook_signup_cancelled()
	name = _clean_name(text)
	if not name:
		return replies.facebook_signup_invalid_name()
	state.update(step="email", full_name=name)
	_set_state(psid, state)
	return replies.facebook_signup_ask_email(name)


def _step_email(psid: str, text: str, state: dict[str, Any]) -> str:
	folded = fold_arabic(text)
	if _is_no(folded):
		_clear_state(psid)
		return replies.facebook_signup_cancelled()
	email = _extract_email(text)
	if not email:
		return replies.facebook_signup_invalid_email()
	if frappe.db.exists("User", email):
		return replies.facebook_signup_email_taken()
	state.update(step="confirm", email=email)
	_set_state(psid, state)
	return replies.facebook_signup_confirm(state.get("full_name") or "", email)


def _step_confirm(psid: str, text: str, state: dict[str, Any]) -> str:
	folded = fold_arabic(text)
	if _is_no(folded):
		_clear_state(psid)
		return replies.facebook_signup_cancelled()
	if not _is_yes(folded) and not _wants_create(folded):
		return replies.facebook_signup_say_yes_no()
	try:
		password = _create_account(psid, state)
	except Exception:
		frappe.log_error(title="sahbi facebook signup failed")
		_clear_state(psid)
		return replies.facebook_signup_failed()
	_clear_state(psid)
	return replies.facebook_signup_done(state.get("full_name") or "", state.get("email") or "", password)


def _create_account(psid: str, state: dict[str, Any]) -> str:
	email = str(state.get("email") or "").strip().lower()
	full_name = str(state.get("full_name") or "").strip()
	if not email or frappe.db.exists("User", email):
		raise ValueError("email unavailable")

	ensure_sahbi_role()
	first, last = _split_name(full_name)
	password = _new_password()
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"last_name": last,
			"send_welcome_email": 0,
			"user_type": "System User",
		}
	)
	user.flags.no_welcome_mail = True
	user.flags.ignore_password_policy = True
	user.insert(ignore_permissions=True)
	user.add_roles("Sahbi User")
	update_password(user.name, password)

	workspace = ensure_workspace_for_user(user=user.name)
	if workspace:
		frappe.db.set_value(
			"Sahbi Workspace",
			workspace,
			{
				"facebook_psid": psid,
				"title": full_name or user.name,
			},
		)
	frappe.db.commit()
	return password


def _clean_name(text: str) -> str:
	name = re.sub(r"\s+", " ", (text or "").strip())
	if EMAIL_RE.search(name):
		return ""
	if len(name) < 2:
		return ""
	folded = fold_arabic(name)
	if _is_yes(folded) or _is_no(folded) or _wants_create(folded):
		return ""
	return name[:80]


def _extract_email(text: str) -> str:
	match = EMAIL_RE.search(text or "")
	if not match:
		return ""
	email = match.group(0).strip().lower()
	checked = validate_email_address(email, throw=False)
	return str(checked or "").strip().lower()


def _split_name(full_name: str) -> tuple[str, str]:
	parts = [p for p in (full_name or "").split() if p]
	if not parts:
		return "Sahbi", "User"
	if len(parts) == 1:
		return parts[0], "-"
	return parts[0], " ".join(parts[1:])


def _new_password() -> str:
	return f"Sb{frappe.generate_hash(length=8)}9"


def _is_yes(folded: str) -> bool:
	return folded in YES_WORDS or folded in {fold_arabic(w) for w in YES_WORDS}


def _is_no(folded: str) -> bool:
	return folded in NO_WORDS or folded in {fold_arabic(w) for w in NO_WORDS}


def _wants_create(folded: str) -> bool:
	if folded in {fold_arabic(w) for w in CREATE_WORDS}:
		return True
	return any(fold_arabic(w) in folded for w in ("اعمل حساب", "حساب جديد", "سجلني"))


def _has_account(folded: str) -> bool:
	return any(fold_arabic(w) in folded for w in HAS_ACCOUNT_WORDS)


def _key(psid: str) -> str:
	return f"sahbi:fb_signup:{psid}"


def _get_state(psid: str) -> dict[str, Any] | None:
	raw = frappe.cache().get_value(_key(psid))
	if not raw:
		return None
	if isinstance(raw, dict):
		return raw
	try:
		data = json.loads(raw)
	except Exception:
		return None
	return data if isinstance(data, dict) else None


def _set_state(psid: str, state: dict[str, Any]) -> None:
	frappe.cache().set_value(_key(psid), json.dumps(state), expires_in_sec=CACHE_TTL)


def _clear_state(psid: str) -> None:
	try:
		frappe.cache().delete_value(_key(psid))
	except Exception:
		pass
