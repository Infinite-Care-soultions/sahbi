# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Redis helpers for Messenger: dedup, sender lock, restriction, reply caps."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import frappe

DEDUP_TTL_SECONDS = 86400
RESTRICT_TTL_SECONDS = 6 * 3600
REPLY_LIMIT_PER_MINUTE = 20
SENDER_LOCK_TTL = 90
SENDER_LOCK_WAIT = 25.0


def claim_event(event_key: str) -> bool:
	"""Atomically claim a message id. False means a duplicate that should be skipped."""
	if not event_key:
		return True
	try:
		cache = frappe.cache()
		redis_key = cache.make_key(f"sahbi:msgr:dedup:{event_key}")
		return bool(cache.set(redis_key, b"1", nx=True, ex=DEDUP_TTL_SECONDS))
	except Exception:
		return True


def sender_restricted(psid: str) -> bool:
	if not psid:
		return False
	try:
		return bool(frappe.cache().get_value(f"sahbi:msgr:restricted:{psid}", expires=True))
	except Exception:
		return False


def mark_sender_restricted(psid: str) -> None:
	if not psid:
		return
	try:
		frappe.cache().set_value(
			f"sahbi:msgr:restricted:{psid}",
			1,
			expires_in_sec=RESTRICT_TTL_SECONDS,
		)
	except Exception:
		pass


def reply_rate_ok(psid: str, *, limit: int = REPLY_LIMIT_PER_MINUTE, seconds: int = 60) -> bool:
	"""Allow at most `limit` outbound replies per sender per window."""
	return _incr_under_limit(f"sahbi:msgr:reply:{psid}", limit=limit, seconds=seconds)


def inbound_rate_ok(psid: str, *, limit: int = 30, seconds: int = 60) -> bool:
	return _incr_under_limit(f"sahbi:rl:psid:{psid}", limit=limit, seconds=seconds)


def _incr_under_limit(cache_key: str, *, limit: int, seconds: int) -> bool:
	try:
		cache = frappe.cache()
		redis_key = cache.make_key(cache_key)
		try:
			current = int(cache.incr(redis_key))
		except Exception:
			cache.delete(redis_key)
			current = int(cache.incr(redis_key))
		if current == 1:
			cache.expire(redis_key, seconds)
		return current <= limit
	except Exception:
		return True


@contextmanager
def sender_lock(psid: str, *, timeout: int = SENDER_LOCK_TTL, wait: float = SENDER_LOCK_WAIT) -> Iterator[None]:
	"""Serialize jobs for one PSID so replies stay in order."""
	if not psid or frappe.flags.in_test:
		yield
		return

	cache = frappe.cache()
	key = cache.make_key(f"sahbi:msgr:lock:{psid}")
	held = False
	deadline = time.time() + wait
	while True:
		try:
			held = bool(cache.set(key, b"1", nx=True, ex=timeout))
		except Exception:
			held = False
			break
		if held or time.time() >= deadline:
			break
		time.sleep(0.2)
	try:
		yield
	finally:
		if held:
			try:
				cache.delete(key)
			except Exception:
				pass
