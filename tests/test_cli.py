"""CLI contract tests: exit codes, JSON report and verify round trip."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from panelshift.cli import main
from panelshift.model import load_plan
from panelshift.report import render_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def test_feasible_plan_exits_zero(self):
        code, out, err = run(["plan", os.path.join(EXAMPLES, "workshop.json")])
        self.assertEqual(code, 0, msg=err)
        self.assertIn("FEASIBLE", out)
        self.assertIn("exact minimum", out)

    def test_infeasible_plan_exits_one(self):
        code, out, err = run(["plan", os.path.join(EXAMPLES, "impossible.json")])
        self.assertEqual(code, 1, msg=err)
        self.assertIn("INFEASIBLE", out)
        self.assertIn("capacity", out)

    def test_slot_shortage_exits_one(self):
        code, out, _ = run(["plan", os.path.join(EXAMPLES, "slots.json")])
        self.assertEqual(code, 1)
        self.assertIn("slots", out)

    def test_missing_file_exits_two(self):
        code, _, err = run(["plan", "no-such-plan.json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_invalid_json_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            code, _, err = run(["plan", path])
            self.assertEqual(code, 2)
            self.assertIn("panel", err)

    def test_json_report_round_trips_through_verify(self):
        code, out, _ = run(["plan", os.path.join(EXAMPLES, "workshop.json"), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["verdict"], "feasible")
        self.assertTrue(report["optimal"])
        self.assertIn("certificate", report)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(out)
            verify_code, verify_out, verify_err = run(["verify", path])
        self.assertEqual(verify_code, 0, msg=verify_out + verify_err)
        self.assertIn("verify: OK", verify_out)

    def test_verify_rejects_tampered_leg(self):
        code, out, _ = run(["plan", os.path.join(EXAMPLES, "workshop.json"), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        target = next(c for c in report["circuits"] if c["poles"] == 1)
        target["leg"] = "B" if target["leg"] == "A" else "A"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tampered.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(report, handle)
            verify_code, verify_out, _ = run(["verify", path])
        self.assertEqual(verify_code, 1)
        self.assertIn("verify: FAIL", verify_out)

    def test_text_report_is_deterministic(self):
        plan = load_plan(os.path.join(EXAMPLES, "workshop.json"))
        from panelshift.balance import solve

        first = render_text(plan, solve(plan))
        second = render_text(plan, solve(plan))
        self.assertEqual(first, second)

    def test_json_report_is_deterministic(self):
        args = ["plan", os.path.join(EXAMPLES, "workshop.json"), "--format", "json"]
        self.assertEqual(run(args)[1], run(args)[1])

    def test_continuous_load_is_reported_at_125_percent(self):
        code, out, _ = run(["plan", os.path.join(EXAMPLES, "workshop.json"), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        ev = next(c for c in report["circuits"] if c["id"] == "ev")
        self.assertEqual(ev["effective_amps"], 20.0)
        self.assertEqual(ev["leg"], "AB")


if __name__ == "__main__":
    unittest.main()
