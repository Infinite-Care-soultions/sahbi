# Copyright (c) 2026, Beshoy Atef and contributors
# For license information, please see license.txt

INTENTS = {
	"financial_operation",
	"financial_query",
	"ordinary_conversation",
}

OPERATION_TYPES = {
	"income",
	"expense",
	"sale",
	"purchase",
	"loan_receivable",
	"loan_payable",
	"opening_receivable",
	"opening_payable",
	"incoming_money",
	"outgoing_money",
	"correction",
	"cancellation",
}

QUERY_KINDS = {
	"search",
	"person_balance",
	"income_expense",
	"period_report",
	"income",
	"expense",
	"sale",
	"purchase",
	"loan_receivable",
	"loan_payable",
	"opening_balance",
	"collections",
	"repayments",
	"outstanding_receivable",
	"outstanding_payable",
	"cash_or_bank",
	"profit",
}

FORBIDDEN_KEYS = {
	"sql",
	"query_sql",
	"python",
	"code",
	"script",
	"execute",
	"totals",
	"total",
	"calculated_total",
	"sum",
}

ALLOWED_ROOT_KEYS = {
	"intent",
	"operation",
	"query",
	"missing_fields",
	"is_ambiguous",
	"ambiguity_reason",
	"clarification_question",
}

ALLOWED_OPERATION_KEYS = {
	"type",
	"amount",
	"person_name",
	"description",
	"date_expression",
	"previous_operation_references",
	"loan_direction",
}

ALLOWED_QUERY_KEYS = {
	"kind",
	"search_terms",
	"person_name",
	"date_expression",
}

JSON_SCHEMA_DESCRIPTION = """
{
  "intent": "financial_operation | financial_query | ordinary_conversation",
  "operation": {
    "type": "income|expense|sale|purchase|loan_receivable|loan_payable|opening_receivable|opening_payable|incoming_money|outgoing_money|correction|cancellation|null",
    "amount": "string number or null",
    "person_name": "string or null",
    "description": "string or null",
    "date_expression": "string or null",
    "previous_operation_references": ["string"],
    "loan_direction": "receivable|payable|null"
  },
  "query": {
    "kind": "search|person_balance|income_expense|period_report|income|expense|sale|purchase|loan_receivable|loan_payable|opening_balance|collections|repayments|outstanding_receivable|outstanding_payable|cash_or_bank|profit|null",
    "search_terms": ["string"],
    "person_name": "string or null",
    "date_expression": "string or null"
  },
  "missing_fields": ["string"],
  "is_ambiguous": false,
  "ambiguity_reason": "string or null",
  "clarification_question": "string or null"
}
""".strip()
