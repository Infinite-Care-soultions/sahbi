# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

"""Chat helpers. Import submodules directly so DocType load does not pull the engine."""

__all__ = ["get_conversation_history", "handle_message"]


def __getattr__(name):
	if name in {"get_conversation_history", "handle_message"}:
		from sahbi.chat.service import get_conversation_history, handle_message

		return get_conversation_history if name == "get_conversation_history" else handle_message
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
