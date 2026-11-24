"""Human-readable and machine-readable rendering."""

from __future__ import annotations

import json
from typing import Any

from .balance import Solution
from .model import PanelPlan, plan_to_document


def _amps(centiamps: int) -> str:
    return f"{centiamps / 100:.1f}"


def _pct(centiamps: int, bus_centiamps: int) -> str:
    if bus_centiamps <= 0:
        return "n/a"
    return f"{100 * centiamps / bus_centiamps:.1f}%"


def _circuit_lookup(plan: PanelPlan):
    return {c.id: c for c in plan.circuits}


def render_text(plan: PanelPlan, solution: Solution) -> str:
    panel = plan.panel
    lookup = _circuit_lookup(plan)
    bus_ca = int(round(panel.bus_amps * 100))
    lines: list[str] = []
    lines.append("panelshift - single-phase panel balance")
    lines.append("=" * 42)
    lines.append(
        f"Panel: {panel.voltage} V | {panel.bus_amps:g} A bus | {panel.spaces} spaces "
        f"({panel.positions_per_leg} positions per leg) | planning factor "
        f"{panel.planning_factor:.2f}"
    )
    lines.append(f"Planning limit per leg: {_amps(solution.capacity_ca)} A")
    lines.append("")

    if not solution.feasible:
        lines.append("Verdict: INFEASIBLE")
        lines.append("")
        lines.append("Reasons:")
        for reason in solution.reasons:
            lines.append(f"  - {reason}")
        if solution.best_max_leg_ca is not None:
            lines.append("")
            lines.append(
                "Best achievable leg load with these circuits: "
                f"{_amps(solution.best_max_leg_ca)} A"
            )
        lines.append("")
        lines.append(
            "No assignment was produced. Reduce or move load, choose a larger panel, "
            "or raise the planning factor only after confirming the actual load calculation."
        )
        return "\n".join(lines)

    positions_a = solution.two_pole_count + sum(
        1
        for c in plan.circuits
        if c.poles == 1 and solution.leg_of.get(c.id) == "A"
    )
    positions_b = solution.two_pole_count + sum(
        1
        for c in plan.circuits
        if c.poles == 1 and solution.leg_of.get(c.id) == "B"
    )
    lines.append(
        f"Leg A  {_amps(solution.leg_a_ca):>6} A  {_pct(solution.leg_a_ca, bus_ca):>6} of bus"
        f"   {positions_a} positions"
    )
    lines.append(
        f"Leg B  {_amps(solution.leg_b_ca):>6} A  {_pct(solution.leg_b_ca, bus_ca):>6} of bus"
        f"   {positions_b} positions"
    )
    heavier = "B" if solution.leg_b_ca > solution.leg_a_ca else "A"
    lines.append(
        f"Imbalance {_amps(solution.imbalance_ca)} A "
        f"({100 * solution.imbalance_ca / bus_ca:.2f}% of bus, {heavier} heavier)"
    )
    lines.append("")
    lines.append(
        "Verdict: FEASIBLE - imbalance is the exact minimum "
        f"({solution.reachable_states} reachable states examined)"
    )
    lines.append("")
    lines.append(f"{'Row':>3}  {'Leg A':<30} {'Leg B':<30} Load A  Load B")
    lines.append("-" * 88)
    for index, (a, b) in enumerate(solution.rows, start=1):
        circuit_a = lookup.get(a) if a else None
        circuit_b = lookup.get(b) if b else None
        label_a = f"{circuit_a.label} ({circuit_a.amps:g} A)" if circuit_a else "-"
        label_b = f"{circuit_b.label} ({circuit_b.amps:g} A)" if circuit_b else "-"
        load_a = _amps(circuit_a.effective_centiamps) if circuit_a else "-"
        load_b = _amps(circuit_b.effective_centiamps) if circuit_b else "-"
        lines.append(f"{index:>3}  {label_a:<30} {label_b:<30} {load_a:>6}  {load_b:>6}")
    lines.append("")
    lines.append(
        "Loads are connected loads in centiamps-safe arithmetic; continuous circuits "
        "carry 125%. This is a planning aid, not a code compliance determination."
    )
    return "\n".join(lines)


def to_document(plan: PanelPlan, solution: Solution) -> dict[str, Any]:
    lookup = _circuit_lookup(plan)
    panel = plan.panel
    circuits: list[dict[str, Any]] = []
    row_of: dict[str, int] = {}
    for index, (a, b) in enumerate(solution.rows, start=1):
        if a:
            row_of.setdefault(a, index)
        if b:
            row_of.setdefault(b, index)
    for circuit in plan.circuits:
        leg = solution.leg_of.get(circuit.id, "AB" if circuit.poles == 2 else "A")
        circuits.append(
            {
                "id": circuit.id,
                "name": circuit.name,
                "amps": circuit.amps,
                "poles": circuit.poles,
                "continuous": circuit.continuous,
                "group": circuit.group,
                "effective_amps": circuit.effective_centiamps / 100,
                "leg": leg,
                "row": row_of.get(circuit.id),
            }
        )
    return {
        "tool": "panelshift",
        "schema_version": 1,
        "input": plan_to_document(plan),
        "panel": {
            "bus_amps": panel.bus_amps,
            "voltage": panel.voltage,
            "spaces": panel.spaces,
            "positions_per_leg": panel.positions_per_leg,
            "planning_factor": panel.planning_factor,
            "capacity_amps": panel.capacity_centiamps / 100,
        },
        "verdict": "feasible" if solution.feasible else "infeasible",
        "optimal": solution.optimal,
        "legs": {
            "a": {
                "amps": solution.leg_a_ca / 100,
                "percent_of_bus": round(
                    100 * solution.leg_a_ca / (panel.bus_amps * 100), 3
                )
                if panel.bus_amps
                else None,
            },
            "b": {
                "amps": solution.leg_b_ca / 100,
                "percent_of_bus": round(
                    100 * solution.leg_b_ca / (panel.bus_amps * 100), 3
                )
                if panel.bus_amps
                else None,
            },
        },
        "imbalance_amps": solution.imbalance_ca / 100,
        "reasons": list(solution.reasons),
        "certificate": {
            "method": "exact-subset-sum-dp",
            "reachable_states": solution.reachable_states,
            "search_complete": True,
            "optimal_imbalance_amps": solution.imbalance_ca / 100,
            "best_achievable_max_leg_amps": (
                solution.best_max_leg_ca / 100
                if solution.best_max_leg_ca is not None
                else None
            ),
            "decision_items": solution.item_count,
            "two_pole_breakers": solution.two_pole_count,
        },
        "circuits": circuits,
        "slots": [
            {"row": index, "a": a, "b": b}
            for index, (a, b) in enumerate(solution.rows, start=1)
        ],
    }


def render_json(plan: PanelPlan, solution: Solution) -> str:
    return json.dumps(to_document(plan, solution), indent=2, sort_keys=False) + "\n"
