# Uniqueness and prior-art investigation

Investigated on 2026-11-24 with web searches for panel-schedule calculators,
phase-balancing tools, open-source breaker planners, and "automatic phase
assignment" tooling. Nothing below claims absolute novelty; it records what was
found and what remains uncertain.

## Closest existing alternatives

| Alternative | What it does | Limitation relative to this project |
|---|---|---|
| AceWatt Panel Schedule Calculator | Enter circuits, assign phases, see per-phase VA and utilization. | Assignment is manual; "balance" is a report, not an optimization. |
| ConceptViz Panel Schedule Generator | Printable two-column schedule with per-phase totals. | Same: the user chooses the phase. |
| SparkShift Panel Schedule Generator | Phase assignment, 125 % continuous loads, imbalance report. | No search for the best assignment. |
| VoltCal LV Panel Board | Interactive balancing, imbalance detection, "Smart Phase Suggestion" assigns the next feeder to the lightest phase. | Greedy suggestion; cannot handle coupled two-pole/MWBC choices optimally, and cannot prove no better split exists. |
| A2Z Electrical Load Schedule Builder | Per-phase currents, imbalance, diversified demand. | Manual phase allocation. |
| CircuitBreakerPlanner (GitHub) | Web app for split-phase panels; computes odd-row vs even-row consumption. | Documents a layout; no optimization or feasibility certificate. |
| Electrical design suites | Full load calcs, schedules, code checks. | Larger, commercial, not a small offline exact balancer. |

## Similarities

- Reads a circuit list with amps and pole counts.
- Reports per-leg connected load, utilization and imbalance.
- Emphasizes 120/240 V split-phase panels.
- Uses the 125 % continuous-load convention.

## Meaningful differences

1. **Optimization, not evaluation.** Existing tools compute the imbalance of a
   chosen assignment (or greedily choose the next circuit). `panelshift` searches
   the reachable assignment space and returns the minimum imbalance, with the
   number of reachable states as a completeness indicator.
2. **Coupled constraints inside the search.** A two-pole breaker consumes a
   position on both legs; a shared-neutral pair must be split. These are hard
   constraints, not post-hoc repairs.
3. **Quantified infeasibility.** When no plan fits, the tool reports the best
   achievable max leg load and the shortfall in amps, plus slot arithmetic.
4. **A checkable certificate.** The JSON report carries its own input and a
   `verify` command recomputes loads, constraints and the optimum.

## Unique mechanism

An exact subset-sum DP over `(leg-A positions used, leg-A load)` where each
decision is either one single-pole circuit or one shared-neutral pair. Paired
items always consume one position per leg and choose which load lands on leg A;
unpaired items may occupy leg A (count + 1) or leg B (count unchanged). The
objective is `(|legA - legB|, max(legA, legB))`, minimized over all reachable
states that satisfy capacity and position limits.

## Why this deserves an independent repository

It is a small, focused decision procedure with its own correctness claim and a
different output contract (proof plus verifiable certificate) from the
entry-sheet calculators that dominate this niche. The algorithm and the
constraint model are reusable for three-phase and multi-panel extensions.

## Remaining originality uncertainties

- Commercial electrical design software may include an optimizer that is not
  documented publicly; this investigation could not inspect closed products.
- "Phase balancing" is a common phrase; a tool with a similar search may exist
  under a name that the searches did not surface.
- The 80 % default planning factor is a planning convention, not a universal
  rule; the tool deliberately does not claim code compliance.
- No survey of electricians was performed, so demand is inferred from the number
  of manual-entry calculators rather than measured.
