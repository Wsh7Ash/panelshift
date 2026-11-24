"""Validation and parsing tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from panelshift.model import (
    Circuit,
    ConfigError,
    Panel,
    PanelPlan,
    load_plan,
    parse_plan,
    to_centiamps,
)


def base_document(**panel_overrides):
    panel = {"bus_amps": 200, "voltage": 240, "spaces": 40, "planning_factor": 0.8}
    panel.update(panel_overrides)
    return {
        "panel": panel,
        "circuits": [
            {"id": "a", "amps": 20, "poles": 1},
            {"id": "b", "amps": 30, "poles": 2},
        ],
    }


class TestUnits(unittest.TestCase):
    def test_centiamps_round_half_up(self):
        self.assertEqual(to_centiamps(12.5), 1250)
        self.assertEqual(to_centiamps(0.005), 1)
        self.assertEqual(to_centiamps(0.004), 0)

    def test_continuous_load_is_125_percent(self):
        circuit = Circuit(id="ev", amps=32, poles=2, continuous=True)
        self.assertEqual(circuit.effective_centiamps, 4000)

    def test_continuous_rounds_to_nearest_centiamp(self):
        circuit = Circuit(id="x", amps=12.5, poles=1, continuous=True)
        # 1250 * 1.25 = 1562.5 -> 1563
        self.assertEqual(circuit.effective_centiamps, 1563)

    def test_non_continuous_is_unchanged(self):
        self.assertEqual(Circuit(id="x", amps=12.5, poles=1).effective_centiamps, 1250)

    def test_panel_capacity_and_positions(self):
        panel = Panel(bus_amps=200, voltage=240, spaces=40, planning_factor=0.8)
        self.assertEqual(panel.positions_per_leg, 20)
        self.assertEqual(panel.capacity_centiamps, 16000)


class TestParsing(unittest.TestCase):
    def test_parses_valid_document(self):
        plan = parse_plan(base_document())
        self.assertEqual(len(plan.circuits), 2)
        self.assertEqual(plan.panel.voltage, 240)
        self.assertEqual(plan.circuits[1].poles, 2)

    def test_rejects_odd_spaces(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(base_document(spaces=39))
        self.assertIn("spaces must be even", str(ctx.exception))

    def test_rejects_unsupported_voltage(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(base_document(voltage=208))
        self.assertIn("panel.voltage", str(ctx.exception))

    def test_rejects_bad_planning_factor(self):
        for factor in (0, 1.5, -1):
            with self.subTest(factor=factor), self.assertRaises(ConfigError):
                parse_plan(base_document(planning_factor=factor))

    def test_rejects_duplicate_ids(self):
        document = base_document()
        document["circuits"].append({"id": "a", "amps": 10, "poles": 1})
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertIn("duplicated", str(ctx.exception))

    def test_rejects_bad_poles(self):
        document = base_document()
        document["circuits"][0]["poles"] = 3
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertIn("poles must be 1 or 2", str(ctx.exception))

    def test_rejects_group_of_wrong_size(self):
        document = base_document()
        document["circuits"] = [
            {"id": "a", "amps": 20, "poles": 1, "group": "shared"},
        ]
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertIn("exactly two", str(ctx.exception))

    def test_rejects_group_on_two_pole(self):
        document = base_document()
        document["circuits"][1]["group"] = "shared"
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertIn("only valid on single-pole", str(ctx.exception))

    def test_reports_multiple_problems_at_once(self):
        document = {
            "panel": {"bus_amps": -5, "voltage": 999, "spaces": 7},
            "circuits": [{"id": "", "amps": 0, "poles": 1}],
        }
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertGreaterEqual(len(ctx.exception.problems), 4)

    def test_missing_file_is_config_error(self):
        with self.assertRaises(ConfigError):
            load_plan("does-not-exist-anywhere.json")

    def test_bad_json_is_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            with self.assertRaises(ConfigError) as ctx:
                load_plan(path)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_round_trip_document(self):
        from panelshift.model import plan_to_document

        plan = parse_plan(base_document())
        again = parse_plan(json.loads(json.dumps(plan_to_document(plan))))
        self.assertEqual(plan, again)

    def test_circuit_limit(self):
        document = base_document()
        document["circuits"] = [
            {"id": f"c{i}", "amps": 1, "poles": 1} for i in range(121)
        ]
        with self.assertRaises(ConfigError) as ctx:
            parse_plan(document)
        self.assertIn("at most", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
