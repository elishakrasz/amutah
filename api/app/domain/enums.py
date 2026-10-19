"""Vocabulary shared by the rules engine and the persistence layer. Pure Python."""

from enum import StrEnum


class Role(StrEnum):
    APPLICANT = "applicant"
    REFERRER = "referrer"
    COORDINATOR = "coordinator"
    COMMITTEE_MEMBER = "committee_member"
    COMMITTEE_CHAIR = "committee_chair"
    TREASURER = "treasurer"
    BOARD_MEMBER = "board_member"
    BOARD_CHAIR = "board_chair"  # assigns alternates when the committee chair is recused (Q21)
    AUDITOR = "auditor"
    ADMIN = "admin"


STAFF_ROLES = frozenset(Role) - {Role.APPLICANT, Role.REFERRER}


class Category(StrEnum):
    RENT = "rent"
    CAR = "car"
    CHILDCARE = "childcare"
    BABY = "baby"
    MEDICAL = "medical"
    OTHER = "other"


class Tier(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    E = "E"


class CaseStatus(StrEnum):
    SUBMITTED = "submitted"
    INTAKE_REVIEW = "intake_review"
    INELIGIBLE = "ineligible"
    ELIGIBLE = "eligible"
    AWAITING_DOCUMENTS = "awaiting_documents"
    VERIFICATION = "verification"
    SCORING = "scoring"
    DECISION_PENDING = "decision_pending"
    APPROVED = "approved"
    PARTIAL = "partial"
    CONDITIONAL = "conditional"
    REFERRED = "referred"
    DECLINED = "declined"
    UNDER_APPEAL = "under_appeal"
    EMERGENCY_REVIEW = "emergency_review"
    RATIFICATION_PENDING = "ratification_pending"
    PAYMENT_APPROVED = "payment_approved"
    IN_BATCH = "in_batch"
    PAID = "paid"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"


class DecisionOutcome(StrEnum):
    APPROVE_FULL = "approve_full"
    APPROVE_PARTIAL = "approve_partial"
    APPROVE_CONDITIONAL = "approve_conditional"
    REFER = "refer"
    DECLINE = "decline"


class AppealOutcome(StrEnum):
    UPHELD = "upheld"  # original decision stands
    RETURNED = "returned"  # case re-enters decision_pending


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    VOUCHER = "voucher"
    EXCEPTION_CASH = "exception_cash"


class PaymentEventKind(StrEnum):
    NEED_CONFIRMED = "need_confirmed"  # AP-6
    IN_BATCH = "in_batch"
    EXECUTED = "executed"
    FAILED = "failed"
    VOUCHER_ISSUED = "voucher_issued"  # AP-14
    VOUCHER_REDEMPTION_REPORTED = "voucher_redemption_reported"  # AP-14


class ChairApprovalKind(StrEnum):
    OTHER_CATEGORY = "other_category"
    COOLING_OFF_OVERRIDE = "cooling_off_override"
    EMERGENCY = "emergency"


class DocumentType(StrEnum):
    LEASE = "lease"
    ARREARS_NOTICE = "arrears_notice"
    LANDLORD_LETTER = "landlord_letter"
    GARAGE_QUOTE = "garage_quote"
    VEHICLE_REGISTRATION = "vehicle_registration"
    DAYCARE_INVOICE = "daycare_invoice"
    WORK_OR_STUDY_PROOF = "work_or_study_proof"
    ID_APPENDIX = "id_appendix"
    BIRTH_CERTIFICATE = "birth_certificate"
    MEDICAL_RECEIPT_OR_QUOTE = "medical_receipt_or_quote"
    PROVIDER_NOTE = "provider_note"
    HEALTH_FUND_NON_COVERAGE = "health_fund_non_coverage"
    INCOME_PROOF = "income_proof"
    REFERRAL_LETTER_SIGNED = "referral_letter_signed"  # AP-2
    BALANCE_EVIDENCE = "balance_evidence"  # AP-12
    OTHER = "other"


class InsiderRelationship(StrEnum):
    FOUNDER = "founder"
    BOARD = "board"
    COMMITTEE = "committee"
    EMPLOYEE = "employee"
    RELATIVE = "relative"


class ActorType(StrEnum):
    STAFF = "staff"
    APPLICANT = "applicant"
    SYSTEM = "system"


class Language(StrEnum):  # AP-4
    HE = "he"
    EN = "en"
    RU = "ru"
    AR = "ar"


RTL_LANGUAGES = frozenset({Language.HE, Language.AR})


class ReferrerStatus(StrEnum):  # AP-1
    PENDING = "pending"
    RECOGNISED = "recognised"
    SUSPENDED = "suspended"


class LeadStatus(StrEnum):  # AP-3
    NEW = "new"
    CONTACTED = "contacted"
    CONSENTED = "consented"
    CONVERTED = "converted"
    CLOSED_NO_CONSENT = "closed_no_consent"
    EXPIRED = "expired"


class IntakeCallOutcome(StrEnum):  # AP-5
    PROCEED = "proceed"
    REFER_ELSEWHERE = "refer_elsewhere"
    WITHDRAWN = "withdrawn"
    NO_ANSWER = "no_answer"


class RightsItem(StrEnum):  # AP-7
    BTL_BENEFIT = "btl_benefit"
    HOUSING_RENT_ASSISTANCE = "housing_rent_assistance"
    DAYCARE_SUBSIDY = "daycare_subsidy"
    HEALTH_FUND_COVERAGE = "health_fund_coverage"
    MUNICIPAL_WELFARE = "municipal_welfare"
    OTHER = "other"


class RightsStatus(StrEnum):  # AP-7
    NOT_APPLICABLE = "not_applicable"
    ELIGIBLE_NOT_CLAIMED = "eligible_not_claimed"
    CLAIM_IN_PROGRESS = "claim_in_progress"
    CLAIMED = "claimed"
    DENIED = "denied"


class ConditionType(StrEnum):  # AP-7, AP-9
    CLAIM_ENTITLEMENT_FIRST = "claim_entitlement_first"
    COACHING_REFERRAL = "coaching_referral"
    OTHER = "other"


class BalanceSource(StrEnum):  # AP-12
    APPLICANT = "applicant"
    FAMILY = "family"
    OTHER_ORG = "other_org"
    VENDOR_DISCOUNT = "vendor_discount"
    WAIVED_BY_VENDOR = "waived_by_vendor"
    NONE = "none"


class NeedConfirmMethod(StrEnum):  # AP-6
    VENDOR_CALL = "vendor_call"
    APPLICANT_CALL = "applicant_call"
    REFERRER = "referrer"


class ConfirmedBy(StrEnum):  # AP-16
    APPLICANT = "applicant"
    REFERRER = "referrer"
    VENDOR = "vendor"


class AllocationStatus(StrEnum):  # AP-15
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class OrgDocumentType(StrEnum):  # AP-18
    REGISTRATION_CERTIFICATE = "registration_certificate"
    ANNUAL_FINANCIAL_REPORT = "annual_financial_report"
    VERBAL_REPORT = "verbal_report"
    PROPER_MANAGEMENT_CERTIFICATE = "proper_management_certificate"
    SECTION_46_APPROVAL = "section_46_approval"


class SlaEventKind(StrEnum):  # Q20, Q21
    PAUSED = "paused"  # no alternate available
    RESUMED = "resumed"
    RESTARTED = "restarted"  # escalation: new tier's SLA from this moment


class ApplicantMessage(StrEnum):
    """Plain messages that never carry a reason (recusals are never disclosed)."""

    SLIGHT_DELAY = "slight_delay"  # Q21: no alternate available
    STILL_IN_PROCESS = "still_in_process"  # Q20: escalated


class RatificationOutcome(StrEnum):  # Q23
    RATIFIED = "ratified"
    OVERTURNED = "overturned"  # after payment: noted, no clawback, still counts toward caps
