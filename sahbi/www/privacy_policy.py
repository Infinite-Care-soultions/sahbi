# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.www._legal_context import build_legal_context

no_cache = 1
sitemap = 1


def get_context(context):
	build_legal_context(context)
	context.title = "Privacy Policy — Sahbi"
	context.metatags = {
		"title": context.title,
		"description": "Privacy Policy for Sahbi. Explains how Messenger chats and personal finance records are collected and used.",
		"og:type": "website",
	}
	return context
