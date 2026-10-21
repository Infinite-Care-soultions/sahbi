# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

from sahbi.www._legal_context import build_legal_context

no_cache = 1
sitemap = 1


def get_context(context):
	build_legal_context(context)
	context.title = "Terms of Service — Sahbi"
	context.metatags = {
		"title": context.title,
		"description": "Terms of Service for Sahbi, the Egyptian personal-finance assistant on Facebook Messenger.",
		"og:type": "website",
	}
	return context
