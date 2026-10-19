# Aid Amuta Case Management System

## What this is

A web application for an Israeli nonprofit (עמותה) that gives small grants to people in need: rent, car repairs, childcare, baby supplies, and small medical costs. The system handles public intake, case management, committee decisions, payment records, and reporting. It implements a written aid procedure (נוהל חלוקת סיוע) adopted by the amuta's board. The procedure is the source of truth; this file summarises the parts that matter for the code.

Every rule in the procedure must be visible in code, configurable, and auditable. Nothing is decided silently.

## Hard constraints (never violate)

1. **Append-only decisions and payments.** Decisions, scores, approvals, recusals and payment records are never updated or deleted. A correction is a new record that references the one it supersedes.
2. **The system never moves money.** It produces an approved payment instruction (batch file) for the treasurer. The transfer is executed in the bank by two signatories. The system then records the bank reference. There is no payment-provider integration for outgoing funds.
3. **Minimum data.** Collect only what the procedure requires for the tier. Do not add fields "for later".
4. **Privacy by design.** Israeli Privacy Protection Law applies (Amendment 13, in force since August 2025, plus the Data Security Regulations). Treat the database as holding highly sensitive personal and financial information. Role-based access, full audit log, encryption at rest and in transit, retention and deletion.
5. **Hebrew first, right-to-left.** All applicant-facing and staff-facing UI in Hebrew with `dir="rtl"`. English is a secondary locale for code, logs and documentation only.
6. **Data stays in Israel.** All Azure resources in the Israel Central region.
7. **No insiders.** Founders, board, committee members, employees and their relatives cannot receive aid. The check is enforced in code, not left to the committee's memory.
8. **Amounts and thresholds are configuration, not code.** Tier boundaries, caps, cooling-off period and scoring thresholds live in a versioned config table the board controls. Every decision records which config version applied.

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, `next-intl` for Hebrew/English, Tailwind with RTL plugin |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic |
| Database | Demo: SQLite (file). Production: Azure Database for PostgreSQL Flexible Server (Israel Central) |
| Documents | Demo: local folder behind a storage interface. Production: Azure Blob Storage, private container, SAS links with short expiry |
| Staff auth | Demo: local dev login with role picker. Production: Microsoft Entra ID (OIDC), MFA required, app roles |
| Applicant auth | Passwordless one-time code. Demo: code printed to console. Production: SMS or email via Azure Communication Services |
| Secrets | Demo: `.env` (gitignored). Production: Azure Key Vault |
| Hosting | Demo: `docker compose up` or two local processes. Production: Azure Container Apps (API), Static Web Apps (frontend) |
| Monitoring | Production: Application Insights |
| Infra as code | Bicep (production only) |
| Tests | pytest (backend), Playwright (frontend), rules engine has 100% branch coverage |

## Demo first, Azure later

The demo runs entirely on a laptop with SQLite and a local documents folder. Production swaps in PostgreSQL, Blob Storage, Entra ID and ACS through configuration. To keep that swap mechanical:

- **One settings object** (`app/settings.py`, pydantic-settings) selects the database URL, storage backend, auth backend and notification backend. Nothing else in the code knows which environment it is in.
- **Dialect-neutral SQLAlchemy.** Use `Uuid`, `DateTime(timezone=True)`, `JSON`, `Numeric` and `Text`. No `ARRAY`, no `JSONB`, no Postgres-only functions in queries. Store money as integer agorot, not floats.
- **Alembic from day one.** Every schema change is a migration, run against SQLite in CI and against PostgreSQL in a second CI job (`services: postgres`). Alembic `batch_alter_table` mode is on so SQLite can handle `ALTER`.
- **Append-only via triggers, not grants.** SQLite has no role grants, so `BEFORE UPDATE` and `BEFORE DELETE` triggers that `RAISE(ABORT)` protect the append-only tables. The same triggers are created in PostgreSQL, and production adds role grants on top. Trigger DDL lives in a migration, written once per dialect.
- **Interfaces for I/O.** `DocumentStore`, `Notifier` and `AuthProvider` are abstract classes with a `Local*` and an `Azure*` implementation each. Domain and service code depend only on the interface.
- **Seed data.** `scripts/seed_demo.py` creates a config version, three staff users with roles, two referrers, and ten synthetic cases spread across statuses and tiers, so the demo opens with something to click through. Synthetic data only; never real applicants.
- **SQLite settings.** Enable WAL mode and `foreign_keys=ON` at connection time. Single API process in demo; concurrency is a production concern.
- **Migration to production** is: provision with Bicep, run Alembic against PostgreSQL, run `scripts/migrate_sqlite_to_pg.py` only if demo data must carry over (normally it should not), switch settings, run the security checklist.

What the demo does not prove: performance under load, encryption at rest, MFA, backup and restore. Say so when showing it.

## Repository layout

```
/api            FastAPI app
  /app
    /domain     pure Python rules engine, no I/O, no framework imports
    /models     SQLAlchemy models
    /schemas    Pydantic request/response models
    /routers    HTTP endpoints
    /services   orchestration between domain, db and storage
    /audit      audit event writer
  /alembic
  /tests
/web            Next.js app
  /app/(public) public site, application form, referral form, status page
  /app/(staff)  coordinator, committee, treasurer, auditor views
  /messages     he.json, en.json
/infra          Bicep templates
/docs           procedure (Hebrew), data dictionary, runbook
```

The `domain` package must stay pure: functions take data in, return decisions out, and never touch the database. This is what makes the rules testable and reviewable by non-engineers.

## Roles

| Role | Can |
| --- | --- |
| `applicant` | Submit and view own application, upload documents, see status, file an appeal |
| `referrer` | Submit a referral form (no login; identity verified by coordinator) |
| `coordinator` | Open cases, run eligibility gate, request documents, verify with vendors, prepare cases for committee, send decisions |
| `committee_member` | View assigned cases, score, approve or decline within tier authority, declare recusal |
| `committee_chair` | All of committee member plus emergency approvals and tier C decisions |
| `treasurer` | View approved payments, generate payment batch, record bank reference |
| `board_member` | Decide appeals, approve exceptions above caps, change config |
| `auditor` | Read-only access to everything including audit log |
| `admin` | Manage users and roles. No access to case content. |

Every access to a case file is written to the audit log with user, role, timestamp and purpose.

## Data model (core tables)

All tables have `id` (UUID), `created_at`, `created_by`. Append-only tables have no `updated_at` and are protected by `BEFORE UPDATE` / `BEFORE DELETE` abort triggers (both dialects); production PostgreSQL also withholds UPDATE and DELETE grants from the application role.

- **applicant**: national ID (hashed for lookup, encrypted for display), name, phone, email, address, household adults, household children, consent timestamp, consent version.
- **household**: groups applicants who share a household, for caps. Derived from applicant ID plus partner ID.
- **referrer**: name, role, organisation, phone, email, recognised_by (coordinator), recognised_at.
- **case** (mutable only in `status` and assignment): case number (year-sequence), applicant, referrer (optional), category (`rent`, `car`, `childcare`, `baby`, `medical`, `other`), amount requested, vendor name, vendor contact, urgency flag, description, status, tier, assigned coordinator, config_version.
- **document**: case, type, storage key, uploaded by, uploaded at, sha256, retention_until. Storage key never exposed; the `DocumentStore` returns a short-lived download link (local signed URL in demo, SAS in production) and every issue is logged.
- **eligibility_check** (append-only): case, five booleans with reasons, outcome, performed by.
- **verification** (append-only): case, vendor contacted, method, contact person, confirmed amount, notes, performed by.
- **score** (append-only): case, committee member, need (0–3), urgency (0–3), impact (0–3), alternatives (0–3), vulnerability (0–1), total, notes.
- **recusal** (append-only): case, committee member, reason.
- **decision** (append-only): case, outcome (`approve_full`, `approve_partial`, `approve_conditional`, `refer`, `decline`), amount approved, conditions, reasoning, approvers (list), config_version, supersedes (nullable), exception_flag, exception_approved_by.
- **appeal** (append-only): case, decision appealed, applicant statement, filed at, decided by (list), outcome, reasoning.
- **payment** (append-only): decision, vendor, vendor bank details (encrypted), amount, method (`bank_transfer`, `voucher`, `exception_cash`), batch id, status (`approved`, `in_batch`, `executed`, `failed`), bank reference, executed at, recorded by.
- **payment_batch** (append-only): generated by, generated at, file sha256, payment count, total, executed confirmed by.
- **follow_up** (append-only): case, contacted at, outcome, notes.
- **config_version** (append-only): JSON of tiers, caps, cooling-off days, scoring thresholds, categories; approved by (board), effective from.
- **audit_event** (append-only, written by trigger and by application): actor, role, action, entity, entity id, case id, purpose, ip, timestamp.
- **insider**: person (hashed ID), relationship type, source (board resolution), effective dates. Used by the eligibility gate.

## Case status machine

```
submitted → intake_review → ineligible (terminal, appealable)
                           → eligible → awaiting_documents → verification
                                                           → scoring → decision_pending
decision_pending → approved → payment_approved → in_batch → paid → follow_up → closed
                 → partial / conditional → (same as approved)
                 → referred (terminal)
                 → declined (terminal, appealable)
any appealable terminal → under_appeal → (appeal outcome re-enters at decision_pending or stays terminal)
emergency path: submitted → emergency_review → approved (chair + 1) → ratification_pending → ...
```

Transitions are defined in one place (`domain/workflow.py`) as an explicit table. Illegal transitions raise. Every transition writes an audit event.

## Rules engine (domain package)

### Eligibility gate (five checks, all must pass)

1. Category is in the configured list, or `other` with chair pre-approval.
2. Applicant and household members are not in `insider` table.
3. Household is within annual cap (count and amount) for the current calendar year.
4. Cooling-off period since last paid grant has elapsed, unless `urgency` flag set and chair confirms.
5. Consent recorded with current consent version.

Output: pass/fail with per-check reason. Failures produce a decline with the reason list.

### Tier assignment

From config. Defaults for the first version:

| Tier | Amount | Approvers required | SLA |
| --- | --- | --- | --- |
| A | ≤ 500 | coordinator + 1 committee member | 2 working days |
| B | 500–3,000 | 2 committee members | 7 working days |
| C | > 3,000 or recurring | 3 committee members, majority | 14 working days |
| E (emergency) | ≤ 1,500 | chair + 1, ratified at next meeting | 24 hours |

Recurring = more than one payment period requested. Working days exclude Friday, Saturday and Israeli public holidays (use a holiday table, not a library guess).

### Scoring (tiers B and C)

Four dimensions 0–3 plus vulnerability 0–1, maximum 13. Each committee member scores independently; the case score is the median of the submitted scores. Guideline outcomes from config:

| Total | Guideline |
| --- | --- |
| 9–13 | approve full |
| 6–8 | approve partial or conditional |
| 3–5 | refer; small grant only with written reason |
| 0–2 | decline with referral |

A decision that departs from the guideline requires `reasoning` to be non-empty and sets `exception_flag`.

### Caps and exceptions

- Per grant, per household per year, and count per household per year, all from config.
- Exceeding any cap requires a board member in `exception_approved_by`.
- The engine computes remaining headroom for a household and exposes it to the UI before scoring.

### Recusal

If a committee member records a recusal on a case, they are removed from the approver pool and cannot view the case documents. Recusal is irreversible for that case.

### Dual control on payments

A payment batch cannot be generated by the same user who approved any decision in it. The batch is marked executed only after a second user records the bank reference.

## Category-specific document requirements (config)

| Category | Required documents |
| --- | --- |
| rent | lease, arrears notice or landlord letter |
| car | garage quote; two quotes above configured threshold; vehicle registration |
| childcare | daycare invoice; proof parent works or studies |
| baby | ID appendix or birth certificate |
| medical | receipt or quote; provider note; confirmation health fund does not cover |

Tier B and above also require income proof for the last three months. The coordinator cannot move a case to `scoring` while required documents are missing; the UI shows exactly what is missing.

## API outline

All endpoints under `/api/v1`. Staff endpoints require Entra bearer token with the right app role. Applicant endpoints require the passwordless session.

Public and applicant:
- `POST /applications` submit application (creates applicant if new, creates case)
- `POST /referrals` referral form
- `POST /auth/otp/request`, `POST /auth/otp/verify`
- `GET /me/cases`, `GET /me/cases/{id}`
- `POST /me/cases/{id}/documents` returns upload SAS
- `POST /me/cases/{id}/appeal`

Staff:
- `GET /cases` filtered by status, tier, assignee
- `GET /cases/{id}` full case view, filtered by role
- `POST /cases/{id}/eligibility` run and record gate
- `POST /cases/{id}/verification`
- `POST /cases/{id}/scores`
- `POST /cases/{id}/recusal`
- `POST /cases/{id}/decision`
- `POST /cases/{id}/transition` explicit status change with reason
- `GET /payments/pending`, `POST /payments/batches`, `POST /payments/{id}/executed`
- `GET /reports/quarterly?year=&q=` grants, totals by category and tier, average days to decision, exceptions, appeals
- `GET /config/current`, `POST /config` (board only)
- `GET /audit?case_id=` (auditor, board)

Every write endpoint is idempotent via an `Idempotency-Key` header.

## Frontend

Public area:
- Home: who we are, who can apply, how to donate (donation link goes to the external receipt provider; no card data touches this app).
- Application form: one page, Hebrew, mobile first, autosave to local draft, document upload after submission so a missing file never blocks the submission.
- Referral form.
- Status page after OTP login: current stage in plain language, what is missing, decision when made, appeal button.

Staff area:
- Coordinator queue with SLA countdown per case.
- Case view: tabs for application, documents, gate, verification, scores, decision, payments, audit. Role determines visible tabs.
- Committee scoring screen: rubric with the four dimensions as radio groups and the config text for each level.
- Treasurer: pending payments, generate batch, record execution.
- Reports: quarterly summary with export to CSV.

Accessibility: WCAG 2.1 AA; Israeli Standard 5568 applies to public-facing sites.

## Notifications

Via Azure Communication Services. Templates in Hebrew. Events: application received, documents requested, decision made, payment executed, appeal received. Never include amounts or category in SMS; include only the case number and a link.

## Retention and deletion

- Case files retained 7 years after closure (accounting requirement), then documents are deleted from Blob and personal fields are nulled in the database. Financial totals remain for reporting.
- A scheduled job runs monthly and writes an audit event per deletion.
- Declined applications that never reached a decision: retain 12 months.

## Security checklist before production launch

Applies to the Azure deployment, not the demo.

- [ ] Entra MFA enforced for all staff roles
- [ ] Database firewall allows only Container Apps outbound IP; no public access
- [ ] All secrets in Key Vault; none in env files committed to git
- [ ] Blob container private; SAS tokens ≤ 15 minutes, read-only, logged
- [ ] National ID stored hashed (lookup) and encrypted (display); never logged
- [ ] Rate limiting on public endpoints and OTP
- [ ] Audit log cannot be modified by any application role
- [ ] Backups: PostgreSQL PITR enabled, 35 days; Blob soft delete enabled
- [ ] Penetration test completed and findings closed
- [ ] Database definition document (מסמך הגדרות מאגר) written and reviewed by the amuta's lawyer

## Engineering conventions

- Idempotent operations everywhere; retries must be safe.
- Explicit provenance: every derived value (tier, score, headroom) stores the config version and inputs it was computed from.
- No silent mutation: status changes go through the transition endpoint with a reason.
- Human review gates: the engine recommends, people decide. The UI never auto-approves.
- Small, reviewable PRs. Each rule change ships with a test that shows the before and after.
- Type hints and Pydantic models everywhere; `mypy --strict` passes.
- Hebrew strings live in `messages/he.json`, never inline in components.

## Build order

Demo (SQLite, local):

1. **Foundation**: repo, settings object, SQLite + Alembic baseline with append-only triggers, local `DocumentStore`, dev auth with role picker, CI running pytest on SQLite and PostgreSQL.
2. **Domain**: rules engine with full tests (gate, tiers, scoring, caps, recusal, workflow table). No UI yet.
3. **Intake**: application form, referral form, OTP login (console), document upload, coordinator queue.
4. **Committee**: case view, scoring, decisions, recusal, console notifications.
5. **Payments**: pending list, batch generation, execution record, dual control.
6. **Seed and demo script**: synthetic cases, a ten-minute walkthrough from application to payment.

Production (Azure):

7. **Infrastructure**: Bicep for PostgreSQL, Blob, Key Vault, Container Apps, Static Web Apps; Entra app registration with roles; ACS.
8. **Swap backends**: Azure implementations of `DocumentStore`, `Notifier`, `AuthProvider`; PostgreSQL grants; Alembic against PostgreSQL.
9. **Reports and audit**: quarterly report, audit viewer, retention job.
10. **Applicant status page and appeals.**
11. **Hardening**: security checklist, penetration test, runbook, handover doc.

Phases 1–6 give the committee something to react to. Phases 7–8 and 11 are required before any real applicant data enters the system.

## Out of scope for version 1

- Donation collection and tax receipts: handled by an Israeli receipt package connected to the Tax Authority's donation system. A later version may import its records.
- Accounting ledger: the accountant's software remains the book of record; this system exports.
- Multi-amuta tenancy.
- Automated eligibility decisions. The engine informs; it never decides alone.
