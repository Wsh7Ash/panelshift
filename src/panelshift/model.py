"""Input model, parsing and validation.

All electrical arithmetic uses integer centiamps (1 A == 100) so that a 125 %
continuous-load multiplier never introduces binary floating point drift.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

MAX_CIRCUITS = 120
MAX_AMPS = 1200.0
SUPPORTED_VOLTAGES = (120, 240)


class ConfigError(ValueError):
    """Raised when a panel plan document is structurally or electrically invalid."""

    def __init__(self, problems: list[str]):
        self.problems = tuple(problems)
        super().__init__("; ".join(problems))


def to_centiamps(amps: float) -> int:
    """Convert amps to integer centiamps, rounding half up."""

    return int(math.floor(float(amps) * 100 + 0.5))


def amps_from_centiamps(value: int) -> float:
    return value / 100.0


@dataclass(frozen=True)
class Panel:
    bus_amps: float
    voltage: int
    spaces: int
    planning_factor: float = 0.8

    @property
    def positions_per_leg(self) -> int:
        """Breaker positions available in each of the two columns."""

        return self.spaces // 2

    @property
    def capacity_centiamps(self) -> int:
        """Per-leg planning limit in centiamps."""

        return int(math.floor(self.bus_amps * 100 * self.planning_factor + 1e-9))


@dataclass(frozen=True)
class Circuit:
    id: str
    amps: float
    poles: int
    name: str = ""
    continuous: bool = False
    group: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.id

    @property
    def effective_centiamps(self) -> int:
        """Connected load in centiamps, with 125 % applied to continuous loads."""

        base = to_centiamps(self.amps)
        if self.continuous:
            return (base * 5 + 2) // 4
        return base


@dataclass(frozen=True)
class PanelPlan:
    panel: Panel
    circuits: tuple[Circuit, ...]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_int(value: Any, field: str, problems: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"{field} must be an integer")
        return None
    return value


def _as_number(value: Any, field: str, problems: list[str]) -> float | None:
    if not _is_number(value):
        problems.append(f"{field} must be a number")
        return None
    return float(value)


def parse_plan(document: Any) -> PanelPlan:
    """Validate a decoded JSON document and return a PanelPlan.

    All problems found are reported together so a user can fix a schedule in one
    pass instead of one error per run.
    """

    problems: list[str] = []
    if not isinstance(document, dict):
        raise ConfigError(["document root must be a JSON object"])

    raw_panel = document.get("panel")
    if not isinstance(raw_panel, dict):
        raise ConfigError(["'panel' must be an object"])
    raw_circuits = document.get("circuits")
    if not isinstance(raw_circuits, list):
        raise ConfigError(["'circuits' must be an array"])

    bus = _as_number(raw_panel.get("bus_amps"), "panel.bus_amps", problems)
    voltage = _as_int(raw_panel.get("voltage"), "panel.voltage", problems)
    spaces = _as_int(raw_panel.get("spaces"), "panel.spaces", problems)
    factor_raw = raw_panel.get("planning_factor", 0.8)
    factor = _as_number(factor_raw, "panel.planning_factor", problems)

    if bus is not None:
        if bus <= 0 or bus > MAX_AMPS:
            problems.append(f"panel.bus_amps must be > 0 and <= {MAX_AMPS:g}")
        if to_centiamps(bus) <= 0:
            problems.append("panel.bus_amps is too small to represent")
    if voltage is not None and voltage not in SUPPORTED_VOLTAGES:
        problems.append(
            "panel.voltage must be one of " + ", ".join(str(v) for v in SUPPORTED_VOLTAGES)
        )
    if spaces is not None:
        if spaces < 2 or spaces > 84:
            problems.append("panel.spaces must be between 2 and 84")
        elif spaces % 2 != 0:
            problems.append("panel.spaces must be even (two breaker columns)")
    if factor is not None and not (0 < factor <= 1):
        problems.append("panel.planning_factor must be in (0, 1]")

    circuits: list[Circuit] = []
    seen_ids: set[str] = set()
    group_members: dict[str, list[str]] = {}

    if len(raw_circuits) > MAX_CIRCUITS:
        problems.append(f"at most {MAX_CIRCUITS} circuits are supported")
    if not raw_circuits:
        problems.append("at least one circuit is required")

    for index, raw in enumerate(raw_circuits):
        where = f"circuits[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{where} must be an object")
            continue
        cid = raw.get("id")
        if not isinstance(cid, str) or not cid.strip():
            problems.append(f"{where}.id must be a non-empty string")
            cid = f"__invalid_{index}"
        elif cid in seen_ids:
            problems.append(f"{where}.id {cid!r} is duplicated")
        else:
            seen_ids.add(cid)

        amps = _as_number(raw.get("amps"), f"{where}.amps", problems)
        poles = _as_int(raw.get("poles"), f"{where}.poles", problems)
        name = raw.get("name", "")
        if name is None:
            name = ""
        if not isinstance(name, str):
            problems.append(f"{where}.name must be a string")
            name = ""
        continuous = raw.get("continuous", False)
        if not isinstance(continuous, bool):
            problems.append(f"{where}.continuous must be true or false")
            continuous = False
        group = raw.get("group")
        if group is not None and (not isinstance(group, str) or not group.strip()):
            problems.append(f"{where}.group must be a non-empty string when present")
            group = None
        if group is not None and poles == 2:
            problems.append(f"{where}.group is only valid on single-pole circuits")

        if amps is not None and (amps <= 0 or amps > MAX_AMPS):
            problems.append(f"{where}.amps must be > 0 and <= {MAX_AMPS:g}")
        if poles is not None and poles not in (1, 2):
            problems.append(f"{where}.poles must be 1 or 2")

        if amps is not None and poles in (1, 2):
            circuit = Circuit(
                id=cid,
                amps=amps,
                poles=poles,
                name=name,
                continuous=continuous,
                group=group,
            )
            circuits.append(circuit)
            if group:
                group_members.setdefault(group, []).append(cid)

    for group, members in sorted(group_members.items()):
        if len(members) != 2:
            problems.append(
                f"group {group!r} must contain exactly two single-pole circuits, "
                f"found {len(members)}"
            )

    if problems:
        raise ConfigError(problems)

    assert bus is not None and voltage is not None and spaces is not None
    assert factor is not None
    return PanelPlan(
        panel=Panel(bus_amps=bus, voltage=voltage, spaces=spaces, planning_factor=factor),
        circuits=tuple(circuits),
    )


def load_plan(path: str) -> PanelPlan:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except OSError as exc:
        raise ConfigError([f"cannot read {path}: {exc.strerror or exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError([f"{path} is not valid JSON: {exc.msg} at line {exc.lineno}"]) from exc
    return parse_plan(document)


def plan_to_document(plan: PanelPlan) -> dict[str, Any]:
    """Return the canonical input document for a plan (used in reports)."""

    return {
        "panel": {
            "bus_amps": plan.panel.bus_amps,
            "voltage": plan.panel.voltage,
            "spaces": plan.panel.spaces,
            "planning_factor": plan.panel.planning_factor,
        },
        "circuits": [
            {
                "id": c.id,
                "name": c.name,
                "amps": c.amps,
                "poles": c.poles,
                "continuous": c.continuous,
                **({"group": c.group} if c.group else {}),
            }
            for c in plan.circuits
        ],
    }
