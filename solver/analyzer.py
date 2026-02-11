from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from base.Core import Card, GameConfig

CardAtom = tuple[int, bool]
StackAtom = tuple[CardAtom, ...]


@dataclass(frozen=True, slots=True)
class SolverState:
    """Immutable spider state used by the solver."""

    base: tuple[int, ...]
    stacks: tuple[StackAtom, ...]
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


@dataclass(slots=True)
class SolveResult:
    status: str
    solution: tuple[Action, ...]
    solution_states: tuple[SolverState, ...]
    expanded_nodes: int
    generated_nodes: int
    unique_states: int
    max_frontier: int
    dead_end_nodes: int
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


def _card_suit(card_id: int) -> int:
    return card_id // Card.NUM_PER_SUIT


def _card_num(card_id: int) -> int:
    return card_id % Card.NUM_PER_SUIT


def _is_goal(state: SolverState) -> bool:
    if state.base:
        return False
    return all(len(stack) == 0 for stack in state.stacks)


def build_initial_state(config: GameConfig) -> SolverState:
    """Build the same initial state as Core.startGame() for a config."""

    base_cards = config.initBase()
    stacks: list[list[CardAtom]] = [[] for _ in range(config.stackCount)]

    draw_count = min(config.initialDealt, len(base_cards))
    dest = 0
    while draw_count > 0:
        card = base_cards.pop()
        stacks[dest].append((card.id, card.hidden))
        dest += 1
        if dest >= len(stacks):
            dest = 0
        draw_count -= 1

    for stack in stacks:
        if not stack:
            continue
        card_id, _ = stack[-1]
        stack[-1] = (card_id, False)

    base = tuple(card.id for card in base_cards)
    return SolverState(base=base, stacks=tuple(tuple(stack) for stack in stacks), finished_count=0)


def _is_valid_sequence(stack: StackAtom, idx: int) -> bool:
    if idx < 0 or idx >= len(stack):
        return False
    base_id, base_hidden = stack[idx]
    if base_hidden:
        return False
    prev_id = base_id
    for i in range(idx + 1, len(stack)):
        upper_id, _ = stack[i]
        if not (_card_suit(prev_id) == _card_suit(upper_id) and _card_num(prev_id) == _card_num(upper_id) + 1):
            return False
        prev_id = upper_id
    return True


def _can_move(state: SolverState, src_stack: int, src_idx: int, dest_stack: int) -> bool:
    if src_stack < 0 or src_stack >= len(state.stacks):
        return False
    if dest_stack < 0 or dest_stack >= len(state.stacks):
        return False
    if src_stack == dest_stack:
        return False
    if not _is_valid_sequence(state.stacks[src_stack], src_idx):
        return False

    dest = state.stacks[dest_stack]
    if not dest:
        return True

    src_card_id, _ = state.stacks[src_stack][src_idx]
    dest_top_id, _ = dest[-1]
    return _card_num(dest_top_id) == _card_num(src_card_id) + 1


def _reveal_top(stack: StackAtom) -> tuple[StackAtom, bool]:
    if not stack:
        return stack, False
    card_id, hidden = stack[-1]
    if not hidden:
        return stack, False
    out = list(stack)
    out[-1] = (card_id, False)
    return tuple(out), True


def _free_once(stack: StackAtom) -> tuple[StackAtom, bool]:
    if len(stack) < Card.NUM_PER_SUIT:
        return stack, False

    suit = _card_suit(stack[-1][0])
    for i in range(Card.NUM_PER_SUIT):
        card_id, _ = stack[len(stack) - i - 1]
        if _card_suit(card_id) != suit or _card_num(card_id) != i:
            return stack, False

    return stack[: len(stack) - Card.NUM_PER_SUIT], True


def _auto_free_all(stacks: tuple[StackAtom, ...], finished_count: int) -> tuple[tuple[StackAtom, ...], int, int, int]:
    """Apply free/reveal repeatedly across all stacks until stable."""

    out = list(stacks)
    freed_total = 0
    revealed_total = 0
    done = False
    while not done:
        done = True
        for idx in range(len(out)):
            new_stack, did_free = _free_once(out[idx])
            if not did_free:
                continue
            done = False
            freed_total += 1
            finished_count += 1
            new_stack, did_reveal = _reveal_top(new_stack)
            if did_reveal:
                revealed_total += 1
            out[idx] = new_stack

    return tuple(out), finished_count, freed_total, revealed_total


def _state_potential(state: SolverState) -> int:
    hidden_count = 0
    same_suit_links = 0
    empty_cols = 0

    for stack in state.stacks:
        if not stack:
            empty_cols += 1
            continue
        hidden_count += sum(1 for _, hidden in stack if hidden)
        for i in range(1, len(stack)):
            lower_id, lower_hidden = stack[i - 1]
            upper_id, upper_hidden = stack[i]
            if lower_hidden or upper_hidden:
                continue
            if _card_suit(lower_id) == _card_suit(upper_id) and _card_num(lower_id) == _card_num(upper_id) + 1:
                same_suit_links += 1

    return (
        state.finished_count * 260
        - hidden_count * 6
        - len(state.base) * 4
        + empty_cols * 3
        + same_suit_links * 2
    )


def _apply_move(state: SolverState, src_stack: int, src_idx: int, dest_stack: int) -> _Transition:
    stacks = [list(stack) for stack in state.stacks]

    src_original = state.stacks[src_stack]
    dest_original = state.stacks[dest_stack]

    moving = src_original[src_idx:]
    moved_len = len(moving)
    src_card_id, _ = moving[0]

    stacks[src_stack] = list(src_original[:src_idx])
    stacks[dest_stack] = list(dest_original) + list(moving)

    reveal_bonus = 0
    if src_idx > 0 and src_original[src_idx - 1][1]:
        reveal_bonus = 40

    revealed = 0
    if stacks[src_stack]:
        top_id, top_hidden = stacks[src_stack][-1]
        if top_hidden:
            stacks[src_stack][-1] = (top_id, False)
            revealed += 1

    dest_stack_tuple = tuple(stacks[dest_stack])
    dest_stack_tuple, did_free = _free_once(dest_stack_tuple)
    freed = 1 if did_free else 0
    finished_count = state.finished_count + freed
    stacks[dest_stack] = list(dest_stack_tuple)

    if stacks[dest_stack]:
        top_id, top_hidden = stacks[dest_stack][-1]
        if top_hidden:
            stacks[dest_stack][-1] = (top_id, False)
            revealed += 1

    out_state = SolverState(
        base=state.base,
        stacks=tuple(tuple(stack) for stack in stacks),
        finished_count=finished_count,
    )

    priority = 30 + moved_len * 2 + reveal_bonus + freed * 120
    if not dest_original:
        priority -= 8
        if moved_len <= 2:
            priority -= 4
    else:
        dest_top_id, _ = dest_original[-1]
        if _card_suit(dest_top_id) == _card_suit(src_card_id):
            priority += 5

    action = Action(
        kind="MOVE",
        src_stack=src_stack,
        src_idx=src_idx,
        dest_stack=dest_stack,
        moved_len=moved_len,
    )
    return _Transition(action=action, state=out_state, revealed=revealed, freed=freed, priority=priority)


def _apply_deal(state: SolverState) -> Optional[_Transition]:
    stack_count = len(state.stacks)
    draw_count = min(stack_count, len(state.base))
    if draw_count <= 0:
        return None

    base = list(state.base)
    stacks = [list(stack) for stack in state.stacks]

    dest = 0
    pending = draw_count
    while pending > 0:
        card_id = base.pop()
        stacks[dest].append((card_id, True))
        dest += 1
        if dest >= stack_count:
            dest = 0
        pending -= 1

    revealed = 0
    for idx in range(stack_count):
        if not stacks[idx]:
            continue
        card_id, hidden = stacks[idx][-1]
        if hidden:
            stacks[idx][-1] = (card_id, False)
            revealed += 1

    stacks_tuple = tuple(tuple(stack) for stack in stacks)
    stacks_tuple, finished_count, freed, revealed_more = _auto_free_all(stacks_tuple, state.finished_count)
    revealed += revealed_more

    out_state = SolverState(base=tuple(base), stacks=stacks_tuple, finished_count=finished_count)
    action = Action(kind="DEAL", draw_count=draw_count)

    priority = -15 + freed * 120 + revealed * 3
    return _Transition(action=action, state=out_state, revealed=revealed, freed=freed, priority=priority)


def _iter_transitions(state: SolverState) -> list[_Transition]:
    transitions: list[_Transition] = []

    for s_idx, stack in enumerate(state.stacks):
        for idx in range(len(stack)):
            if not _is_valid_sequence(stack, idx):
                continue
            for d_idx in range(len(state.stacks)):
                if not _can_move(state, s_idx, idx, d_idx):
                    continue
                transitions.append(_apply_move(state, s_idx, idx, d_idx))

    deal_transition = _apply_deal(state)
    if deal_transition is not None:
        transitions.append(deal_transition)

    transitions.sort(key=lambda t: t.priority, reverse=True)
    return transitions


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


def solve_state(initial_state: SolverState, limits: SearchLimits = SearchLimits()) -> SolveResult:
    """Search for a solution; returns solved/proven_unsolvable/unknown."""

    start = time.perf_counter()

    if _is_goal(initial_state):
        return SolveResult(
            status="solved",
            solution=(),
            solution_states=(initial_state,),
            expanded_nodes=0,
            generated_nodes=1,
            unique_states=1,
            max_frontier=1,
            dead_end_nodes=0,
            avg_branching=0.0,
            elapsed_ms=0.0,
            max_depth=0,
            solution_revealed=0,
            solution_freed=0,
            solution_deals=0,
        )

    counter = 0
    g_cost: dict[SolverState, int] = {initial_state: 0}
    parent: dict[SolverState, tuple[Optional[SolverState], Optional[_Transition]]] = {initial_state: (None, None)}

    frontier: list[tuple[int, int, int, SolverState]] = []
    initial_prio = -_state_potential(initial_state)
    heapq.heappush(frontier, (initial_prio, counter, 0, initial_state))

    expanded = 0
    generated = 1
    max_frontier = 1
    dead_end = 0
    max_depth = 0
    total_branching = 0
    status = "unknown"

    while frontier:
        if expanded >= limits.max_nodes:
            status = "unknown"
            break
        if (time.perf_counter() - start) >= limits.max_seconds:
            status = "unknown"
            break
        if len(frontier) > limits.max_frontier:
            status = "unknown"
            break

        _, _, depth, state = heapq.heappop(frontier)
        if depth != g_cost.get(state):
            continue

        if _is_goal(state):
            solution, solution_states, revealed, freed, deals = _reconstruct(state, parent)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return SolveResult(
                status="solved",
                solution=solution,
                solution_states=solution_states,
                expanded_nodes=expanded,
                generated_nodes=generated,
                unique_states=len(g_cost),
                max_frontier=max_frontier,
                dead_end_nodes=dead_end,
                avg_branching=(total_branching / expanded) if expanded > 0 else 0.0,
                elapsed_ms=elapsed_ms,
                max_depth=max_depth,
                solution_revealed=revealed,
                solution_freed=freed,
                solution_deals=deals,
            )

        transitions = _iter_transitions(state)
        expanded += 1
        total_branching += len(transitions)
        max_depth = max(max_depth, depth)

        if not transitions:
            dead_end += 1
            continue

        for tr in transitions:
            new_depth = depth + 1
            old_depth = g_cost.get(tr.state)
            if old_depth is not None and old_depth <= new_depth:
                continue

            g_cost[tr.state] = new_depth
            parent[tr.state] = (state, tr)
            counter += 1
            prio = new_depth * 4 - _state_potential(tr.state) - tr.priority
            heapq.heappush(frontier, (prio, counter, new_depth, tr.state))
            generated += 1

        if len(frontier) > max_frontier:
            max_frontier = len(frontier)

    if not frontier:
        status = "proven_unsolvable"

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return SolveResult(
        status=status,
        solution=(),
        solution_states=(),
        expanded_nodes=expanded,
        generated_nodes=generated,
        unique_states=len(g_cost),
        max_frontier=max_frontier,
        dead_end_nodes=dead_end,
        avg_branching=(total_branching / expanded) if expanded > 0 else 0.0,
        elapsed_ms=elapsed_ms,
        max_depth=max_depth,
        solution_revealed=0,
        solution_freed=0,
        solution_deals=0,
    )


def _count_legal_actions(state: SolverState) -> int:
    total = 0
    for s_idx, stack in enumerate(state.stacks):
        for idx in range(len(stack)):
            if not _is_valid_sequence(stack, idx):
                continue
            for d_idx in range(len(state.stacks)):
                if _can_move(state, s_idx, idx, d_idx):
                    total += 1
    if state.base:
        total += 1
    return total


def _difficulty_band(score: float) -> str:
    if score < 34.0:
        return "Easy"
    if score < 67.0:
        return "Medium"
    return "Hard"


def analyze_state(
    initial_state: SolverState,
    suits: Optional[int] = None,
    seed: Optional[int] = None,
    limits: SearchLimits = SearchLimits(),
) -> AnalyzeResult:
    """Run solver and estimate difficulty from solver/search metrics."""

    solved = solve_state(initial_state, limits)

    metrics = {
        "expanded_nodes": solved.expanded_nodes,
        "generated_nodes": solved.generated_nodes,
        "unique_states": solved.unique_states,
        "max_frontier": solved.max_frontier,
        "dead_end_nodes": solved.dead_end_nodes,
        "avg_branching": round(solved.avg_branching, 4),
        "elapsed_ms": round(solved.elapsed_ms, 3),
        "max_depth": solved.max_depth,
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
        suit_factor = max(0, (suits or 1) - 1)

        raw = (
            9.0 * math.log1p(solved.expanded_nodes)
            + 0.6 * len(solved.solution)
            + 22.0 * dead_ratio
            + 20.0 * choice_pressure
            + 10.0 * forced_ratio
            + 8.0 * solved.solution_deals
            + 4.0 * suit_factor
        )
        score = max(0.0, min(100.0, raw))
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
        metrics["reason"] = "search_space_exhausted"
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

    metrics["reason"] = "limits_reached"
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


def analyze_seed(seed: int, suits: int = 4, limits: SearchLimits = SearchLimits()) -> AnalyzeResult:
    cfg = GameConfig()
    cfg.seed = seed
    cfg.suits = suits
    state = build_initial_state(cfg)
    return analyze_state(initial_state=state, suits=suits, seed=seed, limits=limits)


def analyze_seeds(seeds: Iterable[int], suits: int = 4, limits: SearchLimits = SearchLimits()) -> list[AnalyzeResult]:
    return [analyze_seed(seed=seed, suits=suits, limits=limits) for seed in seeds]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Spider seed solvability and difficulty.")
    parser.add_argument("--seed", type=int, action="append", required=True, help="Seed to analyze; can be repeated.")
    parser.add_argument("--suits", type=int, choices=(1, 2, 4), default=4, help="Suit count.")
    parser.add_argument("--max-nodes", type=int, default=200_000, help="Search node limit.")
    parser.add_argument("--max-seconds", type=float, default=2.0, help="Search time limit in seconds.")
    parser.add_argument("--max-frontier", type=int, default=500_000, help="Search frontier size limit.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print json output.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    limits = SearchLimits(max_nodes=args.max_nodes, max_seconds=args.max_seconds, max_frontier=args.max_frontier)
    results = analyze_seeds(args.seed, suits=args.suits, limits=limits)

    payload = [result.to_dict() for result in results]
    if len(payload) == 1:
        payload = payload[0]

    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
