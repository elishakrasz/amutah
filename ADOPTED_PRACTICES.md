# Adopted Practices: Changes Derived from Comparable Israeli Aid Organisations

Companion to `CLAUDE.md`. Read that first; this file extends it. Where the two conflict, this file wins, because it is newer.

Each item below came from studying how seven Israeli organisations run similar aid (Ten Gav, the Kehillat Yael community fund, Ogen, Paamonim, Pitchon Lev, Yad Eliezer, Chasdei Naomi) and the Welfare Ministry's essential-needs grant. Each item states the practice, the change to this system, and how to know it is done. Items marked **Board** need a board decision before the value is final; build them with config placeholders.

The numbering here is stable. Reference items as `AP-7` in commits, tests and issues.

---

## A. Intake

### AP-1 Referrer register with recognition status

**Practice.** Ten Gav accepts requests only from social-service agencies it has pre-approved.

**Change.**
- Extend `referrer`: add `status` (`pending`, `recognised`, `suspended`), `organisation`, `organisation_verified_by`, `organisation_verified_at`, `manager_name`, `manager_contact`.
- A referral form submission from an unknown referrer creates a `referrer` row with `status = pending` and a case flagged `referral_unverified = true`.
- Rules engine: a case counts as "referred" (lighter document tier, see `CLAUDE.md` Stage 3) only when `referrer.status = recognised` at the time of eligibility check. Otherwise it is treated as a direct application.
- Coordinator UI: a referrer queue to verify by phone and set `recognised`; the organisation and manager are recorded.

**Done when.** A referral from a pending referrer requires the full Tier B document set; after recognition, re-running the gate downgrades the document requirement and writes an audit event.

### AP-2 Department sign-off for Tier C referrals

**Practice.** Ten Gav requires the social worker's superior to authorise the request.

**Change.**
- New document type `referral_letter_signed` (signed by the referrer's manager or department head).
- Config: `tiers.C.required_documents` includes `referral_letter_signed` when a referrer is attached.
- The coordinator cannot move a referred Tier C case to `scoring` without it.

**Done when.** The missing-documents list shows `referral_letter_signed` for a referred Tier C case and the transition is refused until it is uploaded.

### AP-3 Anonymous nomination (lead, not case)

**Practice.** Kehillat Yael lets a community member flag someone in need through the rabbi without identifying themselves.

**Change.**
- New table `lead`: `nominator_name` (nullable), `nominator_contact` (nullable), `subject_name`, `subject_contact`, `note`, `status` (`new`, `contacted`, `consented`, `converted`, `closed_no_consent`, `expired`), `converted_case_id` (nullable), `created_at`.
- Public form "מישהו שאני מכיר/ה זקוק/ה לעזרה" creates a lead. No case, no applicant record, no documents.
- Coordinator contacts the subject. A case is created only after the subject gives consent (`status = consented`), and the subject then completes the normal application.
- Retention: leads not converted within 90 days are deleted by the monthly job (names and contacts nulled, status set to `expired`).
- The nominator is never shown to the subject.

**Done when.** Creating a case from a lead without a recorded consent timestamp is refused; expired leads carry no personal data.

### AP-4 Multilingual forms

**Practice.** Paamonim's intake form is offered in Hebrew, English and Russian.

**Change.**
- Add `messages/ru.json` beside `he.json` and `en.json`. Arabic (`ar.json`) is **Board**; build the switch so adding it is a file, not code.
- `applicant.preferred_language` (`he`, `en`, `ru`, `ar`). Notifications use it.
- RTL applies to `he` and `ar`; LTR to `en` and `ru`.

**Done when.** The public form renders fully in each enabled language with correct direction, and a notification to a `ru` applicant is sent in Russian.

### AP-5 Intake call before documents (Tier B and C)

**Practice.** Paamonim holds an orientation call (שיחת הכוון) before anything else.

**Change.**
- New append-only table `intake_call`: `case_id`, `called_by`, `called_at`, `duration_minutes`, `summary`, `outcome` (`proceed`, `refer_elsewhere`, `withdrawn`, `no_answer`).
- Workflow: for Tier B and C, `eligible → awaiting_documents` requires an `intake_call` with `outcome = proceed`. Tier A and E skip this.
- Coordinator UI shows a call script: confirm the need, explain documents, run the rights checklist (AP-7).

**Done when.** The transition is refused for Tier B/C without a `proceed` call; Tier A is unaffected.

---

## B. Vetting

### AP-6 "Still needed" confirmation before payment

**Practice.** Ten Gav re-checks that a funded need is still current before paying.

**Change.**
- `payment` gains `need_confirmed_at`, `need_confirmed_by`, `need_confirmed_method` (`vendor_call`, `applicant_call`, `referrer`).
- Rule: if the decision is older than `config.payment.reconfirm_after_days` (default 14), a payment cannot enter a batch without confirmation.

**Done when.** Batch generation skips unconfirmed stale payments and lists them with the reason.

### AP-7 Rights check before the amuta pays

**Practice.** Pitchon Lev runs rights-realisation centres; the amuta should fill gaps the state leaves, not replace entitlements.

**Change.**
- New append-only table `rights_check`: `case_id`, `performed_by`, `performed_at`, and one row per item in `rights_check_item`: `item` (`btl_benefit`, `housing_rent_assistance`, `daycare_subsidy`, `health_fund_coverage`, `municipal_welfare`, `other`), `status` (`not_applicable`, `eligible_not_claimed`, `claim_in_progress`, `claimed`, `denied`), `note`.
- Required for Tier B and C before `scoring`. Done during the intake call (AP-5) and completed after documents arrive.
- Rules engine: the "alternatives" scoring dimension gets a **suggested** score from the rights check (any `eligible_not_claimed` → suggest 0 or 1; all `claimed`/`denied`/`not_applicable` → suggest 3). Committee members still enter their own score; the suggestion is shown, not applied.
- Decision condition type `claim_entitlement_first` for conditional approvals.

**Done when.** A Tier B case cannot be scored without a rights check; the scoring screen shows the suggested alternatives score with its reason.

### AP-8 Standard income worksheet

**Practice.** The Welfare Ministry's grant uses one calculation form (ט"ז 8) for every applicant.

**Change.**
- New append-only table `income_worksheet`: `case_id`, `earned_net`, `btl_benefits`, `other_income`, `household_adults`, `household_children`, `per_person_net` (computed, stored), `source_documents` (list of document ids), `prepared_by`, `prepared_at`.
- Config: `scoring.need_thresholds` = per-person net cut-offs for scores 0–3. **Board** sets the values; defaults in the seed are placeholders tied to a stated reference (e.g. a fraction of the national median).
- Rules engine: suggested "financial need" score from the worksheet, shown to the committee, never auto-applied.
- Money as integer agorot, as in `CLAUDE.md`.

**Done when.** Two coordinators entering the same figures get the same per-person value and the same suggested score; the worksheet links to the pay-slip documents it was built from.

### AP-9 Coaching as a condition for repeat rent help

**Practice.** Paamonim gives money only inside a rehabilitation process.

**Change.**
- Config: `conditions.repeat_rent_requires_coaching = true`, `conditions.repeat_window_days = 365`.
- Rules engine: a second `rent` grant for the same household within the window forces outcome `approve_conditional` with condition `coaching_referral` (free text for the organisation, default "פעמונים"), unless a board member records an exception.
- `follow_up` gains `condition_met` (bool) and `condition_evidence`.

**Done when.** The engine refuses `approve_full` for a repeat rent case without an exception, and the follow-up screen asks whether the coaching referral happened.

---

## C. Scope and caps

### AP-10 Published exclusion list **Board**

**Practice.** Ten Gav states publicly what it will not fund (food, dental, debt, recurring).

**Change.**
- Config: `excluded_purposes` = list of `{code, label_he, label_en, label_ru}`. Seed with placeholders: `debt_repayment`, `cash`, `recurring_beyond_limit`, `food` (refer to food organisations), `luxury`.
- Eligibility gate check 1 extended: a request whose stated purpose matches an exclusion fails with that exclusion as the reason, and the decline message carries a referral to the relevant organisation from `config.referral_directory`.
- Public site: a "מה אנחנו לא מממנים" section rendered from config.

**Done when.** Changing the exclusion list in config changes both the gate behaviour and the public page without a deploy.

### AP-11 Public policy endpoint

**Practice.** Both Ten Gav and Kehillat Yael publish their cap.

**Change.**
- `GET /api/v1/public/policy` returns from the current config: categories, per-grant cap, annual household cap, exclusions, SLA per tier, required documents per category. No auth.
- The public site's "איך זה עובד" page renders from it.

**Done when.** The page shows the same numbers the engine enforces, read from the same config version.

### AP-12 No partial funding without a covered balance

**Practice.** Ten Gav will not partially fund unless the remainder is guaranteed; the Welfare Ministry asks how amounts above ₪10,000 will be completed.

**Change.**
- `decision` gains `balance_source` (`applicant`, `family`, `other_org`, `vendor_discount`, `waived_by_vendor`, `none`) and `balance_evidence_document_id` (nullable).
- Rule: if `amount_approved < amount_requested` and outcome is an approval, `balance_source` must not be `none`; for Tier C, evidence is required.
- Exception path: board member override with reason.

**Done when.** A partial approval without a balance source is refused by the API with a clear message.

### AP-13 Align the count cap to once per year for large categories

**Practice.** The Welfare Ministry grant is once per budget year.

**Change.** Config already has per-household count caps. Add per-category caps: `caps.per_category_per_year = {rent: 1, car: 1, childcare: 2, baby: 12, medical: 2}` (placeholders, **Board**). Gate check 3 uses both the household cap and the category cap.

**Done when.** A second `car` request in the same year fails the gate with the category cap as the reason.

---

## D. Payment and delivery

### AP-14 Voucher payment method

**Practice.** Chasdei Naomi moved supplies to online-supermarket vouchers.

**Change.**
- `payment.method` gains `voucher`. Voucher payments carry `vendor` (chain), `face_value`, `voucher_reference_hash` (never the code itself), `issued_to_applicant_at`, `redeemed_reported_at` (nullable).
- Vouchers are bought in batches by the treasurer; a `voucher_stock` table tracks purchased vs issued per vendor so the audit committee can reconcile.
- Voucher issue requires the same dual control as a bank payment: approval by the decision, issue recorded by a different user.

**Done when.** The quarterly report shows vouchers issued vs stock purchased, and the difference reconciles to zero or to a listed explanation.

### AP-15 Standing monthly allocation for infants **Board**

**Practice.** Yad Eliezer runs a fixed monthly formula programme per infant.

**Change.**
- New table `allocation`: `household_id`, `child_reference` (birth year/month, no name needed), `category` (`baby` only in v1), `monthly_amount`, `method` (`voucher`), `start_month`, `end_month` (max 12 months, cannot pass the child's second birthday), `approved_by` (full committee), `config_version`, `status` (`active`, `paused`, `ended`), `superseded_by`.
- A scheduled job creates one `payment` per active allocation per month, linked to a system case per allocation, so every payment still traces to a decision.
- Allocations count toward the annual household cap unless `config.caps.baby_allocation_exempt = true` (**Board**).
- Renewal after `end_month` is a new allocation with a fresh review.

**Done when.** An active allocation produces exactly one payment per month, visible in the treasurer's pending list, and stops automatically at `end_month`.

### AP-16 Delivery confirmed by the referrer

**Practice.** Ten Gav arranges delivery with the social worker.

**Change.**
- `follow_up` gains `confirmed_by` (`applicant`, `referrer`, `vendor`) and `delivery_confirmed` (bool).
- For goods and repairs (not rent or childcare), Tier B and C follow-up asks the referrer, when there is one, to confirm receipt. A notification template for referrers is added.

**Done when.** The follow-up record for a referred appliance case shows the referrer's confirmation, and the case cannot close without a follow-up.

---

## E. Transparency

### AP-17 Public quarterly numbers, no names

**Practice.** Ten Gav publishes recipients, agencies, cities, total value and category breakdown each quarter.

**Change.**
- `GET /api/v1/public/stats?year=&quarter=` returns: grants count, households helped, total paid, breakdown by category and by tier, average days to decision per tier, referrer organisations count, cities count.
- Small-cell suppression: any breakdown cell with fewer than `config.public_stats.min_cell` (default 5) households is shown as "<5". Cities are listed only when at least `min_cell` households were helped there.
- Public site renders a "מספרים" page from it; the board reviews each quarter before it goes live (`published_at` set by a board member).

**Done when.** No public figure can identify a household, and the page shows nothing until a board member publishes the quarter.

### AP-18 Documents page

**Practice.** Ten Gav posts financial statements and certifications.

**Change.** Static uploads managed through an `org_document` table (`title`, `type`, `year`, `file`, `published`). Types: registration certificate, annual financial report, verbal report, proper-management certificate, Section 46 approval. Admin-only upload; public read.

**Done when.** The public site lists published documents with year and type.

### AP-19 Funding statement

**Practice.** Ten Gav's "100% model".

**Change.** Content only. If overheads are covered by the founder, the home page says every donated shekel goes to grants. Text lives in `messages/*.json` under `home.funding_statement` so the board can change it without a deploy. **Board** confirms the claim is true before it goes live.

---

## F. Operations

### AP-20 Budget exhaustion rule

**Practice.** Ogen and Pitchon Lev saw demand double in wartime.

**Change.**
- Config: `budget.monthly_allocation`, `budget.reserve_percent` (default 20), `budget.emergency_only_threshold_percent` (default 10).
- Engine exposes `budget_status(month)`: remaining, committed (approved not yet paid), pending by tier.
- When remaining < committed + pending Tier B/C, the committee queue sorts pending cases by score, then by urgency, and shows "waiting for budget" instead of an SLA countdown. Tier E still draws from the reserve.
- Board is notified when the emergency-only threshold is crossed.

**Done when.** Seed data with an exhausted month shows the re-sorted queue and the board notification in the console notifier.

### AP-21 Committee capacity KPI

**Practice.** Ogen doubled its underwriting staff to keep up.

**Change.**
- Quarterly report includes, per tier: median and 90th-percentile days from submission to decision, and SLA breach count.
- Config: `sla.breach_alert_percent` (default 20). If breaches exceed it in a month, the board gets a notification suggesting an additional committee member.

**Done when.** The report shows the two percentiles and the breach count, and the alert fires on seed data designed to breach.

---

## G. Not adopted (recorded so nobody re-proposes them)

- **Public case stories or crowdfunding pages.** The amuta is funded, not crowdfunded; publishing stories raises privacy risk under Amendment 13 for no benefit.
- **Food distribution.** Logistics-heavy and well served by Yad Eliezer, Pitchon Lev, Chasdei Naomi. `config.referral_directory` holds their contact details; food requests get a referral, not a grant.
- **Loans.** Repayment tracking changes the operation. Refer to Ogen.

---

## Schema and config summary

New tables: `lead`, `intake_call`, `rights_check`, `rights_check_item`, `income_worksheet`, `allocation`, `voucher_stock`, `org_document`.

Changed tables: `referrer` (status, organisation fields), `payment` (need-confirmation fields, voucher fields, `method = voucher`), `decision` (balance fields), `follow_up` (condition and delivery fields), `applicant` (`preferred_language`).

New config keys (all in `config_version.json`):

```
excluded_purposes[]
referral_directory[]
caps.per_category_per_year{}
caps.baby_allocation_exempt
conditions.repeat_rent_requires_coaching
conditions.repeat_window_days
payment.reconfirm_after_days
scoring.need_thresholds[]
public_stats.min_cell
budget.monthly_allocation
budget.reserve_percent
budget.emergency_only_threshold_percent
sla.breach_alert_percent
tiers.C.required_documents (+ referral_letter_signed)
```

New public endpoints: `GET /public/policy`, `GET /public/stats`, `GET /public/documents`, `POST /leads`.

## Where each item lands in the build order

| Phase (from CLAUDE.md) | Items |
| --- | --- |
| 2 Domain | AP-1 gate logic, AP-7 suggestion, AP-8 worksheet maths, AP-9, AP-10 gate, AP-12, AP-13, AP-20 engine |
| 3 Intake | AP-1 referrer queue, AP-3, AP-4, AP-5 |
| 4 Committee | AP-2, AP-7 UI, AP-8 UI, AP-9 UI, AP-11 |
| 5 Payments | AP-6, AP-14, AP-15, AP-16 |
| 9 Reports | AP-17, AP-18, AP-19, AP-21 |

## Tests this file requires

Each AP item gets at least one test named `test_ap<N>_<behaviour>` in `api/tests/`. The "Done when" line is the assertion. Items touching the gate or scoring also get a table-driven test in `tests/domain/` showing before and after with the config placeholders.

## Board decisions to collect before go-live

| Item | Decision |
| --- | --- |
| AP-4 | Add Arabic? |
| AP-8 | Income thresholds for need scores 0–3 |
| AP-10 | Final exclusion list and referral directory |
| AP-13 | Per-category annual caps |
| AP-15 | Infant allocation: monthly amount, duration, cap exemption |
| AP-19 | Is the "100% to grants" statement accurate? |
| AP-20 | Monthly allocation and reserve percentage |
