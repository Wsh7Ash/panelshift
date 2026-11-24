# panelshift

**Assign breakers to the two legs of a split-phase panel so the legs are as
close as possible — and get a proof that no better assignment exists.**

```text
$ panelshift plan examples/workshop.json

Leg A   159.0 A   79.5% of bus   7 positions
Leg B   160.0 A   80.0% of bus   8 positions
Imbalance 1.0 A (0.50% of bus, B heavier)

Verdict: FEASIBLE - imbalance is the exact minimum (62 reachable states examined)
```

## The problem

A 120/240 V panel has two hot legs. Every single-pole circuit must go on one
leg; a two-pole circuit lands on both at once. Electricians balance the two
columns by hand or with a panel-schedule app that assigns circuits to the slot
you pick and reports the resulting load. When a panel is close to its limit,
"roughly balanced" is not enough: the difference between a good split and the
best split can be the difference between a feasible panel and a service upgrade.

`panelshift` treats the assignment as the combinatorial problem it is and solves
it exactly. It handles the constraints that make the problem awkward:

- **Two-pole breakers** load both legs equally.
- **Multi-wire branch circuits (shared neutral)** must place their two hots on
  **opposite legs** — a hard constraint that a greedy "lightest leg next"
  heuristic can violate.
- **Continuous loads** carry 125 % (NEC 210.19/215.2 continuous-load sizing).
- **Breaker spaces** limit how many positions each leg has.
- **A per-leg planning limit** (`bus_amps × planning_factor`, default 80 %)
  bounds the result.

## Who should use it

Electricians, electrical designers, solar/battery installers, workshop and
homelab owners, and anyone reviewing a panel schedule who wants to know whether
a load can actually be split inside the panel — before pulling wire.

## What makes it different

Existing panel-schedule calculators are **entry sheets**: you choose the phase
and they add it up, or they suggest the lighter leg for the next circuit. This
tool **searches the whole assignment space** and returns:

- the **minimum possible imbalance**, not the imbalance of one manual guess;
- the **best achievable leg load** when the panel is infeasible, so you know how
  far over you are instead of only that you failed;
- a **slot-by-slot layout** with the shared-neutral pairs on opposite legs;
- a **certificate** (reachable-state count, method, completeness flag) plus a
  `verify` subcommand that recomputes the report from its own input.

No network, no dependencies, integer arithmetic in centiamps.

## Features

1. Exact leg assignment by subset-sum dynamic programming over
   `(leg-A positions used, leg-A load)`.
2. Two-pole and shared-neutral constraints handled inside the search, not fixed
   up afterwards.
3. Continuous loads at 125 % with centiamp-exact results.
4. Feasibility diagnosis: capacity shortfall, slot shortfall, or an irreducible
   two-pole base that exceeds the limit.
5. Two-column slot layout and machine-readable JSON report.
6. Independent `verify` command that recomputes loads, limits and the optimum.

## Requirements

- Python 3.12 or newer.
- Standard library only. No install step.

## Quick start

```bash
export PYTHONPATH=src
python -m panelshift plan examples/workshop.json
python -m panelshift plan examples/workshop.json --format json > report.json
python -m panelshift verify report.json
```

Run the tests and the end-to-end demo:

```bash
python -m unittest discover -s tests -v
bash scripts/demo.sh
```

## Input format

```json
{
  "panel": {
    "bus_amps": 200,
    "voltage": 240,
    "spaces": 40,
    "planning_factor": 0.8
  },
  "circuits": [
    {"id": "range", "name": "Range", "amps": 40, "poles": 2},
    {"id": "kitchen-a", "amps": 20, "poles": 1, "group": "kitchen-mwbc"},
    {"id": "kitchen-b", "amps": 20, "poles": 1, "group": "kitchen-mwbc"},
    {"id": "ev", "amps": 16, "continuous": true, "poles": 2}
  ]
}
```

| Field | Meaning |
|---|---|
| `panel.bus_amps` | Bus rating in amps. |
| `panel.voltage` | `120` or `240` (single-phase, split-phase systems). |
| `panel.spaces` | Total breaker spaces; must be even. Each leg gets half. |
| `panel.planning_factor` | Per-leg limit as a fraction of the bus (default `0.8`). |
| `circuits[].amps` | Connected load in amps. |
| `circuits[].poles` | `1` (line-to-neutral) or `2` (line-to-line, occupies both legs). |
| `circuits[].continuous` | Apply the 125 % continuous-load multiplier. |
| `circuits[].group` | Two one-pole circuits sharing this string must sit on opposite legs. |

All problems are collected and reported together; the tool exits `2` for an
invalid document.

## Output and exit codes

| Exit | Meaning |
|---:|---|
| `0` | Feasible: a plan was produced with the proved-minimal imbalance. |
| `1` | Infeasible: no assignment fits the leg limit and slot count. Reasons are printed. |
| `2` | Invalid input document or unreadable file. |

The JSON report includes the original `input` document, the per-circuit leg and
row, the two-column `slots`, and a `certificate`:

```json
"certificate": {
  "method": "exact-subset-sum-dp",
  "reachable_states": 62,
  "search_complete": true,
  "optimal_imbalance_amps": 1.0,
  "best_achievable_max_leg_amps": 160.0
}
```

## How it works

1. Two-pole circuits contribute a fixed load to both legs.
2. Each remaining decision — one single-pole circuit, or one shared-neutral pair
   — is an item. A pair always consumes one position on each leg and chooses
   which of its two loads lands on leg A.
3. A bitset DP records every reachable `(positions used on A, load on A)`.
4. The best reachable state is the one closest to half the single-pole load,
   among states that fit both legs' limits and slot counts. Because every
   reachable state is enumerated, the reported imbalance is minimal.
5. The assignment is reconstructed by re-checking feasibility of the remaining
   items, then laid out in two columns.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

## Limitations

- **Not a code-compliance determination.** The planning factor is a user-chosen
  planning limit, not a substitute for a Article 220 load calculation, demand
  factors, or your AHJ's rules.
- Single-phase 120/240 V panels only; three-phase phase balancing is out of scope.
- No modelling of AFCI/GFCI requirements, tandem/quad breaker space-savers,
  conductor ampacity, voltage drop, or neutral current from non-linear loads.
- Two-pole breakers are assumed to occupy aligned positions in both columns.
- The DP is exact but memory grows with the number of circuits; input is capped
  at 120 circuits.
- Transformer/panel bus temperature derating and main-breaker/bus mismatch are
  not modelled.

## Roadmap

- Three-phase (A/B/C) balancing with the same certificate approach.
- Tandem/quad breaker space modelling.
- Optional per-circuit preferred leg (keep an existing schedule stable).
- Import from a CSV panel schedule.

## Testing

43 `unittest` tests cover parsing/validation, the DP optimality claim (checked
against a brute-force oracle on 40 seeded random panels), shared-neutral and
two-pole constraints, continuous-load arithmetic, infeasible diagnostics, the
independent verifier, and the CLI contract. See [`RESULTS.md`](RESULTS.md) for
observed output.

## License

MIT. See [`LICENSE`](LICENSE).
