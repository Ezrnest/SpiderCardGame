from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from dataclasses import dataclass, replace
from typing import Iterable, Optional

from base.Core import Card, GameConfig

CardAtom = int
StackAtom = tuple[CardAtom, ...]
StateKey = tuple[tuple[int, ...], tuple[tuple[StackAtom, int], ...], int]


@dataclass(frozen=True, slots=True)
class SolverState:
    """Immutable full-information state used by the solver."""

    base: tuple[int, ...]
    stacks: tuple[StackAtom, ...]
    # Number of hidden cards from bottom for each stack.
    hidden_prefix: tuple[int, ...] = ()
    finished_count: int = 0


@dataclass(frozen=True, slots=True)
class Action:
    """A single player action in solver notation."""

    kind: str
    src_stack: int = -1
    src_idx: int = -1
    dest_stack: int = -1
    moved_len: int = 0
    draw_count: int = 0

    def to_notation(self) -> str:
        if self.kind == "DEAL":
            return f"DEAL({self.draw_count})"
        return f"MOVE(S{self.src_stack}:{self.src_idx}->S{self.dest_stack},len={self.moved_len})"


@dataclass(frozen=True, slots=True)
class SearchLimits:
    max_nodes: int = 200_000
    max_seconds: float = 2.0
    max_frontier: int = 500_000


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    # If the source is already part of an ordered same-suit run, do not split it.
    lock_same_suit_runs: bool = True
    # If there is at least one same-suit destination, only keep those destinations.
    require_same_suit_destination_when_available: bool = True
    # Prefer keeping empty columns for future mobility.
    avoid_empty_for_short_moves: bool = True
    min_len_for_empty_move: int = 3
    # Human-like policy: do not deal while meaningful moves still exist.
    defer_deal_until_no_moves: bool = True
    # Symmetric empty columns are equivalent; keep at most one.
    limit_empty_destinations_per_move: bool = True
    # Macro policy: greedily chain human-like follow-up moves to reduce depth.
    macro_chain_enabled: bool = True
    macro_max_steps: int = 4
    macro_empty_restore_enabled: bool = True
    macro_empty_restore_min_len: int = 5
    # Tabu: avoid immediate backtrack (reverse of the previous move).
    taboo_immediate_reverse: bool = True


DEFAULT_POLICY = SearchPolicy()


@dataclass(frozen=True, slots=True)
class SearchStage:
    name: str
    policy: SearchPolicy
    time_share: float
    node_share: float
    frontier_share: float = 1.0


@dataclass(slots=True)
class SolveResult:
    status: str
    stop_reason: str
    solution: tuple[Action, ...]
    solution_states: tuple[SolverState, ...]
    expanded_nodes: int
    generated_nodes: int
    unique_states: int
    max_frontier: int
    dead_end_nodes: int
    duplicate_states_skipped: int
    avg_branching: float
    elapsed_ms: float
    max_depth: int
    solution_revealed: int
    solution_freed: int
    solution_deals: int


@dataclass(slots=True)
class AnalyzeResult:
    status: str
    solvable: Optional[bool]
    proven: bool
    difficulty_score: Optional[float]
    difficulty_band: Optional[str]
    metrics: dict
    seed: Optional[int] = None
    suits: Optional[int] = None
    solution: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "suits": self.suits,
            "status": self.status,
            "solvable": self.solvable,
            "proven": self.proven,
            "difficulty_score": self.difficulty_score,
            "difficulty_band": self.difficulty_band,
            "metrics": self.metrics,
            "solution": list(self.solution),
        }


@dataclass(frozen=True, slots=True)
class _Transition:
    action: Action
    state: SolverState
    revealed: int
    freed: int
    priority: int
    macro_steps: int = 0
    state_key: Optional[StateKey] = None


def _normalized_hidden_prefix(state: SolverState) -> tuple[int, ...]:
    if len(state.hidden_prefix) == len(state.stacks):
        return state.hidden_prefix
    return tuple(0 for _ in state.stacks)


def _canonical_state_key(state: SolverState) -> StateKey:
    """
    Canonical key for dedup:
    - keep base order (deal order matters)
    - sort tableau columns to collapse permutation symmetry
    """
    hidden = _normalized_hidden_prefix(state)
    stacks_with_hidden = tuple((state.stacks[i], hidden[i]) for i in range(len(state.stacks)))
    return state.base, tuple(sorted(stacks_with_hidden)), state.finished_count


def _card_suit(card_id: int) -> int:
    return card_id // Card.NUM_PER_SUIT


def _card_num(card_id: int) -> int:
    return card_id % Card.NUM_PER_SUIT


def _is_goal(state: SolverState) -> bool:
    if state.base:
        return False
    return all(len(stack) == 0 for stack in state.stacks)


def build_initial_state(config: GameConfig) -> SolverState:
    """Build the initial state with hidden-prefix information."""

    base_cards = config.initBase()
    stacks: list[list[CardAtom]] = [[] for _ in range(config.stackCount)]

    draw_count = min(config.initialDealt, len(base_cards))
    dest = 0
    while draw_count > 0:
        card = base_cards.pop()
        stacks[dest].append(card.id)
        dest += 1
        if dest >= len(stacks):
            dest = 0
        draw_count -= 1

    base = tuple(card.id for card in base_cards)
    stacks_tuple = tuple(tuple(stack) for stack in stacks)
    hidden_prefix = tuple(max(0, len(stack) - 1) for stack in stacks_tuple)
    return SolverState(base=base, stacks=stacks_tuple, hidden_prefix=hidden_prefix, finished_count=0)


def _is_valid_sequence(stack: StackAtom, hidden_prefix: int, idx: int) -> bool:
    if idx < 0 or idx >= len(stack):
        return False
    # Cannot start moving from hidden cards.
    if idx < hidden_prefix:
        return False
    prev_id = stack[idx]
    for i in range(idx + 1, len(stack)):
        upper_id = stack[i]
        if not (_card_suit(prev_id) == _card_suit(upper_id) and _card_num(prev_id) == _card_num(upper_id) + 1):
            return False
        prev_id = upper_id
    return True


def _valid_move_starts(stack: StackAtom, hidden_prefix: int) -> tuple[int, ...]:
    """Return all indices that start a movable same-suit descending run."""
    n = len(stack)
    if n == 0 or hidden_prefix >= n:
        return ()
    hidden_prefix = max(0, hidden_prefix)

    valid: list[int] = [n - 1]
    contiguous = True
    for idx in range(n - 2, hidden_prefix - 1, -1):
        if contiguous:
            lower = stack[idx]
            upper = stack[idx + 1]
            contiguous = _card_suit(lower) == _card_suit(upper) and _card_num(lower) == _card_num(upper) + 1
        if contiguous:
            valid.append(idx)
    valid.reverse()
    return tuple(valid)


def _can_move(state: SolverState, src_stack: int, src_idx: int, dest_stack: int) -> bool:
    if src_stack < 0 or src_stack >= len(state.stacks):
        return False
    if dest_stack < 0 or dest_stack >= len(state.stacks):
        return False
    if src_stack == dest_stack:
        return False
    hidden = _normalized_hidden_prefix(state)
    if not _is_valid_sequence(state.stacks[src_stack], hidden[src_stack], src_idx):
        return False

    dest = state.stacks[dest_stack]
    if not dest:
        return True

    src_card_id = state.stacks[src_stack][src_idx]
    dest_top_id = dest[-1]
    return _card_num(dest_top_id) == _card_num(src_card_id) + 1


def _free_once(stack: StackAtom, hidden_prefix: int) -> tuple[StackAtom, int, bool, int]:
    if len(stack) < Card.NUM_PER_SUIT:
        return stack, hidden_prefix, False, 0
    # If top 13 contains hidden cards, cannot auto-free.
    if len(stack) - Card.NUM_PER_SUIT < hidden_prefix:
        return stack, hidden_prefix, False, 0

    suit = _card_suit(stack[-1])
    for i in range(Card.NUM_PER_SUIT):
        card_id = stack[len(stack) - i - 1]
        if _card_suit(card_id) != suit or _card_num(card_id) != i:
            return stack, hidden_prefix, False, 0

    new_stack = stack[: len(stack) - Card.NUM_PER_SUIT]
    new_hidden_prefix = min(hidden_prefix, len(new_stack))
    revealed = 0
    if len(new_stack) > 0 and new_hidden_prefix >= len(new_stack):
        new_hidden_prefix = len(new_stack) - 1
        revealed = 1
    return new_stack, new_hidden_prefix, True, revealed


def _auto_free_all(
    stacks: tuple[StackAtom, ...],
    hidden_prefix: tuple[int, ...],
    finished_count: int,
) -> tuple[tuple[StackAtom, ...], tuple[int, ...], int, int, int]:
    """Apply free repeatedly across all stacks until stable."""

    out = list(stacks)
    hidden = list(hidden_prefix)
    freed_total = 0
    revealed_total = 0
    changed = True
    while changed:
        changed = False
        for idx in range(len(out)):
            new_stack, new_hidden_prefix, did_free, revealed = _free_once(out[idx], hidden[idx])
            if not did_free:
                continue
            changed = True
            freed_total += 1
            finished_count += 1
            out[idx] = new_stack
            hidden[idx] = new_hidden_prefix
            revealed_total += revealed

    return tuple(out), tuple(hidden), finished_count, freed_total, revealed_total


def _ordered_links(stack: StackAtom) -> tuple[int, int]:
    same_suit = 0
    any_suit = 0
    for i in range(1, len(stack)):
        lower = stack[i - 1]
        upper = stack[i]
        if _card_num(lower) == _card_num(upper) + 1:
            any_suit += 1
            if _card_suit(lower) == _card_suit(upper):
                same_suit += 1
    return same_suit, any_suit


def _state_potential(state: SolverState) -> int:
    empty_cols = 0
    same_suit_links = 0
    any_suit_links = 0
    breakpoints = 0

    for stack in state.stacks:
        if not stack:
            empty_cols += 1
            continue
        ss, aa = _ordered_links(stack)
        same_suit_links += ss
        any_suit_links += aa
        breakpoints += max(0, len(stack) - 1 - aa)

    return (
        state.finished_count * 400
        - len(state.base) * 5
        + empty_cols * 12
        + same_suit_links * 5
        + any_suit_links * 2
        - breakpoints
    )


def _move_priority(
    state: SolverState,
    src_stack: int,
    src_idx: int,
    dest_stack: int,
    moved_len: int,
    freed: int,
) -> int:
    src = state.stacks[src_stack]
    dst = state.stacks[dest_stack]
    src_card = src[src_idx]

    score = 40 + moved_len * 3 + freed * 150

    if not dst:
        score -= 18
        if moved_len <= 2:
            score -= 10
    else:
        dst_top = dst[-1]
        if _card_suit(dst_top) == _card_suit(src_card):
            score += 14

    if src_idx > 0:
        below = src[src_idx - 1]
        if _card_suit(below) == _card_suit(src_card) and _card_num(below) == _card_num(src_card) + 1:
            score -= 12

    if moved_len >= 6:
        score += 10

    if src_idx == 0:
        score += 6

    return score


def _is_immediate_reverse(
    state: SolverState,
    last_action: Optional[Action],
    src_stack: int,
    src_idx: int,
    dest_stack: int,
    moved_len: int,
) -> bool:
    if last_action is None:
        return False
    if last_action.kind != "MOVE":
        return False
    if src_stack != last_action.dest_stack or dest_stack != last_action.src_stack:
        return False
    if moved_len != last_action.moved_len:
        return False
    expected_src_idx = len(state.stacks[src_stack]) - moved_len
    return src_idx == expected_src_idx


def _splits_same_suit_run(stack: StackAtom, hidden_prefix: int, idx: int) -> bool:
    if idx <= 0:
        return False
    # If the lower card is hidden, this is not a movable run split.
    if idx - 1 < hidden_prefix:
        return False
    below = stack[idx - 1]
    cur = stack[idx]
    return _card_suit(below) == _card_suit(cur) and _card_num(below) == _card_num(cur) + 1


def _legal_destinations(state: SolverState, src_stack: int, src_idx: int) -> list[int]:
    dests: list[int] = []
    stacks = state.stacks
    src_card_id = stacks[src_stack][src_idx]
    src_num = _card_num(src_card_id)
    for d_idx in range(len(stacks)):
        if d_idx == src_stack:
            continue
        dest = stacks[d_idx]
        if not dest or _card_num(dest[-1]) == src_num + 1:
            dests.append(d_idx)
    return dests


def _filter_destinations_by_policy(
    state: SolverState,
    src_stack: int,
    src_idx: int,
    dests: list[int],
    moved_len: int,
    policy: SearchPolicy,
) -> list[int]:
    if not dests:
        return dests

    src_card = state.stacks[src_stack][src_idx]
    filtered = dests

    if policy.require_same_suit_destination_when_available:
        same_suit = []
        for d_idx in filtered:
            dst = state.stacks[d_idx]
            if not dst:
                continue
            top = dst[-1]
            if _card_suit(top) == _card_suit(src_card):
                same_suit.append(d_idx)
        if same_suit:
            filtered = same_suit

    if policy.avoid_empty_for_short_moves and moved_len < policy.min_len_for_empty_move:
        non_empty = [d for d in filtered if len(state.stacks[d]) > 0]
        if non_empty:
            filtered = non_empty

    return filtered


def _apply_move(state: SolverState, src_stack: int, src_idx: int, dest_stack: int) -> _Transition:
    stacks = list(state.stacks)
    hidden = list(_normalized_hidden_prefix(state))

    src_original = stacks[src_stack]
    moving = src_original[src_idx:]
    moved_len = len(moving)
    dest_original = stacks[dest_stack]

    new_src = src_original[:src_idx]
    hidden[src_stack] = min(hidden[src_stack], len(new_src))
    revealed = 0
    if len(new_src) > 0 and hidden[src_stack] >= len(new_src):
        hidden[src_stack] = len(new_src) - 1
        revealed = 1
    new_dest = dest_original + moving
    hidden[dest_stack] = min(hidden[dest_stack], len(new_dest))

    new_dest, new_dest_hidden_prefix, did_free, free_revealed = _free_once(new_dest, hidden[dest_stack])
    freed = 1 if did_free else 0
    revealed += free_revealed
    finished_count = state.finished_count + freed
    stacks[src_stack] = new_src
    stacks[dest_stack] = new_dest
    hidden[dest_stack] = new_dest_hidden_prefix

    out_state = SolverState(
        base=state.base,
        stacks=tuple(stacks),
        hidden_prefix=tuple(hidden),
        finished_count=finished_count,
    )

    priority = _move_priority(state, src_stack, src_idx, dest_stack, moved_len, freed)
    action = Action(
        kind="MOVE",
        src_stack=src_stack,
        src_idx=src_idx,
        dest_stack=dest_stack,
        moved_len=moved_len,
    )
    return _Transition(action=action, state=out_state, revealed=revealed, freed=freed, priority=priority, macro_steps=0)


def _apply_deal(state: SolverState) -> Optional[_Transition]:
    stack_count = len(state.stacks)
    draw_count = min(stack_count, len(state.base))
    if draw_count <= 0:
        return None

    base = list(state.base)
    stacks = [list(stack) for stack in state.stacks]
    hidden = list(_normalized_hidden_prefix(state))

    dest = 0
    pending = draw_count
    while pending > 0:
        card_id = base.pop()
        stacks[dest].append(card_id)
        hidden[dest] = min(hidden[dest], len(stacks[dest]) - 1)
        dest += 1
        if dest >= stack_count:
            dest = 0
        pending -= 1

    stacks_tuple = tuple(tuple(stack) for stack in stacks)
    hidden_tuple = tuple(hidden)
    stacks_tuple, hidden_tuple, finished_count, freed, revealed = _auto_free_all(stacks_tuple, hidden_tuple, state.finished_count)

    out_state = SolverState(base=tuple(base), stacks=stacks_tuple, hidden_prefix=hidden_tuple, finished_count=finished_count)
    action = Action(kind="DEAL", draw_count=draw_count)
    priority = -15 + freed * 140
    return _Transition(action=action, state=out_state, revealed=revealed, freed=freed, priority=priority, macro_steps=0)


def _pick_macro_follow_up(
    state: SolverState,
    policy: SearchPolicy,
    last_action: Optional[Action],
) -> Optional[_Transition]:
    best: Optional[_Transition] = None
    hidden = _normalized_hidden_prefix(state)

    for s_idx, stack in enumerate(state.stacks):
        for idx in _valid_move_starts(stack, hidden[s_idx]):
            if policy.lock_same_suit_runs and _splits_same_suit_run(stack, hidden[s_idx], idx):
                continue

            moved_len = len(stack) - idx
            src_card = stack[idx]
            for d_idx in _legal_destinations(state, s_idx, idx):
                dst = state.stacks[d_idx]
                if not dst:
                    continue
                if _card_suit(dst[-1]) != _card_suit(src_card):
                    continue
                if policy.taboo_immediate_reverse and _is_immediate_reverse(
                    state, last_action, s_idx, idx, d_idx, moved_len
                ):
                    continue
                tr = _apply_move(state, s_idx, idx, d_idx)
                tr = _Transition(
                    action=tr.action,
                    state=tr.state,
                    revealed=tr.revealed,
                    freed=tr.freed,
                    priority=tr.priority + 20,
                    macro_steps=tr.macro_steps,
                )
                if best is None or tr.priority > best.priority:
                    best = tr

    if best is not None:
        return best

    if not policy.macro_empty_restore_enabled:
        return None

    for s_idx, stack in enumerate(state.stacks):
        for idx in _valid_move_starts(stack, hidden[s_idx]):
            moved_len = len(stack) - idx
            if moved_len < policy.macro_empty_restore_min_len:
                continue
            for d_idx in _legal_destinations(state, s_idx, idx):
                if len(state.stacks[d_idx]) > 0:
                    continue
                if policy.taboo_immediate_reverse and _is_immediate_reverse(
                    state, last_action, s_idx, idx, d_idx, moved_len
                ):
                    continue
                tr = _apply_move(state, s_idx, idx, d_idx)
                tr = _Transition(
                    action=tr.action,
                    state=tr.state,
                    revealed=tr.revealed,
                    freed=tr.freed,
                    priority=tr.priority - 10,
                    macro_steps=tr.macro_steps,
                )
                if best is None or tr.priority > best.priority:
                    best = tr
    return best


def _apply_macro_chain(
    state: SolverState,
    policy: SearchPolicy,
    seed_action: Optional[Action],
) -> tuple[SolverState, int, int]:
    if not policy.macro_chain_enabled or policy.macro_max_steps <= 0:
        return state, 0, 0

    cur = state
    last_action = seed_action
    freed_total = 0
    steps = 0
    local_seen = {_canonical_state_key(cur)}

    while steps < policy.macro_max_steps:
        tr = _pick_macro_follow_up(cur, policy, last_action)
        if tr is None:
            break
        key = _canonical_state_key(tr.state)
        if key in local_seen:
            break
        local_seen.add(key)
        cur = tr.state
        freed_total += tr.freed
        steps += 1
        last_action = tr.action

    return cur, freed_total, steps


def _iter_transitions(
    state: SolverState,
    policy: SearchPolicy = DEFAULT_POLICY,
    last_action: Optional[Action] = None,
) -> list[_Transition]:
    best_by_key: dict[StateKey, _Transition] = {}
    generated_move_count = 0
    hidden = _normalized_hidden_prefix(state)

    for s_idx, stack in enumerate(state.stacks):
        for idx in _valid_move_starts(stack, hidden[s_idx]):
            if policy.lock_same_suit_runs and _splits_same_suit_run(stack, hidden[s_idx], idx):
                continue

            moved_len = len(stack) - idx
            dests = _legal_destinations(state, s_idx, idx)
            dests = _filter_destinations_by_policy(state, s_idx, idx, dests, moved_len, policy)

            used_empty_dest = False
            for d_idx in dests:
                if policy.taboo_immediate_reverse and _is_immediate_reverse(
                    state, last_action, s_idx, idx, d_idx, moved_len
                ):
                    continue
                if policy.limit_empty_destinations_per_move and len(state.stacks[d_idx]) == 0:
                    if used_empty_dest:
                        continue
                    used_empty_dest = True
                tr = _apply_move(state, s_idx, idx, d_idx)
                macro_state, macro_freed, macro_steps = _apply_macro_chain(tr.state, policy, tr.action)
                if macro_steps > 0:
                    tr = _Transition(
                        action=tr.action,
                        state=macro_state,
                        revealed=tr.revealed,
                        freed=tr.freed + macro_freed,
                        priority=tr.priority + macro_steps * 18 + macro_freed * 80,
                        macro_steps=macro_steps,
                    )
                key = _canonical_state_key(tr.state)
                tr = _Transition(
                    action=tr.action,
                    state=tr.state,
                    revealed=tr.revealed,
                    freed=tr.freed,
                    priority=tr.priority,
                    macro_steps=tr.macro_steps,
                    state_key=key,
                )
                prev = best_by_key.get(key)
                if prev is None or tr.priority > prev.priority:
                    best_by_key[key] = tr
                generated_move_count += 1

    allow_deal = True
    if policy.defer_deal_until_no_moves and generated_move_count > 0:
        allow_deal = False
    if allow_deal:
        deal_transition = _apply_deal(state)
        if deal_transition is not None:
            macro_state, macro_freed, macro_steps = _apply_macro_chain(deal_transition.state, policy, deal_transition.action)
            if macro_steps > 0:
                deal_transition = _Transition(
                    action=deal_transition.action,
                    state=macro_state,
                    revealed=deal_transition.revealed,
                    freed=deal_transition.freed + macro_freed,
                    priority=deal_transition.priority + macro_steps * 18 + macro_freed * 80,
                    macro_steps=macro_steps,
                )
            key = _canonical_state_key(deal_transition.state)
            deal_transition = _Transition(
                action=deal_transition.action,
                state=deal_transition.state,
                revealed=deal_transition.revealed,
                freed=deal_transition.freed,
                priority=deal_transition.priority,
                macro_steps=deal_transition.macro_steps,
                state_key=key,
            )
            prev = best_by_key.get(key)
            if prev is None or deal_transition.priority > prev.priority:
                best_by_key[key] = deal_transition

    transitions = list(best_by_key.values())
    transitions.sort(key=lambda t: t.priority, reverse=True)
    return transitions


def _policy_is_complete(policy: SearchPolicy) -> bool:
    return not (
        policy.lock_same_suit_runs
        or policy.require_same_suit_destination_when_available
        or policy.avoid_empty_for_short_moves
        or policy.defer_deal_until_no_moves
    )


def _build_stage_plan(suits: Optional[int]) -> tuple[SearchStage, ...]:
    strict = DEFAULT_POLICY
    balanced = replace(
        DEFAULT_POLICY,
        lock_same_suit_runs=False,
        macro_max_steps=3,
    )
    wide = replace(
        DEFAULT_POLICY,
        lock_same_suit_runs=False,
        require_same_suit_destination_when_available=False,
        avoid_empty_for_short_moves=False,
        defer_deal_until_no_moves=False,
        macro_chain_enabled=False,
        taboo_immediate_reverse=False,
    )

    if suits == 1:
        return (
            SearchStage("strict", strict, 0.55, 0.50),
            SearchStage("balanced", balanced, 0.45, 0.50),
        )
    if suits == 2:
        return (
            SearchStage("strict", strict, 0.40, 0.35),
            SearchStage("balanced", balanced, 0.35, 0.35),
            SearchStage("wide", wide, 0.25, 0.30),
        )
    return (
        SearchStage("strict", strict, 0.30, 0.25),
        SearchStage("balanced", balanced, 0.35, 0.35),
        SearchStage("wide", wide, 0.35, 0.40),
    )


def _allocate_stage_limits(base: SearchLimits, stage: SearchStage) -> SearchLimits:
    return SearchLimits(
        max_nodes=max(2_000, int(base.max_nodes * stage.node_share)),
        max_seconds=max(0.05, base.max_seconds * stage.time_share),
        max_frontier=max(10_000, int(base.max_frontier * stage.frontier_share)),
    )


def _run_staged_search(
    initial_state: SolverState,
    limits: SearchLimits,
    suits: Optional[int],
) -> tuple[SolveResult, list[dict], str]:
    stages = _build_stage_plan(suits)
    stage_details: list[dict] = []
    final_result: Optional[SolveResult] = None
    final_stage = stages[-1].name
    totals = {
        "expanded_nodes": 0,
        "generated_nodes": 0,
        "unique_states": 0,
        "dead_end_nodes": 0,
        "duplicate_states_skipped": 0,
        "elapsed_ms": 0.0,
        "max_frontier": 0,
        "max_depth": 0,
        "weighted_branching_num": 0.0,
        "weighted_branching_den": 0,
    }

    for stage in stages:
        stage_limits = _allocate_stage_limits(limits, stage)
        result = solve_state(initial_state, limits=stage_limits, policy=stage.policy)
        stage_details.append(
            {
                "name": stage.name,
                "status": result.status,
                "reason": result.stop_reason,
                "elapsed_ms": round(result.elapsed_ms, 3),
                "expanded_nodes": result.expanded_nodes,
                "generated_nodes": result.generated_nodes,
                "unique_states": result.unique_states,
                "duplicates": result.duplicate_states_skipped,
                "max_frontier": result.max_frontier,
            }
        )
        totals["expanded_nodes"] += result.expanded_nodes
        totals["generated_nodes"] += result.generated_nodes
        totals["unique_states"] += result.unique_states
        totals["dead_end_nodes"] += result.dead_end_nodes
        totals["duplicate_states_skipped"] += result.duplicate_states_skipped
        totals["elapsed_ms"] += result.elapsed_ms
        totals["max_frontier"] = max(totals["max_frontier"], result.max_frontier)
        totals["max_depth"] = max(totals["max_depth"], result.max_depth)
        totals["weighted_branching_num"] += result.avg_branching * max(1, result.expanded_nodes)
        totals["weighted_branching_den"] += max(1, result.expanded_nodes)
        final_result = result
        final_stage = stage.name
        if result.status in ("solved", "proven_unsolvable"):
            break

    assert final_result is not None
    merged = SolveResult(
        status=final_result.status,
        stop_reason=final_result.stop_reason,
        solution=final_result.solution,
        solution_states=final_result.solution_states,
        expanded_nodes=totals["expanded_nodes"],
        generated_nodes=totals["generated_nodes"],
        unique_states=totals["unique_states"],
        max_frontier=totals["max_frontier"],
        dead_end_nodes=totals["dead_end_nodes"],
        duplicate_states_skipped=totals["duplicate_states_skipped"],
        avg_branching=totals["weighted_branching_num"] / max(1, totals["weighted_branching_den"]),
        elapsed_ms=totals["elapsed_ms"],
        max_depth=totals["max_depth"],
        solution_revealed=final_result.solution_revealed,
        solution_freed=final_result.solution_freed,
        solution_deals=final_result.solution_deals,
    )
    return merged, stage_details, final_stage


def _reconstruct(
    goal: SolverState,
    parent: dict[SolverState, tuple[Optional[SolverState], Optional[_Transition]]],
) -> tuple[tuple[Action, ...], tuple[SolverState, ...], int, int, int]:
    actions: list[Action] = []
    states: list[SolverState] = [goal]
    revealed = 0
    freed = 0
    deals = 0

    cur = goal
    while True:
        prev, tr = parent[cur]
        if prev is None or tr is None:
            break
        actions.append(tr.action)
        states.append(prev)
        revealed += tr.revealed
        freed += tr.freed
        if tr.action.kind == "DEAL":
            deals += 1
        cur = prev

    actions.reverse()
    states.reverse()
    return tuple(actions), tuple(states), revealed, freed, deals


def solve_state(
    initial_state: SolverState,
    limits: SearchLimits = SearchLimits(),
    policy: SearchPolicy = DEFAULT_POLICY,
) -> SolveResult:
    """Search for a solution with strict duplicate-state elimination."""

    start = time.perf_counter()

    if _is_goal(initial_state):
        return SolveResult(
            status="solved",
            stop_reason="goal_reached",
            solution=(),
            solution_states=(initial_state,),
            expanded_nodes=0,
            generated_nodes=1,
            unique_states=1,
            max_frontier=1,
            dead_end_nodes=0,
            duplicate_states_skipped=0,
            avg_branching=0.0,
            elapsed_ms=0.0,
            max_depth=0,
            solution_revealed=0,
            solution_freed=0,
            solution_deals=0,
        )

    counter = 0
    parent: dict[SolverState, tuple[Optional[SolverState], Optional[_Transition]]] = {initial_state: (None, None)}
    seen_keys: set[StateKey] = {_canonical_state_key(initial_state)}

    frontier: list[tuple[int, int, int, SolverState]] = []
    initial_prio = -_state_potential(initial_state)
    heapq.heappush(frontier, (initial_prio, counter, 0, initial_state))

    expanded = 0
    generated = 1
    max_frontier = 1
    dead_end = 0
    duplicates = 0
    max_depth = 0
    total_branching = 0
    hit_limits = False

    while frontier:
        if expanded >= limits.max_nodes:
            hit_limits = True
            break
        if (time.perf_counter() - start) >= limits.max_seconds:
            hit_limits = True
            break
        if len(frontier) > limits.max_frontier:
            hit_limits = True
            break

        _, _, depth, state = heapq.heappop(frontier)

        if _is_goal(state):
            solution, solution_states, revealed, freed, deals = _reconstruct(state, parent)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return SolveResult(
                status="solved",
                stop_reason="goal_reached",
                solution=solution,
                solution_states=solution_states,
                expanded_nodes=expanded,
                generated_nodes=generated,
                unique_states=len(seen_keys),
                max_frontier=max_frontier,
                dead_end_nodes=dead_end,
                duplicate_states_skipped=duplicates,
                avg_branching=(total_branching / expanded) if expanded > 0 else 0.0,
                elapsed_ms=elapsed_ms,
                max_depth=max_depth,
                solution_revealed=revealed,
                solution_freed=freed,
                solution_deals=deals,
            )

        incoming = parent[state][1].action if parent[state][1] is not None else None
        transitions = _iter_transitions(state, policy=policy, last_action=incoming)
        expanded += 1
        total_branching += len(transitions)

        if not transitions:
            dead_end += 1
            continue

        for tr in transitions:
            key = tr.state_key if tr.state_key is not None else _canonical_state_key(tr.state)
            if key in seen_keys:
                duplicates += 1
                continue

            seen_keys.add(key)
            parent[tr.state] = (state, tr)
            next_depth = depth + 1
            max_depth = max(max_depth, next_depth)

            counter += 1
            prio = next_depth * 4 - _state_potential(tr.state) - tr.priority
            heapq.heappush(frontier, (prio, counter, next_depth, tr.state))
            generated += 1

        if len(frontier) > max_frontier:
            max_frontier = len(frontier)

    if hit_limits:
        status = "unknown"
        stop_reason = "limits_reached"
    else:
        if _policy_is_complete(policy):
            status = "proven_unsolvable"
            stop_reason = "search_space_exhausted"
        else:
            status = "unknown"
            stop_reason = "policy_space_exhausted"
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return SolveResult(
        status=status,
        stop_reason=stop_reason,
        solution=(),
        solution_states=(),
        expanded_nodes=expanded,
        generated_nodes=generated,
        unique_states=len(seen_keys),
        max_frontier=max_frontier,
        dead_end_nodes=dead_end,
        duplicate_states_skipped=duplicates,
        avg_branching=(total_branching / expanded) if expanded > 0 else 0.0,
        elapsed_ms=elapsed_ms,
        max_depth=max_depth,
        solution_revealed=0,
        solution_freed=0,
        solution_deals=0,
    )


def _count_legal_actions(state: SolverState) -> int:
    total = 0
    stacks = state.stacks
    hidden = _normalized_hidden_prefix(state)
    for s_idx, stack in enumerate(stacks):
        for idx in _valid_move_starts(stack, hidden[s_idx]):
            src_num = _card_num(stack[idx])
            for d_idx, dest in enumerate(stacks):
                if d_idx == s_idx:
                    continue
                if not dest or _card_num(dest[-1]) == src_num + 1:
                    total += 1
    if state.base:
        total += 1
    return total


def _difficulty_band(score: float) -> str:
    if score < 80_000.0:
        return "Easy"
    if score < 220_000.0:
        return "Medium"
    return "Hard"


def analyze_state(
    initial_state: SolverState,
    suits: Optional[int] = None,
    seed: Optional[int] = None,
    limits: SearchLimits = SearchLimits(),
    policy: SearchPolicy = DEFAULT_POLICY,
    staged: bool = True,
) -> AnalyzeResult:
    """Run solver and estimate difficulty from search metrics."""

    if staged:
        solved, stage_details, final_stage = _run_staged_search(initial_state, limits, suits)
    else:
        solved = solve_state(initial_state, limits, policy=policy)
        stage_details = [
            {
                "name": "single",
                "status": solved.status,
                "reason": solved.stop_reason,
                "elapsed_ms": round(solved.elapsed_ms, 3),
                "expanded_nodes": solved.expanded_nodes,
                "generated_nodes": solved.generated_nodes,
                "unique_states": solved.unique_states,
                "duplicates": solved.duplicate_states_skipped,
                "max_frontier": solved.max_frontier,
            }
        ]
        final_stage = "single"

    metrics = {
        "expanded_nodes": solved.expanded_nodes,
        "generated_nodes": solved.generated_nodes,
        "unique_states": solved.unique_states,
        "duplicate_states_skipped": solved.duplicate_states_skipped,
        "max_frontier": solved.max_frontier,
        "dead_end_nodes": solved.dead_end_nodes,
        "avg_branching": round(solved.avg_branching, 4),
        "elapsed_ms": round(solved.elapsed_ms, 3),
        "max_depth": solved.max_depth,
        "final_stage": final_stage,
        "stages": stage_details,
    }

    if solved.status == "solved":
        legal_counts = [_count_legal_actions(state) for state in solved.solution_states[:-1]]
        if legal_counts:
            avg_legal = sum(legal_counts) / len(legal_counts)
            forced_ratio = sum(1 for n in legal_counts if n == 1) / len(legal_counts)
        else:
            avg_legal = 0.0
            forced_ratio = 1.0

        dead_ratio = solved.dead_end_nodes / max(1, solved.expanded_nodes)
        choice_pressure = 1.0 / max(1.0, avg_legal)
        suit_factor = max(1, suits or 1) - 1
        expanded_nodes = float(solved.expanded_nodes)
        solution_len = float(len(solved.solution))
        forced_pct = forced_ratio * 100.0
        dead_pct = dead_ratio * 100.0
        pressure_pct = choice_pressure * 100.0
        branching = float(solved.avg_branching)
        deal_count = float(solved.solution_deals)

        # Keep score as a large raw value; downstream bucketing uses quantiles.
        score = (
            expanded_nodes
            + 420.0 * solution_len
            + 9_000.0 * deal_count
            + 1_600.0 * branching
            + 2_600.0 * forced_pct
            + 1_800.0 * dead_pct
            + 1_200.0 * pressure_pct
            + 15_000.0 * suit_factor
        )
        score = max(0.0, score)
        band = _difficulty_band(score)

        metrics.update(
            {
                "solution_len": len(solved.solution),
                "solution_revealed": solved.solution_revealed,
                "solution_freed": solved.solution_freed,
                "solution_deals": solved.solution_deals,
                "avg_legal_on_path": round(avg_legal, 4),
                "forced_ratio": round(forced_ratio, 4),
                "dead_end_ratio": round(dead_ratio, 4),
                "difficulty_components": {
                    "expanded_nodes": round(expanded_nodes, 3),
                    "solution_len": round(solution_len, 3),
                    "deal_count": round(deal_count, 3),
                    "avg_branching": round(branching, 4),
                    "forced_pct": round(forced_pct, 4),
                    "dead_pct": round(dead_pct, 4),
                    "pressure_pct": round(pressure_pct, 4),
                    "suit_factor": round(suit_factor, 4),
                },
            }
        )

        return AnalyzeResult(
            seed=seed,
            suits=suits,
            status="solved",
            solvable=True,
            proven=False,
            difficulty_score=round(score, 3),
            difficulty_band=band,
            metrics=metrics,
            solution=tuple(action.to_notation() for action in solved.solution),
        )

    if solved.status == "proven_unsolvable":
        metrics["reason"] = solved.stop_reason
        return AnalyzeResult(
            seed=seed,
            suits=suits,
            status="proven_unsolvable",
            solvable=False,
            proven=True,
            difficulty_score=100.0,
            difficulty_band="Unsolvable",
            metrics=metrics,
            solution=(),
        )

    metrics["reason"] = solved.stop_reason
    effort = min(
        100.0,
        100.0
        * (
            0.70 * min(1.0, math.log1p(solved.expanded_nodes) / math.log1p(max(2_000, limits.max_nodes)))
            + 0.30 * min(1.0, solved.elapsed_ms / max(1.0, limits.max_seconds * 1000.0))
        ),
    )
    metrics["effort_score"] = round(effort, 3)
    return AnalyzeResult(
        seed=seed,
        suits=suits,
        status="unknown",
        solvable=None,
        proven=False,
        difficulty_score=None,
        difficulty_band=None,
        metrics=metrics,
        solution=(),
    )


def analyze_seed(
    seed: int,
    suits: int = 4,
    limits: SearchLimits = SearchLimits(),
    policy: SearchPolicy = DEFAULT_POLICY,
    staged: bool = True,
) -> AnalyzeResult:
    cfg = GameConfig()
    cfg.seed = seed
    cfg.suits = suits
    state = build_initial_state(cfg)
    return analyze_state(initial_state=state, suits=suits, seed=seed, limits=limits, policy=policy, staged=staged)


def analyze_seeds(
    seeds: Iterable[int],
    suits: int = 4,
    limits: SearchLimits = SearchLimits(),
    policy: SearchPolicy = DEFAULT_POLICY,
    staged: bool = True,
) -> list[AnalyzeResult]:
    return [analyze_seed(seed=seed, suits=suits, limits=limits, policy=policy, staged=staged) for seed in seeds]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Spider seed solvability and difficulty.")
    parser.add_argument("--seed", type=int, action="append", required=True, help="Seed to analyze; can be repeated.")
    parser.add_argument("--suits", type=int, choices=(1, 2, 3, 4), default=4, help="Suit count.")
    parser.add_argument("--max-nodes", type=int, default=200_000, help="Search node limit.")
    parser.add_argument("--max-seconds", type=float, default=2.0, help="Search time limit in seconds.")
    parser.add_argument("--max-frontier", type=int, default=500_000, help="Search frontier size limit.")
    parser.add_argument("--single-stage", action="store_true", help="Disable staged widening search.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print json output.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    limits = SearchLimits(max_nodes=args.max_nodes, max_seconds=args.max_seconds, max_frontier=args.max_frontier)
    results = analyze_seeds(
        args.seed,
        suits=args.suits,
        limits=limits,
        policy=DEFAULT_POLICY,
        staged=not args.single_stage,
    )

    payload = [result.to_dict() for result in results]
    if len(payload) == 1:
        payload = payload[0]

    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
