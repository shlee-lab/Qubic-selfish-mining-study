import os
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

from data_utils import load_blocks, verified_qubic_self_fork_heights

from analyze_periods import (
    HOURLY_VALIDITY_CONFIG,
    format_hourly_variant,
    compute_hourly_valid_segments,
    create_period_group_visualization,
)

# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# spacing constants
LABEL_PAD = 10   # distance between axis and axis label
TICK_PAD = 6     # distance between ticks and axis

# Use SHOW_PLOTS=1 for interactive windows
SHOW_PLOTS = os.environ.get("SHOW_PLOTS", "").strip() in {"1", "true", "TRUE", "yes", "YES"}

def _parse_figsize_env(var_name: str, default: tuple[float, float]) -> tuple[float, float]:
    """
    Parse an environment variable like "15,4.2" into a (w,h) tuple.
    """
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return default
    try:
        w_s, h_s = raw.split(",", 1)
        return (float(w_s.strip()), float(h_s.strip()))
    except Exception:
        return default

# Match aspect ratio with fig/qubic_withholding_timeline.pdf (from plot_withhold.py)
WITHHOLD_FIGSIZE = (15.0, 4.2)
# Default paper-like size for Fig.6 unless overridden
HOURLY_TIMELINE_FIGSIZE = _parse_figsize_env("HOURLY_TIMELINE_FIGSIZE", (15.0, 6.0))
# If set, force hourly timeline to match the withholding timeline aspect ratio
MATCH_WITHHOLD_TIMELINE = os.environ.get("MATCH_WITHHOLD_TIMELINE", "").strip() in {"1", "true", "TRUE", "yes", "YES"}


def load_orphan_blocks():
    """
    Load all blocks and separate into Qubic orphan blocks and other orphan blocks.
    """
    print("Loading orphan blocks data...")
    all_blocks_df = load_blocks()
    all_blocks_df['timestamp'] = pd.to_datetime(all_blocks_df['timestamp'])
    
    # Normalize timezone: remove timezone info if present
    if all_blocks_df['timestamp'].dt.tz is not None:
        all_blocks_df['timestamp'] = all_blocks_df['timestamp'].dt.tz_localize(None)
    
    # Separate orphan blocks
    qubic_orphan_blocks = all_blocks_df[
        (all_blocks_df['is_qubic'] == True) & 
        (all_blocks_df['is_orphan'] == True)
    ].copy()
    
    other_orphan_blocks = all_blocks_df[
        (all_blocks_df['is_qubic'] == False) & 
        (all_blocks_df['is_orphan'] == True)
    ].copy()
    
    print(f"  Qubic orphan blocks: {len(qubic_orphan_blocks)}")
    print(f"  Other orphan blocks: {len(other_orphan_blocks)}")
    print(f"  Date range: {all_blocks_df['timestamp'].min()} to {all_blocks_df['timestamp'].max()}")
    
    return qubic_orphan_blocks, other_orphan_blocks, all_blocks_df

def load_run_data():
    """
    Load run-summary CSV used for per-period run scatter.

    Historical filename (may be renamed in repo history):
      - data/qubic_orphan_start_qubic_continuous_split.csv

    Current repo provides an equivalent schema at:
      - data/selfish_mining_blocks.csv

    For reproducibility, we fall back when the historical filename is absent.
    """
    # Canonical filename in this repo
    primary = 'data/selfish_mining_blocks.csv'
    # Historical filename (kept as fallback for old checkouts)
    fallback = 'data/qubic_orphan_start_qubic_continuous_split.csv'

    path = primary if os.path.exists(primary) else fallback
    print(f"Loading run summary data from: {path}")
    runs = pd.read_csv(path)
    runs['start_ts'] = pd.to_datetime(runs['start_ts'])
    # Normalize timezone: make tz-naive to match all_blocks_df segments
    if runs['start_ts'].dt.tz is not None:
        runs['start_ts'] = runs['start_ts'].dt.tz_localize(None)

    # A same-height Qubic main block and Qubic orphan block form a self fork.
    # Such events do not reveal a private lead and must be separated from the
    # fork runs used for release policy interpretation.
    blocks = load_blocks()
    self_fork_heights = verified_qubic_self_fork_heights(blocks)
    runs['is_qubic_self_fork'] = runs.apply(
        lambda row: any(
            height in self_fork_heights
            for height in range(
                int(row['start_height']),
                int(row['end_height']) + 1,
            )
        ),
        axis=1,
    )
    print(
        "  Qubic self fork runs marked separately: "
        f"{int(runs['is_qubic_self_fork'].sum())}"
    )
    return runs


def compute_share_statistics(all_blocks_df, merged_spans):
    """
    Calculate Qubic block percentages for each validity period,
    the overall validity-region percentage, the complement percentage,
    and the global average across the full dataset.
    """
    df = all_blocks_df.sort_values('timestamp').reset_index(drop=True)
    is_qubic = df['is_qubic'].astype(int)

    per_period = []
    total_valid_blocks = 0
    total_valid_qubic = 0
    valid_mask = pd.Series(False, index=df.index)

    for idx, (start, end) in enumerate(merged_spans, start=1):
        mask = (df['timestamp'] >= start) & (df['timestamp'] < end)
        period_blocks = mask.sum()
        period_qubic = is_qubic.where(mask).sum()
        share = (period_qubic / period_blocks * 100) if period_blocks > 0 else None
        per_period.append({
            'label': f'P{idx}',
            'start': start,
            'end': end,
            'total_blocks': int(period_blocks),
            'qubic_blocks': int(period_qubic),
            'share': share,
        })
        total_valid_blocks += period_blocks
        total_valid_qubic += period_qubic
        valid_mask |= mask

    overall_blocks = len(df)
    overall_qubic = int(is_qubic.sum())
    overall_share = overall_qubic / overall_blocks * 100 if overall_blocks > 0 else None

    valid_share = (total_valid_qubic / total_valid_blocks * 100) if total_valid_blocks > 0 else None

    complement_mask = ~valid_mask
    complement_blocks = complement_mask.sum()
    complement_qubic = int(is_qubic.where(complement_mask).sum())
    complement_share = (
        complement_qubic / complement_blocks * 100 if complement_blocks > 0 else None
    )

    return {
        'per_period': per_period,
        'valid_share': valid_share,
        'complement_share': complement_share,
        'overall_share': overall_share,
    }


def create_hourly_timeline(all_blocks_df, segments_info, config):
    idx = segments_info['index']
    q_counts = segments_info['qubic_counts']
    o_counts = segments_info['other_counts']
    total_counts = segments_info['total_counts']
    merged_spans = segments_info['merged_spans']
    raw_spans = segments_info['raw_spans']

    figsize = WITHHOLD_FIGSIZE if MATCH_WITHHOLD_TIMELINE else HOURLY_TIMELINE_FIGSIZE
    fig, ax = plt.subplots(figsize=figsize)
    bar_width = 1.0 / 24.0

    ax.bar(idx, q_counts.values, label='Qubic orphan blocks', color='#2E86AB', alpha=0.8, width=bar_width)
    ax.bar(idx, o_counts.values, bottom=q_counts.values, label='Other orphan blocks', color='#A23B72', alpha=0.6, width=bar_width)

    for s, e in raw_spans:
        ax.axvspan(s, e, color='green', alpha=0.1, zorder=0)
    y_upper = ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1
    for idx, (s, e) in enumerate(merged_spans, start=1):
        ax.axvspan(s, e, color='green', alpha=0.25, zorder=1)
        mid = s + (e - s) / 2
        ax.text(
            mid,
            y_upper * 0.9,
            f'P{idx}',
            ha='center',
            va='center',
            fontsize=15,
            color='black'
        )

    title = f'Hourly Orphan Counts with Validity ({format_hourly_variant(config)})'
    # ax.set_title(title, fontsize=14)
    ax.set_ylabel('Orphan blocks per hour', fontsize=14, labelpad=LABEL_PAD)
    ax.set_xlabel('Date', fontsize=14, labelpad=LABEL_PAD)
    ax.tick_params(axis='both', pad=TICK_PAD)
    ax.grid(True, alpha=0.3, axis='y')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MONDAY, interval=1))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    ax.legend(loc='upper right')
    fig.tight_layout()

    os.makedirs('fig', exist_ok=True)
    out_path = 'fig/hourly_validity_timeline.pdf'
    plt.savefig(out_path, bbox_inches='tight', dpi=300)
    print(f"Saved timeline figure to {out_path}")
    if SHOW_PLOTS:
        plt.show()
    plt.close(fig)


def create_run_scatter(run_df, segments_info, config):
    merged_spans = segments_info['merged_spans']
    if not merged_spans:
        print("No validity segments found; skipping run scatter plot.")
        return

    periods = []
    for idx, (seg_start, seg_end) in enumerate(merged_spans, start=1):
        seg_runs = run_df[
            (run_df['start_ts'] >= seg_start) &
            (run_df['start_ts'] < seg_end)
        ]
        if seg_runs.empty:
            continue
        total_orphans = seg_runs['total_orphans_on_run'].sum()
        periods.append({
            'status': 'VALID',
            'start_date': seg_start,
            'end_date': seg_end,
            'total_orphans': total_orphans,
        })

    if not periods:
        print("No runs within validity segments; skipping run scatter plot.")
        return

    print(f"Generating run-length scatter for {len(periods)} validity periods...")
    create_period_group_visualization(run_df, periods, "VALID")


def main():
    print("=" * 80)
    print("HOURLY ORPHAN VALIDITY COMPARISON")
    print("=" * 80)
    print()

    qubic_orphan_blocks, other_orphan_blocks, all_blocks_df = load_orphan_blocks()
    runs_df = load_run_data()
    print()

    print("Computing hourly validity segments...")
    segments_info = compute_hourly_valid_segments(
        all_blocks_df,
        min_per_hour=HOURLY_VALIDITY_CONFIG['min_per_hour'],
        min_duration_hours=HOURLY_VALIDITY_CONFIG['min_duration_hours'],
        merge_gap_hours=HOURLY_VALIDITY_CONFIG['merge_gap_hours'],
    )
    merged_spans = segments_info['merged_spans']
    if merged_spans:
        print(f"  Found {len(merged_spans)} validity segments:")
        for seg_start, seg_end in merged_spans:
            print(f"    {seg_start} -> {seg_end} (duration {seg_end - seg_start})")
    else:
        print("  No validity segments detected.")

    # Compute block percentage statistics
    share_stats = compute_share_statistics(all_blocks_df, merged_spans)
    print("\nQubic block percentage by validity period:")
    for info in share_stats['per_period']:
        share_txt = f"{info['share']:.2f}%" if info['share'] is not None else "N/A"
        print(
            f"  {info['label']}: {info['start']} -> {info['end']} "
            f"(total blocks {info['total_blocks']}, qubic {info['qubic_blocks']}) "
            f"share = {share_txt}"
        )
    if share_stats['valid_share'] is not None:
        print(f"  Valid periods combined share: {share_stats['valid_share']:.2f}%")
    else:
        print("  Valid periods combined share: N/A")
    if share_stats['complement_share'] is not None:
        print(f"  Non-valid periods share: {share_stats['complement_share']:.2f}%")
    else:
        print("  Non-valid periods share: N/A")
    if share_stats['overall_share'] is not None:
        print(f"  Overall dataset share: {share_stats['overall_share']:.2f}%")
    else:
        print("  Overall dataset share: N/A")

    if os.environ.get("SKIP_RUN_SCATTER", "").strip() not in {"1", "true", "TRUE", "yes", "YES"}:
        print("\nGenerating selfish mining run scatter plot...")
        create_run_scatter(runs_df, segments_info, HOURLY_VALIDITY_CONFIG)
    else:
        print("\nSkipping run scatter plot (SKIP_RUN_SCATTER set).")

    print("\nGenerating hourly timeline plot...")
    # Allow override output path for reproducibility tests without overwriting repo figure.
    out_override = os.environ.get("HOURLY_TIMELINE_OUT", "").strip()
    if out_override:
        # Monkeypatch the output path by temporarily overriding the module-level constant use.
        # The plotting function uses a local variable, so we pass via env and branch here.
        idx = segments_info['index']
        q_counts = segments_info['qubic_counts']
        o_counts = segments_info['other_counts']
        total_counts = segments_info['total_counts']
        merged_spans = segments_info['merged_spans']
        raw_spans = segments_info['raw_spans']

        fig, ax = plt.subplots(figsize=(15, 6))
        bar_width = 1.0 / 24.0

        ax.bar(idx, q_counts.values, label='Qubic orphan blocks', color='#2E86AB', alpha=0.8, width=bar_width)
        ax.bar(idx, o_counts.values, bottom=q_counts.values, label='Other orphan blocks', color='#A23B72', alpha=0.6, width=bar_width)

        for s, e in raw_spans:
            ax.axvspan(s, e, color='green', alpha=0.1, zorder=0)
        y_upper = ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1
        for idx_i, (s, e) in enumerate(merged_spans, start=1):
            ax.axvspan(s, e, color='green', alpha=0.25, zorder=1)
            mid = s + (e - s) / 2
            ax.text(
                mid,
                y_upper * 0.9,
                f'P{idx_i}',
                ha='center',
                va='center',
                fontsize=15,
                color='black'
            )

        ax.set_ylabel('Orphan blocks per hour', fontsize=14, labelpad=LABEL_PAD)
        ax.set_xlabel('Date', fontsize=14, labelpad=LABEL_PAD)
        ax.tick_params(axis='both', pad=TICK_PAD)
        ax.grid(True, alpha=0.3, axis='y')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MONDAY, interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        ax.legend(loc='upper right')
        fig.tight_layout()

        os.makedirs(os.path.dirname(out_override) or '.', exist_ok=True)
        plt.savefig(out_override, bbox_inches='tight', dpi=300)
        print(f"Saved timeline figure to {out_override}")
        plt.close(fig)
    else:
        create_hourly_timeline(all_blocks_df, segments_info, HOURLY_VALIDITY_CONFIG)

    print("\n" + "=" * 80)
    print("Visualization Complete")
    print("=" * 80)


if __name__ == '__main__':
    main()
