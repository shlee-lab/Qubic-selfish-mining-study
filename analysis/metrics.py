"""Compute the tabular values underlying the paper's empirical figures."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

import numpy as np
import pandas as pd

from data import RAW_DIR


RAW_JOBS = RAW_DIR / "qubic_pool_job_notifications.csv.gz"
RAW_JOB_COLUMNS = {
    "ts",
    "event",
    "height",
    "job_id",
    "prev_raw",
    "seed_hash",
    "target",
    "algo",
    "blob_len",
}
TARGET_BLOCK_SECONDS = 120


def validate_job_notifications_source(path: Path = RAW_JOBS) -> None:
    """Fail early if the compressed raw job log is missing or damaged."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing compressed Qubic job log: {path}"
        )
    with path.open("rb") as stream:
        if stream.read(2) != b"\x1f\x8b":
            raise ValueError(f"Expected a gzip-compressed file: {path}")

    try:
        with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
            header = next(csv.reader(stream), None)
            while stream.read(1024 * 1024):
                pass
    except (EOFError, OSError) as exc:
        raise ValueError(f"Invalid or truncated gzip file: {path}") from exc

    if header is None:
        raise ValueError(f"Compressed job log is empty: {path}")
    missing = RAW_JOB_COLUMNS.difference(header)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(
            f"Compressed job log is missing columns: {missing_text}"
        )


def parse_difficulty(value: object) -> int:
    text = str(value).strip()
    if text.startswith(("0x", "0X")):
        return int(text[2:], 16)
    return int(float(text))


def overview_tables(
    blocks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = blocks.copy()
    data["date"] = data["timestamp"].dt.floor("D")
    data["hour"] = data["timestamp"].dt.floor("h")
    data["week"] = data["timestamp"].dt.to_period("W-WED").dt.end_time
    data["difficulty_int"] = data["difficulty"].map(parse_difficulty)

    def aggregate(grouped, time_name: str) -> pd.DataFrame:
        rows = []
        for time_value, frame in grouped:
            qubic = frame["is_qubic"]
            orphan = frame["is_orphan"]
            rows.append(
                {
                    time_name: time_value,
                    "total_blocks": len(frame),
                    "qubic_blocks": int(qubic.sum()),
                    "orphan_blocks": int(orphan.sum()),
                    "qubic_orphan_blocks": int((qubic & orphan).sum()),
                    "other_orphan_blocks": int((~qubic & orphan).sum()),
                    "qubic_share": float(qubic.mean()),
                    "mean_difficulty": float(
                        frame["difficulty_int"].mean()
                    ),
                }
            )
        return pd.DataFrame(rows)

    return (
        aggregate(data.groupby("hour", sort=True), "hour"),
        aggregate(data.groupby("date", sort=True), "date"),
        aggregate(data.groupby("week", sort=True), "week"),
    )


def orphan_fork_length_tables(
    blocks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the event and weekly-bin values used in Figure 1(c).

    Figure 1(c) uses an observational sequence proxy because parent hashes
    are unavailable for many non-Qubic orphans. Consecutive orphan records
    belong to one sequence when their heights differ by one and their
    timestamps are at most five minutes apart.
    """

    orphans = blocks.loc[blocks["is_orphan"]].sort_values(
        "timestamp",
        kind="mergesort",
    )
    sequences: list[list[object]] = []
    current: list[object] = []
    for orphan in orphans.itertuples(index=False):
        if not current:
            current = [orphan]
            continue
        previous = current[-1]
        time_difference = (
            orphan.timestamp - previous.timestamp
        ).total_seconds()
        height_difference = orphan.height - previous.height
        if time_difference <= 300 and height_difference == 1:
            current.append(orphan)
        else:
            sequences.append(current)
            current = [orphan]
    if current:
        sequences.append(current)

    event_rows = []
    for event_id, sequence in enumerate(sequences, start=1):
        start = sequence[0]
        end = sequence[-1]
        length = len(sequence)
        qubic_count = sum(bool(block.is_qubic) for block in sequence)
        week = pd.Timestamp(start.timestamp).to_period(
            "W-TUE"
        ).start_time
        event_rows.append(
            {
                "event_id": event_id,
                "week": week,
                "start_timestamp": start.timestamp,
                "end_timestamp": end.timestamp,
                "duration_seconds": (
                    end.timestamp - start.timestamp
                ).total_seconds(),
                "start_height": int(start.height),
                "end_height": int(end.height),
                "fork_length": length,
                "length_bin_upper": min(length, 6),
                "length_bin_label": "6+" if length >= 6 else str(length),
                "qubic_orphan_blocks": qubic_count,
                "other_orphan_blocks": length - qubic_count,
                "contains_qubic": qubic_count > 0,
            }
        )
    events = pd.DataFrame(event_rows)

    weeks = sorted(events["week"].unique())
    weekly_index = pd.MultiIndex.from_product(
        [weeks, range(1, 7)],
        names=["week", "length_bin_upper"],
    )
    weekly = (
        events.groupby(["week", "length_bin_upper"])
        .size()
        .rename("fork_count")
        .reindex(weekly_index, fill_value=0)
        .reset_index()
    )
    weekly["length_bin_label"] = weekly["length_bin_upper"].map(
        lambda value: "6+" if value == 6 else str(value)
    )
    return events, weekly


def timestamp_differences(blocks: pd.DataFrame) -> pd.DataFrame:
    main = (
        blocks.loc[~blocks["is_orphan"]]
        .sort_values(["height", "timestamp"], kind="mergesort")
        .drop_duplicates("height")
        .set_index("height")
    )
    orphan = blocks.loc[
        blocks["is_orphan"] & blocks["is_qubic"]
    ].copy()
    orphan = orphan.join(
        main[["timestamp", "block hash"]],
        on="height",
        rsuffix="_main",
        how="inner",
    )
    orphan["time_difference_seconds"] = (
        orphan["timestamp"] - orphan["timestamp_main"]
    ).dt.total_seconds()
    return orphan[
        [
            "height",
            "block hash",
            "block hash_main",
            "timestamp",
            "timestamp_main",
            "time_difference_seconds",
        ]
    ].rename(
        columns={
            "block hash": "qubic_orphan_hash",
            "block hash_main": "main_block_hash",
            "timestamp": "qubic_orphan_timestamp",
            "timestamp_main": "main_block_timestamp",
        }
    )


def job_timing_tables(
    blocks: pd.DataFrame,
    raw_jobs_path: Path = RAW_JOBS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(raw_jobs_path)
    jobs = raw.loc[raw["event"].eq("job")].copy()
    jobs["job_timestamp"] = pd.to_datetime(
        jobs["ts"], unit="s", errors="raise"
    )
    jobs["job_prev_hash"] = jobs["prev_raw"].astype(str).str.strip()
    jobs = jobs.sort_values("job_timestamp").reset_index(drop=True)

    intervals = jobs["job_timestamp"].diff().dt.total_seconds().dropna()
    interval_table = pd.DataFrame({"interval_seconds": intervals})
    interval_table["used_for_summary"] = (
        interval_table["interval_seconds"].gt(0)
        & interval_table["interval_seconds"].le(60)
    )

    block_data = blocks.copy()
    block_data["block hash"] = (
        block_data["block hash"].astype(str).str.strip()
    )
    q_blocks = block_data.loc[block_data["is_qubic"]].copy()
    first_job = jobs["job_timestamp"].min()
    jobs_by_hash = {
        key: group.sort_values("job_timestamp")
        for key, group in jobs.groupby("job_prev_hash")
    }

    rows = []
    for _, block in q_blocks.iterrows():
        block_hash = block["block hash"]
        block_time = block["timestamp"]
        if block_time < first_job or block_hash not in jobs_by_hash:
            continue
        after = jobs_by_hash[block_hash].loc[
            jobs_by_hash[block_hash]["job_timestamp"] > block_time
        ]
        if after.empty:
            continue
        job = after.iloc[0]
        rows.append(
            {
                "height": int(block["height"]),
                "block_hash": block_hash,
                "block_timestamp": block_time,
                "job_timestamp": job["job_timestamp"],
                "delay_seconds": (
                    job["job_timestamp"] - block_time
                ).total_seconds(),
            }
        )
    delays = pd.DataFrame(rows)

    normal_intervals = interval_table.loc[
        interval_table["used_for_summary"], "interval_seconds"
    ]
    delay_values = delays["delay_seconds"] if not delays.empty else pd.Series(dtype=float)
    summary = pd.DataFrame(
        [
            {
                "job_events": len(jobs),
                "job_intervals": len(interval_table),
                "normal_job_intervals": len(normal_intervals),
                "mean_job_interval_seconds": normal_intervals.mean(),
                "std_job_interval_seconds": normal_intervals.std(ddof=0),
                "matched_blocks": len(delays),
                "mean_delay_seconds": delay_values.mean(),
                "median_delay_seconds": delay_values.median(),
                "share_within_8_seconds": (
                    float((delay_values <= 8).mean())
                    if len(delay_values)
                    else np.nan
                ),
                "share_within_16_seconds": (
                    float((delay_values <= 16).mean())
                    if len(delay_values)
                    else np.nan
                ),
            }
        ]
    )
    return interval_table, delays, summary


def weekly_tie_breaking(blocks: pd.DataFrame) -> pd.DataFrame:
    data = blocks.copy()
    data["week"] = (
        data["timestamp"]
        .dt.to_period("W-TUE")
        .apply(lambda period: period.start_time.date())
    )
    rows = []
    for week, frame in data.groupby("week", sort=True):
        total_races = 0
        honest_next = 0
        honest_extended_qubic = 0
        contested = frame["height"].value_counts()
        for height in contested[contested > 1].index:
            height_blocks = frame.loc[frame["height"].eq(height)]
            qubic_blocks = height_blocks.loc[height_blocks["is_qubic"]]
            honest_blocks = height_blocks.loc[~height_blocks["is_qubic"]]
            if len(qubic_blocks) != 1 or honest_blocks.empty:
                continue

            next_main = data.loc[
                data["height"].eq(height + 1) & ~data["is_orphan"]
            ]
            if next_main.empty:
                continue
            next_block = next_main.sort_values("timestamp").iloc[0]

            if bool(next_block["is_qubic"]):
                earliest_honest = honest_blocks["timestamp"].min()
                if next_block["timestamp"] < earliest_honest:
                    continue

            total_races += 1
            if not bool(next_block["is_qubic"]):
                honest_next += 1
                if not bool(qubic_blocks.iloc[0]["is_orphan"]):
                    honest_extended_qubic += 1

        rows.append(
            {
                "week": week,
                "alpha": float(frame["is_qubic"].mean()),
                "gamma": (
                    honest_extended_qubic / honest_next
                    if honest_next
                    else 0.0
                ),
                "total_tie_breaking_races": total_races,
                "honest_next_blocks": honest_next,
                "honest_extensions_of_qubic": honest_extended_qubic,
                "blocks": len(frame),
            }
        )
    return pd.DataFrame(rows)


def statistics_for_spans(
    blocks: pd.DataFrame,
    spans: list[tuple[pd.Timestamp, pd.Timestamp]],
    label: str,
    category: str,
) -> dict[str, object]:
    mask = pd.Series(False, index=blocks.index)
    duration_seconds = 0.0
    for start, end in spans:
        mask |= blocks["timestamp"].between(
            start, end, inclusive="left"
        )
        duration_seconds += (end - start).total_seconds()

    selected = blocks.loc[mask]
    main = selected.loc[~selected["is_orphan"]]
    expected_main = duration_seconds / TARGET_BLOCK_SECONDS
    return {
        "label": label,
        "start": min(start for start, _ in spans),
        "end": max(end for _, end in spans),
        "category": category,
        "duration_seconds": duration_seconds,
        "total_blocks": len(selected),
        "qubic_blocks": int(selected["is_qubic"].sum()),
        "alpha": float(selected["is_qubic"].mean()),
        "main_chain_blocks": len(main),
        "qubic_main_chain_blocks": int(main["is_qubic"].sum()),
        "expected_main_chain_blocks": expected_main,
        "target_rate_normalized_yield": (
            float(main["is_qubic"].sum() / expected_main)
            if expected_main
            else np.nan
        ),
        "main_chain_share": (
            float(main["is_qubic"].mean()) if len(main) else np.nan
        ),
    }


def period_revenue(
    blocks: pd.DataFrame,
    periods: pd.DataFrame,
) -> pd.DataFrame:
    spans = [
        (row.start, row.end)
        for row in periods.itertuples(index=False)
    ]
    rows = [
        statistics_for_spans(
            blocks,
            [(row.start, row.end)],
            row.period,
            "period",
        )
        for row in periods.itertuples(index=False)
    ]
    rows.append(
        statistics_for_spans(
            blocks,
            spans,
            "P1-P10",
            "aggregate_active",
        )
    )
    rows.append(
        statistics_for_spans(
            blocks,
            [(blocks["timestamp"].min(), blocks["timestamp"].max())],
            "ALL",
            "aggregate_global",
        )
    )
    return pd.DataFrame(rows)


def honest_revenue(alpha: np.ndarray) -> np.ndarray:
    return alpha


def classical_selfish_revenue(
    alpha: np.ndarray, gamma: float
) -> np.ndarray:
    numerator = (
        alpha
        * (1 - alpha) ** 2
        * (4 * alpha + gamma * (1 - 2 * alpha))
        - alpha**3
    )
    denominator = 1 - alpha * (1 + (2 - alpha) * alpha)
    return numerator / denominator


def conservative_revenue(
    alpha: np.ndarray, gamma: float
) -> np.ndarray:
    numerator = alpha * (
        -2 * alpha**3 * gamma
        + 3 * alpha**3
        + 5 * alpha**2 * gamma
        - 9 * alpha**2
        - 4 * alpha * gamma
        + 4 * alpha
        + gamma
    )
    denominator = (
        1 - alpha - 2 * alpha**2 + alpha**3 - alpha**4
    )
    return numerator / denominator


def theoretical_revenue_values(
    gamma: float = 0.0,
) -> pd.DataFrame:
    alpha = np.linspace(0.001, 0.499, 499)
    return pd.DataFrame(
        {
            "alpha": alpha,
            "honest_mining": honest_revenue(alpha),
            "classical_selfish_mining": classical_selfish_revenue(
                alpha, gamma
            ),
            "conservative_release": conservative_revenue(
                alpha, gamma
            ),
            "gamma": gamma,
        }
    )


def race_resolution(
    blocks: pd.DataFrame,
    periods: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for period in periods.itertuples(index=False):
        frame = blocks.loc[
            blocks["timestamp"].between(
                period.start, period.end, inclusive="left"
            )
        ]
        races = 0
        q_wins = 0
        contested = frame["height"].value_counts()
        for height in contested[contested > 1].index:
            height_blocks = frame.loc[frame["height"].eq(height)]
            qubic_blocks = height_blocks.loc[height_blocks["is_qubic"]]
            honest_blocks = height_blocks.loc[~height_blocks["is_qubic"]]
            if len(qubic_blocks) != 1 or honest_blocks.empty:
                continue

            next_main = blocks.loc[
                blocks["height"].eq(height + 1)
                & ~blocks["is_orphan"]
            ]
            if next_main.empty:
                continue
            next_block = next_main.sort_values("timestamp").iloc[0]
            if bool(next_block["is_qubic"]) and (
                next_block["timestamp"]
                < honest_blocks["timestamp"].min()
            ):
                continue

            races += 1
            # The miner of the next accepted block does not by itself
            # identify the winning branch.  In several early-campaign
            # events, Qubic mined the next block after abandoning its
            # competing block and switching to the accepted non-Qubic
            # branch.  Conversely, an honest miner can extend Qubic's
            # branch.  Classify the race by whether the contested Qubic
            # block at this height was accepted.
            qubic_won = not bool(qubic_blocks.iloc[0]["is_orphan"])
            if qubic_won:
                q_wins += 1

        rows.append(
            {
                "period": period.period,
                "alpha": float(frame["is_qubic"].mean()),
                "total_races": races,
                "qubic_race_wins": q_wins,
                "race_win_rate": q_wins / races if races else 0.0,
            }
        )
    return pd.DataFrame(rows)
