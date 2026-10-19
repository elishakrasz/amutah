import pytest

from app.domain.documents import Requirement, missing_documents, required_documents
from app.domain.enums import Category, Tier
from app.domain.enums import DocumentType as D
from tests.domain.helpers import cfg

C = cfg()


def types(reqs: tuple[Requirement, ...]) -> list[tuple[tuple[str, ...], int]]:
    return [(tuple(d.value for d in r.any_of), r.min_count) for r in reqs]


def test_rent_tier_a() -> None:
    assert types(required_documents(Category.RENT, Tier.A, 40_000, C)) == [
        (("lease",), 1),
        (("arrears_notice", "landlord_letter"), 1),
    ]


def test_tier_b_adds_income_proof() -> None:
    reqs = required_documents(Category.BABY, Tier.B, 100_000, C)
    assert (("income_proof",), 1) in types(reqs)


@pytest.mark.parametrize(("amount", "quotes"), [(200_000, 1), (200_001, 2)])
def test_car_second_quote_above_threshold(amount: int, quotes: int) -> None:
    reqs = required_documents(Category.CAR, Tier.B, amount, C)
    assert (("garage_quote",), quotes) in types(reqs)


def test_other_category_has_no_category_documents() -> None:
    assert required_documents(Category.OTHER, Tier.A, 10_000, C) == ()


@pytest.mark.parametrize(
    ("tier", "has_referrer", "needs_letter"),
    [(Tier.C, True, True), (Tier.C, False, False), (Tier.B, True, False)],
)
def test_ap2_tier_c_referral_needs_signed_letter(
    tier: Tier, has_referrer: bool, needs_letter: bool
) -> None:
    reqs = required_documents(Category.MEDICAL, tier, 400_000, C, has_referrer=has_referrer)
    assert ((("referral_letter_signed",), 1) in types(reqs)) is needs_letter


def test_ap2_missing_list_shows_the_letter() -> None:
    reqs = required_documents(Category.BABY, Tier.C, 400_000, C, has_referrer=True)
    missing = missing_documents(reqs, [D.BIRTH_CERTIFICATE, D.INCOME_PROOF])
    assert types(missing) == [(("referral_letter_signed",), 1)]


def test_ap1_recognised_referral_waives_configured_documents() -> None:
    c = cfg(**{"documents.recognised_referral_waives": ["income_proof"]})
    pending = required_documents(Category.BABY, Tier.B, 100_000, c, has_referrer=True)
    recognised = required_documents(
        Category.BABY, Tier.B, 100_000, c, has_referrer=True, referral_recognised=True
    )
    assert (("income_proof",), 1) in types(pending)
    assert (("income_proof",), 1) not in types(recognised)


def test_missing_counts_documents() -> None:
    reqs = required_documents(Category.CAR, Tier.B, 250_000, C)
    uploaded = [D.GARAGE_QUOTE, D.VEHICLE_REGISTRATION, D.INCOME_PROOF]
    assert types(missing_documents(reqs, uploaded)) == [(("garage_quote",), 2)]
    assert missing_documents(reqs, [*uploaded, D.GARAGE_QUOTE]) == ()


@pytest.mark.parametrize(
    ("tier", "origin", "expected"),
    [(Tier.B, Tier.A, Tier.A), (Tier.C, Tier.A, Tier.A), (Tier.B, None, Tier.B)],
)
def test_q26_documents_stay_at_the_starting_tier(
    tier: Tier, origin: Tier | None, expected: Tier
) -> None:
    from app.domain.documents import document_tier

    assert document_tier(tier, origin) is expected
    reqs = required_documents(Category.BABY, document_tier(tier, origin), 30_000, C)
    assert ((("income_proof",), 1) in types(reqs)) is (expected is not Tier.A)
