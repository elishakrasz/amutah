"""AP-8 income worksheet maths, using Bituach Leumi's standard persons
(נפשות תקניות). Integer arithmetic only, so two coordinators entering the
same figures always get the same result."""

from dataclasses import dataclass

from app.domain.config import RulesConfig
from app.domain.results import Reason, Suggestion


@dataclass(frozen=True)
class IncomeResult:
    total_income: int  # agorot per month
    household_size: int
    standard_persons: int  # hundredths, e.g. 375 = 3.75
    per_standard_person: int  # agorot per month, rounded down

    @property
    def divisor_label(self) -> str:
        return f"{self.standard_persons // 100}.{self.standard_persons % 100:02d}"


def standard_persons(household_size: int, cfg: RulesConfig) -> int:
    if household_size < 1:
        raise ValueError("household must have at least one person")
    table = cfg.need.standard_persons
    if household_size <= len(table):
        return table[household_size - 1]
    return table[-1] + (household_size - len(table)) * cfg.need.extra_person


def per_standard_person(
    earned_net: int,
    btl_benefits: int,
    other_income: int,
    adults: int,
    children: int,
    cfg: RulesConfig,
) -> IncomeResult:
    if min(earned_net, btl_benefits, other_income, children) < 0 or adults < 1:
        raise ValueError("incomes and children must be non-negative; at least one adult")
    total = earned_net + btl_benefits + other_income
    size = adults + children
    weight = standard_persons(size, cfg)
    return IncomeResult(total, size, weight, total * 100 // weight)


def suggest_need(result: IncomeResult, cfg: RulesConfig) -> Suggestion | None:
    """Advisory only: the committee enters its own score. None while the
    suggestion is switched off or no poverty line is set. Bands are
    half-open: exactly 100% of the line falls in the 100-125% band."""
    line = cfg.need.poverty_line_per_standard_person
    if not cfg.need.enabled or line is None:
        return None
    pct_x100 = result.per_standard_person * 100  # compare without division
    for band in cfg.need.bands:
        if band.below_percent is None or pct_x100 < line * band.below_percent:
            return Suggestion(
                band.score,
                band.score,
                Reason(
                    "need_from_income",
                    {
                        "per_standard_person": result.per_standard_person,
                        "poverty_line": line,
                        "poverty_line_year": cfg.need.poverty_line_year,
                        "poverty_line_source": cfg.need.poverty_line_source,
                        "divisor": result.divisor_label,
                    },
                ),
            )
    raise AssertionError("need bands end with an open band")  # pragma: no cover
