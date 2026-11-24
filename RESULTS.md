# Observed results

Environment: Windows 11, Git Bash, Python 3.14.3. Commands run from the
repository root on 2026-11-24.

## Test suite

```text
$ PYTHONPATH=src python -m unittest discover -s tests
...........................................
----------------------------------------------------------------------
Ran 43 tests in 0.086s

OK
```

The suite includes a brute-force oracle: 40 seeded random panels (3–9 decision
items, mixed one-pole, two-pole and shared-neutral circuits, bus sizes 60–200 A)
are enumerated exhaustively and compared with the DP on `(imbalance, max leg)`.
All 40 match, and the independent verifier returns no problems on each.

## Compilation

```text
$ PYTHONPATH=src python -m compileall -q src
$ echo $?
0
```

## Continuous integration

The committed workflow (`python -m compileall`, `unittest`, then the demo)
completed successfully on GitHub Actions for the release commit `9d90974`:
run **45336451246**, conclusion **success** (8 s, 2026-11-24).

## Demo gate

```text
$ bash scripts/demo.sh
panelshift demo
---------------
ok   feasible workshop plan (exit 0)
ok   infeasible capacity plan (exit 1)
ok   infeasible slot plan (exit 1)
ok   invalid path (exit 2)
ok   json report contract (satisfied)
     legs 159.0 A / 160.0 A, imbalance 1.0 A, 62 states
ok   verify emitted report (exit 0)
ok   reject tampered report (exit 1)
demo: all checks passed
```

## Observed panel geometry

`examples/workshop.json` — 200 A bus, 240 V, 40 spaces, factor 0.80, so the
planning limit is 160.0 A per leg. The two-pole base (range 40 A, dryer 30 A,
EV 16 A continuous → 20 A) is 90.0 A on each leg. Single-pole connected load is
129.0 A, of which 35.0 A is continuous-scaled (dishwasher 12 A → 15 A).

Result:

```text
Leg A   159.0 A   79.5% of bus   7 positions
Leg B   160.0 A   80.0% of bus   8 positions
Imbalance 1.0 A (0.50% of bus, B heavier)
```

The minimum is 1.0 A because the single-pole loads are 20, 20, 15, 15, 20, 15,
8, 12, 14 A: a 64/65 A split is the closest possible, and 90 + 64 = 154 A is not
reachable given the same-neutral pair constraint (20 A must go to each leg).
The exact optimum is therefore 159/160 A.

`examples/impossible.json` — 60 A bus, factor 0.80 → 48.0 A per leg. The
two-pole breakers alone (40 + 30 + 40 + 50 A, with the 40 A EV continuous)
put 170.0 A on each leg. No assignment can fix that, and the report says so
before any slot reasoning.

`examples/slots.json` — 200 A bus, 8 spaces → 4 positions per leg. Eleven
one-pole circuits need 11 positions per leg. The capacity is irrelevant; the
slot reason is reported.

## Verifier

```text
$ python -m panelshift verify report.json
verify: OK
  verdict: feasible
  leg A: 159.0 A
  leg B: 160.0 A
  imbalance: 1.0 A (proved minimal)
  reachable states examined: 62
```

Tampering with one circuit's leg (20 A moved to the other leg) yields
`verify: FAIL` and exit 1, even though the loads still fit, because the report's
legs no longer match the recomputed optimum.

## Defects found and fixed during development

1. **Reconstruction inverted the leg mapping.** The DP transition that increments
   the used-position count assigns the item to leg A, but `_reconstruct` wrote
   `B` for that branch. The verifier caught it immediately as a recomputed-load
   mismatch on random panels. Fixed for both unpaired and paired items.
2. **The first workshop example was overloaded.** 110 A of two-pole base plus
   175 A of single-pole load cannot fit 160 A legs. The CLI correctly exited 1;
   the example, not the solver, was wrong. Rebalanced to a feasible 200 A panel.
3. **A test asserted 50/50 legs for a 40 A two-pole plus one 10 A single-pole
   circuit.** That is arithmetically impossible; changed to assert the true
   optimum of 50/40 A.
4. **Demo used `/tmp`,** which Git Bash and the Python interpreter resolve
   differently on Windows. Moved to a project-local `.demo-tmp` directory.
5. **Text report used non-ASCII separators** that a Windows console rendered as
   replacement characters. Switched to ASCII.

## Not run

- No comparison against a live electrical design suite (none installed).
- No three-phase testing (out of scope).
- No load-calculation validation against NEC Article 220 (the tool models
  connected leg loading only, by design).
