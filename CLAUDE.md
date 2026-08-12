# Working in this repo

- **Always exercise a change against real data before calling it done.** Run
  the pytest suite (`pytest`) and, for anything touching the profiling
  engine or the HTML report, also run it against a synthetic DataFrame or
  `example.py` and check the actual output — not just that it imports or
  type-checks cleanly. Several real bugs in this codebase (a purity-metric
  flaw in functional-dependency detection, a PII false positive on
  continuous numeric columns) were only caught by running real data through
  the profiler, not by reading the code.
- Package code lives under `src/datascope/`. Install with `pip install -e .[dev]`
  before running tests or `example.py`.
