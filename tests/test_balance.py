"""Solver correctness: exact optimum, brute-force cross-check, certificates."""

from __future__ import annotations

import itertools
import random
import unittest

from panelshift.balance import build_items, solve, verify
from panelshift.model import Circuit, Panel, PanelPlan


def make_plan(circuits, bus=200, spaces=40, factor=0.8, voltage=240):
    return PanelPlan(
        panel=Panel(bus_amps=bus, voltage=voltage, spaces=spaces, planning_factor=factor),
        circuits=tuple(circuits),
    )


def brute_force(plan):
    """Enumerate every assignment and return (feasible, imbalance, max_leg)."""

    items, two_load, two_count, single_total = build_items(plan.circuits)
    positions = plan.panel.positions_per_leg
    capacity = plan.panel.capacity_centiamps
    best = None
    for choices in itertools.product([0, 1], repeat=len(items)):
        leg_a = two_load
        leg_b = two_load
        positions_a = two_count
        positions_b = two_count
        for item, choice in zip(items, choices):
            if item.b is None:
                if choice == 0:
                    leg_a += item.a
                    positions_a += 1
                else:
                    leg_b += item.a
                    positions_b += 1
            else:
                if positions_a + 1 > positions or positions_b + 1 > positions:
                    continue
                positions_a += 1
                positions_b += 1
                leg_a += item.a if choice == 0 else item.b
                leg_b += item.b if choice == 0 else item.a
        if positions_a > positions or positions_b > positions:
            continue
        if leg_a > capacity or leg_b > capacity:
            continue
        key = (abs(leg_a - leg_b), max(leg_a, leg_b))
        if best is None or key < best:
            best = key
    return best


class TestOptimality(unittest.TestCase):
    def test_matches_brute_force_on_random_panels(self):
        rng = random.Random(20261124)
        for case in range(40):
            circuits = []
            index = 0
            for _ in range(rng.randint(3, 7)):
                index += 1
                circuits.append(
                    Circuit(id=f"s{index}", amps=rng.choice([8, 12, 15, 16, 20, 24]), poles=1)
                )
            if rng.random() < 0.5:
                index += 1
                circuits.append(
                    Circuit(
                        id=f"t{index}",
                        amps=rng.choice([20, 30, 40]),
                        poles=2,
                    )
                )
            if rng.random() < 0.4:
                index += 1
                circuits.append(
                    Circuit(id=f"g{index}a", amps=rng.choice([12, 15, 20]), poles=1, group="mwbc")
                )
                circuits.append(
                    Circuit(id=f"g{index}b", amps=rng.choice([12, 15, 20]), poles=1, group="mwbc")
                )
            plan = make_plan(circuits, bus=rng.choice([60, 100, 125, 200]))
            expected = brute_force(plan)
            result = solve(plan)
            with self.subTest(case=case):
                if expected is None:
                    self.assertFalse(result.feasible)
                    continue
                self.assertTrue(result.feasible, msg=str(result.reasons))
                self.assertEqual(
                    (result.imbalance_ca, result.max_leg_ca),
                    expected,
                )
                self.assertEqual(verify(plan, result), [])

    def test_two_pole_load_lands_on_both_legs(self):
        plan = make_plan(
            [
                Circuit(id="range", amps=40, poles=2),
                Circuit(id="light", amps=10, poles=1),
            ],
            bus=100,
        )
        result = solve(plan)
        self.assertTrue(result.feasible)
        # 40 A two-pole load is on both legs; the single 10 A circuit cannot be
        # split, so the exact optimum is 50 A / 40 A.
        self.assertEqual(sorted([result.leg_a_ca, result.leg_b_ca]), [4000, 5000])
        self.assertEqual(result.imbalance_ca, 1000)
        self.assertEqual(result.leg_of["range"], "AB")

    def test_mwbc_pair_is_split_across_legs(self):
        plan = make_plan(
            [
                Circuit(id="k1", amps=20, poles=1, group="kitchen"),
                Circuit(id="k2", amps=20, poles=1, group="kitchen"),
                Circuit(id="misc", amps=5, poles=1),
            ]
        )
        result = solve(plan)
        self.assertTrue(result.feasible)
        self.assertEqual({result.leg_of["k1"], result.leg_of["k2"]}, {"A", "B"})
        self.assertEqual(verify(plan, result), [])

    def test_continuous_load_raises_both_legs(self):
        plan = make_plan(
            [Circuit(id="ev", amps=32, poles=2, continuous=True)],
            bus=100,
            spaces=8,
        )
        result = solve(plan)
        self.assertTrue(result.feasible)
        self.assertEqual(result.leg_a_ca, 4000)
        self.assertEqual(result.leg_b_ca, 4000)

    def test_adds_extra_load_to_the_lighter_leg(self):
        plan = make_plan(
            [
                Circuit(id="a", amps=30, poles=1),
                Circuit(id="b", amps=30, poles=1),
                Circuit(id="c", amps=20, poles=1),
            ],
            bus=200,
        )
        result = solve(plan)
        self.assertTrue(result.feasible)
        self.assertLessEqual(result.imbalance_ca, 2000)
        self.assertEqual(result.imbalance_ca, 2000)

    def test_zero_imbalance_when_partition_is_exact(self):
        plan = make_plan(
            [
                Circuit(id="a", amps=20, poles=1),
                Circuit(id="b", amps=20, poles=1),
                Circuit(id="c", amps=10, poles=1),
                Circuit(id="d", amps=10, poles=1),
            ]
        )
        result = solve(plan)
        self.assertEqual(result.imbalance_ca, 0)

    def test_layout_places_each_circuit_once(self):
        plan = make_plan(
            [
                Circuit(id="range", amps=40, poles=2),
                Circuit(id="a", amps=20, poles=1),
                Circuit(id="b", amps=15, poles=1),
                Circuit(id="c", amps=12, poles=1),
            ]
        )
        result = solve(plan)
        flat = [cid for row in result.rows for cid in row if cid]
        # A two-pole breaker deliberately appears in both columns of its row.
        self.assertEqual(sorted(set(flat)), ["a", "b", "c", "range"])
        self.assertEqual(flat.count("range"), 2)
        self.assertEqual(flat.count("a"), 1)
        self.assertEqual(flat.count("b"), 1)
        self.assertEqual(flat.count("c"), 1)


class TestInfeasible(unittest.TestCase):
    def test_capacity_overflow_reports_shortfall(self):
        plan = make_plan(
            [
                Circuit(id="range", amps=40, poles=2),
                Circuit(id="dryer", amps=30, poles=2),
                Circuit(id="ev", amps=40, poles=2, continuous=True),
                Circuit(id="shop", amps=50, poles=2),
            ],
            bus=60,
            spaces=12,
        )
        result = solve(plan)
        self.assertFalse(result.feasible)
        self.assertTrue(any("capacity" in reason for reason in result.reasons))
        self.assertIsNotNone(result.best_max_leg_ca)
        self.assertGreater(result.best_max_leg_ca, result.capacity_ca)

    def test_capacity_shortfall_is_reported_when_legs_cannot_fit(self):
        plan = make_plan(
            [
                Circuit(id="a", amps=60, poles=1),
                Circuit(id="b", amps=60, poles=1),
                Circuit(id="c", amps=60, poles=1),
            ],
            bus=100,
            spaces=12,
        )
        result = solve(plan)
        self.assertFalse(result.feasible)
        text = " ".join(result.reasons)
        self.assertIn("best achievable leg load", text)
        self.assertIn("short by", text)

    def test_slot_shortage_is_explicit(self):
        plan = make_plan(
            [Circuit(id=f"c{i}", amps=10, poles=1) for i in range(11)],
            bus=200,
            spaces=8,
        )
        result = solve(plan)
        self.assertFalse(result.feasible)
        self.assertTrue(any("slots" in reason for reason in result.reasons))

    def test_infeasible_solution_has_no_assignments(self):
        plan = make_plan([Circuit(id="a", amps=90, poles=1)], bus=60, spaces=8)
        result = solve(plan)
        self.assertFalse(result.feasible)
        self.assertEqual(result.leg_of, {})
        self.assertEqual(result.rows, [])


class TestVerifier(unittest.TestCase):
    def test_verifier_accepts_solver_output(self):
        plan = make_plan(
            [
                Circuit(id="range", amps=40, poles=2),
                Circuit(id="a", amps=20, poles=1),
                Circuit(id="b", amps=20, poles=1),
                Circuit(id="c", amps=14, poles=1),
            ]
        )
        result = solve(plan)
        self.assertEqual(verify(plan, result), [])

    def test_verifier_detects_wrong_leg(self):
        plan = make_plan(
            [
                Circuit(id="a", amps=20, poles=1),
                Circuit(id="b", amps=20, poles=1),
            ]
        )
        result = solve(plan)
        result.leg_of["a"] = "B" if result.leg_of["a"] == "A" else "A"
        self.assertNotEqual(verify(plan, result), [])

    def test_verifier_detects_missing_assignment(self):
        plan = make_plan([Circuit(id="a", amps=20, poles=1)])
        result = solve(plan)
        del result.leg_of["a"]
        self.assertTrue(any("no leg assignment" in p for p in verify(plan, result)))

    def test_verifier_detects_mwbc_on_same_leg(self):
        plan = make_plan(
            [
                Circuit(id="a", amps=20, poles=1, group="shared"),
                Circuit(id="b", amps=20, poles=1, group="shared"),
            ]
        )
        result = solve(plan)
        result.leg_of["a"] = "A"
        result.leg_of["b"] = "A"
        self.assertTrue(any("opposite legs" in p for p in verify(plan, result)))


if __name__ == "__main__":
    unittest.main()
