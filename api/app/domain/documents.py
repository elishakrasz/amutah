"""Required documents per category and tier. The coordinator cannot move a
case on while anything here is missing; the UI lists exactly what is."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.config import RulesConfig
from app.domain.enums import Category, DocumentType, Tier

TIER_RANK = {Tier.A: 0, Tier.E: 0, Tier.B: 1, Tier.C: 2}


@dataclass(frozen=True)
class Requirement:
    any_of: tuple[DocumentType, ...]
    min_count: int = 1


def required_documents(
    category: Category,
    tier: Tier,
    amount: int,
    cfg: RulesConfig,
    *,
    has_referrer: bool = False,
    referral_recognised: bool = False,
) -> tuple[Requirement, ...]:
    rules = cfg.documents
    reqs = [Requirement(group) for group in rules.by_category.get(category, ())]
    if category is Category.CAR and amount > rules.car_second_quote_above:
        reqs = [
            Requirement(r.any_of, 2) if r.any_of == (DocumentType.GARAGE_QUOTE,) else r
            for r in reqs
        ]
    if TIER_RANK[tier] >= TIER_RANK[rules.income_proof_from_tier]:
        reqs.append(Requirement((DocumentType.INCOME_PROOF,)))
    if has_referrer and TIER_RANK[tier] >= TIER_RANK[rules.referral_letter_from_tier]:
        reqs.append(Requirement((DocumentType.REFERRAL_LETTER_SIGNED,)))  # AP-2
    if referral_recognised and rules.recognised_referral_waives:
        waived = set(rules.recognised_referral_waives)
        reqs = [r for r in reqs if not set(r.any_of) <= waived]  # AP-1
    return tuple(reqs)


def document_tier(tier: Tier, escalated_from: Tier | None) -> Tier:
    """Q26: escalation changes who decides, not what the applicant provides.
    Documents stay at the tier the case started at."""
    return escalated_from or tier


def missing_documents(
    required: tuple[Requirement, ...], uploaded: Sequence[DocumentType]
) -> tuple[Requirement, ...]:
    return tuple(r for r in required if sum(1 for d in uploaded if d in r.any_of) < r.min_count)
