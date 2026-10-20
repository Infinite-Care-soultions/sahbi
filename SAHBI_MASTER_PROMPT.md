# Project: Sahbi (صاحبي)

## 1. Product Overview

Build a personal financial assistant for everyday Egyptian users,
especially tradespeople, drivers, households, and small workshops.

Product name: Sahbi (صاحبي)
Primary language: Egyptian Arabic
Initial interface: Text-based
Backend: Frappe Framework and Python
Database: MariaDB
Local LLM: Qwen through Ollama

The assistant should feel like a practical, trustworthy Egyptian
friend who understands everyday money management.

It must be friendly, direct, nonjudgmental, and easy to use.

The user must not need accounting knowledge.

## 2. Core Architecture

Use Frappe as the application framework.

Frappe/Python and MariaDB are the authoritative sources for:
- Financial transactions
- Payment records
- Outstanding balances
- Person accounts
- Opening balances
- Reports
- Audit history
- Permissions and validations

Qwen through Ollama is responsible for:
- Understanding Egyptian colloquial Arabic
- Classifying user messages
- Extracting transaction details
- Identifying transaction intent
- Understanding references to previous transactions
- Preparing structured search requests
- Generating conversational responses from verified application results

The LLM must never independently calculate financial totals,
invent transactions, modify database records, or fabricate results.

All financial calculations must be performed by deterministic
Python business logic and database queries.

Never tell the user that a transaction was saved until the
database operation has completed successfully.

## 3. Initial Scope

The first version must support:

- Recording income
- Recording expenses
- Recording sales
- Recording purchases
- Recording generic loans
- Recording partial payments
- Recording collections and repayments
- Tracking outstanding amounts owed by people
- Tracking amounts owed to people
- Optional opening balances
- Financial transaction history
- Correcting and cancelling transactions safely
- Searching recorded transactions using natural language
- Basic income and expense reports
- Person account statements
- Egyptian Arabic conversational interaction

The initial version is NOT:
- A complete ERP system
- A woodworking-specific application
- A formal invoicing system
- A cash-register system
- A bank-account tracking application
- A stock-management system
- A manufacturing-management system

Do not implement unrelated features without explicit approval.

## 4. Financial Spaces

The MVP uses one financial workspace per user.

Household and work transactions can exist in the same workspace.

Household transaction types:
- Income
- Expense

Work transaction types:
- Income
- Expense
- Sale
- Purchase
- Loan

Loans are distinct from income and expenses.

Do not force users to create separate household and work spaces.

Keep the architecture extensible for future independent spaces.

## 5. People

A person is optional in every transaction.

A person can act as a buyer, seller, supplier, employee, borrower,
or lender without needing separate person records for each role.

Do not assign an immutable business role to a person.

Use one person record and preserve the type of each transaction.

If a referenced person does not exist, ask for clarification or
confirmation before creating a new person when necessary.

Never invent a person's identity.

## 6. Transaction Rules

Every financial operation must have:
- Transaction type
- Amount
- Transaction date
- Creation timestamp
- Financial workspace
- Audit information

The person and description are optional.

If no date is provided, use the current date according to the
application's configured timezone.

Store both:
- transaction_date: when the event actually happened
- creation timestamp: when the system recorded it

Preserve the original user description.

Do not require categories in the MVP.

## 7. Incoming Money

When the user says:
"محمد اداني 2000 جنيه"

If there is no clearly identifiable existing transaction or debt
to settle, record the amount as new income.

If the message clearly refers to repayment of a loan or payment
against an existing sale, link the payment to that operation.

Never count repayment of an existing receivable as new income
a second time.

If several materially different matching operations exist,
ask the user which one is intended.

Prefer minimal questions.

## 8. Outgoing Money

When the user says:
"دفعت لمحمد 1000 جنيه"

If no clearly identifiable existing obligation exists, record
the amount as an expense.

If the payment clearly settles an existing purchase, loan, or
other obligation, link it to that operation.

Do not record the same payment as a new expense if it is already
settling an operation whose financial value was recorded.

If multiple plausible obligations exist, ask a short question.

## 9. Sales and Purchases

An original sale or purchase has one record containing its total
value.

A sale or purchase can be:
- Fully paid
- Partially paid
- Unpaid

Every payment must have its own independent record.

Each payment record must include:
- Unique identifier
- Amount
- Payment date
- Creation timestamp
- Reference to the original transaction or transactions
- Audit information

Calculate paid amounts and outstanding amounts from the actual
payment records.

Never create a new sale or purchase simply because a payment
was received or made.

A single payment can be allocated across multiple original
transactions.

Record a payment once and represent its allocations separately.

Never allocate a payment randomly.

If allocation is ambiguous, ask the user.

## 10. Generic Loans

Loans must be represented separately from income and expenses.

Example:
"سلفت محمد 2000 جنيه"

This creates an amount receivable from Mohamed.

Example:
"استلفت من محمد 2000 جنيه"

This creates an amount payable by the user.

Repayments must link to the original loan whenever identifiable.

A loan repayment is not new income or a new expense.

A generic loan type must support worker advances without creating
a special transaction type for every person category.

## 11. Opening Balances

Opening balances are optional.

Users can start without opening balances and add them later.

Opening balances must not be treated as new income, expense,
sale, purchase, or loan activity.

Examples:
"محمد ليه 2000 جنيه حساب قديم"
"أنا عليّ لأحمد 1500 جنيه من حساب قديم"

Record the opening balance in an auditable way.

Never force the user to provide opening balances during setup.

## 12. Cash and Bank Scope

The MVP does not maintain cash, bank, or card balances.

Do not claim to know the user's actual cash or bank balance.

The system can calculate income, expenses, outstanding receivables,
outstanding payables, loan balances, and recorded financial activity.

Clearly distinguish these figures in reports.

## 13. Corrections and Cancellations

Never permanently delete posted financial records.

Never silently modify posted financial values.

Every correction or cancellation requires explicit user confirmation.

Before execution:
1. Identify the original transaction.
2. Show the current values.
3. Show the proposed change.
4. Explain the financial impact where applicable.
5. Obtain explicit confirmation.

Preserve audit history, including:
- Original values
- Corrected values where applicable
- Reason
- User
- Timestamp
- Related replacement or reversal records

Use a safe reversal or auditable adjustment strategy.

Review linked payments and allocations before changing or
cancelling an original transaction.

Prevent inconsistent financial balances.

## 14. Duplicate Protection

Implement two distinct mechanisms.

Technical idempotency:
The same retried request must not post the same operation twice.

Semantic duplicate detection:
Check relevant attributes such as amount, person, description,
transaction type, and timing.

Matching amounts alone do not prove a duplicate.

When a potential duplicate is found, ask the user whether the
operation is new.

Do not silently delete or reject a legitimate transaction.

## 15. Natural Language Search

Users can ask questions such as:
"اشتريت خشب بكام الشهر ده؟"
"صرفنا كام على نقل الخشب؟"
"محمد لسه ليه كام؟"
"دفعت لمحمد كام الشهر اللي فات؟"

Qwen may extract search intent and relevant terms.

Python and MariaDB must perform the actual filtering,
aggregation, and calculation.

Preserve semantic distinctions between:
- Income and expense
- Sale and purchase
- Wood and wood transportation
- New income and collection against a previous sale
- Loan principal and loan repayment

Do not mix unrelated transactions in search results.

Return a clear response when there is insufficient data.

## 16. Message Routing

Every user message must be classified into one of three categories:

1. Create, correct, or cancel a financial operation.
2. Query or report about recorded financial data.
3. Ordinary conversation.

Do not treat ordinary conversation as a financial transaction.

Corrections and cancellations require explicit confirmation.

## 17. User Experience

Keep the interaction simple.

Ask only for missing information that is necessary.

Do not ask for an optional person, description, or category.

Use conversational Egyptian Arabic by default.

If a transaction is clear and complete, record it without
unnecessary questions.

Confirm a successful operation with an accurate summary.

If a request is ambiguous in a way that affects financial
correctness, ask one concise clarification question.

## 18. Engineering Rules

Before changing code:
- Inspect the existing repository.
- Inspect the Frappe version and installed applications.
- Follow the existing project structure.
- Avoid unnecessary dependencies.
- Do not rewrite unrelated files.

Use standard Frappe conventions.

Use DocTypes and server-side business logic where appropriate.

Use database transactions for operations that must succeed or
fail together.

Enforce permissions on every server-side operation.

Validate monetary amounts using appropriate decimal handling.
Never use binary floating-point arithmetic for financial values.

Add automated tests for financial business rules.

Do not expose secrets or sensitive personal data in logs.

Do not place business rules inside LLM prompts as the only
enforcement mechanism.

Do not use the LLM to execute arbitrary SQL or Python code.

## 19. Development Workflow

Implement the project in small, testable phases.

For each phase:
1. Inspect the current code.
2. Explain the implementation plan.
3. Implement only the requested phase.
4. Add or update tests.
5. Run available tests.
6. Fix failures introduced by the changes.
7. Report files changed and test results.
8. Identify any remaining blockers.

Do not skip ahead to later phases.

Do not claim tests passed unless they were actually executed.

Do not claim functionality exists unless it has been implemented
and verified.

When a requirement is ambiguous, identify the ambiguity rather
than inventing a product decision.

The master specification takes precedence over assumptions
made by the coding assistant.