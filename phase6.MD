# PHASE 6: Security, Financial Integrity, and Acceptance Testing

Status: COMPLETE (audit)
Date: 2026-10-20
Site: shbi.localhost
App: sahbi 0.0.1 (develop)

Read `SAHBI_MASTER_PROMPT.md` completely.

This phase audits the implemented Sahbi application. It does not
add product features. It does not claim production readiness.

---

## Scope of this phase

Verify twenty controls, run the full test suite, fix defects found
in the audit, and report what a real-user pilot still needs.

---

## Audit result

| # | Control | Result |
|---|---|---|
| 1 | Users cannot access another workspace | Pass. List filters, `has_permission`, engine, and document validate all check the workspace owner. |
| 2 | Server-side permissions | Pass for Sahbi User. Guest cannot call chat. Workspace owner cannot be reassigned. System Manager still sees every workspace. |
| 3 | Retry idempotency | Pass. Same workspace + key replays one submitted row. |
| 4 | Independent payment records | Pass. Payment is its own DocType with separate allocations. |
| 5 | Allocation limits | Pass. Cannot exceed payment amount or entry outstanding. |
| 6 | Outstanding calculation | Pass. `amount − submitted allocations`, including opening balances. |
| 7 | Settlements are not income/expense | Pass. Collections and repayments stay on Sahbi Payment. |
| 8 | Loans are not income/expense | Pass. Separate type and report kind. |
| 9 | Opening balances are not new activity | Pass. Separate type. Income/expense totals stay zero. |
| 10 | Posted records cannot be silently deleted | Pass. `on_trash` blocks `docstatus != 0`. Cancelled rows remain. |
| 11 | Corrections need confirmation | Pass on the engine/chat path (`confirm=True`). |
| 12 | Cancellations need confirmation | Pass on the engine/chat path. Desk cancel still exists for roles that have Cancel. |
| 13 | Linked payments handled | Pass. Cancelling an entry through the engine cancels allocations and orphan payments. |
| 14 | LLM cannot bypass validation | Pass. Forbidden keys (`sql`, `python`, `totals`) are rejected. |
| 15 | LLM cannot write the database | Pass. `interpret_message` does not import the engine. |
| 16 | Invalid amounts and dates | Pass. `to_money` and `getdate` reject bad values. Amount must be > 0. |
| 17 | Decimal money | Pass. Calculations use `Decimal`, stored as 2-dp strings. |
| 18 | No false success | Pass. Chat replies `اتسجل` only after a submitted row exists. Failed insert returns an error. |
| 19 | Search does not mix types | Pass. Wood purchase and wood transport stay apart. Mixed types are not summed. |
| 20 | No fabricated cash/bank | Pass. `cash_or_bank` and `profit` return a limitation and no number. |

These twenty controls now have dedicated tests in
`sahbi/tests/test_acceptance.py`.

---

## Defects fixed in this phase

- `has_permission` no longer treats a string document as allowed.
- Financial DocTypes now call `assert_workspace_access` on validate.
- A Sahbi User cannot change `Sahbi Workspace.user`.
- Chat whitelist methods set `allow_guest=False`.

---

## Security findings

1. **System Manager and Administrator can read every workspace.**
   That is normal Frappe admin access. Do not give those roles to
   a pilot user.

2. **Sahbi User can still create, submit, and cancel through Desk
   forms.** Chat is the product path. Desk posting skips chat
   clarification. Desk cancel uses Frappe's dialog, not the engine
   preview. Document validation and allocation limits still apply.

3. **Document names are sequential** (`ENT-#####`, `PAY-#####`).
   List and form APIs check permission. Guessing a name does not
   grant read through `has_permission`.

4. **Ollama is a local HTTP service.** The model is not a trust
   boundary. Server validation is.

5. **`shbi.localhost` is a development site.**
   `developer_mode` and `allow_tests` are on. That is not a
   production configuration.

---

## Financial-integrity findings

- Money is `Decimal`, quantized to 0.01. Engine tests cover
  10.10 + 10.20 = 20.30.
- Outstanding is recalculated from submitted allocations.
- Settlements, loans, and openings stay out of income/expense.
- Engine cancel/correct without `confirm=True` does not change
  `docstatus`.
- A payment larger than outstanding can leave a remainder as
  income or expense. That is the Phase 2 settlement rule, not a
  silent double count of the allocated part.

---

## Known limitations

- Historical outstanding as-of a past date is not implemented.
  Current outstanding is live.
- Qwen `qwen2.5:1.5b` is small. Live Egyptian Arabic quality was
  not certified. Chat tests mock the model.
- The Desk page `/app/sahbi-chat` was not clicked in a browser
  during this audit.
- No WhatsApp, Messenger, or voice.
- No cash, bank, stock, or formal profit.
- Semantic duplicate detection still asks; it does not auto-reject.
- One workspace per user.

---

## Remaining blockers for production

Do **not** treat this app as production-ready.

Still required before real money:

1. A staging site without `developer_mode` / `allow_tests`
2. HTTPS, backups, and a restore drill
3. A larger Qwen model, evaluated on real Egyptian messages
4. A decision: lock Desk create/cancel for Sahbi User, or keep
   Desk as an admin tool
5. Browser walkthrough of صاحبي chat
6. Written support path when Ollama is down
7. Privacy review of Error Log contents

---

## Exact steps for a real-user pilot

Pilot only on a throwaway site, with fake amounts, after a backup.

1. Confirm the bench: `/home/beshoy/SAAS/frappe-press`
2. Confirm the site: `shbi.localhost`
3. Confirm Ollama: `systemctl status ollama` and
   `ollama list` shows `qwen2.5:1.5b` (or the configured model)
4. `bench --site shbi.localhost migrate`
5. `bench --site shbi.localhost run-tests --app sahbi`
   (must be OK)
6. Create the pilot user in Desk. Give only **Sahbi User**.
   Do not give System Manager.
7. Confirm a `Sahbi Workspace` exists for that user after login
8. Open `http://shbi.localhost:8000/app/sahbi-chat` (or the
   site's actual host/port)
9. Record, as separate messages:
   - اشتريت خشب بـ5000
   - صرفنا 250 على نقل الخشب
   - سلفت محمد 1000
   - محمد اداني 200
10. When asked, answer the clarification. Do not assume
    incoming money is income.
11. Ask:
    - اشتريت خشب بكام؟
    - صرفنا كام على نقل الخشب؟
    - محمد لسه ليه كام؟
    - معايا كام في البنك؟
12. Confirm wood and transport stay apart, outstanding includes
    the loan remainder, and the bank question is refused
13. Cancel one entry through chat (`الغي العملية` then `أيوه`)
    and confirm the row is still in the archive
14. Stop the pilot if any total is wrong. Do not correct live
    data by deleting rows.

---

## Verification

```bash
cd /home/beshoy/SAAS/frappe-press
bench --site shbi.localhost run-tests --app sahbi
```

Tests: `Ran 93 tests in 16.304s` — OK

73 earlier tests still pass.
20 acceptance tests cover the checklist above.

---

## Files created or changed

Created:

- `sahbi/tests/test_acceptance.py`

Changed:

- `sahbi/permissions.py` — stricter `has_permission`, validate hook
- `sahbi/hooks.py` — workspace access on financial DocTypes
- `sahbi/sahbi/doctype/sahbi_workspace/sahbi_workspace.py` — owner lock
- `sahbi/chat/api.py` — `allow_guest=False`
- `phase6.MD` — this report

---

## Phase 6 conclusion

The twenty controls hold in automated tests on `shbi.localhost`.
Sahbi is ready for a **supervised pilot with fake money**, not
for production and not for real balances.
