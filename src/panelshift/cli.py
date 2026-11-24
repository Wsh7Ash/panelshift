"""Command line interface.

Exit codes
----------
0  the plan is feasible (and, for `verify`, the report is internally consistent)
1  the plan is infeasible, or a verification found contradictions
2  the input document is invalid or a path cannot be read
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from .balance import solve, verify
from .model import ConfigError, load_plan, parse_plan
from .report import render_json, render_text, to_document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="panelshift",
        description="Assign breakers to panel legs with a proved-minimal imbalance.",
    )
    parser.add_argument("--version", action="version", version=f"panelshift {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="balance a panel plan")
    plan.add_argument("file", help="JSON panel plan")
    plan.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="report format (default: text)",
    )

    verify_cmd = sub.add_parser(
        "verify", help="re-check a plan document emitted by `plan --format json`"
    )
    verify_cmd.add_argument("file", help="JSON report containing its input document")
    return parser


def _cmd_plan(path: str, fmt: str) -> int:
    try:
        plan = load_plan(path)
    except ConfigError as exc:
        for problem in exc.problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2
    solution = solve(plan)
    if fmt == "json":
        sys.stdout.write(render_json(plan, solution))
    else:
        print(render_text(plan, solution))
    return 0 if solution.feasible else 1


def _cmd_verify(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {path} is not valid JSON: {exc.msg}", file=sys.stderr)
        return 2

    if not isinstance(report, dict) or "input" not in report:
        print("error: report does not contain its 'input' document", file=sys.stderr)
        return 2
    try:
        plan = parse_plan(report["input"])
    except ConfigError as exc:
        for problem in exc.problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    solution = solve(plan)
    claimed = report.get("circuits")
    claimed_legs = {
        item.get("id"): item.get("leg")
        for item in claimed
        if isinstance(item, dict)
    } if isinstance(claimed, list) else {}

    problems: list[str] = []
    if report.get("verdict") not in ("feasible", "infeasible"):
        problems.append("report has no valid verdict")
    if isinstance(claimed, list) and claimed_legs:
        mismatched = {
            cid: leg
            for cid, leg in claimed_legs.items()
            if solution.leg_of.get(cid) != leg
        }
        if mismatched:
            problems.append(
                "report assigns legs that the solver does not reproduce: "
                + ", ".join(f"{cid}={leg}" for cid, leg in sorted(mismatched.items()))
            )
    if report.get("verdict") == "feasible":
        problems.extend(verify(plan, solution))
        claimed_imbalance = report.get("imbalance_amps")
        if isinstance(claimed_imbalance, (int, float)):
            if abs(float(claimed_imbalance) * 100 - solution.imbalance_ca) > 0.5:
                problems.append(
                    "report imbalance does not match the recomputed optimum "
                    f"({claimed_imbalance} A vs {solution.imbalance_ca / 100:.2f} A)"
                )
    else:
        if solution.feasible:
            problems.append("report says infeasible but the recomputed solver finds a plan")

    if problems:
        print("verify: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    document = to_document(plan, solution)
    print("verify: OK")
    print(f"  verdict: {document['verdict']}")
    print(f"  leg A: {document['legs']['a']['amps']:.1f} A")
    print(f"  leg B: {document['legs']['b']['amps']:.1f} A")
    print(f"  imbalance: {document['imbalance_amps']:.1f} A (proved minimal)")
    print(
        f"  reachable states examined: {document['certificate']['reachable_states']}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        return _cmd_plan(args.file, args.format)
    if args.command == "verify":
        return _cmd_verify(args.file)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
