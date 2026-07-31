# Numerical analysis

`run_all.py` regenerates the processed attribution table and every public
result CSV without creating plots.

- `data.py` combines the node and community block datasets, parses parent
  hashes from community block blobs, and verifies parent-linked Qubic self
  forks. It also regenerates the cross-source attribution and parent-coverage
  validation tables.
- `periods.py` applies the hourly orphan-activity heuristic and constructs
  height-inclusive Qubic runs.
- `metrics.py` computes timing, tie-breaking, race, mining-share, and revenue
  tables, including the observational orphan-fork sequences used in
  Figure 1(c). The timing calculation uses the original node-derived labels
  to reproduce Figure 3; the other empirical tables use the final
  attribution.
- `sensitivity.py` reruns period detection over the 80 threshold combinations
  reported in Appendix G and exports the full grid, detected spans, summary
  subsets, and representative settings.
- `viewkey.py` parses community orphan block blobs and checks their miner
  transaction outputs against Qubic's retrospectively disclosed Monero view
  keys.
- `daa.py` replays Monero's difficulty adjustment rule for the no-slowdown
  counterfactual.

Run the entry point from the repository root:

```bash
python analysis/run_all.py
```

For a faster pass that keeps the existing DAA result files:

```bash
python analysis/run_all.py --skip-daa
```
