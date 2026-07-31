"""Reproduce the threshold-sensitivity analysis reported in Appendix G."""

from __future__ import annotations

from itertools import product

import pandas as pd

from metrics import period_revenue
from periods import PERIOD_CONFIG, detect_periods


THRESHOLD_GRID = {
    "min_orphans_per_hour": (1, 2, 3, 4),
    "min_duration_hours": (2, 4, 6, 8),
    "merge_gap_hours": (2, 4, 6, 8, 12),
}

# The near-baseline subset varies each default upward or by one adjacent
# grid step: tau in {2, 3}, duration in {4, 6}, and gap in {4, 6, 8}.
NEAR_BASELINE_GRID = {
    "min_orphans_per_hour": (2, 3),
    "min_duration_hours": (4, 6),
    "merge_gap_hours": (4, 6, 8),
}

SELECTED_CONFIGS = {
    (1, 4, 6): "loose_threshold",
    (2, 2, 6): "short_duration",
    (2, 4, 2): "small_merge_gap",
    (2, 4, 6): "baseline",
    (2, 8, 6): "long_duration",
    (3, 4, 6): "higher_threshold",
    (4, 4, 6): "strict_threshold",
}


def covered_hours(periods: pd.DataFrame) -> set[pd.Timestamp]:
    """Return the complete set of hourly bins covered by period spans."""

    result: set[pd.Timestamp] = set()
    for period in periods.itertuples(index=False):
        result.update(
            pd.date_range(
                period.start,
                period.end - pd.Timedelta(hours=1),
                freq="h",
            )
        )
    return result


def config_mask(
    grid: pd.DataFrame,
    values: dict[str, tuple[int, ...]],
) -> pd.Series:
    mask = pd.Series(True, index=grid.index)
    for column, allowed in values.items():
        mask &= grid[column].isin(allowed)
    return mask


def summarize_subset(
    grid: pd.DataFrame,
    label: str,
    mask: pd.Series,
) -> dict[str, object]:
    subset = grid.loc[mask]
    median_columns = [
        "period_count",
        "total_duration_hours",
        "alpha",
        "target_rate_normalized_yield",
        "yield_minus_alpha",
        "main_chain_share",
        "baseline_hour_recall",
        "baseline_hour_extra_ratio",
    ]
    row: dict[str, object] = {
        "subset": label,
        "configurations": len(subset),
    }
    row.update(
        {
            column: float(subset[column].median())
            for column in median_columns
        }
    )
    row["configurations_below_alpha"] = int(
        subset["yield_minus_alpha"].lt(0).sum()
    )
    return row


def threshold_sensitivity_tables(
    blocks: pd.DataFrame,
    baseline_periods: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the 80-point period-threshold grid and return public tables."""

    if baseline_periods is None:
        baseline_periods, _ = detect_periods(blocks)
    baseline_hours = covered_hours(baseline_periods)
    if not baseline_hours:
        raise ValueError("The baseline period detector returned no hours.")

    grid_rows: list[dict[str, object]] = []
    period_frames: list[pd.DataFrame] = []
    for threshold, duration, gap in product(
        THRESHOLD_GRID["min_orphans_per_hour"],
        THRESHOLD_GRID["min_duration_hours"],
        THRESHOLD_GRID["merge_gap_hours"],
    ):
        config = {
            "min_orphans_per_hour": threshold,
            "min_duration_hours": duration,
            "merge_gap_hours": gap,
        }
        periods, _ = detect_periods(blocks, config)
        if periods.empty:
            raise ValueError(f"Threshold configuration returned no periods: {config}")

        config_id = f"t{threshold}_d{duration}_g{gap}"
        period_frame = periods.copy()
        period_frame.insert(0, "config_id", config_id)
        period_frame.insert(1, "min_orphans_per_hour", threshold)
        period_frame.insert(2, "min_duration_hours", duration)
        period_frame.insert(3, "merge_gap_hours", gap)
        period_frames.append(period_frame)

        revenue = period_revenue(blocks, periods)
        aggregate = revenue.loc[
            revenue["category"].eq("aggregate_active")
        ].iloc[0]
        hours = covered_hours(periods)
        overlap = len(hours & baseline_hours)
        union = len(hours | baseline_hours)
        grid_rows.append(
            {
                "config_id": config_id,
                **config,
                "period_count": len(periods),
                "total_duration_hours": float(
                    periods["duration_hours"].sum()
                ),
                "total_blocks": int(aggregate["total_blocks"]),
                "main_chain_blocks": int(
                    aggregate["main_chain_blocks"]
                ),
                "expected_main_chain_blocks": float(
                    aggregate["expected_main_chain_blocks"]
                ),
                "qubic_blocks": int(aggregate["qubic_blocks"]),
                "qubic_main_chain_blocks": int(
                    aggregate["qubic_main_chain_blocks"]
                ),
                "alpha": float(aggregate["alpha"]),
                "target_rate_normalized_yield": float(
                    aggregate["target_rate_normalized_yield"]
                ),
                "yield_minus_alpha": float(
                    aggregate["target_rate_normalized_yield"]
                    - aggregate["alpha"]
                ),
                "main_chain_share": float(
                    aggregate["main_chain_share"]
                ),
                "baseline_hour_jaccard": overlap / union,
                "baseline_hour_recall": overlap / len(baseline_hours),
                "baseline_hour_extra_ratio": (
                    len(hours - baseline_hours) / len(baseline_hours)
                ),
            }
        )

    grid = pd.DataFrame(grid_rows)
    baseline_mask = (
        grid["min_orphans_per_hour"].eq(
            PERIOD_CONFIG["min_orphans_per_hour"]
        )
        & grid["min_duration_hours"].eq(
            PERIOD_CONFIG["min_duration_hours"]
        )
        & grid["merge_gap_hours"].eq(
            PERIOD_CONFIG["merge_gap_hours"]
        )
    )
    summary = pd.DataFrame(
        [
            summarize_subset(grid, "baseline", baseline_mask),
            summarize_subset(
                grid,
                "near_baseline",
                config_mask(grid, NEAR_BASELINE_GRID),
            ),
            summarize_subset(
                grid,
                "min_orphans_per_hour_at_least_2",
                grid["min_orphans_per_hour"].ge(2),
            ),
            summarize_subset(
                grid,
                "all_grid",
                pd.Series(True, index=grid.index),
            ),
        ]
    )

    selected_keys = pd.MultiIndex.from_tuples(
        SELECTED_CONFIGS,
        names=[
            "min_orphans_per_hour",
            "min_duration_hours",
            "merge_gap_hours",
        ],
    )
    selected = (
        grid.set_index(list(selected_keys.names))
        .loc[selected_keys]
        .reset_index()
    )
    selected.insert(
        0,
        "setting",
        [SELECTED_CONFIGS[key] for key in SELECTED_CONFIGS],
    )

    return {
        "threshold_sensitivity_grid.csv": grid,
        "threshold_sensitivity_periods.csv": pd.concat(
            period_frames,
            ignore_index=True,
        ),
        "threshold_sensitivity_summary.csv": summary,
        "threshold_sensitivity_selected.csv": selected,
    }
