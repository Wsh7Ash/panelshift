"""Exact phase-balancing solver.

The problem
-----------
A USA-style split-phase panel has two columns (legs) of breaker positions. Each
single-pole circuit draws its full current on one leg. A two-pole circuit spans
both columns and draws its current on *both* legs. Circuits that share a neutral
(a multi-wire branch circuit) must sit on opposite legs.

Choosing a leg for each single-pole circuit so that the two legs are as close as
possible is a constrained two-way partition problem. This module solves it
exactly with a subset-sum dynamic program over (positions used on leg A, load on
leg A), which is enough to prove the imbalance is minimal rather than merely
good. It also reconstructs the assignment, builds a two-column slot layout, and
verifies the result with an independent recomputation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .model import Circuit, PanelPlan


@dataclass(frozen=True)
class Item:
    """One solver decision: a single-pole circuit, or a two-circuit MWBC pair."""

    ids: tuple[str, ...]
    a: int
    b: int | None = None

    @property
    def total(self) -> int:
        return self.a + (self.b or 0)


@dataclass
class Solution:
    feasible: bool
    reasons: list[str]
    leg_of: dict[str, str]
    rows: list[tuple[str | None, str | None]]
    leg_a_ca: int
    leg_b_ca: int
    capacity_ca: int
    base_ca: int
    total_single_ca: int
    positions_per_leg: int
    best_max_leg_ca: int | None
    reachable_states: int
    two_pole_count: int
    item_count: int
    optimal: bool = True

    @property
    def imbalance_ca(self) -> int:
        return abs(self.leg_a_ca - self.leg_b_ca)

    @property
    def max_leg_ca(self) -> int:
        return max(self.leg_a_ca, self.leg_b_ca)


def build_items(circuits: Iterable[Circuit]) -> tuple[list[Item], int, int, int]:
    """Split circuits into solver items.

    Returns (items, two_pole_load, two_pole_count, single_pole_total).
    """

    circuits = list(circuits)
    two = [c for c in circuits if c.poles == 2]
    two_load = sum(c.effective_centiamps for c in two)

    groups: dict[str, list[Circuit]] = {}
    for circuit in circuits:
        if circuit.poles == 1 and circuit.group:
            groups.setdefault(circuit.group, []).append(circuit)

    paired = {c.id for members in groups.values() for c in members}
    items: list[Item] = [
        Item((c.id,), c.effective_centiamps)
        for c in circuits
        if c.poles == 1 and c.id not in paired
    ]
    for group in sorted(groups):
        first, second = groups[group]
        items.append(
            Item(
                (first.id, second.id),
                first.effective_centiamps,
                second.effective_centiamps,
            )
        )

    order = {c.id: index for index, c in enumerate(circuits)}
    items.sort(key=lambda item: order[item.ids[0]])
    single_total = sum(item.total for item in items)
    return items, two_load, len(two), single_total


def _build_dp(items: list[Item]) -> list[int]:
    """dp[c] is a bitmask of achievable leg-A loads using c leg-A positions."""

    dp = [1]
    for item in items:
        new = [0] * (len(dp) + 1)
        for used, mask in enumerate(dp):
            if not mask:
                continue
            if item.b is None:
                new[used] |= mask
                new[used + 1] |= mask << item.a
            else:
                new[used + 1] |= (mask << item.a) | (mask << item.b)
        dp = new
    return dp


def _completable(items: list[Item], used: int, load: int) -> bool:
    if used < 0 or load < 0:
        return False
    if used > len(items):
        return False
    dp = _build_dp(items)
    if used >= len(dp):
        return False
    return bool((dp[used] >> load) & 1)


def _nearest_candidates(mask: int, target: int) -> list[int]:
    candidates: list[int] = []
    below = mask & ((1 << (target + 1)) - 1)
    if below:
        candidates.append(below.bit_length() - 1)
    above = mask >> target
    if above:
        candidates.append(target + (above & -above).bit_length() - 1)
    return candidates


def _search(
    dp: list[int],
    items: list[Item],
    *,
    base: int,
    total_single: int,
    capacity: int | None,
    positions_per_leg: int,
    two_count: int,
) -> tuple[tuple[int, int, int, int], int] | None:
    """Return ((imbalance, max_leg, used_a, load_a), states) for the best plan."""

    best: tuple[int, int, int, int] | None = None
    states = 0
    item_count = len(items)
    for used, mask in enumerate(dp):
        if not mask:
            continue
        states += mask.bit_count()
        if used + two_count > positions_per_leg:
            continue
        if (item_count - used) + two_count > positions_per_leg:
            continue
        low = 0
        high = total_single
        if capacity is not None:
            # leg_b = base + (total_single - load_a) must also fit.
            low = max(low, total_single + base - capacity)
            high = min(high, capacity - base)
            if low > high:
                continue
        window = mask
        if low > 0:
            window &= ~((1 << low) - 1)
        if high < total_single:
            window &= (1 << (high + 1)) - 1
        if not window:
            continue
        target = total_single // 2
        for load_a in _nearest_candidates(window, target):
            if load_a < low or load_a > high:
                continue
            leg_a = base + load_a
            leg_b = base + total_single - load_a
            key = (abs(leg_a - leg_b), max(leg_a, leg_b), used, load_a)
            if best is None or key < best:
                best = key
    return (best, states) if best is not None else None


def _reconstruct(
    items: list[Item], used_a: int, load_a: int
) -> tuple[dict[str, str], int]:
    """Walk the items once more to recover a concrete assignment."""

    legs: dict[str, str] = {}
    used, load = used_a, load_a
    for index, item in enumerate(items):
        rest = items[index + 1 :]
        if item.b is None:
            # Taking a position on leg A is the transition that increments both
            # the used count and the leg-A load.
            if (
                used >= 1
                and load >= item.a
                and _completable(rest, used - 1, load - item.a)
            ):
                legs[item.ids[0]] = "A"
                used -= 1
                load -= item.a
                continue
            if _completable(rest, used, load):
                legs[item.ids[0]] = "B"
                continue
            raise RuntimeError("internal error: could not reconstruct unpaired item")
        # A paired item always occupies one position on each leg; only which of
        # its two loads lands on leg A is a choice.
        if (
            used >= 1
            and load >= item.a
            and _completable(rest, used - 1, load - item.a)
        ):
            legs[item.ids[0]] = "A"
            legs[item.ids[1]] = "B"
            used -= 1
            load -= item.a
            continue
        assert item.b is not None
        if (
            used >= 1
            and load >= item.b
            and _completable(rest, used - 1, load - item.b)
        ):
            legs[item.ids[0]] = "B"
            legs[item.ids[1]] = "A"
            used -= 1
            load -= item.b
            continue
        raise RuntimeError("internal error: could not reconstruct paired item")
    if used != 0 or load != 0:
        raise RuntimeError("internal error: reconstruction ended with a non-zero residual")
    return legs, used


def solve(plan: PanelPlan) -> Solution:
    panel = plan.panel
    capacity = panel.capacity_centiamps
    positions = panel.positions_per_leg
    items, two_load, two_count, single_total = build_items(plan.circuits)
    dp = _build_dp(items)

    reasons: list[str] = []
    if two_load > capacity:
        reasons.append(
            f"capacity: two-pole breakers alone put {two_load / 100:.1f} A on each leg, "
            f"above the {capacity / 100:.1f} A planning limit"
        )
    if len(items) + two_count > positions:
        reasons.append(
            f"slots: {len(items)} decision items plus {two_count} two-pole breakers "
            f"need {len(items) + two_count} positions per leg, panel has {positions}"
        )

    found = _search(
        dp,
        items,
        base=two_load,
        total_single=single_total,
        capacity=capacity,
        positions_per_leg=positions,
        two_count=two_count,
    )
    unconstrained = _search(
        dp,
        items,
        base=two_load,
        total_single=single_total,
        capacity=None,
        positions_per_leg=positions,
        two_count=two_count,
    )

    states = found[1] if found else (unconstrained[1] if unconstrained else 0)
    best_max = None
    if unconstrained is not None:
        best_max = unconstrained[0][1]

    if found is None:
        if not reasons:
            if best_max is not None and best_max > capacity:
                short = best_max - capacity
                reasons.append(
                    f"capacity: best achievable leg load is {best_max / 100:.1f} A "
                    f"against the {capacity / 100:.1f} A planning limit "
                    f"(short by {short / 100:.1f} A)"
                )
            else:
                reasons.append("no assignment satisfies the panel constraints")
        return Solution(
            feasible=False,
            reasons=reasons,
            leg_of={},
            rows=[],
            leg_a_ca=0,
            leg_b_ca=0,
            capacity_ca=capacity,
            base_ca=two_load,
            total_single_ca=single_total,
            positions_per_leg=positions,
            best_max_leg_ca=best_max,
            reachable_states=states,
            two_pole_count=two_count,
            item_count=len(items),
        )

    (_, _, used_a, load_a), _ = found
    legs, _ = _reconstruct(items, used_a, load_a)
    for circuit in plan.circuits:
        if circuit.poles == 2:
            legs.setdefault(circuit.id, "AB")
        else:
            legs.setdefault(circuit.id, "A")

    col_a = [c.id for c in plan.circuits if c.poles == 2]
    col_b = [c.id for c in plan.circuits if c.poles == 2]
    col_a += [c.id for c in plan.circuits if c.poles == 1 and legs.get(c.id) == "A"]
    col_b += [c.id for c in plan.circuits if c.poles == 1 and legs.get(c.id) == "B"]
    rows = [
        (col_a[i] if i < len(col_a) else None, col_b[i] if i < len(col_b) else None)
        for i in range(max(len(col_a), len(col_b)))
    ]

    leg_a = two_load + load_a
    leg_b = two_load + single_total - load_a
    return Solution(
        feasible=True,
        reasons=reasons,
        leg_of=legs,
        rows=rows,
        leg_a_ca=leg_a,
        leg_b_ca=leg_b,
        capacity_ca=capacity,
        base_ca=two_load,
        total_single_ca=single_total,
        positions_per_leg=positions,
        best_max_leg_ca=best_max,
        reachable_states=states,
        two_pole_count=two_count,
        item_count=len(items),
    )


def verify(plan: PanelPlan, solution: Solution) -> list[str]:
    """Independently recompute a solution's loads and constraints."""

    problems: list[str] = []
    panel = plan.panel
    seen: set[str] = set()
    leg_a = 0
    leg_b = 0
    positions_a = 0
    positions_b = 0
    for circuit in plan.circuits:
        leg = solution.leg_of.get(circuit.id)
        if leg is None:
            problems.append(f"circuit {circuit.id!r} has no leg assignment")
            continue
        if circuit.id in seen:
            problems.append(f"circuit {circuit.id!r} is assigned more than once")
        seen.add(circuit.id)
        load = circuit.effective_centiamps
        if circuit.poles == 2:
            if leg != "AB":
                problems.append(f"two-pole circuit {circuit.id!r} must occupy both legs")
            leg_a += load
            leg_b += load
            positions_a += 1
            positions_b += 1
        elif leg == "A":
            leg_a += load
            positions_a += 1
        elif leg == "B":
            leg_b += load
            positions_b += 1
        else:
            problems.append(f"circuit {circuit.id!r} has leg {leg!r}, expected A, B or AB")

    if leg_a != solution.leg_a_ca:
        problems.append(f"leg A recomputes to {leg_a} ca, report says {solution.leg_a_ca} ca")
    if leg_b != solution.leg_b_ca:
        problems.append(f"leg B recomputes to {leg_b} ca, report says {solution.leg_b_ca} ca")

    capacity = panel.capacity_centiamps
    if leg_a > capacity or leg_b > capacity:
        problems.append(
            f"leg load exceeds the {capacity / 100:.1f} A planning limit"
        )
    positions = panel.positions_per_leg
    if positions_a > positions or positions_b > positions:
        problems.append(
            f"slot count exceeds the {positions} positions available per leg"
        )

    by_group: dict[str, list[str]] = {}
    for circuit in plan.circuits:
        if circuit.group:
            by_group.setdefault(circuit.group, []).append(circuit.id)
    for group, members in sorted(by_group.items()):
        legs = {solution.leg_of.get(member) for member in members}
        if legs == {"A", "B"}:
            continue
        problems.append(f"group {group!r} is not split across opposite legs")

    used_rows = len(solution.rows)
    if used_rows > positions:
        problems.append(f"layout uses {used_rows} rows, panel has {positions}")

    return problems
