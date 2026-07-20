# Analysis scripts

Run all commands from the repository root after activating the venv.

The revised run analysis must be generated in this order:

```bash
python code/plot_orphan_run_length.py
python code/plot_period_orphan_blocks.py
```

`data_utils.py` performs the deterministic union of node observations and community-shared Qubic labels. The remaining paper entrypoints are:

- `plot_block_production.py`
- `plot_orphan_length.py`
- `plot_qubic_timestamp.py`
- `plot_job_block_delay.py`
- `plot_gamma.py`
- `plot_race_resolution.py`
- `plot_theory_vs_reality.py`
- `plot_withhold.py`

Supporting utilities include `analyze_periods.py` and `compare_qubic_datasets.py`. Generated intermediate CSV files remain untracked.
