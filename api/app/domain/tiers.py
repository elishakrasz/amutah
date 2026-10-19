from dataclasses import dataclass

from app.domain.config import RulesConfig
from app.domain.enums import Tier
from app.domain.results import Reason


@dataclass(frozen=True)
class TierAssignment:
    tier: Tier  # who decides and how (E for the emergency path)
    reason: Reason
    band: Tier  # Q25: A, B or C by amount; emergency cases are reported under this


def amount_band(amount: int, payment_periods: int, cfg: RulesConfig) -> Tier:
    """The A/B/C band for reporting, whatever path the case took."""
    if payment_periods > 1:
        return Tier.C
    for tier in (Tier.A, Tier.B):
        if cfg.tier(tier).contains(amount):
            return tier
    return Tier.C


def assign_tier(
    amount: int, payment_periods: int, emergency: bool, cfg: RulesConfig
) -> TierAssignment:
    """Tier from the requested amount (agorot). Bands are lower-bound
    inclusive (Q24): exactly ₪500 is tier B, exactly ₪3,000 is tier C.
    The emergency ceiling is inclusive: exactly ₪1,500 can be tier E."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if payment_periods < 1:
        raise ValueError("payment_periods must be at least 1")

    recurring = payment_periods > 1
    band = amount_band(amount, payment_periods, cfg)
    if emergency:
        e_rule = cfg.tier(Tier.E)
        e_max = e_rule.upper_bound
        if recurring:
            emergency_blocker = Reason("emergency_not_for_recurring")
        elif not e_rule.contains(amount):
            emergency_blocker = Reason("emergency_amount_above_max", {"max": e_max})
        else:
            return TierAssignment(Tier.E, Reason("emergency", {"max": e_max}), band)
    else:
        emergency_blocker = None

    if recurring:
        return TierAssignment(Tier.C, emergency_blocker or Reason("recurring"), band)
    if band is Tier.C:
        reason = Reason("amount_from", {"from": cfg.tier(Tier.B).upper_bound})
    else:
        reason = Reason("amount_below", {"below": cfg.tier(band).upper_bound})
    return TierAssignment(band, emergency_blocker or reason, band)


def boundary_flag(new_amount: int, cfg: RulesConfig) -> Reason | None:
    """Q21: a re-entered amount within the configured window (₪200) of a tier
    boundary is flagged for the audit committee. Never used to suggest a
    lower amount."""
    window = cfg.boundary_flag_window
    for tier in (Tier.A, Tier.E, Tier.B):
        boundary = cfg.tier(tier).upper_bound
        assert boundary is not None
        if abs(new_amount - boundary) <= window:
            return Reason("amount_near_tier_boundary", {"boundary": boundary, "tier": tier.value})
    return None
