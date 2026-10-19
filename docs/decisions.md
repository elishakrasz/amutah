# Engineering decisions and open questions

Where `amutah.md` or `ADOPTED_PRACTICES.md` was ambiguous or self-contradictory,
this file records what the code does and why. `ADOPTED_PRACTICES.md` says it
extends "CLAUDE.md"; this repo treats `amutah.md` as that file. Items under "Open questions" need an answer from the board
or committee before the phase noted.

## Decisions taken (phase 1)

| # | Spec text | What the code does | Why |
|---|---|---|---|
| D1 | `case` table | Named `aid_case` | `CASE` is an SQL keyword; quoting it in every trigger and raw query invites bugs. |
| D2 | `payment` has `status`, `batch id`, `bank reference`; `payment_batch` has `executed confirmed by`; `appeal` has `decided by`, `outcome` | Those later facts are separate append-only rows: `payment_event`, `payment_batch_execution`, `appeal_decision`. Current status is derived from the latest event. | A row that is filled in later cannot be append-only. |
| D3 | `decision.approvers (list)` | `decision_approver` join table | Dual control ("batch generator approved none of these") and recusal checks become plain joins with foreign keys. |
| D4 | Tier and gate inputs need chair approvals (`other` category, cooling-off override, emergency) | `chair_approval` append-only table | The spec requires these approvals but gives them nowhere to live. |
| D5 | Provenance for derived values | `tier_assignment` (append-only) records amount, periods, emergency flag and config version; `case_transition` records every status change with its reason | Engineering convention "every derived value stores the config version and inputs". |
| D6 | `audit_event` "written by trigger and by application" | Written by the application in the same transaction; triggers make it immutable | A database trigger cannot know the actor, role, purpose or IP, especially on SQLite. |
| D7 | National ID "hashed for lookup" | HMAC-SHA256 with a secret key (Key Vault in production); check digit validated | Israeli IDs have about 10⁹ values; a plain SHA-256 is reversed by enumeration in minutes. |
| D8 | `aid_case` "mutable only in status and assignment" | Trigger also allows `tier` and `closed_at`, and allows `description`, `vendor_name`, `vendor_contact` to be set to NULL only | Tier is assigned after intake; the retention job must be able to erase free text. |
| D9 | Money | Integer agorot everywhere, including config (`"currency_unit": "agorot"`) | Spec rule; config tables in the spec are in shekels, so the unit is stated explicitly. |
| D10 | Tier boundaries "≤ 500" and "500–3,000" overlap at 500 | ~~A: ≤ 50,000 agorot; B: 50,001–300,000; C: > 300,000~~ Since Q24: A below 50,000 agorot; B 50,000 to below 300,000; C 300,000 and above, or recurring. Tier E keeps an inclusive ceiling of 150,000 | Lower bound inclusive (Q24). |
| D11 | Enum columns | `VARCHAR` + `CHECK` on both dialects, no native PostgreSQL enums | Identical behaviour on SQLite and PostgreSQL; adding a value is a plain migration. |
| D12 | Tailwind "with RTL plugin" | No plugin; Tailwind v4 logical utilities (`ms-*`, `ps-*`, `text-start`) and `rtl:` variant | Built into Tailwind v4. |
| D13 | Seed "three staff users" | Nine: one per staff role plus three committee members | Tier C needs three committee members and dual control needs distinct users; three users cannot demonstrate either. |
| D14 | Secrets | Settings refuse HMAC and signing keys shorter than 32 characters, and refuse every demo backend when `environment=production` | Fail fast on misconfiguration rather than at first use. |
| D15 | Status machine has `scoring` before `decision_pending` for all tiers | (Phase 2) Tier A goes `verification → decision_pending` directly | Scoring applies only to tiers B and C. |
| D16 | Gate "failures produce a decline" | (Phase 2) The gate produces a recommendation; the coordinator records the `ineligible` transition | Out-of-scope rule: "The engine informs; it never decides alone." |

## Decisions taken (adopted practices, migration 0003)

| # | Item | What the code does | Why |
|---|---|---|---|
| D17 | AP-6, AP-14 add later-arriving fields to `payment` (need confirmation, voucher issued, redemption reported) | They are `payment_event` kinds: `need_confirmed`, `voucher_issued`, `voucher_redemption_reported`, with `need_confirmed_method` and `voucher_reference_hash` on the event | `payment` is append-only (D2). Voucher face value is the payment amount; the voucher code is stored only as a keyed hash. |
| D18 | AP-14 "`payment.method` gains `voucher`" | Already present since phase 1 | |
| D19 | AP-3 "refused without a recorded consent timestamp" | `lead.consented_at`, and a database CHECK: `converted_case_id` requires `consented_at` | Enforced below the API, like the other hard rules. |
| D20 | AP-15 "exactly one payment per month" | Partial unique index on `payment(allocation_id, allocation_month)` for non-superseded rows; `allocation` links to the case and decision that approved it | A scheduled job that runs twice cannot double-pay. |
| D21 | AP-10 "stated purpose matches an exclusion" | (Phase 2) The coordinator selects the exclusion code at the gate; no free-text matching | Matching free text is unreliable and would decide silently. |
| D22 | AP-17 `published_at` set by a board member | Append-only `public_stats_publication` stores the exact published figures (`snapshot`) | What was published stays reproducible after later corrections. |
| D23 | AP-8 `per_person_net` | Stored together with the divisor used | The divisor method is an open question (Q14). |
| D24 | AP-9, AP-12 "the engine refuses" | Treated like caps: the rule limits the options and a board exception is the way past it; a person still makes the decision | Consistent with "the engine informs; it never decides alone". |
| D25 | Migrations that alter guarded tables on SQLite | `app/migration_ddl.py` re-creates triggers after batch rebuilds; enum CHECKs are dropped before their columns; `tests/test_schema_integrity.py` fails if any trigger, enum CHECK or model CHECK is missing after upgrade or a downgrade/upgrade cycle | SQLite batch mode rebuilds the table, which silently drops its triggers. |

## Decisions taken (phase 2, rules engine)

| # | Item | What the code does | Why |
|---|---|---|---|
| D26 | Approval panels | Each tier has seats (coordinator / chair / committee) and `min_for`. Every seat must vote before a decision carries; it fails early once it can no longer reach `min_for`. A decision is a proposal the panel votes on, including declines | One rule shape covers A, B, C and E; Q3 |
| D27 | Chair on panels | The chair may fill a committee seat, but never two seats on one panel (tier E needs a second person) | "Chair + 1" |
| D28 | Need bands | Half-open, lower bound inclusive (confirmed by Q24): exactly 100% scores 2, 125% scores 1, 150% scores 0. Per-person income is rounded down to the agora | Deterministic for AP-8's "same figures, same result" |
| D29 | Emergency grants | Paid first, then `paid → ratification_pending → follow_up`. The case cannot close until ratified | Paying an emergency grant should not wait for the next meeting |
| D30 | New status `withdrawn` (migration 0004) | Allowed from any status before a decision | The intake call outcome "withdrawn" (AP-5) had nowhere to go |
| D31 | Appeals | Upheld returns the case to the status it was appealed from; returned goes to `decision_pending` | `amutah.md` status machine |
| D32 | AP-7 `claim_in_progress` | Suggests 1–2 (DEMO) | AP-7 covers only "unclaimed" and "all resolved" |
| D33 | AP-20 reserve | Reserve = `reserve_percent` of the month's allocation, kept for tier E. Budget is "constrained" when (remaining − reserve) < committed + pending B/C. Board alert below `emergency_only_threshold_percent` of the allocation remaining | AP-20 names these values but not how they combine |

## Decisions taken (Q20–Q22, migration 0005)

| # | Item | What the code does | Why |
|---|---|---|---|
| D34 | "If the chair is recused, the board chair assigns" | New staff role `board_chair` | No existing role identified the board chair. |
| D35 | Votes | `decision_proposal` (what the panel votes on) and `decision_vote` (member, seat, in favour, one-line reasoning ≤ 200 characters; one vote per member per proposal). The `decision` row is written from the proposal when it carries and points back to it | Dissent kept for appeals; "no re-vote on different terms" is enforced by refusing a new proposal once the current one has any vote |
| D36 | Escalation | The case's `tier` becomes the target tier and `escalated_from_tier` keeps the tier the case **started** at (set on the first escalation only, so A → B → C still says A); a `tier_assignment` row records each step. Documents stay at the starting tier (`document_tier`) | The escalation is about who decides, not what the applicant must provide |
| D37 | Alternates | `committee_alternate` (the board-approved list, mutable `active`) and `alternate_assignment` (append-only, one case). A vote in a committee seat counts only from a committee member, the chair, or an alternate assigned to that case | "Never ad hoc" is enforced, not left to memory |
| D38 | SLA clock | `sla_event` rows: paused, resumed, restarted. While paused there is no due time. A working-day SLA is extended by the working days the pause spanned (Israel dates); an hour SLA by the paused duration. A restart (escalation) starts the new tier's SLA from that moment | Q20, Q21 |
| D39 | Boundary flag | `amount_amendment` rows; flagged when the new amount is within ₪200 either side of the tier A, E or B maximum. The original `amount_requested` stays as submitted | Q21; tier E's maximum is also a boundary someone could aim for |
| D40 | ~~Splits in tiers A and E stay pending~~ | Superseded by Q23 and D41 | |

## Decisions taken (Q23–Q24, migration 0006)

| # | Item | What the code does | Why |
|---|---|---|---|
| D41 | What a "split" is | Once every seat has voted: enough in favour → carried; enough against → **rejected**; anything else → **split**. Only a split escalates or goes to the chair. A rejected proposal may be followed by a new one | Two tier B members who both vote against a proposal agree with each other; that is not a split. Tier C (three seats, two needed) can never split |
| D42 | `on_split` config | `escalate_to_<tier>` or `chair_decides`. Escalation must add committee seats (A 1 → B 2 → C 3); `chair_decides` needs a chair seat | Q23 |
| D43 | Tier E ceiling | Stays inclusive: exactly ₪1,500 can use the emergency path | Confirmed by Q25 |
| D44 | Ratification | Append-only `ratification` row (ratified / overturned, reasoning, meeting reference). `ratification_pending → follow_up` needs either outcome recorded | Q23: overturned after payment is noted, not clawed back |

## Decisions taken (Q25–Q26, migration 0007)

| # | Item | What the code does | Why |
|---|---|---|---|
| D45 | Path vs band | `tier_assignment.band` (A/B/C only, enforced by a CHECK) is stored beside `tier` (which can be E). Reports group by `band` | Q25 |
| D46 | Scoring after escalation | `scoring_required(tier, escalated_from)`: a scored tier needs scores unless the case started at an unscored tier whose `escalation_requires_scoring` is false | Q26; one switch for the board |
| D47 | Extra requests after escalation | `check_extra_request` limits an escalated tier A panel to `escalation_extra_requests` (1). The request record itself (document request or phone verification) arrives with the committee screens in phase 4 | Q26 |

## Open questions

| # | Question | Needed by |
|---|---|---|
| Q1 | ~~Is a request of exactly ₪500 tier A or B? Exactly ₪3,000 tier B or C?~~ ~~**Answered 2026-10-19:** up to and including ₪500 is A; up to and including ₪3,000 is B.~~ **Superseded by Q24:** exactly ₪500 is B; exactly ₪3,000 is C. | Phase 2 |
| Q2 | ~~Case score is the median of submitted scores. With two scorers (tier B) the median can be x.5, e.g. 8.5 falls between the 6–8 and 9–13 bands. Round up, round down, or require a third score?~~ **Answered 2026-10-19:** round up. `scoring.median_rounding = "up"`. | Phase 2 |
| Q3 | ~~Tier C "3 committee members, majority": three must take part and two must approve? Or three approvals required?~~ **Answered 2026-10-19:** B = two members, both must agree. C = all three vote, two of three carries. A and E = every seat in favour. Encoded as `approval.seats` + `approval.min_for` per tier. | Phase 2 |
| Q4 | ~~If recusals leave fewer eligible members than the tier requires, what happens: chair appoints, escalate to board, or case waits?~~ **Partly answered 2026-10-19:** "we contact them; they receive an email or text to update their request". Read as: the case waits and the applicant is notified. Superseded by Q21. | Phase 2 |
| Q5 | Emergency path: if the committee does not ratify an emergency grant that has already been paid, what is recorded and what follows? | Phase 2 |
| Q6 | Caps (per grant, per household per year amount and count), cooling-off days, and the two-quote threshold for car repairs are not in the procedure. Seed uses DEMO values marked as such. | Before any real case |
| Q7 | Household is "derived from applicant ID plus partner ID", but the applicant fields listed have no partner ID, and the insider check covers "household members". The schema stores a keyed hash of the partner's ID only. Is that the agreed minimum? Do other adult household members need checking? | Phase 3 |
| Q8 | `approve_conditional`: who confirms the condition is met, and does payment wait for it? | Phase 4 |
| Q9 | Retention: "declined applications that never reached a decision: retain 12 months". Does this mean cases closed as `ineligible` or withdrawn before a committee decision? | Phase 9 |
| Q10 | Retention vs append-only: decisions, verifications and notes contain personal free text in append-only tables, which the 7-year purge must erase. Proposed: encrypt those fields with a per-case key and destroy the key at purge (crypto-shredding). Needs lawyer sign-off. | Phase 9 |
| Q11 | Data residency: Azure Static Web Apps is not offered in Israel Central, and ACS data-location options may not include Israel. Proposed: serve the frontend from Container Apps in Israel Central; confirm the ACS data location (or accept that SMS/email metadata leaves Israel) with the lawyer. | Phase 7 |
| Q12 | Uploaded documents are not malware-scanned in the spec. Proposed: Defender for Storage malware scanning on the Blob container in production. | Phase 8 |
| Q13 | AP-1 refers to "the lighter document tier for referred cases (CLAUDE.md Stage 3)". `amutah.md` has no such tier: referred and direct cases have the same document requirements. Is there a newer CLAUDE.md? Until this is answered, AP-1's "Done when" cannot be tested. | Phase 2 |
| Q14 | ~~AP-8 per-person income: plain division by household size, or the standard-persons scale (נפש תקנית) that Bituach Leumi and the Welfare Ministry use? The two give very different need scores for large families.~~ **Answered 2026-10-19:** standard persons (נפשות תקניות), table 1.25 / 2.00 / 2.65 / 3.20 / 3.75 / 4.25 / 4.75 / 5.20 / 5.60, +0.40 per further person. Need bands are % of BTL's poverty line per standard person: <100% → 3, 100–125% → 2, 125–150% → 1, ≥150% → 0. Config holds the line (updated yearly) and the band percentages. | Phase 2 |
| Q15 | AP-17 lists cities, but the applicant's address is free text. Add a structured `city` field (derived from the address already collected)? Small-cell suppression also needs complementary suppression: one hidden cell can be recovered as the total minus the visible cells. | Phase 9 |
| Q16 | AP-3 holds a third party's name and contact details before they know about it. The lawyer should confirm the legal basis and any notice duty under Amendment 13, for both the subject and the nominator. | Phase 3 |
| Q17 | AP-15: an allocation is recurring, which makes it tier C under `amutah.md`. Does "full committee" mean every member, or the tier C quorum? Each monthly voucher issue also needs a second user (dual control): 12 actions per child per year. Acceptable? | Phase 5 |
| Q18 | AP-20 and AP-21 notify the board. The `Notifier` is applicant-facing (SMS, no amounts). Staff alerts need a separate channel (email). | Phase 4 |
| Q19 | AP-4 Russian (and possibly Arabic) applicant text and notification templates need a qualified translator, not machine translation. Who provides it? | Phase 3 |
| Q20 | ~~When a panel does not agree (tier A/B/E: anyone votes against; tier C: two against), what happens? Currently the case stays in `decision_pending` with the vote recorded as not agreed. Options: decline, escalate to the chair or a tier C panel, or re-propose with different terms.~~ **Answered 2026-10-19:** escalate one level, never decline by default. Tier B split → full tier C panel (both members stay, votes stand, third added, majority decides). Tier C split only after a recusal → add an alternate. No re-vote on different terms. Status stays `decision_pending`; `escalated_from_tier` set; SLA restarts on the tier C SLA; applicant gets "still in process". Every vote is kept with one line of reasoning. | Phase 4 |
| Q21 | ~~Confirm Q4: when recusals leave too few committee members, does the case wait while the applicant is told it is delayed? Or did "update their request" mean the applicant is asked to change it (for example a smaller amount that drops to a lower tier)? Who fills the missing seat: a board member, or a member co-opted by the chair?~~ **Answered 2026-10-19:** fill the seat from a board-approved alternates list; the committee chair assigns within 2 working days (the board chair if the chair is recused); the alternate has member rights for that case only. No alternate → the case waits with the SLA clock paused and the applicant gets a plain "slight delay" message. Recusal reasons are never disclosed. Never suggest a lower amount; flag re-entered amounts within ₪200 of a tier boundary. Board members only via the alternates list. | Phase 4 |
| Q22 | ~~Which BTL poverty-line figure should be used: monthly net per standard person for the latest published year? The board should record the source and year with each config version.~~ **Answered 2026-10-19:** 2024 NII figure, ₪3,547 per standard person per month (`scoring.poverty_line_monthly_agorot = 354700`). Update when the 2025 figure is published. The band percentages remain board placeholders; the suggestion is on and advisory. | Before any real case |
| Q23 | ~~Q20 covers splits in tiers B and C. What about tier A (coordinator + one member disagree) and tier E (chair + one member disagree)? Options: escalate A to the B panel (which then needs committee scores) and E to a three-member panel (chair + two). Currently both stay pending with the chair notified. Set per tier with `tiers.X.escalate_to`.~~ **Answered 2026-10-19:** A splits → tier B (a second committee member joins; the coordinator's vote is recorded but does not count at B; a split at B then goes on to C). E splits → the chair decides, the dissent is recorded, and the case goes to `ratification_pending` as every emergency case does; the full committee ratifies or overturns at its next meeting. Overturned after payment: noted on the record, no clawback, still counts against the household's caps as a paid grant. Config: `tiers.A.on_split = escalate_to_B`, `tiers.B.on_split = escalate_to_C`, `tiers.E.on_split = chair_decides`. | Phase 4 |
| Q24 | ~~Need-band edges: the code treats bands as half-open, so exactly 125% scores 1 and exactly 150% scores 0. The answer to Q22 reads "125–150 → 1, >150 → 0", which would make exactly 150% score 1. Which one?~~ **Answered 2026-10-19:** half-open bands, lower bound inclusive, so each value lands in exactly one band: below 100% → 3; 100% to below 125% → 2; 125% to below 150% → 1; 150% and above → 0. So exactly 100% scores 2, exactly 125% scores 1, exactly 150% scores 0: a household at a threshold has reached the next band up in means and gets the lower score. The same rule applies to tier amounts: exactly ₪500 is tier B, exactly ₪3,000 is tier C (supersedes Q1). Tests: `test_q24_each_boundary_lands_in_the_upper_band`, `test_tier_assignment`. | Before go-live |
| Q25 | ~~Tier E ceiling: exactly ₪1,500 can currently use the emergency path (inclusive). Should Q24's rule apply here too, so only amounts below ₪1,500 qualify?~~ **Answered 2026-10-19:** keep it inclusive. ₪1,500 is a ceiling on a separate path, not a band edge; Q24's lower-bound rule applies only to bands (tiers A/B/C and need scores). For reporting, an emergency case counts under the band its amount falls into: path and band are separate attributes. | Phase 4 |
| Q26 | ~~A tier A case escalated to B has no committee scores (tier A is not scored). Should the two members score it before deciding, or does the proposal already tabled stand without scores? Currently it stands.~~ **Answered 2026-10-19:** the proposal stands without scores. The second member decides on the tier A file as it is; both members record a one-line reason. The panel may ask for one additional document or a phone verification, never the full tier B set. A further B → C split also proceeds without scoring. Config: `tiers.A.escalation_requires_scoring = false`, `tiers.A.escalation_extra_requests = 1`. | Phase 4 |
| Q27 | `amutah.md` still says "A ≤ 500 / B 500–3,000". After Q24 the code differs. Update the written procedure (and the board resolution behind it) to match. | Before go-live |

