"""Compute the Monero difficulty-adjustment counterfactual used in the paper."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from metrics import TARGET_BLOCK_SECONDS, parse_difficulty


DIFFICULTY_WINDOW = 720
DIFFICULTY_LAG = 15
DIFFICULTY_CUT = 60
DIFFICULTY_BLOCKS_COUNT = DIFFICULTY_WINDOW + DIFFICULTY_LAG


@dataclass(frozen=True)
class Period:
    label: str
    start: pd.Timestamp
    end: pd.Timestamp
    alpha: float
    observed_yield: float
    qubic_main_blocks: int
    total_main_blocks: int
    expected_main_blocks: float


def periods_from_results(results: pd.DataFrame) -> list[Period]:
    periods = []
    for row in results.loc[
        results["category"].eq("period")
    ].itertuples(index=False):
        periods.append(
            Period(
                label=str(row.label),
                start=pd.Timestamp(row.start),
                end=pd.Timestamp(row.end),
                alpha=float(row.alpha),
                observed_yield=float(
                    row.target_rate_normalized_yield
                ),
                qubic_main_blocks=int(row.qubic_main_chain_blocks),
                total_main_blocks=int(row.main_chain_blocks),
                expected_main_blocks=float(
                    row.expected_main_chain_blocks
                ),
            )
        )
    return periods


def next_difficulty(
    timestamps: list[int],
    cumulative_difficulties: list[int],
) -> int:
    """Reproduce Monero's HF2+ next-difficulty rule at a 120 s target."""

    if len(timestamps) > DIFFICULTY_WINDOW:
        timestamps = timestamps[:DIFFICULTY_WINDOW]
        cumulative_difficulties = cumulative_difficulties[
            :DIFFICULTY_WINDOW
        ]
    length = len(timestamps)
    if length <= 1:
        return 1

    sorted_timestamps = sorted(int(value) for value in timestamps)
    accounted = DIFFICULTY_WINDOW - 2 * DIFFICULTY_CUT
    if length <= accounted:
        cut_begin = 0
        cut_end = length
    else:
        cut_begin = (length - accounted + 1) // 2
        cut_end = cut_begin + accounted

    time_span = (
        sorted_timestamps[cut_end - 1] - sorted_timestamps[cut_begin]
    )
    if time_span == 0:
        time_span = 1
    total_work = (
        int(cumulative_difficulties[cut_end - 1])
        - int(cumulative_difficulties[cut_begin])
    )
    if total_work <= 0:
        return 1
    return (
        total_work * TARGET_BLOCK_SECONDS + time_span - 1
    ) // time_span


def prepare_blocks(blocks: pd.DataFrame) -> pd.DataFrame:
    data = blocks.copy()
    data["ts"] = (
        data["timestamp"].astype("int64") // 10**9
    ).astype(int)
    data["difficulty_int"] = data["difficulty"].map(
        parse_difficulty
    ).astype("int64")
    return data.sort_values(["timestamp", "height"]).reset_index(
        drop=True
    )


def synthetic_slots(
    periods: list[Period],
    main: pd.DataFrame,
    only_label: str | None = None,
) -> pd.DataFrame:
    rows = []
    for period in periods:
        if only_label is not None and period.label != only_label:
            continue
        missing = int(
            round(
                max(
                    0.0,
                    period.expected_main_blocks
                    - period.total_main_blocks,
                )
            )
        )
        if missing <= 0:
            continue
        period_main = main.loc[
            main["timestamp"].between(
                period.start, period.end, inclusive="left"
            )
        ].sort_values("height")
        if period_main.empty:
            continue
        duration = (period.end - period.start).total_seconds()
        for idx in range(missing):
            timestamp = period.start + pd.Timedelta(
                seconds=duration * (idx + 1) / (missing + 1)
            )
            after_position = int(
                np.floor(
                    (idx + 1) * len(period_main) / (missing + 1)
                )
            )
            after_position = min(
                max(after_position, 0), len(period_main) - 1
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "height": -1,
                    "after_height": int(
                        period_main.iloc[after_position]["height"]
                    ),
                    "is_qubic": False,
                    "difficulty_int": np.nan,
                    "ts": int(timestamp.timestamp()),
                    "event_type": "synthetic_slot",
                    "source_period": period.label,
                }
            )
    return pd.DataFrame(rows)


def replay_counterfactual(
    blocks: pd.DataFrame,
    periods: list[Period],
    only_period: str | None = None,
) -> pd.DataFrame:
    main = (
        blocks.loc[~blocks["is_orphan"]]
        .sort_values("height")
        .reset_index(drop=True)
    )
    if len(main) <= DIFFICULTY_BLOCKS_COUNT:
        raise ValueError("Not enough blocks to warm up the DAA replay")

    warmup = main.iloc[:DIFFICULTY_BLOCKS_COUNT]
    chain_timestamps = warmup["ts"].astype(int).tolist()
    chain_difficulties = warmup["difficulty_int"].astype(int).tolist()
    cumulative = np.cumsum(
        chain_difficulties, dtype=object
    ).astype(object).tolist()

    main_events = main.iloc[DIFFICULTY_BLOCKS_COUNT:].copy()
    main_events["event_type"] = "main"
    main_events["source_period"] = pd.NA

    synthetic = synthetic_slots(
        periods, main, only_label=only_period
    )
    synthetic_by_height: dict[int, pd.DataFrame] = {}
    if not synthetic.empty:
        for height, group in synthetic.groupby("after_height"):
            synthetic_by_height[int(height)] = group.sort_values(
                "timestamp"
            )

    rows = []

    def append_event(event) -> None:
        timestamps = chain_timestamps[-DIFFICULTY_BLOCKS_COUNT:]
        work = cumulative[-DIFFICULTY_BLOCKS_COUNT:]
        counterfactual = int(next_difficulty(timestamps, work))
        chain_timestamps.append(int(event.ts))
        chain_difficulties.append(counterfactual)
        cumulative.append(int(cumulative[-1]) + counterfactual)
        rows.append(
            {
                "timestamp": event.timestamp,
                "height": int(event.height),
                "event_type": event.event_type,
                "is_qubic": bool(event.is_qubic),
                "actual_difficulty": (
                    int(event.difficulty_int)
                    if event.event_type == "main"
                    else np.nan
                ),
                "counterfactual_difficulty": counterfactual,
                "source_period": event.source_period,
            }
        )

    for event in main_events.itertuples(index=False):
        append_event(event)
        additions = synthetic_by_height.get(
            int(event.height), pd.DataFrame()
        )
        for addition in additions.itertuples(index=False):
            append_event(addition)

    replay = pd.DataFrame(rows)
    return replay.loc[replay["event_type"].eq("main")].copy()


def off_windows(
    periods: list[Period],
    data_end: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    for idx, period in enumerate(periods):
        end = (
            periods[idx + 1].start
            if idx + 1 < len(periods)
            else data_end
        )
        next_label = (
            periods[idx + 1].label
            if idx + 1 < len(periods)
            else "end"
        )
        rows.append(
            {
                "period": period.label,
                "interval": f"G{idx + 1}",
                "inter_window": f"{period.label}->{next_label}",
                "start": period.end,
                "end": end,
                "hours": (end - period.end).total_seconds() / 3600,
            }
        )
    return pd.DataFrame(rows)


def period_effect(
    replay: pd.DataFrame,
    period: Period,
    window: pd.Series,
) -> dict[str, object]:
    off = replay.loc[
        replay["timestamp"].between(
            window["start"], window["end"], inclusive="left"
        )
    ]
    qubic = off.loc[off["is_qubic"]]
    if len(qubic):
        ratio = (
            qubic["actual_difficulty"].astype(float)
            / qubic["counterfactual_difficulty"].astype(float)
        )
        windfall = float((1.0 - ratio).sum())
        counterfactual_blocks = len(qubic) - windfall
    else:
        windfall = 0.0
        counterfactual_blocks = 0.0

    active_delta = (
        period.qubic_main_blocks
        - period.alpha * period.expected_main_blocks
    )
    target_blocks = (
        float(window["hours"]) * 3600 / TARGET_BLOCK_SECONDS
    )
    return {
        "period": period.label,
        "interval": window["interval"],
        "inter_window": window["inter_window"],
        "active_start": period.start,
        "active_end": period.end,
        "off_start": window["start"],
        "off_end": window["end"],
        "off_hours": float(window["hours"]),
        "active_alpha": period.alpha,
        "active_observed_yield": period.observed_yield,
        "active_qubic_main_blocks": period.qubic_main_blocks,
        "active_total_main_blocks": period.total_main_blocks,
        "active_expected_main_blocks": period.expected_main_blocks,
        "active_delta_blocks": active_delta,
        "post_qubic_main_blocks": len(qubic),
        "post_counterfactual_qubic_blocks": counterfactual_blocks,
        "post_network_main_blocks": len(off),
        "post_target_network_blocks": target_blocks,
        "post_qubic_difficulty_windfall_blocks": windfall,
        "net_qubic_blocks": active_delta + windfall,
    }


def marginal_period_effects(
    blocks: pd.DataFrame,
    periods: list[Period],
) -> pd.DataFrame:
    windows = off_windows(periods, blocks["timestamp"].max())
    rows = []
    for period in periods:
        replay = replay_counterfactual(
            blocks, periods, only_period=period.label
        )
        window = windows.loc[
            windows["period"].eq(period.label)
        ].iloc[0]
        rows.append(period_effect(replay, period, window))
    return pd.DataFrame(rows)


def interperiod_revenue(
    blocks: pd.DataFrame,
    effects: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for effect in effects.itertuples(index=False):
        frame = blocks.loc[
            blocks["timestamp"].between(
                effect.off_start, effect.off_end, inclusive="left"
            )
        ]
        main = frame.loc[~frame["is_orphan"]]
        expected_main = (
            (effect.off_end - effect.off_start).total_seconds()
            / TARGET_BLOCK_SECONDS
        )
        alpha = (
            float(frame["is_qubic"].mean()) if len(frame) else np.nan
        )
        observed = (
            float(main["is_qubic"].sum() / expected_main)
            if expected_main
            else np.nan
        )
        counterfactual = (
            effect.post_counterfactual_qubic_blocks / expected_main
            if expected_main
            else np.nan
        )
        rows.append(
            {
                "interval": effect.interval,
                "inter_window": effect.inter_window,
                "start": effect.off_start,
                "end": effect.off_end,
                "alpha": alpha,
                "observed_yield": observed,
                "counterfactual_yield": counterfactual,
                "daa_windfall_blocks": (
                    effect.post_qubic_difficulty_windfall_blocks
                ),
                "observed_minus_alpha": observed - alpha,
                "counterfactual_minus_alpha": counterfactual - alpha,
            }
        )
    return pd.DataFrame(rows)


def validate_replay(blocks: pd.DataFrame) -> pd.DataFrame:
    main = (
        blocks.loc[~blocks["is_orphan"]]
        .sort_values("height")
        .reset_index(drop=True)
    )
    main["cumulative_difficulty"] = main[
        "difficulty_int"
    ].cumsum()
    errors = []
    for idx in range(DIFFICULTY_BLOCKS_COUNT, len(main)):
        window = main.iloc[idx - DIFFICULTY_BLOCKS_COUNT : idx]
        predicted = next_difficulty(
            window["ts"].tolist(),
            window["cumulative_difficulty"].tolist(),
        )
        actual = int(main.iloc[idx]["difficulty_int"])
        errors.append(abs(predicted - actual) / actual)
    values = np.asarray(errors, dtype=float)
    return pd.DataFrame(
        [
            {
                "validation_rows": len(values),
                "max_relative_error": values.max(),
                "mean_relative_error": values.mean(),
            }
        ]
    )


def compute_daa_results(
    blocks: pd.DataFrame,
    revenue: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prepared = prepare_blocks(blocks)
    periods = periods_from_results(revenue)
    effects = marginal_period_effects(prepared, periods)
    interperiod = interperiod_revenue(prepared, effects)
    validation = validate_replay(prepared)
    return effects, interperiod, validation
