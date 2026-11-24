# Usage

## Install

No packaging step is required:

```bash
git clone https://github.com/Wsh7Ash/panelshift
cd panelshift
export PYTHONPATH=src
alias panelshift='PYTHONPATH=src python -m panelshift'
```

## Plan a panel

```bash
python -m panelshift plan examples/workshop.json
```

Text output lists both legs, the imbalance, the verdict, and every slot row.
Two-pole breakers appear in both columns of their row; a blank cell is `-`.

## Machine-readable report

```bash
python -m panelshift plan examples/workshop.json --format json > report.json
```

The report embeds the `input` document so it can be verified later without the
original file.

## Verify a report

```bash
python -m panelshift verify report.json
```

Exit `0` means the report's legs, loads, limits and optimum were reproduced.
Exit `1` means a contradiction (for example, a leg was moved by hand). Exit `2`
means the file is unreadable or not a valid plan.

## Diagnose an infeasible panel

```bash
python -m panelshift plan examples/impossible.json; echo $?
```

```text
Verdict: INFEASIBLE

Reasons:
  - capacity: two-pole breakers alone put 170.0 A on each leg, above the 48.0 A planning limit

Best achievable leg load with these circuits: 170.0 A
```

For a panel that is over only because of single-pole load, the reason instead
reads:

```text
  - capacity: best achievable leg load is 171.4 A against the 160.0 A planning
    limit (short by 11.4 A)
```

Slot exhaustion is reported separately:

```text
  - slots: 11 decision items plus 0 two-pole breakers need 11 positions per leg,
    panel has 4
```

## Encode a shared-neutral circuit

Both hot conductors of a multi-wire branch circuit must be on opposite legs:

```json
{"id": "kitchen-a", "amps": 20, "poles": 1, "group": "kitchen-mwbc"},
{"id": "kitchen-b", "amps": 20, "poles": 1, "group": "kitchen-mwbc"}
```

A group must contain exactly two one-pole circuits. If the group cannot be split
(for example, because the input is malformed), validation fails before solving.

## Continuous loads

```json
{"id": "ev", "amps": 16, "continuous": true, "poles": 2}
```

The reported `effective_amps` is `20.0` and both legs carry that load.

## Use as a design gate

```bash
if ! python -m panelshift plan panel.json --format json > report.json; then
  echo "panel plan does not fit" >&2
  exit 1
fi
python -m panelshift verify report.json
```

## Interpreting the certificate

| Field | Meaning |
|---|---|
| `method` | `exact-subset-sum-dp` |
| `reachable_states` | Number of reachable `(positions, load)` states examined |
| `search_complete` | Always `true`; the search enumerates all reachable states |
| `optimal_imbalance_amps` | Minimum achievable imbalance for the model |
| `best_achievable_max_leg_amps` | Best max leg load ignoring capacity, for diagnosis |
| `decision_items` | Single-pole circuits plus shared-neutral pairs |
| `two_pole_breakers` | Two-pole breakers loading both legs |

## Common input errors

| Message | Fix |
|---|---|
| `panel.spaces must be even` | Panels have two columns; use an even space count. |
| `panel.voltage must be one of 120, 240` | Only single-phase split panels are modelled. |
| `group 'x' must contain exactly two ...` | A shared-neutral group needs two one-pole circuits. |
| `circuits[i].poles must be 1 or 2` | Two-pole breakers only. |
| `at most 120 circuits are supported` | Split the panel or raise the code limit deliberately. |
