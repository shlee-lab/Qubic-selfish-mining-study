# Qubic Selfish Mining on Monero

This repository contains the public datasets and numerical analysis for:

> **Inside Qubic's Selfish Mining Campaign on Monero: Evidence, Tactics, and Limits**
>
> Suhyeon Lee and Hyeongyeong Kim | Accepted at AFT 2026 |
> [Read the paper on arXiv](https://arxiv.org/abs/2512.01437)

The study examines Qubic's 2025 Monero mining campaign using Monero node
measurements, Qubic pool job notifications, community-observed block data, and
retrospectively disclosed view keys.

## What this repository provides

- The original node, pool-job, and community datasets used in the study
- A clean 58,944-row block table with the final Qubic attribution
- The P1-P10 candidate-period boundaries and run-level measurements
- The numerical values underlying the empirical figures and tables
- A deterministic pipeline that regenerates the processed data and results

The public code intentionally stops at numerical data products. It does not
render figures or include the manuscript, internal review material, or the
interactive inspection tools used during the study.

## Quick start

The pipeline was tested with Python 3.12. In addition to NumPy and pandas, the
view-key validation uses the Monero Python library and its pinned cryptographic
dependencies.

```bash
git clone https://github.com/shlee-lab/Qubic-selfish-mining-study.git
cd Qubic-selfish-mining-study

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python analysis/run_all.py
```

On a typical desktop, the complete run takes about three minutes. Most of that
time is spent replaying Monero's difficulty adjustment for the counterfactual
analysis.

For a faster pass that regenerates everything except the DAA replay:

```bash
python analysis/run_all.py --skip-daa
```

The fast pass takes approximately 15 seconds and keeps the existing DAA result
files unchanged.

## Expected checks

A successful run ends with `Reproduction checks passed.` and verifies:

| Check | Expected value |
| --- | ---: |
| Blocks in the final attributed table | 58,944 |
| Qubic-attributed blocks | 13,782 |
| Candidate periods | 10 |
| Period-threshold configurations | 80 |
| Configurations with target yield below alpha | 80 |
| Community Qubic orphan parents found | 1,218 / 1,228 |
| View-key-eligible community orphans verified | 1,221 / 1,221 |
| Orphan-fork sequences in Figure 1(c) | 2,495 |
| Parent-verified Qubic self forks | 11 |
| Blocks in the job-timing analysis | 2,884 |
| Mean delay to the next job fetch | 5.61 seconds |

The pipeline first validates the compressed pool-job log, then rewrites
`data/processed/attributed_blocks.csv` and the CSV files in `data/results/`
and `data/validation/`.

## Repository layout

| Path | Contents |
| --- | --- |
| `analysis/` | Attribution, period detection, timing, revenue, race, and DAA calculations |
| `data/raw/` | Original node observations, pool job notifications, and community-observed blocks |
| `data/processed/` | Final attributed block table |
| `data/results/` | Numerical values underlying the paper's figures and tables |
| `data/validation/` | Cross-source attribution comparisons and unmatched-hash records |

See [`data/README.md`](data/README.md) for provenance and a file-by-file
description.

## Paper results and corresponding files

| Paper item | Public numerical output |
| --- | --- |
| Figure 1: campaign overview | `overview_hourly.csv`, `overview_daily.csv`, `overview_weekly.csv`, `hourly_orphan_activity.csv`, `orphan_fork_events.csv`, `orphan_fork_length_weekly.csv` |
| Figure 2: timestamp differences | `timestamp_differences.csv` |
| Figure 3: job-fetch delay | `job_fetch_intervals.csv`, `job_block_delays.csv`, `job_timing_summary.csv` |
| Figure 4: Qubic runs and orphan blocks | `candidate_periods.csv`, `selfish_mining_runs.csv`, `verified_qubic_self_forks.csv` |
| Parent-linkage validation table | `community_orphan_parent_coverage.csv`, `community_orphan_parent_linkage.csv` |
| View-key ownership validation | `view_key_address_validation.csv`, `view_key_orphan_output_validation.csv`, `view_key_validation_summary.csv` |
| Appendix G: period-threshold sensitivity | `threshold_sensitivity_grid.csv`, `threshold_sensitivity_periods.csv`, `threshold_sensitivity_summary.csv`, `threshold_sensitivity_selected.csv` |
| Figure 7: tie-breaking observations | `weekly_tie_breaking.csv` |
| Figure 8: models and observed revenue | `theoretical_revenue.csv`, `period_revenue.csv` |
| Figure 9: race outcomes | `race_resolution.csv` |
| Figure 10: difficulty-adjustment spillovers | `daa_period_effects.csv`, `interperiod_revenue.csv`, `daa_validation.csv` |

Figure and sensitivity outputs are relative to `data/results/`. Parent-linkage
outputs are relative to `data/validation/`.

## Attribution in brief

Monero blocks do not expose a conventional mining-pool identifier. The study
therefore combines several sources:

1. Initial Qubic candidates derived from orphan-fork observations and two
   extra-nonce patterns
2. Community-observed Qubic block hashes collected independently from Qubic
   network traffic and related artifacts
3. Retrospective verification using Qubic's disclosed view keys where the
   required coinbase data were available

The final table treats community-observed hashes as positive Qubic labels while
retaining the initial node-derived positive labels. It also adds community-only
orphan blocks that fall inside the node table's observation window. The
cross-source differences are preserved in `data/validation/` rather than being
silently discarded.

## Reproducibility notes

- `analysis/run_all.py` is the single public entry point.
- The scripts create CSV data only; no plotting package is required.
- Result files are deterministic for the included source data and dependency
  versions.
- The job-timing measurement uses the original node-derived Qubic labels,
  matching the analysis reported in Figure 3. The final attributed table uses
  the later community augmentation.
- The DAA analysis is a no-slowdown counterfactual replay, not an exact
  reconstruction of Qubic's private strategy.
- The community dataset is an independent observation source, not assumed to
  be a complete Qubic-provided ground truth.

For questions about the data or reproduction procedure, please open a GitHub
issue with the command used and the relevant output.
