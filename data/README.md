# Data

## Raw source data

| File | Description |
| --- | --- |
| `raw/node_observed_blocks.csv` | Original Monero node-observation export. It includes main-chain and locally observed orphan blocks. The attribution columns preserve the initial labels used during collection. |
| `raw/qubic_pool_job_notifications.csv.gz` | Losslessly gzip-compressed raw Qubic pool job-notification log. The analysis reads it directly without creating an unpacked copy. |
| `raw/community_observed_qubic_blocks.csv` | Qubic-related blocks collected by the Monero community from Qubic network traffic and related artifacts. Raw block blobs are retained when available. |
| `raw/qubic_disclosed_view_keys.csv` | Qubic reward addresses and private view keys disclosed retrospectively for epochs 172-185. Epoch 182 has two address-key pairs. |

The node and pool-job files were collected by the authors. The community block
dataset was shared by Monero community members
[DataHoarder](https://github.com/WeebDataHoarder) and Sergei Chernykh (sech1),
whose monitoring infrastructure observed Qubic's Computor-network traffic. The
paper explains the collection and cross-source validation procedures in
detail. Timestamps in the analysis outputs are interpreted as UTC unless a
file explicitly states otherwise.

## Processed data

| File | Description |
| --- | --- |
| `processed/attributed_blocks.csv` | Final 58,944-row analysis table. It combines node observations, community-observed hashes, and community-only orphan blocks within the observation window. |

The final attribution treats community-observed hashes as positive Qubic
labels while retaining the initial node-derived positive labels. Community-only
orphan blocks are added only when they fall inside the node table's observation
window.

## Numerical results

The files in `results/` contain the values used to construct the paper's
figures and tables. They do not contain rendered figures.

| File | Role |
| --- | --- |
| `candidate_periods.csv` | P1-P10 boundaries selected by the hourly orphan-activity heuristic |
| `hourly_orphan_activity.csv` | Hourly Qubic and non-Qubic orphan counts |
| `selfish_mining_runs.csv` | Height-inclusive Qubic run and orphan-run measurements |
| `verified_qubic_self_forks.csv` | Parent-verified same-height Qubic sibling-block events, including main/orphan and orphan/orphan pairs |
| `overview_hourly.csv`, `overview_daily.csv`, `overview_weekly.csv` | Mining-share, orphan-count, and difficulty aggregates |
| `orphan_fork_events.csv` | Event-level orphan-fork sequences used in Figure 1(c) |
| `orphan_fork_length_weekly.csv` | Weekly counts of orphan-fork sequences in length bins 1 through 5 and 6+ |
| `timestamp_differences.csv` | Qubic orphan timestamps relative to accepted blocks at the same height |
| `job_fetch_intervals.csv`, `job_block_delays.csv`, `job_timing_summary.csv` | Pool-job timing measurements |
| `weekly_tie_breaking.csv` | Weekly tie-breaking observations and gamma estimates |
| `period_revenue.csv` | Period and aggregate mining-share and yield measurements |
| `threshold_sensitivity_grid.csv` | Full 80-point period-detection threshold grid and the resulting aggregate measurements |
| `threshold_sensitivity_periods.csv` | Every period span detected under each threshold configuration |
| `threshold_sensitivity_summary.csv` | Median results for the baseline, near-baseline, threshold-at-least-two, and full-grid subsets reported in Appendix G |
| `threshold_sensitivity_selected.csv` | Seven representative threshold settings reported in Appendix G |
| `theoretical_revenue.csv` | Classical and conservative-release model predictions at gamma = 0 |
| `race_resolution.csv` | Per-period race counts and Qubic win rates |
| `daa_period_effects.csv`, `interperiod_revenue.csv`, `daa_validation.csv` | Difficulty-adjustment counterfactual results and replay validation |

The near-baseline subset uses
`min_orphans_per_hour` in `{2, 3}`, `min_duration_hours` in `{4, 6}`, and
`merge_gap_hours` in `{4, 6, 8}`, for 12 configurations. Share and yield
columns are stored as proportions rather than percentages.

For Figure 1(c), two consecutive orphan records are grouped into the same
observational fork sequence when their heights differ by one and their
timestamps are no more than 300 seconds apart. This is a sequence proxy rather
than a parent-hash proof because parent hashes are unavailable for many
non-Qubic orphan blocks. Lengths of six or more are combined in the `6+` bin.

## Attribution validation

The files in `validation/` compare the initial node-derived labels with the
community dataset over their common observation range. They separate
node-only and community-only hashes instead of treating either source as a
complete ground truth.

`community_orphan_parent_coverage.csv` reproduces the three parent-linkage
scopes reported in the paper. `community_orphan_parent_linkage.csv` contains
the corresponding orphan-level parent hash and membership checks. A parent is
known when its hash appears in either the node-observed table or the community
dataset; these two membership counts can overlap.

`view_key_address_validation.csv` verifies that each disclosed private view
key corresponds to the public view key encoded in its address.
`view_key_orphan_output_validation.csv` parses each community orphan's miner
transaction and checks its one-time output keys with the disclosed view key
and public spend key. `view_key_validation_summary.csv` reports the aggregate
and per-epoch coverage. The check applies to 1,221 orphans in epochs with a
disclosed key; seven orphan records belong to epochs for which this repository
has no disclosed key. All 93 community-only orphans inside the node
observation window are covered by a disclosed key and pass the output check.

The job-timing result files use the original node-derived Qubic labels to
reproduce Figure 3. The remaining result tables use the final attributed block
table unless their descriptions state otherwise.
