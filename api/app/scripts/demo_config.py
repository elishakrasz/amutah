"""Config version 1 for the demo. Money in agorot.

DEMO = not in the written procedure; BOARD = the board must decide before
go-live. Values without a marker come from amutah.md, ADOPTED_PRACTICES.md
or the board's answers recorded in docs/decisions.md.
"""

from typing import Any

CONFIG_V1: dict[str, Any] = {
    "currency_unit": "agorot",
    "tiers": {
        # Q24: bands are lower-bound inclusive. Exactly ₪500 is tier B and
        # exactly ₪3,000 is tier C. (Reverses Q1; amutah.md must be updated.)
        "A": {
            "below_amount": 50_000,
            "approval": {"seats": {"coordinator": 1, "committee": 1}, "min_for": 2},
            "sla": {"working_days": 2},
            "scoring": False,
            "intake_call": False,
            "on_split": "escalate_to_B",  # Q23: a second member joins; the coordinator no longer votes
            # Q26: decide on the tier A file as it is; at most one extra document or phone check.
            "escalation_requires_scoring": False,
            "escalation_extra_requests": 1,
        },
        # Q3: two committee members, both must agree.
        "B": {
            "below_amount": 300_000,
            "approval": {"seats": {"committee": 2}, "min_for": 2},
            "sla": {"working_days": 7},
            "scoring": True,
            "intake_call": True,
            "on_split": "escalate_to_C",  # Q20: the full tier C panel decides by majority
        },
        # Q3: all three vote; passes with two of three.
        "C": {
            "approval": {"seats": {"committee": 3}, "min_for": 2},
            "sla": {"working_days": 14},
            "scoring": True,
            "intake_call": True,
        },
        # Tier E is a ceiling on the emergency path, inclusive: exactly ₪1,500 is E (Q25).
        "E": {
            "max_amount": 150_000,
            "approval": {"seats": {"chair": 1, "committee": 1}, "min_for": 2},
            "sla": {"hours": 24},
            "ratify": True,
            "on_split": "chair_decides",  # Q23: must not stall; ratification follows
        },
    },
    "caps": {
        "per_grant": 500_000,  # DEMO
        "household_amount_per_year": 1_000_000,  # DEMO
        "household_grants_per_year": 3,  # DEMO
        "per_category_per_year": {
            "rent": 1,
            "car": 1,
            "childcare": 2,
            "baby": 12,
            "medical": 2,
        },  # AP-13, BOARD
    },
    "cooling_off_days": 180,  # DEMO
    "scoring": {
        "max_total": 13,
        "median_rounding": "up",  # Q2
        "bands": [
            {"min": 9, "max": 13, "guideline": "approve_full"},
            {"min": 6, "max": 8, "guideline": "approve_partial_or_conditional"},
            {"min": 3, "max": 5, "guideline": "refer_small_grant_with_reason"},
            {"min": 0, "max": 2, "guideline": "decline_with_referral"},
        ],
        # AP-8 / Q14 / Q22: Bituach Leumi standard persons and poverty line.
        "need_suggestion_enabled": True,
        "poverty_line_monthly_agorot": 354_700,  # ₪3,547 per standard person per month
        "poverty_line_year": 2024,
        "poverty_line_source": "NII poverty report 2024",  # update when the 2025 figure is published
        "equivalence_scale": [1.25, 2.00, 2.65, 3.20, 3.75, 4.25, 4.75, 5.20, 5.60],
        "equivalence_extra_person": 0.40,
        "need_bands_percent": [
            100,
            125,
            150,
        ],  # BOARD: <100 → 3, 100–125 → 2, 125–150 → 1, ≥150 → 0
    },
    "rights_suggestion": {  # AP-7
        "eligible_not_claimed": [0, 1],
        "claim_in_progress": [1, 2],  # DEMO: AP-7 does not cover this status
        "resolved": [3, 3],
    },
    "categories": ["rent", "car", "childcare", "baby", "medical", "other"],
    "documents": {
        "by_category": {
            "rent": [["lease"], ["arrears_notice", "landlord_letter"]],
            "car": [["garage_quote"], ["vehicle_registration"]],
            "childcare": [["daycare_invoice"], ["work_or_study_proof"]],
            "baby": [["id_appendix", "birth_certificate"]],
            "medical": [
                ["medical_receipt_or_quote"],
                ["provider_note"],
                ["health_fund_non_coverage"],
            ],
        },
        "car_second_quote_above": 200_000,  # DEMO
        "income_proof_from_tier": "B",
        "referral_letter_from_tier": "C",  # AP-2
        "recognised_referral_waives": [],  # AP-1: empty until Q13 is answered
    },
    "excluded_purposes": [  # AP-10, BOARD
        {
            "code": "debt_repayment",
            "label_he": "החזר חובות",
            "label_en": "Debt repayment",
            "label_ru": "Погашение долгов",
        },
        {"code": "cash", "label_he": "מזומן", "label_en": "Cash", "label_ru": "Наличные"},
        {
            "code": "recurring_beyond_limit",
            "label_he": "תמיכה מתמשכת מעבר למותר",
            "label_en": "Recurring support beyond the limit",
            "label_ru": "Постоянная помощь сверх лимита",
        },
        {"code": "food", "label_he": "מזון", "label_en": "Food", "label_ru": "Продукты"},
        {
            "code": "luxury",
            "label_he": "מותרות",
            "label_en": "Luxury items",
            "label_ru": "Предметы роскоши",
        },
    ],
    "referral_directory": [],  # AP-10, BOARD
    "caps_baby_allocation_exempt": False,  # AP-15, BOARD
    "conditions": {
        "repeat_rent_requires_coaching": True,
        "repeat_window_days": 365,
        "coaching_default_org": "פעמונים",
    },  # AP-9
    "payment": {"reconfirm_after_days": 14},  # AP-6
    "public_stats": {"min_cell": 5},  # AP-17
    "budget": {
        "monthly_allocation": None,
        "reserve_percent": 20,
        "emergency_only_threshold_percent": 10,
    },  # AP-20, BOARD
    "sla": {"breach_alert_percent": 20},  # AP-21
    "languages_enabled": ["he", "en", "ru"],  # AP-4; "ar" is BOARD
    "alternates": {"assign_within_working_days": 2},  # Q21
    "audit": {
        "boundary_flag_window_agorot": 20_000
    },  # Q21: re-entered amount within ₪200 of a tier boundary
    "votes": {"reasoning_max_chars": 200},  # Q20: one-line reasoning per vote
    "consent_version": "2026-1",
}
