# Contributing

## Development loop

```bash
export PYTHONPATH=src
python -m unittest discover -s tests -v
bash scripts/demo.sh
```

There is no build step and no runtime dependency to install.

## Expectations

- Keep the solver deterministic. Do not introduce randomness, clocks, or
  environment-dependent iteration order.
- Keep load arithmetic in integer centiamps. If a new multiplier is needed,
  extend the centiamp helpers rather than switching to floats.
- Any change to the solver must keep the brute-force oracle test green.
- A new input rule needs a validation test; a new constraint needs both a
  positive test and an infeasibility/diagnosis test.
- Update `RESULTS.md` with the command output you actually observed.
- Do not claim code compliance. This is a planning tool.

## Reporting a bug

Include the input JSON, the command, the observed exit code, and the full report
or traceback. If the issue is an electrical modelling assumption rather than a
code defect, state the assumption you expected.
