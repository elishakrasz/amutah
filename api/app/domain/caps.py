"""Annual household caps (amount, count) and per-category caps (AP-13)."""

from dataclasses import dataclass
from datetime import date

from app.domain.config import RulesConfig
from app.domain.enums import Category
from app.domain.results import Reason


@dataclass(frozen=True)
class PriorGrant:
    """A grant to the same household that was approved (and maybe paid)."""

    decided_on: date
    amount: int  # agorot approved
    category: Category
    paid_on: date | None = None


@dataclass(frozen=True)
class Headroom:
    """What the household can still receive this calendar year. Shown to the
    committee before scoring."""

    year: int
    amount_remaining: int
    grants_remaining: int
    category_grants_remaining: int | None  # None = no per-category cap
    per_grant: int


def headroom(
    prior: tuple[PriorGrant, ...], category: Category, year: int, cfg: RulesConfig
) -> Headroom:
    this_year = [g for g in prior if g.decided_on.year == year]
    cat_cap = cfg.caps.per_category_per_year.get(category)
    same_cat = sum(1 for g in this_year if g.category is category)
    return Headroom(
        year=year,
        amount_remaining=max(
            0, cfg.caps.household_amount_per_year - sum(g.amount for g in this_year)
        ),
        grants_remaining=max(0, cfg.caps.household_grants_per_year - len(this_year)),
        category_grants_remaining=None if cat_cap is None else max(0, cat_cap - same_cat),
        per_grant=cfg.caps.per_grant,
    )


def exceeded_caps(amount: int, room: Headroom, category: Category) -> tuple[Reason, ...]:
    """Every cap this request would break. Empty means within all caps."""
    out = []
    if amount > room.per_grant:
        out.append(Reason("cap_per_grant", {"cap": room.per_grant}))
    if amount > room.amount_remaining:
        out.append(Reason("cap_household_amount", {"remaining": room.amount_remaining}))
    if room.grants_remaining < 1:
        out.append(Reason("cap_household_count"))
    if room.category_grants_remaining is not None and room.category_grants_remaining < 1:
        out.append(Reason("cap_category_count", {"category": category.value}))
    return tuple(out)
