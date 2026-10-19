"""Who must vote on a decision, who may sit on the panel, and what happens
when it splits.

Q3  A: coordinator + one committee member, both in favour.
    B: two committee members, both in favour.
    C: three committee members all vote; two in favour carries.
    E: chair + one other committee member, both in favour; ratified later.
Q20 Every seat votes. Enough votes in favour carries; enough against
    rejects the proposal (the panel agrees it is wrong, and may table
    another). Anything else is a split, which never ends in a decline:
Q23 A -> B (a second member joins; the coordinator's vote is recorded but
    does not count at B), B -> full C panel (votes stand), E -> the chair
    decides and the dissent is recorded. C cannot split with three seats.
Q21 Seats left empty by recusals are filled from the board-approved
    alternates list, for that case only. Never ad hoc.
"""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.domain.config import ApprovalRule, RulesConfig, Seat, SplitPolicy
from app.domain.enums import Role, Tier
from app.domain.results import Reason
from app.domain.working_days import add_working_days


class ApprovalState(StrEnum):
    PENDING = "pending"  # seats still to vote
    CARRIED = "carried"
    REJECTED = "rejected"  # enough members voted against the proposal
    SPLIT = "split"  # every seat voted and neither side reached min_for


@dataclass(frozen=True)
class Vote:
    voter: Hashable
    seat: Seat
    in_favour: bool
    reasoning: str  # one line, kept with the decision for appeals


@dataclass(frozen=True)
class Panel:
    """Who may fill each seat on this case. `alternates` are the
    board-approved alternates assigned to this case (Q21)."""

    coordinators: frozenset[Hashable] = frozenset()
    chairs: frozenset[Hashable] = frozenset()
    committee: frozenset[Hashable] = frozenset()
    alternates: frozenset[Hashable] = frozenset()
    recused: frozenset[Hashable] = field(default_factory=frozenset)

    def may_sit(self, voter: Hashable, seat: Seat) -> bool:
        if seat is Seat.COORDINATOR:
            return voter in self.coordinators
        if seat is Seat.CHAIR:
            return voter in self.chairs
        return voter in self.committee or voter in self.chairs or voter in self.alternates

    def available(self) -> dict[Seat, int]:
        """Counts for quorum_shortfall, after recusals."""
        chairs = self.chairs - self.recused
        return {
            Seat.COORDINATOR: len(self.coordinators - self.recused),
            Seat.CHAIR: len(chairs),
            Seat.COMMITTEE: len((self.committee | self.alternates) - chairs - self.recused),
        }


@dataclass(frozen=True)
class ApprovalResult:
    state: ApprovalState
    votes_for: int
    votes_against: int
    seats_open: int
    counted: tuple[Vote, ...]  # every vote that counts, with its reasoning (dissent too)
    rejected_votes: tuple[Reason, ...]

    @property
    def approvers(self) -> tuple[Hashable, ...]:
        return tuple(v.voter for v in self.counted if v.in_favour)


def _reasoning_problem(text: str, max_chars: int) -> Reason | None:
    if not text.strip():
        return Reason("vote_reasoning_required")
    if "\n" in text.strip() or len(text.strip()) > max_chars:
        return Reason("vote_reasoning_one_line", {"max": max_chars})
    return None


def evaluate_votes(
    rule: ApprovalRule, votes: Sequence[Vote], panel: Panel, cfg: RulesConfig
) -> ApprovalResult:
    rejected: list[Reason] = []
    seen: set[Hashable] = set()
    filled: dict[Seat, int] = {}
    counted: list[Vote] = []
    for v in votes:
        who = {"voter": str(v.voter)}
        problem = _reasoning_problem(v.reasoning, cfg.vote_reasoning_max_chars)
        if v.voter in panel.recused:
            rejected.append(Reason("voter_recused", who))
        elif not panel.may_sit(v.voter, v.seat):
            rejected.append(Reason("not_eligible_for_seat", {**who, "seat": v.seat.value}))
        elif v.voter in seen:
            rejected.append(Reason("duplicate_voter", who))
        elif filled.get(v.seat, 0) >= rule.seats.get(v.seat, 0):
            rejected.append(Reason("seat_not_available", {"seat": v.seat.value}))
        elif problem is not None:
            rejected.append(problem)
        else:
            seen.add(v.voter)
            filled[v.seat] = filled.get(v.seat, 0) + 1
            counted.append(v)

    votes_for = sum(1 for v in counted if v.in_favour)
    votes_against = len(counted) - votes_for
    seats_open = rule.total_seats - len(counted)
    if seats_open:
        state = ApprovalState.PENDING  # Q3: every seat votes
    elif votes_for >= rule.min_for:
        state = ApprovalState.CARRIED
    elif votes_against >= rule.min_for:
        state = ApprovalState.REJECTED
    else:
        state = ApprovalState.SPLIT
    return ApprovalResult(
        state=state,
        votes_for=votes_for,
        votes_against=votes_against,
        seats_open=seats_open,
        counted=tuple(counted),
        rejected_votes=tuple(rejected),
    )


def quorum_shortfall(rule: ApprovalRule, available: Mapping[Seat, int]) -> dict[Seat, int]:
    """Seats that cannot be filled. Empty means quorum is possible. The chair
    counts toward committee seats only when not needed in the chair seat."""
    short: dict[Seat, int] = {}
    chair_free = available.get(Seat.CHAIR, 0) - rule.seats.get(Seat.CHAIR, 0)
    if chair_free < 0:
        short[Seat.CHAIR] = -chair_free
    for seat in (Seat.COORDINATOR, Seat.COMMITTEE):
        need = rule.seats.get(seat, 0)
        have = available.get(seat, 0)
        if seat is Seat.COMMITTEE:
            have += max(0, chair_free)
        if have < need:
            short[seat] = need - have
    return short


# --- Q21 alternates


@dataclass(frozen=True)
class AlternateCandidate:
    person: Hashable
    active: bool


@dataclass(frozen=True)
class AlternatePlan:
    assigner: Role  # committee chair, or board chair if the chair is recused
    assign_by: date  # within N working days of the shortfall
    candidates: tuple[Hashable, ...]  # in list order; empty = case waits, SLA paused


def plan_alternate(
    shortfall_on: date,
    chair_recused: bool,
    approved_list: Sequence[AlternateCandidate],
    panel: Panel,
    holidays: frozenset[date],
    cfg: RulesConfig,
) -> AlternatePlan:
    """Only people on the board-approved list, active, not recused and not
    already on this case's panel."""
    already = panel.committee | panel.chairs | panel.coordinators | panel.alternates
    within = cfg.alternate_assign_within_working_days
    return AlternatePlan(
        assigner=Role.BOARD_CHAIR if chair_recused else Role.COMMITTEE_CHAIR,
        assign_by=add_working_days(shortfall_on, within, holidays),
        candidates=tuple(
            c.person
            for c in approved_list
            if c.active and c.person not in panel.recused and c.person not in already
        ),
    )


# --- Q20 / Q23 splits


@dataclass(frozen=True)
class Escalation:
    from_tier: Tier
    to_tier: Tier
    result: ApprovalResult  # earlier votes re-counted on the larger panel
    not_carried: tuple[Vote, ...]  # e.g. the coordinator's: recorded, not counted


@dataclass(frozen=True)
class ChairDecision:
    """Tier E: on a split the chair's vote decides; the dissent stays on
    record and the case is ratified (or overturned) at the next meeting."""

    state: ApprovalState  # CARRIED or REJECTED
    chair_vote: Vote
    dissent: tuple[Vote, ...]


def resolve_split(
    tier: Tier, result: ApprovalResult, panel: Panel, cfg: RulesConfig
) -> Escalation | ChairDecision:
    if result.state is not ApprovalState.SPLIT:
        raise ValueError("only a split panel is resolved")
    rule = cfg.tier(tier).on_split
    if rule is None:
        raise ValueError(f"tier {tier.value} has no split rule configured")
    if rule.policy is SplitPolicy.CHAIR_DECIDES:
        chair = next(v for v in result.counted if v.seat is Seat.CHAIR)
        return ChairDecision(
            state=ApprovalState.CARRIED if chair.in_favour else ApprovalState.REJECTED,
            chair_vote=chair,
            dissent=tuple(v for v in result.counted if v.in_favour is not chair.in_favour),
        )
    assert rule.escalate_to is not None
    target = cfg.tier(rule.escalate_to).approval
    carried = tuple(v for v in result.counted if target.seats.get(v.seat))
    return Escalation(
        from_tier=tier,
        to_tier=rule.escalate_to,
        result=evaluate_votes(target, carried, panel, cfg),
        not_carried=tuple(v for v in result.counted if v not in carried),
    )
