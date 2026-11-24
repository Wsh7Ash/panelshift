# panelshift — Project Specification

## 1. Vision

Make panel phase balancing a solved problem rather than a manual guess: an
offline tool that returns the best possible split of a single-phase panel, or a
precise explanation of why no split fits.

## 2. Target audience

Electricians, electrical designers, solar/battery installers, workshop and
homelab owners, plan reviewers, and instructors teaching panel schedules.

## 3. Problem statement

A split-phase panel has two legs. Single-pole circuits choose a leg, two-pole
circuits consume a position on both, and shared-neutral circuits must be split
across legs. Manual balancing and entry-sheet calculators either report the
result of a chosen layout or suggest the lighter leg for the next circuit. When
a panel is near its limit, either approach can miss the feasible assignment, and
neither can prove that no better one exists.

## 4. Existing alternatives

- Panel-schedule and load-schedule calculators (AceWatt, ConceptViz, SparkShift,
  VoltCal, A2Z Tools): manual phase entry with per-phase totals; VoltCal and
  some others suggest the lighter phase for the next feeder (greedy).
- CircuitBreakerPlanner: reports odd-row vs even-row consumption for a manual
  layout.
- Spreadsheets and paper schedules: arithmetic only.
- Full electrical design suites: broader scope, commercial, not a small
  offline optimizer.

## 5. Competitive differentiation

- The objective is optimized, not evaluated: minimum achievable imbalance.
- Hard constraints are part of the search: coupled two-pole breakers and
  shared-neutral pairs on opposite legs.
- Infeasibility is quantified: best achievable leg load and the shortfall.
- A certificate and an independent `verify` command make the claim checkable.
- Zero dependencies, integer centiamp arithmetic, deterministic output.

## 6. Core functionality

1. Parse and validate a panel plan (panel, circuits, groups).
2. Compute effective loads with the 125 % continuous multiplier.
3. Solve the assignment exactly.
4. Diagnose infeasibility (capacity, slots, two-pole base).
5. Emit a two-column slot layout, text report and JSON report.
6. Verify a report by recomputation.

## 7. Technical architecture

- `model.py`: dataclasses, parsing, validation, centiamp conversion.
- `balance.py`: item construction, subset-sum DP, optimal selection,
  reconstruction, slot layout, independent verifier.
- `report.py`: text and JSON rendering.
- `cli.py`: `plan` and `verify` subcommands and exit-code mapping.

## 8. Main components

| Component | Responsibility |
|---|---|
| `Panel` / `Circuit` / `PanelPlan` | Immutable input model |
| `build_items` | Collapse circuits into solver decisions |
| `_build_dp` | Reachable `(positions, load)` bitsets |
| `_search` | Constrained optimum over reachable states |
| `_reconstruct` | Concrete assignment from the chosen state |
| `verify` | Independent recomputation of loads and constraints |

## 9. Data flow

```text
JSON document
  -> parse_plan (validation, centiamps)
  -> build_items (two-pole base, single items, MWBC pairs)
  -> _build_dp (subset-sum bitsets)
  -> _search (min |legA-legB|, then min max leg)
  -> _reconstruct (leg per circuit)
  -> layout rows (two columns)
  -> report (text | JSON) / verify
```

## 10. Dependencies

Python standard library only (`json`, `argparse`, `math`, `dataclasses`,
`typing`). Tests use `unittest`. CI uses GitHub Actions.

## 11. Security considerations

- Reads local files only; no network, sockets, subprocesses or credentials.
- Strict input validation; malformed documents are usage errors, not tracebacks.
- No writes except stdout; no temporary files.
- No personal data is required by the schema.

## 12. User workflows

1. **Plan a new panel**: write a JSON circuit list, run `plan`, use the slot
   layout.
2. **Check an existing schedule**: encode the panel and circuits, run `plan`,
   compare with the as-built schedule.
3. **Gate a design**: run with `--format json` in a script and fail the build on
   exit code 1.
4. **Audit a report**: `verify report.json` recomputes everything from `input`.

## 13. Testing strategy

- Unit tests for parsing and every validation rule.
- Brute-force oracle over 40 seeded random panels (up to 9 decisions) compared
  with the DP result on `(imbalance, max leg)`.
- Constraint tests for two-pole and shared-neutral circuits.
- Infeasibility tests for capacity and slot shortages.
- Verifier tampering tests.
- CLI tests for exit codes, JSON round trip and determinism.
- End-to-end demo script asserting documented exit codes.

## 14. Definition of done

- All tests pass and the demo gate passes.
- Text and JSON reports are deterministic.
- The optimum matches brute force on random small instances.
- Infeasible inputs produce actionable reasons and exit 1.
- Documentation matches the implementation and states limitations.

## 15. Known limitations

See the README. Notably: not a code-compliance calculation; single-phase only;
no AFCI/GFCI, tandem breakers, conductor sizing or voltage drop; DP memory
growth with circuit count.

## 16. Future development

Three-phase balancing, tandem/quad space modelling, preferred-leg stability,
CSV import, and an optional panel-schedule PDF renderer.
