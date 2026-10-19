from datetime import date

import pytest

from app.domain.approval import (
    AlternateCandidate,
    ApprovalState,
    ChairDecision,
    Escalation,
    Panel,
    Vote,
    evaluate_votes,
    plan_alternate,
    quorum_shortfall,
    resolve_split,
)
from app.domain.config import Seat
from app.domain.enums import Role, Tier
from tests.domain.helpers import cfg

C = cfg()
CO, CH, CM = Seat.COORDINATOR, Seat.CHAIR, Seat.COMMITTEE
PANEL = Panel(
    coordinators=frozenset({"c"}),
    chairs=frozenset({"ch"}),
    committee=frozenset({"m1", "m2", "m3"}),
)


def v(voter: str, seat: Seat, yes: bool = True, why: str = "Need is clear") -> Vote:
    return Vote(voter, seat, yes, why)


def state(tier: Tier, votes: list[Vote], panel: Panel = PANEL) -> ApprovalState:
    return evaluate_votes(C.tier(tier).approval, votes, panel, C).state


@pytest.mark.parametrize(
    ("tier", "votes", "expected"),
    [
        # Every seat votes before anything is decided (Q3).
        (Tier.A, [v("c", CO)], ApprovalState.PENDING),
        (Tier.A, [v("c", CO), v("m1", CM)], ApprovalState.CARRIED),
        (Tier.A, [v("c", CO), v("m1", CM, False)], ApprovalState.SPLIT),
        (Tier.A, [v("c", CO, False), v("m1", CM, False)], ApprovalState.REJECTED),
        (Tier.B, [v("m1", CM, False)], ApprovalState.PENDING),
        (Tier.B, [v("m1", CM), v("m2", CM)], ApprovalState.CARRIED),
        (Tier.B, [v("m1", CM), v("m2", CM, False)], ApprovalState.SPLIT),
        (Tier.B, [v("m1", CM, False), v("m2", CM, False)], ApprovalState.REJECTED),
        (Tier.C, [v("m1", CM), v("m2", CM)], ApprovalState.PENDING),
        (Tier.C, [v("m1", CM), v("m2", CM), v("m3", CM, False)], ApprovalState.CARRIED),
        (Tier.C, [v("m1", CM, False), v("m2", CM, False), v("m3", CM)], ApprovalState.REJECTED),
        (Tier.E, [v("ch", CH), v("m1", CM)], ApprovalState.CARRIED),
        (Tier.E, [v("ch", CH), v("m1", CM, False)], ApprovalState.SPLIT),
        (Tier.B, [v("ch", CM), v("m1", CM)], ApprovalState.CARRIED),  # chair in a committee seat
    ],
)
def test_panel_rules(tier: Tier, votes: list[Vote], expected: ApprovalState) -> None:
    assert state(tier, votes) is expected


def test_q20_dissent_is_kept_with_reasoning() -> None:
    r = evaluate_votes(
        C.tier(Tier.C).approval,
        [v("m1", CM), v("m2", CM, False, "Health fund should cover this"), v("m3", CM)],
        PANEL,
        C,
    )
    assert r.approvers == ("m1", "m3")
    assert [(x.voter, x.in_favour, x.reasoning) for x in r.counted][1] == (
        "m2",
        False,
        "Health fund should cover this",
    )
    assert (r.votes_for, r.votes_against, r.seats_open) == (2, 1, 0)


def test_invalid_votes_are_rejected_not_counted() -> None:
    panel = Panel(
        chairs=frozenset({"ch"}),
        committee=frozenset({"m1", "m2", "m3", "rec"}),
        recused=frozenset({"rec"}),
    )
    r = evaluate_votes(
        C.tier(Tier.B).approval,
        [
            v("m1", CM),
            v("m1", CM),
            v("rec", CM),
            v("outsider", CM),
            v("m2", CO),
            v("ch", CH),
            v("m2", CM, why=" "),
            v("m2", CM, why="line one\nline two"),
            v("m2", CM, why="x" * 201),
            v("m2", CM),
            v("m3", CM),
        ],
        panel,
        C,
    )
    assert [x.code for x in r.rejected_votes] == [
        "duplicate_voter",
        "voter_recused",
        "not_eligible_for_seat",  # not on the committee or the alternates list
        "not_eligible_for_seat",  # committee member in the coordinator seat
        "seat_not_available",  # tier B has no chair seat
        "vote_reasoning_required",
        "vote_reasoning_one_line",
        "vote_reasoning_one_line",
        "seat_not_available",  # third committee vote
    ]
    assert r.state is ApprovalState.CARRIED


# --- Q21 alternates


def test_q21_alternate_has_member_rights_for_the_case() -> None:
    with_alt = Panel(committee=frozenset({"m1"}), alternates=frozenset({"alt"}))
    assert state(Tier.B, [v("m1", CM), v("alt", CM)], with_alt) is ApprovalState.CARRIED
    without = Panel(committee=frozenset({"m1"}))
    assert state(Tier.B, [v("m1", CM), v("alt", CM)], without) is ApprovalState.PENDING


@pytest.mark.parametrize(
    ("tier", "panel", "short"),
    [
        (Tier.C, Panel(committee=frozenset({"a", "b", "c"})), {}),
        (Tier.C, Panel(committee=frozenset({"a", "b", "c"}), recused=frozenset({"c"})), {CM: 1}),
        (
            Tier.C,
            Panel(
                committee=frozenset({"a", "b", "c"}),
                alternates=frozenset({"alt"}),
                recused=frozenset({"c"}),
            ),
            {},
        ),
        (Tier.C, Panel(chairs=frozenset({"ch"}), committee=frozenset({"a", "b"})), {}),
        (Tier.E, Panel(chairs=frozenset({"ch"}), committee=frozenset({"a"})), {}),
        (Tier.E, Panel(chairs=frozenset({"ch"}), committee=frozenset({"ch"})), {CM: 1}),
        (
            Tier.E,
            Panel(chairs=frozenset({"ch"}), committee=frozenset({"a"}), recused=frozenset({"ch"})),
            {CH: 1},
        ),
        (Tier.A, Panel(committee=frozenset({"a"})), {CO: 1}),
    ],
)
def test_quorum_shortfall_after_recusals(tier: Tier, panel: Panel, short: dict[Seat, int]) -> None:
    assert quorum_shortfall(C.tier(tier).approval, panel.available()) == short


SUNDAY = date(2026, 10, 18)
LIST = [
    AlternateCandidate("board-1", True),
    AlternateCandidate("inactive", False),
    AlternateCandidate("m1", True),  # already on the panel
    AlternateCandidate("rec", True),  # recused on this case
    AlternateCandidate("board-2", True),
]


def test_q21_committee_chair_assigns_within_two_working_days() -> None:
    panel = Panel(committee=frozenset({"m1"}), recused=frozenset({"rec"}))
    plan = plan_alternate(SUNDAY, False, LIST, panel, frozenset(), C)
    assert plan.assigner is Role.COMMITTEE_CHAIR
    assert plan.assign_by == date(2026, 10, 20)
    assert plan.candidates == ("board-1", "board-2")


def test_q21_board_chair_assigns_when_the_chair_is_recused() -> None:
    plan = plan_alternate(SUNDAY, True, LIST, PANEL, frozenset(), C)
    assert plan.assigner is Role.BOARD_CHAIR


def test_q21_no_candidates_means_the_case_waits() -> None:
    plan = plan_alternate(SUNDAY, False, [AlternateCandidate("x", False)], PANEL, frozenset(), C)
    assert plan.candidates == ()


# --- Q20 / Q23 splits


def test_tier_c_cannot_split() -> None:
    for votes in ([True, True, False], [True, False, False], [False, False, False]):
        ballots = [v(f"m{i + 1}", CM, yes) for i, yes in enumerate(votes)]
        assert state(Tier.C, ballots) is not ApprovalState.SPLIT


def test_q20_tier_b_split_goes_to_tier_c_and_votes_stand() -> None:
    split = evaluate_votes(
        C.tier(Tier.B).approval,
        [v("m1", CM), v("m2", CM, False, "Not the cheapest quote")],
        PANEL,
        C,
    )
    esc = resolve_split(Tier.B, split, PANEL, C)
    assert isinstance(esc, Escalation)
    assert (esc.from_tier, esc.to_tier) == (Tier.B, Tier.C)
    assert esc.result.state is ApprovalState.PENDING
    assert (esc.result.votes_for, esc.result.votes_against, esc.result.seats_open) == (1, 1, 1)
    assert esc.not_carried == ()
    third = evaluate_votes(C.tier(Tier.C).approval, [*esc.result.counted, v("m3", CM)], PANEL, C)
    assert third.state is ApprovalState.CARRIED


def test_q23_tier_a_split_goes_to_tier_b_without_the_coordinator() -> None:
    coordinator = v("c", CO, True, "Vendor confirmed the quote")
    split = evaluate_votes(
        C.tier(Tier.A).approval, [coordinator, v("m1", CM, False, "Covered by BTL")], PANEL, C
    )
    assert split.state is ApprovalState.SPLIT
    esc = resolve_split(Tier.A, split, PANEL, C)
    assert isinstance(esc, Escalation)
    assert esc.to_tier is Tier.B
    assert [x.voter for x in esc.result.counted] == ["m1"]
    assert esc.not_carried == (coordinator,)  # recorded, does not vote at B
    assert esc.result.seats_open == 1  # a second committee member joins


def test_q23_escalated_a_then_split_at_b_goes_on_to_c() -> None:
    split_a = evaluate_votes(C.tier(Tier.A).approval, [v("c", CO), v("m1", CM, False)], PANEL, C)
    to_b = resolve_split(Tier.A, split_a, PANEL, C)
    assert isinstance(to_b, Escalation)
    at_b = evaluate_votes(C.tier(Tier.B).approval, [*to_b.result.counted, v("m2", CM)], PANEL, C)
    assert at_b.state is ApprovalState.SPLIT
    to_c = resolve_split(Tier.B, at_b, PANEL, C)
    assert isinstance(to_c, Escalation)
    assert to_c.to_tier is Tier.C


@pytest.mark.parametrize(
    ("chair_for", "outcome"), [(True, ApprovalState.CARRIED), (False, ApprovalState.REJECTED)]
)
def test_q23_tier_e_split_the_chair_decides(chair_for: bool, outcome: ApprovalState) -> None:
    chair = v("ch", CH, chair_for, "Eviction tomorrow" if chair_for else "Other help exists")
    member = v("m1", CM, not chair_for, "Disagree")
    split = evaluate_votes(C.tier(Tier.E).approval, [chair, member], PANEL, C)
    assert split.state is ApprovalState.SPLIT
    decided = resolve_split(Tier.E, split, PANEL, C)
    assert isinstance(decided, ChairDecision)
    assert decided.state is outcome
    assert decided.chair_vote == chair
    assert decided.dissent == (member,)


def test_only_a_split_is_resolved() -> None:
    pending = evaluate_votes(C.tier(Tier.B).approval, [v("m1", CM)], PANEL, C)
    with pytest.raises(ValueError, match="only a split"):
        resolve_split(Tier.B, pending, PANEL, C)


def test_a_split_without_a_rule_is_a_configuration_error() -> None:
    c = cfg(**{"tiers.B.on_split": None})
    split = evaluate_votes(c.tier(Tier.B).approval, [v("m1", CM), v("m2", CM, False)], PANEL, c)
    with pytest.raises(ValueError, match="no split rule"):
        resolve_split(Tier.B, split, PANEL, c)
