#!/usr/bin/env python3
"""Regenerate all public processed datasets and numerical result tables."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data import (
    ATTRIBUTED_BLOCKS,
    NODE_BLOCKS,
    ROOT,
    VALIDATION_DIR,
    attribution_validation_tables,
    coerce_bool,
    parent_linkage_validation_tables,
    verified_qubic_self_fork_heights,
    write_attributed_blocks,
)
from daa import compute_daa_results
from metrics import (
    job_timing_tables,
    orphan_fork_length_tables,
    overview_tables,
    period_revenue,
    race_resolution,
    theoretical_revenue_values,
    timestamp_differences,
    validate_job_notifications_source,
    weekly_tie_breaking,
)
from periods import build_orphan_runs, detect_periods, normalize_blocks
from sensitivity import threshold_sensitivity_tables
from viewkey import view_key_validation_tables


RESULTS = ROOT / "data" / "results"
PROCESSED = ROOT / "data" / "processed"


def write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"{path.relative_to(ROOT)}: {len(frame):,} rows")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-daa",
        action="store_true",
        help="Regenerate all results except the slower DAA replay.",
    )
    args = parser.parse_args()

    validate_job_notifications_source()
    attributed = write_attributed_blocks(ATTRIBUTED_BLOCKS)
    blocks = normalize_blocks(attributed)
    node_blocks = pd.read_csv(NODE_BLOCKS)
    node_blocks["is_orphan"] = coerce_bool(node_blocks["is_orphan"])
    node_blocks["is_qubic"] = coerce_bool(node_blocks["is_qubic"])
    node_blocks = normalize_blocks(node_blocks)

    validation = attribution_validation_tables()
    for filename, frame in validation.items():
        write(frame, VALIDATION_DIR / filename)
    parent_validation = parent_linkage_validation_tables()
    for filename, frame in parent_validation.items():
        write(frame, VALIDATION_DIR / filename)
    view_key_validation = view_key_validation_tables()
    for filename, frame in view_key_validation.items():
        write(frame, VALIDATION_DIR / filename)

    periods, hourly_orphans = detect_periods(blocks)
    write(periods, RESULTS / "candidate_periods.csv")
    write(hourly_orphans, RESULTS / "hourly_orphan_activity.csv")

    self_fork_heights = sorted(
        verified_qubic_self_fork_heights(attributed)
    )
    self_forks = pd.DataFrame({"height": self_fork_heights})
    write(self_forks, RESULTS / "verified_qubic_self_forks.csv")

    runs = build_orphan_runs(blocks)
    runs["period"] = pd.NA
    for period in periods.itertuples(index=False):
        mask = runs["start_ts"].between(
            period.start, period.end, inclusive="left"
        )
        runs.loc[mask, "period"] = period.period
    runs["verified_self_fork_count"] = runs.apply(
        lambda row: sum(
            row["start_height"] <= height <= row["end_height"]
            for height in self_fork_heights
        ),
        axis=1,
    )
    runs["release_inference_eligible"] = (
        runs["verified_self_fork_count"] == 0
    )
    write(runs, RESULTS / "selfish_mining_runs.csv")

    hourly, daily, weekly = overview_tables(blocks)
    write(hourly, RESULTS / "overview_hourly.csv")
    write(daily, RESULTS / "overview_daily.csv")
    write(weekly, RESULTS / "overview_weekly.csv")
    fork_events, fork_weekly = orphan_fork_length_tables(blocks)
    write(fork_events, RESULTS / "orphan_fork_events.csv")
    write(
        fork_weekly,
        RESULTS / "orphan_fork_length_weekly.csv",
    )

    write(
        timestamp_differences(blocks),
        RESULTS / "timestamp_differences.csv",
    )
    # Reproduce the paper's timing measurement using the Qubic labels in
    # the original node observations. The later community augmentation is
    # used for the final attribution table and the other analyses.
    intervals, delays, timing_summary = job_timing_tables(node_blocks)
    write(intervals, RESULTS / "job_fetch_intervals.csv")
    write(delays, RESULTS / "job_block_delays.csv")
    write(timing_summary, RESULTS / "job_timing_summary.csv")

    write(
        weekly_tie_breaking(blocks),
        RESULTS / "weekly_tie_breaking.csv",
    )
    revenue = period_revenue(blocks, periods)
    write(revenue, RESULTS / "period_revenue.csv")
    sensitivity = threshold_sensitivity_tables(blocks, periods)
    for filename, frame in sensitivity.items():
        write(frame, RESULTS / filename)
    write(
        theoretical_revenue_values(),
        RESULTS / "theoretical_revenue.csv",
    )
    race_results = race_resolution(blocks, periods)
    write(race_results, RESULTS / "race_resolution.csv")
    if not args.skip_daa:
        daa_effects, interperiod, daa_validation = compute_daa_results(
            blocks, revenue
        )
        write(daa_effects, RESULTS / "daa_period_effects.csv")
        write(interperiod, RESULTS / "interperiod_revenue.csv")
        write(daa_validation, RESULTS / "daa_validation.csv")

    expected = {
        "attributed_blocks": 58_944,
        "qubic_blocks": 13_782,
        "candidate_periods": 10,
        "verified_self_forks": 11,
        "job_timing_matches": 2_884,
        "community_only_overlap": 782,
        "node_only_overlap": 11,
        "race_events": 1_711,
        "qubic_branch_wins": 615,
        "threshold_grid_points": 80,
        "threshold_grid_below_alpha": 80,
        "community_orphan_parent_records": 1_228,
        "community_orphan_parents_known": 1_218,
        "window_orphan_parents_known": 1_213,
        "node_observed_orphan_parents_known": 1_123,
        "orphan_fork_events": 2_495,
        "orphan_blocks_in_fork_events": 3_006,
        "maximum_orphan_fork_length": 9,
        "weekly_orphan_fork_rows": 72,
        "weekly_orphan_fork_count": 2_495,
        "orphan_forks_in_6_plus_bin": 12,
        "disclosed_view_key_pairs": 15,
        "disclosed_view_key_address_matches": 15,
        "parsed_community_orphan_blobs": 1_228,
        "miner_transaction_height_matches": 1_228,
        "view_key_eligible_orphans": 1_221,
        "view_key_verified_orphans": 1_221,
        "orphans_without_disclosed_view_key": 7,
        "community_only_view_key_verified_orphans": 93,
    }
    parent_coverage = parent_validation[
        "community_orphan_parent_coverage.csv"
    ].set_index("scope")
    observed = {
        "attributed_blocks": len(attributed),
        "qubic_blocks": int(attributed["is_qubic"].sum()),
        "candidate_periods": len(periods),
        "verified_self_forks": len(self_forks),
        "job_timing_matches": len(delays),
        "community_only_overlap": len(
            validation["community_only_qubic_blocks_overlap.csv"]
        ),
        "node_only_overlap": len(
            validation["node_only_qubic_blocks_overlap.csv"]
        ),
        "race_events": int(race_results["total_races"].sum()),
        "qubic_branch_wins": int(
            race_results["qubic_race_wins"].sum()
        ),
        "threshold_grid_points": len(
            sensitivity["threshold_sensitivity_grid.csv"]
        ),
        "threshold_grid_below_alpha": int(
            sensitivity["threshold_sensitivity_grid.csv"][
                "yield_minus_alpha"
            ]
            .lt(0)
            .sum()
        ),
        "community_orphan_parent_records": len(
            parent_validation["community_orphan_parent_linkage.csv"]
        ),
        "community_orphan_parents_known": int(
            parent_coverage.loc[
                "all_community_qubic_orphans", "parent_known"
            ]
        ),
        "window_orphan_parents_known": int(
            parent_coverage.loc[
                "orphans_in_node_observation_window",
                "parent_known",
            ]
        ),
        "node_observed_orphan_parents_known": int(
            parent_coverage.loc[
                "orphans_also_observed_by_nodes", "parent_known"
            ]
        ),
        "orphan_fork_events": len(fork_events),
        "orphan_blocks_in_fork_events": int(
            fork_events["fork_length"].sum()
        ),
        "maximum_orphan_fork_length": int(
            fork_events["fork_length"].max()
        ),
        "weekly_orphan_fork_rows": len(fork_weekly),
        "weekly_orphan_fork_count": int(
            fork_weekly["fork_count"].sum()
        ),
        "orphan_forks_in_6_plus_bin": int(
            fork_weekly.loc[
                fork_weekly["length_bin_upper"].eq(6),
                "fork_count",
            ].sum()
        ),
        "disclosed_view_key_pairs": len(
            view_key_validation["view_key_address_validation.csv"]
        ),
        "disclosed_view_key_address_matches": int(
            view_key_validation[
                "view_key_address_validation.csv"
            ]["private_view_key_matches_address"].sum()
        ),
        "parsed_community_orphan_blobs": int(
            view_key_validation[
                "view_key_orphan_output_validation.csv"
            ]["parse_error"].isna().sum()
        ),
        "miner_transaction_height_matches": int(
            (
                view_key_validation[
                    "view_key_orphan_output_validation.csv"
                ]["height"]
                == view_key_validation[
                    "view_key_orphan_output_validation.csv"
                ]["miner_tx_height"]
            ).sum()
        ),
        "view_key_eligible_orphans": int(
            view_key_validation[
                "view_key_orphan_output_validation.csv"
            ]["has_disclosed_view_key"].sum()
        ),
        "view_key_verified_orphans": int(
            view_key_validation[
                "view_key_orphan_output_validation.csv"
            ]["view_key_verified"].sum()
        ),
        "orphans_without_disclosed_view_key": int(
            (
                ~view_key_validation[
                    "view_key_orphan_output_validation.csv"
                ]["has_disclosed_view_key"]
            ).sum()
        ),
        "community_only_view_key_verified_orphans": int(
            view_key_validation[
                "view_key_orphan_output_validation.csv"
            ]
            .loc[
                lambda frame: (
                    ~frame["orphan_observed_by_node"]
                    & frame["in_node_observation_window"]
                ),
                "view_key_verified",
            ]
            .sum()
        ),
    }
    if observed != expected:
        raise AssertionError(
            f"Reproduction checks failed: expected={expected}, "
            f"observed={observed}"
        )
    timing = timing_summary.iloc[0]
    expected_timing = {
        "mean_job_interval_seconds": 7.74,
        "std_job_interval_seconds": 1.46,
        "mean_delay_seconds": 5.61,
        "share_within_8_seconds": 86.30,
        "share_within_16_seconds": 99.97,
    }
    observed_timing = {
        "mean_job_interval_seconds": round(
            float(timing["mean_job_interval_seconds"]), 2
        ),
        "std_job_interval_seconds": round(
            float(timing["std_job_interval_seconds"]), 2
        ),
        "mean_delay_seconds": round(
            float(timing["mean_delay_seconds"]), 2
        ),
        "share_within_8_seconds": round(
            100 * float(timing["share_within_8_seconds"]), 2
        ),
        "share_within_16_seconds": round(
            100 * float(timing["share_within_16_seconds"]), 2
        ),
    }
    if observed_timing != expected_timing:
        raise AssertionError(
            "Timing checks failed: "
            f"expected={expected_timing}, observed={observed_timing}"
        )
    baseline_sensitivity = sensitivity[
        "threshold_sensitivity_selected.csv"
    ].loc[lambda frame: frame["setting"].eq("baseline")].iloc[0]
    expected_baseline_sensitivity = {
        "period_count": 10,
        "total_duration_hours": 430.0,
        "alpha_percent": 28.33,
        "target_yield_percent": 25.11,
        "yield_minus_alpha_pp": -3.22,
    }
    observed_baseline_sensitivity = {
        "period_count": int(baseline_sensitivity["period_count"]),
        "total_duration_hours": float(
            baseline_sensitivity["total_duration_hours"]
        ),
        "alpha_percent": round(
            100 * float(baseline_sensitivity["alpha"]), 2
        ),
        "target_yield_percent": round(
            100
            * float(
                baseline_sensitivity[
                    "target_rate_normalized_yield"
                ]
            ),
            2,
        ),
        "yield_minus_alpha_pp": round(
            100 * float(baseline_sensitivity["yield_minus_alpha"]),
            2,
        ),
    }
    if observed_baseline_sensitivity != expected_baseline_sensitivity:
        raise AssertionError(
            "Threshold-sensitivity checks failed: "
            f"expected={expected_baseline_sensitivity}, "
            f"observed={observed_baseline_sensitivity}"
        )
    print("Reproduction checks passed.")
    print(
        f"{ATTRIBUTED_BLOCKS.relative_to(ROOT)}: "
        f"{len(attributed):,} rows"
    )


if __name__ == "__main__":
    main()
