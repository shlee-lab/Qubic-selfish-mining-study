"""Detect candidate activity periods and construct Qubic orphan runs."""

from __future__ import annotations

import numpy as np
import pandas as pd


PERIOD_CONFIG = {
    "min_orphans_per_hour": 2,
    "min_duration_hours": 4,
    "merge_gap_hours": 6,
}


def normalize_blocks(blocks: pd.DataFrame) -> pd.DataFrame:
    result = blocks.copy()
    result["timestamp"] = pd.to_datetime(
        result["timestamp"], utc=True, errors="raise"
    ).dt.tz_convert(None)
    result["height"] = pd.to_numeric(
        result["height"], errors="raise"
    ).astype("int64")
    result["is_orphan"] = result["is_orphan"].astype(bool)
    result["is_qubic"] = result["is_qubic"].astype(bool)
    return result


def hourly_orphan_counts(
    blocks: pd.DataFrame,
) -> tuple[pd.DatetimeIndex, pd.Series, pd.Series]:
    orphan = blocks.loc[blocks["is_orphan"]].copy()
    orphan["hour"] = orphan["timestamp"].dt.floor("h")
    qubic = (
        orphan.loc[orphan["is_qubic"]]
        .groupby("hour")
        .size()
        .rename("qubic_orphans")
    )
    other = (
        orphan.loc[~orphan["is_qubic"]]
        .groupby("hour")
        .size()
        .rename("other_orphans")
    )
    observed = qubic.index.union(other.index).sort_values()
    if len(observed):
        index = pd.date_range(observed.min(), observed.max(), freq="h")
    else:
        index = observed
    return (
        index,
        qubic.reindex(index, fill_value=0),
        other.reindex(index, fill_value=0),
    )


def detect_contiguous_segments(
    index: pd.DatetimeIndex,
    counts: pd.Series,
    min_count: int,
    min_duration_hours: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    mask = (counts >= min_count).to_numpy(dtype=bool)
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start: int | None = None
    for idx, active in enumerate(mask):
        if active and start is None:
            start = idx
        is_last = idx == len(mask) - 1
        if start is not None and ((not active) or is_last):
            end_idx = idx if is_last and active else idx - 1
            duration = end_idx - start + 1
            if duration >= min_duration_hours:
                spans.append(
                    (index[start], index[end_idx] + pd.Timedelta(hours=1))
                )
            start = None
    return spans


def merge_segments(
    spans: list[tuple[pd.Timestamp, pd.Timestamp]],
    max_gap_hours: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if not spans:
        return []
    gap = pd.Timedelta(hours=max_gap_hours)
    merged = [spans[0]]
    for start, end in spans[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= gap:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def detect_periods(
    blocks: pd.DataFrame,
    config: dict[str, int] = PERIOD_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    index, qubic, other = hourly_orphan_counts(blocks)
    total = qubic + other
    raw = detect_contiguous_segments(
        index,
        total,
        min_count=config["min_orphans_per_hour"],
        min_duration_hours=config["min_duration_hours"],
    )
    merged = merge_segments(raw, config["merge_gap_hours"])
    periods = pd.DataFrame(
        [
            {
                "period": f"P{idx}",
                "start": start,
                "end": end,
                "duration_hours": (end - start).total_seconds() / 3600,
            }
            for idx, (start, end) in enumerate(merged, start=1)
        ]
    )
    hourly = pd.DataFrame(
        {
            "hour": index,
            "qubic_orphans": qubic.to_numpy(),
            "other_orphans": other.to_numpy(),
            "total_orphans": total.to_numpy(),
        }
    )
    return periods, hourly


def build_q_main(blocks: pd.DataFrame) -> pd.DataFrame:
    main = blocks.loc[
        ~blocks["is_orphan"], ["height", "timestamp", "is_qubic"]
    ].copy()
    return (
        main.sort_values(["height", "timestamp"], kind="mergesort")
        .groupby("height", as_index=False)
        .first()
        .sort_values("timestamp", kind="mergesort")
        .reset_index(drop=True)
    )


def build_orphan_runs(blocks: pd.DataFrame) -> pd.DataFrame:
    """Build consecutive orphan runs whose accepted block is Qubic."""

    main = build_q_main(blocks)
    main_by_height = main.set_index("height")
    orphan = blocks.loc[
        blocks["is_orphan"], ["height", "timestamp"]
    ].copy()
    orphan = (
        orphan.sort_values(["height", "timestamp"], kind="mergesort")
        .groupby("height", as_index=False)
        .first()
    )
    orphan = orphan.join(
        main_by_height[["is_qubic"]],
        on="height",
        how="left",
    )
    orphan = orphan.loc[orphan["is_qubic"]].sort_values("height").copy()
    if orphan.empty:
        return pd.DataFrame(
            columns=[
                "start_height",
                "end_height",
                "length_qubic_run",
                "total_orphans_on_run",
                "max_consecutive_orphan_heights",
                "start_ts",
                "end_ts",
            ]
        )

    heights = orphan["height"].to_numpy(dtype="int64")
    group_id = np.cumsum(
        np.diff(heights, prepend=heights[0] - 1) != 1
    )
    runs = (
        orphan.assign(group_id=group_id)
        .groupby("group_id", as_index=False)
        .agg(
            start_height=("height", "min"),
            end_height=("height", "max"),
            total_orphans_on_run=("height", "size"),
            end_ts=("timestamp", "max"),
        )
    )
    runs["max_consecutive_orphan_heights"] = runs[
        "total_orphans_on_run"
    ]

    main_indexed = main.set_index("height")
    runs["start_ts"] = (
        main_indexed.reindex(runs["start_height"] - 1)["timestamp"]
        .reset_index(drop=True)
    )

    q_main = main.loc[main["is_qubic"], ["height", "timestamp"]].copy()
    lengths: list[int] = []
    for run in runs.itertuples(index=False):
        in_time = q_main.loc[
            (q_main["timestamp"] > run.start_ts)
            & (q_main["timestamp"] <= run.end_ts),
            "height",
        ]
        at_contested_height = q_main.loc[
            q_main["height"].between(run.start_height, run.end_height),
            "height",
        ]
        lengths.append(
            len(set(in_time.astype(int)) | set(at_contested_height.astype(int)))
        )
    runs["length_qubic_run"] = lengths

    return runs[
        [
            "start_height",
            "end_height",
            "length_qubic_run",
            "total_orphans_on_run",
            "max_consecutive_orphan_heights",
            "start_ts",
            "end_ts",
        ]
    ].sort_values(["start_height", "end_height"])
