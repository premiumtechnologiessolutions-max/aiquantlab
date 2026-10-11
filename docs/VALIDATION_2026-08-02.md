# Validation Record — 2026-08-02

## Automated checks completed

- `python -m compileall -q src tests scripts` passed.
- The complete test suite passed: **333 tests**.
- Added tests cover timeframe annualization, Bonferroni correction, replay-safe Thompson
  selection, outcome/selection matching, HMM calibration evidence, genetic proposals,
  bounded model output, hard-false live authority, disconnected-MT5 health, frozen
  parameters, and absence of `order_send` calls from institutional research code.

## Runner caveat

The validation container used Python 3.13 while the project targets Python 3.12. The
container did not provide `pyarrow`, so tests were executed with an external temporary
compatibility stub for the Parquet boundary; that stub is not included in this project.
Run the following on the target Windows Python 3.12 environment to validate the real
`pyarrow` installation and static checks:

```powershell
.\.venv312\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv312\Scripts\python.exe -m pytest
.\.venv312\Scripts\ruff.exe check src tests scripts
.\.venv312\Scripts\mypy.exe src
```

`ruff` and `mypy` were not available in the validation container, so no claim is made that
those two commands were executed here.
