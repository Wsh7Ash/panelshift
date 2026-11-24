# Architecture

## Modules

```text
src/panelshift/
├── model.py     input dataclasses, validation, centiamp arithmetic
├── balance.py   solver, diagnostics, layout, verifier
├── report.py    text and JSON rendering
├── cli.py       argument parsing and exit codes
└── __main__.py  python -m panelshift
```

`model.py` has no dependency on the solver; `balance.py` depends only on the
model; `report.py` depends on both; `cli.py` is the only module that touches the
filesystem and stdout.

## Load arithmetic

Loads are integer **centiamps** (1 A = 100). A continuous circuit is multiplied
by 125 % with round-half-up at the centiamp level, so `12.5 A → 1563 ca` and no
binary floating point error can change a verdict.

`Panel.capacity_centiamps = floor(bus_amps × 100 × planning_factor)`, with a
small epsilon guard against float representation (e.g. `200 × 100 × 0.8`).

## Solver

Let:

- `base` = sum of effective loads of two-pole circuits (applied to both legs),
- `S` = sum of effective loads of all single-pole circuits,
- `n` = number of decision items,
- `used` = positions occupied on leg A by decision items,
- `load` = single-pole load assigned to leg A.

Then `legA = base + load`, `legB = base + (S - load)`, and the positions on leg B
are `(n - used) + two_pole_count`.

`dp[used]` is a Python integer used as a bitset: bit `load` is set when some
subset of the processed items reaches that state.

Transitions per item:

- unpaired circuit of weight `a`:
  `new[used] |= mask` (goes to leg B) and
  `new[used + 1] |= mask << a` (goes to leg A);
- shared-neutral pair of weights `a, b`:
  `new[used + 1] |= (mask << a) | (mask << b)` — the pair always consumes one
  position on each leg; only which load lands on leg A is a choice.

Selection scans every reachable state, rejects states that break capacity or
position limits, and minimizes `(|legA - legB|, max(legA, legB), used, load)`.
Because the scan is exhaustive over reachable states, the result is the exact
optimum for the modelled problem. `reachable_states` records how many states
were examined.

Reconstruction re-checks the remaining items' reachability with a fresh DP for
each step, which is `O(n²)` DP builds but keeps memory bounded. The residual
`(used, load)` must end at zero, otherwise the solver raises rather than emit an
inconsistent plan.

## Layout

Both columns start with the two-pole breakers in input order, so a two-pole
breaker aligns across the same row. Leg-A singles are appended to column A and
leg-B singles to column B. Because the position limits were enforced in the
search, each column fits by construction.

## Verification

`verify(plan, solution)` recomputes each leg from the per-circuit assignment and
checks:

- every circuit is assigned exactly once, with a valid leg (`A`, `B`, or `AB`
  for two-pole);
- recomputed leg loads equal the reported ones;
- capacity and position limits hold;
- each `group` is split `{A, B}`.

The CLI `verify` command additionally re-solves the embedded input and compares
the optimum and the claimed legs, so a hand-edited report cannot pass.

## Determinism

- No randomness, no clocks, no environment-dependent ordering.
- Items are sorted by first circuit position in the input document.
- Ties are broken by `(imbalance, max leg, used, load)`.
- JSON uses insertion-ordered keys and `indent=2`.

## Error handling

- `ConfigError` collects all document problems and is reported one per line to
  stderr, exit 2.
- Solver infeasibility is not an exception: it is a result with reasons, exit 1.
- Internal reconstruction failures raise `RuntimeError` instead of emitting a
  plan that fails verification.
