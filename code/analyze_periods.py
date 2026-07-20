import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta

from data_utils import load_blocks

# ---------------------------------------------------------------------------
# Hourly validity parameters shared with plotting utilities
# ---------------------------------------------------------------------------

HOURLY_VALIDITY_CONFIG = {
    "min_per_hour": 2,
    "min_duration_hours": 4,
    "merge_gap_hours": 6,
}


def format_hourly_variant(variant: dict) -> str:
    """
    Return a human-readable summary string for a hourly validity variant.
    """
    return (
        variant.get("label")
        or f"≥{variant['min_per_hour']}/hour, duration≥{variant['min_duration_hours']}h, merge≤{variant['merge_gap_hours']}h"
    )


def aggregate_counts_hourly(all_blocks_df: pd.DataFrame):
    """
    Return hourly counts for Qubic orphan blocks, other orphan blocks, and aligned index.
    """
    orphan_df = all_blocks_df[all_blocks_df["is_orphan"] == True].copy()
    qubic = orphan_df[orphan_df["is_qubic"] == True]
    other = orphan_df[orphan_df["is_qubic"] == False]

    qubic = qubic.copy()
    other = other.copy()
    qubic["hour"] = qubic["timestamp"].dt.floor("h")
    other["hour"] = other["timestamp"].dt.floor("h")

    q_counts = qubic.groupby("hour").size().rename("Qubic")
    o_counts = other.groupby("hour").size().rename("Other")

    observed_index = q_counts.index.union(o_counts.index).sort_values()
    # Preserve zero-orphan hours in the time axis.  Without this reindexing,
    # two non-adjacent observations can be mistaken for consecutive hours.
    if len(observed_index):
        index = pd.date_range(observed_index.min(), observed_index.max(), freq="h")
    else:
        index = observed_index
    q_counts = q_counts.reindex(index, fill_value=0)
    o_counts = o_counts.reindex(index, fill_value=0)
    return index, q_counts, o_counts


def detect_hourly_segments(
    index,
    total_counts: pd.Series,
    min_per_hour: int = 1,
    min_duration_hours: int = 5,
):
    """
    Identify contiguous hourly segments (start inclusive, end exclusive) where total orphan
    counts meet the minimum per-hour requirement and total duration meets the threshold.
    """
    mask = (total_counts >= min_per_hour).astype(int).values
    spans = []
    start = None
    for i, val in enumerate(mask):
        if val and start is None:
            start = i
        is_last = i == len(mask) - 1
        if (not val or is_last) and start is not None:
            end_idx = i if is_last and val else i - 1
            duration_hours = end_idx - start + 1
            if duration_hours >= min_duration_hours:
                spans.append((index[start], index[end_idx] + pd.Timedelta(hours=1)))
            start = None
    return spans


def merge_segments(spans, max_gap_hours: int = 0):
    """
    Merge contiguous/nearby segments whose gaps are less than or equal to max_gap_hours.
    """
    if not spans:
        return []
    spans = sorted(spans, key=lambda x: x[0])
    merged = [spans[0]]
    gap_delta = pd.Timedelta(hours=max_gap_hours)
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= gap_delta:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_hourly_valid_segments(
    all_blocks_df: pd.DataFrame,
    min_per_hour: int,
    min_duration_hours: int,
    merge_gap_hours: int,
):
    """
    Compute merged hourly validity segments along with supporting hourly counts.
    """
    index, q_counts, o_counts = aggregate_counts_hourly(all_blocks_df)
    total_counts = q_counts + o_counts
    raw_spans = detect_hourly_segments(
        index,
        total_counts,
        min_per_hour=min_per_hour,
        min_duration_hours=min_duration_hours,
    )
    merged_spans = merge_segments(raw_spans, max_gap_hours=merge_gap_hours)
    return {
        "index": index,
        "qubic_counts": q_counts,
        "other_counts": o_counts,
        "total_counts": total_counts,
        "raw_spans": raw_spans,
        "merged_spans": merged_spans,
    }


def load_data(hourly_variant: dict | None = None):
    """
    Load the orphan run length data and compute orphan/run length ratio.
    Filters out runs using hourly orphan block activity defined by hourly_variant.
    """
    if hourly_variant is None:
        hourly_variant = HOURLY_VALIDITY_CONFIG
    variant_label = format_hourly_variant(hourly_variant)

    # Load run data
    df = pd.read_csv('data/selfish_mining_blocks.csv')
    df['start_ts'] = pd.to_datetime(df['start_ts'])
    # Make tz-naive to match segments
    if df['start_ts'].dt.tz is not None:
        df['start_ts'] = df['start_ts'].dt.tz_localize(None)
    df = df.sort_values('start_ts').reset_index(drop=True)
    
    # Load all blocks to compute hourly orphan counts
    print(f"  Loading all_blocks.csv to compute hourly orphan activity...")
    all_blocks_df = load_blocks()
    all_blocks_df['timestamp'] = pd.to_datetime(all_blocks_df['timestamp'])
    
    if all_blocks_df['timestamp'].dt.tz is not None:
        all_blocks_df['timestamp'] = all_blocks_df['timestamp'].dt.tz_localize(None)
    
    original_count = len(df)
    
    segments_info = compute_hourly_valid_segments(
        all_blocks_df,
        min_per_hour=hourly_variant['min_per_hour'],
        min_duration_hours=hourly_variant['min_duration_hours'],
        merge_gap_hours=hourly_variant['merge_gap_hours'],
    )
    merged_segments = segments_info['merged_spans']
    
    print(f"  Hourly validity criteria: {variant_label}")
    if merged_segments:
        print(f"  Identified {len(merged_segments)} merged validity segments:")
        for seg_start, seg_end in merged_segments:
            duration = seg_end - seg_start
            print(f"    {seg_start} -> {seg_end} (duration {duration})")
    else:
        print("  No validity segments found with current settings.")
    
    def is_valid_run(timestamp):
        for seg_start, seg_end in merged_segments:
            if seg_start <= timestamp < seg_end:
                return True
        return False
    
    run_status = df['start_ts'].apply(is_valid_run)
    active_mask = run_status.values
    total_counts_map = segments_info['total_counts']
    filter_results = []
    for ts, valid in zip(df['start_ts'], active_mask):
        hour_slot = ts.floor('h')
        total_count = int(total_counts_map.get(hour_slot, 0))
        filter_results.append({
            'date': ts,
            'status': 'VALID' if valid else 'EXCLUDED',
            'count': total_count,
            'backward_count': total_count,
            'forward_count': 0,
            'symmetric_count': 0,
            'window_start': hour_slot,
            'window_end': hour_slot + pd.Timedelta(hours=1),
            'last_orphan_time': None,
            'hours_since_last_orphan': None,
            'reason': 'HOURLY' if valid else 'INSUFFICIENT',
        })
    
    df = df[active_mask].copy().reset_index(drop=True)
    filtered_count = len(df)

    print(f"  Summary: Filtered out {original_count - filtered_count} runs in inactive periods")
    print(f"  Remaining runs for analysis: {filtered_count}")

    if len(df) == 0:
        raise ValueError("No runs satisfy the hourly orphan criteria. Adjust HOURLY_VALIDITY_CONFIG.")
    
    df['orphans_per_length'] = df['total_orphans_on_run'] / df['length_qubic_run']
    df['orphans_per_length'] = df['orphans_per_length'].replace([np.inf, -np.inf], 0).fillna(0)
    
    return df, filter_results, segments_info


def detect_change_points(data, feature_col, min_segment_size=5, penalty=10, min_orphans_per_window=2):
    """
    Detect change points using a simple statistical approach.
    Uses sliding window to find points where mean changes significantly.
    Only considers windows with sufficient orphan blocks (selfish mining activity).
    """
    values = data[feature_col].values
    orphan_counts = data['total_orphans_on_run'].values
    change_points = [0]  # Start with beginning
    
    i = min_segment_size
    while i < len(values) - min_segment_size:
        # Check if both windows have sufficient orphan blocks
        left_orphans = orphan_counts[i-min_segment_size:i].sum()
        right_orphans = orphan_counts[i:i+min_segment_size].sum()
        
        # Skip if either window has insufficient orphan activity
        if left_orphans < min_orphans_per_window or right_orphans < min_orphans_per_window:
            i += 1
            continue
        
        # Compare statistics of left and right windows
        left_window = values[i-min_segment_size:i]
        right_window = values[i:i+min_segment_size]
        
        # Mann-Whitney U test for distribution difference
        if len(left_window) > 0 and len(right_window) > 0:
            try:
                statistic, p_value = stats.mannwhitneyu(left_window, right_window, alternative='two-sided')
                
                # If significant difference, mark as change point
                if p_value < 0.05:  # Significant change
                    change_points.append(i)
                    i += min_segment_size  # Skip ahead to avoid too many close points
                else:
                    i += 1
            except:
                i += 1
        else:
            i += 1
    
    change_points.append(len(values))  # End with last point
    return sorted(list(set(change_points)))


def compute_segment_statistics(data, start_idx, end_idx):
    """Compute comprehensive statistics for a segment, focusing on orphan/run length ratio."""
    segment = data.iloc[start_idx:end_idx]
    
    if len(segment) == 0:
        return None
    
    # Compute linear regression for orphans_per_length over time (1차 함수)
    segment_sorted = segment.sort_values('start_ts')
    time_numeric = (segment_sorted['start_ts'] - segment_sorted['start_ts'].min()).dt.total_seconds() / 86400  # days
    ratio_values = segment_sorted['orphans_per_length'].values
    
    # Linear regression: ratio = slope * time + intercept
    if len(time_numeric) > 1 and len(ratio_values) > 1:
        slope, intercept, r_value, p_value, std_err = stats.linregress(time_numeric, ratio_values)
    else:
        slope, intercept, r_value, p_value, std_err = 0, ratio_values[0] if len(ratio_values) > 0 else 0, 0, 1, 0
    
    stats_dict = {
        'start_time': segment['start_ts'].min(),
        'end_time': segment['start_ts'].max(),
        'duration_days': (segment['start_ts'].max() - segment['start_ts'].min()).days + 1,
        'num_runs': len(segment),
        # Ratio statistics (primary focus)
        'mean_ratio': segment['orphans_per_length'].mean(),
        'median_ratio': segment['orphans_per_length'].median(),
        'std_ratio': segment['orphans_per_length'].std(),
        'min_ratio': segment['orphans_per_length'].min(),
        'max_ratio': segment['orphans_per_length'].max(),
        # Linear trend (1차 함수)
        'ratio_slope': slope,  # 변화율 (양수면 증가, 음수면 감소)
        'ratio_intercept': intercept,  # 시작점
        'ratio_r_squared': r_value ** 2,  # 선형성 정도
        'ratio_p_value': p_value,  # 선형 관계의 유의성
        # Supporting statistics
        'mean_run_length': segment['length_qubic_run'].mean(),
        'mean_orphans': segment['total_orphans_on_run'].mean(),
    }
    
    return stats_dict


def compute_similarity(stat1, stat2):
    """Compute similarity score between two segments based on ratio pattern."""
    if stat1 is None or stat2 is None:
        return 0.0
    
    # Focus on ratio pattern (1차 함수 특성)
    features = [
        'mean_ratio',  # 평균 비율
        'ratio_slope',  # 변화율 (1차 함수의 기울기)
        'std_ratio',  # 비율의 변동성
    ]
    
    similarity = 0.0
    for feat in features:
        val1 = stat1.get(feat, 0)
        val2 = stat2.get(feat, 0)
        
        if val1 == 0 and val2 == 0:
            similarity += 1.0
        elif val1 == 0 or val2 == 0:
            similarity += 0.0
        else:
            # Use relative difference
            diff = abs(val1 - val2) / max(abs(val1), abs(val2), 0.001)  # Avoid division by zero
            similarity += max(0, 1 - diff)
    
    return similarity / len(features)


def merge_similar_segments(segments, similarity_threshold=0.7, min_segment_size=3):
    """Merge segments that are statistically similar."""
    if len(segments) <= 1:
        return segments
    
    merged = []
    i = 0
    
    while i < len(segments):
        current = segments[i]
        j = i + 1
        
        # Try to merge with following segments
        while j < len(segments):
            next_seg = segments[j]
            similarity = compute_similarity(current['stats'], next_seg['stats'])
            
            if similarity >= similarity_threshold:
                # Merge segments
                current['end_idx'] = next_seg['end_idx']
                current['stats'] = compute_segment_statistics(
                    current['data'], current['start_idx'], current['end_idx']
                )
                j += 1
            else:
                break
        
        merged.append(current)
        i = j
    
    # Filter out segments that are too small
    filtered = [s for s in merged if s['stats']['num_runs'] >= min_segment_size]
    
    return filtered


def create_period_visualizations_by_status(data, filter_results):
    """
    Create scatter plots for VALID periods only.
    Similar to plot_orphan_run_length.py style.
    """
    # Group consecutive periods by status
    periods = []
    i = 0
    while i < len(filter_results):
        current_status = filter_results[i]['status']
        start_date = filter_results[i]['date']
        start_idx = i
        
        # Find consecutive same status
        while i < len(filter_results) and filter_results[i]['status'] == current_status:
            i += 1
        end_idx = i - 1
        end_date = filter_results[end_idx]['date']
        
        periods.append({
            'status': current_status,
            'start_date': start_date,
            'end_date': end_date,
            'start_idx': start_idx,
            'end_idx': end_idx
        })
    
    # Only VALID periods
    valid_periods = [p for p in periods if p['status'] == 'VALID']
    
    # Filter out VALID periods with total orphan count <= 5
    filtered_valid_periods = []
    for period in valid_periods:
        # Get all runs within this period
        period_runs = data[
            (data['start_ts'] >= period['start_date']) & 
            (data['start_ts'] < period['end_date'])
        ]
        
        # Calculate total orphan count in this period
        # Sum of total_orphans_on_run for all runs in the period
        total_orphans = period_runs['total_orphans_on_run'].sum() if len(period_runs) > 0 else 0
        
        # Only include periods with more than 5 total orphans
        if total_orphans > 5:
            period['total_orphans'] = total_orphans
            filtered_valid_periods.append(period)
        else:
            print(f"  Excluding VALID period {period['start_date'].strftime('%Y-%m-%d')} to {period['end_date'].strftime('%Y-%m-%d')}: only {total_orphans} total orphans (<= 5)")
    
    # Create visualizations for filtered VALID periods only
    if len(filtered_valid_periods) > 0:
        print("\n" + "=" * 80)
        print("VISUALIZING VALID PERIODS (with > 5 total orphans)")
        print("=" * 80)
        print(f"  Showing {len(filtered_valid_periods)} out of {len(valid_periods)} VALID periods")
        create_period_group_visualization(data, filtered_valid_periods, "VALID")
    else:
        print("\n" + "=" * 80)
        print("VISUALIZING VALID PERIODS")
        print("=" * 80)
        print("  No VALID periods with > 5 total orphans found.")


def create_period_group_visualization(data, periods, status_label):
    """
    Create scatter plots for a group of periods (EXCLUDED or VALID).
    """
    import math
    
    num_periods = len(periods)
    if num_periods == 0:
        return
    
    # Determine grid size dynamically
    if num_periods == 1:
        rows, cols = 1, 1
    elif num_periods == 2:
        rows, cols = 1, 2
    elif num_periods <= 4:
        rows, cols = 2, 2
    elif num_periods <= 6:
        rows, cols = 2, 3
    elif num_periods <= 9:
        rows, cols = 3, 3
    elif num_periods == 10 and status_label == "VALID":
        # The paper uses ten candidate periods.  A compact 5-by-2 layout,
        # shared axes, and one common colorbar devote more space to data than
        # the former 4-by-3 layout with a colorbar in every panel.
        rows, cols = 2, 5
    elif num_periods <= 12:
        rows, cols = 3, 4
    elif num_periods <= 16:
        rows, cols = 4, 4
    elif num_periods <= 20:
        rows, cols = 4, 5
    elif num_periods <= 25:
        rows, cols = 5, 5
    else:
        # For more than 25 periods, use a more flexible approach
        cols = math.ceil(math.sqrt(num_periods))
        rows = math.ceil(num_periods / cols)
    
    # First pass: collect all data to determine global axis limits
    all_period_runs = []
    for period in periods:
        period_runs = data[
            (data['start_ts'] >= period['start_date']) & 
            (data['start_ts'] < period['end_date'])
        ]
        if len(period_runs) > 0:
            all_period_runs.append(period_runs)
    
    # Determine global max x and y values for consistent axis limits
    compact_paper_layout = num_periods == 10 and status_label == "VALID"

    if len(all_period_runs) > 0:
        all_runs = pd.concat(all_period_runs, ignore_index=True)
        global_max_x = int(all_runs['length_qubic_run'].max()) if len(all_runs) > 0 else 1
        global_max_y = int(all_runs['total_orphans_on_run'].max()) if len(all_runs) > 0 else 1
        global_coord_counts = all_runs.groupby(
            ['length_qubic_run', 'total_orphans_on_run']
        ).size()
        global_max_count = int(global_coord_counts.max())
    else:
        global_max_x = 1
        global_max_y = 1
        global_max_count = 1

    if compact_paper_layout:
        from matplotlib.colors import PowerNorm
        global_norm = PowerNorm(
            gamma=0.5,
            vmin=1,
            vmax=max(2, global_max_count),
        )
    else:
        global_norm = None

    if compact_paper_layout:
        fig, axes = plt.subplots(
            rows,
            cols,
            figsize=(14.0, 5.8),
            sharex=True,
            sharey=True,
            constrained_layout=True,
        )
    else:
        fig, axes = plt.subplots(rows, cols, figsize=(6*cols, 6*rows))
    if num_periods == 1:
        axes = [axes]
    else:
        axes = axes.flatten()
    
    for idx, period in enumerate(periods):
        ax = axes[idx]
        
        # Filter runs that start within this period
        period_runs = data[
            (data['start_ts'] >= period['start_date']) & 
            (data['start_ts'] < period['end_date'])
        ]

        if 'is_qubic_self_fork' in period_runs.columns:
            self_fork_mask = period_runs['is_qubic_self_fork'].fillna(False).astype(bool)
        else:
            self_fork_mask = pd.Series(False, index=period_runs.index)
        fork_runs = period_runs[~self_fork_mask]
        self_fork_runs = period_runs[self_fork_mask]
        
        if len(period_runs) > 0:
            # Use all observations for a common frequency scale in each panel,
            # while drawing self forks with a distinct marker.
            all_coord_counts = period_runs.groupby(
                ['length_qubic_run', 'total_orphans_on_run']
            ).size().reset_index(name='count')
            
            # Set explicit vmin and vmax to match actual data range (prevents white band at top)
            vmin = all_coord_counts['count'].min()
            vmax = all_coord_counts['count'].max()
            
            norm = global_norm if compact_paper_layout else plt.Normalize(vmin=vmin, vmax=vmax)

            if len(fork_runs) > 0:
                coord_counts = fork_runs.groupby(
                    ['length_qubic_run', 'total_orphans_on_run']
                ).size().reset_index(name='count')
                ax.scatter(
                    coord_counts['length_qubic_run'],
                    coord_counts['total_orphans_on_run'],
                    s=(
                        32 + 26 * np.sqrt(coord_counts['count'])
                        if compact_paper_layout
                        else coord_counts['count'] * 50
                    ),
                    c=coord_counts['count'],
                    cmap='Reds',
                    norm=norm,
                    alpha=0.7,
                    edgecolors='black',
                    linewidths=0.5,
                    zorder=3,
                )

            if len(self_fork_runs) > 0:
                self_fork_counts = self_fork_runs.groupby(
                    ['length_qubic_run', 'total_orphans_on_run']
                ).size().reset_index(name='count')
                ax.scatter(
                    self_fork_counts['length_qubic_run'],
                    self_fork_counts['total_orphans_on_run'],
                    s=(
                        55 + 18 * np.sqrt(self_fork_counts['count'])
                        if compact_paper_layout
                        else 90 + self_fork_counts['count'] * 25
                    ),
                    marker='x',
                    color='#4d4d4d',
                    linewidths=2.0,
                    zorder=5,
                )
                if not compact_paper_layout:
                    for _, self_row in self_fork_counts.iterrows():
                        ax.annotate(
                            f"n={int(self_row['count'])}",
                            (
                                self_row['length_qubic_run'],
                                self_row['total_orphans_on_run'],
                            ),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=9,
                            color='#333333',
                            zorder=6,
                        )

            # Add colorbar to show frequency scale
            # Create a ScalarMappable with exact range to ensure colorbar matches exactly
            if not compact_paper_layout:
                from matplotlib import cm
                sm = cm.ScalarMappable(norm=norm, cmap='Reds')
                sm.set_array([])  # Empty array, we just need the mappable for colorbar

                cbar = plt.colorbar(sm, ax=ax, extend='neither')
                cbar.set_label('Frequency (number of runs)', fontsize=10)

                # Ensure colorbar image covers exactly the data range
                # Set both the mappable limits and the axis limits
                cbar.mappable.set_clim(vmin=vmin, vmax=vmax)
                if vmin != vmax:
                    cbar.ax.set_ylim(vmin, vmax)

                # Filter ticks to show only integers (remove decimal ticks while maintaining natural spacing)
                current_ticks = cbar.get_ticks()
                integer_ticks = [tick for tick in current_ticks if tick == int(tick) and vmin <= tick <= vmax]
                if len(integer_ticks) > 0:
                    cbar.set_ticks(integer_ticks)
                # Format colorbar labels to show only integers
                cbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x)}'))
        else:
            ax.text(0.5, 0.5, 'No data in this period', 
                   ha='center', va='center', transform=ax.transAxes)
        
        # Set consistent axis limits for all subplots
        # Zero-length Qubic runs are valid observations (for example, an
        # orphan-only event).  Keep x=0 visible instead of clipping it at the
        # left boundary.
        ax.set_xlim(-0.5, global_max_x + 0.5)
        ax.set_ylim(-0.5, global_max_y + 0.5)
        if compact_paper_layout:
            from matplotlib.ticker import MaxNLocator
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.tick_params(axis='both', labelsize=9)
        else:
            ax.set_xticks(range(0, global_max_x + 1))
            ax.set_yticks(range(0, global_max_y + 1))
        # Format y-axis to show only integers
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x)}'))
        
        # Add ideal selfish mining reference lines: y = x - 1 and y = x - 2
        # Calculate x range: from 1 to min(global_max_x, global_max_y + 1)
        x_line_max = min(global_max_x, global_max_y + 1)
        if x_line_max >= 1:
            x_line = np.arange(1, x_line_max + 1)
            # y = x - 1 (blue dashed line)
            y_line_1 = x_line - 1
            ax.plot(x_line, y_line_1, 'b--', linewidth=2, alpha=0.7, label='Ideal (y=x-1)', zorder=1)
            # y = x - 2 (red dotted line)
            y_line_2 = x_line - 2
            ax.plot(x_line, y_line_2, 'r:', linewidth=2, alpha=0.7, label='Reference (y=x-2)', zorder=1)
        
        if not compact_paper_layout:
            ax.set_xlabel('Qubic Run Length', fontsize=12)
            ax.set_ylabel('Total Orphans in Run', fontsize=12)
        
        # Include hour in date format for precise period boundaries
        period_label = f"{period['start_date'].strftime('%Y-%m-%d %H:%M')} to {period['end_date'].strftime('%Y-%m-%d %H:%M')}"
        
        if len(self_fork_runs) > 0:
            self_fork_label = (
                "self fork" if len(self_fork_runs) == 1 else "self forks"
            )
            count_label = (
                f"{len(fork_runs)} runs, "
                f"{len(self_fork_runs)} {self_fork_label}"
            )
        else:
            count_label = f"{len(fork_runs)} runs"
        
        # Add alphabet label (a), (b), (c), etc.
        alphabet_label = chr(ord('a') + idx)
        if compact_paper_layout:
            ax.set_title(
                f'({alphabet_label}) P{idx+1}\n{count_label}',
                fontsize=9.5,
                pad=4,
            )
        else:
            ax.set_title(
                f'({alphabet_label}) Candidate P{idx+1} ({count_label})\n{period_label}',
                fontsize=12,
            )
        ax.grid(True, alpha=0.3)
    
    # Hide unused subplots
    for idx in range(num_periods, len(axes)):
        axes[idx].axis('off')
    
    if compact_paper_layout:
        from matplotlib import cm
        sm = cm.ScalarMappable(norm=global_norm, cmap='Reds')
        sm.set_array([])
        cbar = fig.colorbar(
            sm,
            ax=axes[:num_periods].tolist(),
            fraction=0.025,
            pad=0.015,
        )
        cbar.set_label('Run frequency', fontsize=10)
        cbar.ax.tick_params(labelsize=8)
        cbar.ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        fig.supxlabel('Qubic run length', fontsize=16)
        fig.supylabel('Orphans in run', fontsize=16)
    else:
        plt.tight_layout()
    
    # Keep exploratory diagnostics separate from the paper figure generated by
    # plot_period_orphan_blocks.py.
    os.makedirs('derived/diagnostics', exist_ok=True)
    filename = f'derived/diagnostics/orphan_run_length_{status_label.lower()}_periods.pdf'
    plt.savefig(filename, bbox_inches='tight', dpi=300)
    print(f"  Saved visualization to {filename}")
    
    plt.show()
    plt.close(fig)


def validate_segments(segments, min_runs=3, min_orphans_per_period=5):
    """
    Validate and filter segments based on minimum requirements.
    Note: Duration-based filtering is removed since inactive periods are already filtered.
    """
    validated = []
    
    for seg in segments:
        stats = seg['stats']
        segment_data = seg['data'].iloc[seg['start_idx']:seg['end_idx']]
        total_orphans = segment_data['total_orphans_on_run'].sum()
        
        # Check requirements (duration check removed - already filtered by 24h window)
        if (stats['num_runs'] >= min_runs and
            total_orphans >= min_orphans_per_period):
            validated.append(seg)
        else:
            # Log why segment was excluded
            reasons = []
            if stats['num_runs'] < min_runs:
                reasons.append(f"runs < {min_runs}")
            if total_orphans < min_orphans_per_period:
                reasons.append(f"total orphans < {min_orphans_per_period}")
            print(f"  Excluded segment {stats['start_time'].strftime('%Y-%m-%d')}: {', '.join(reasons)}")
    
    return validated


def analyze_periods():
    """Main analysis function using hybrid approach."""
    print("=" * 80)
    print("PERIOD ANALYSIS: Hybrid Change Point Detection + Statistical Clustering")
    print("=" * 80)
    print()
    
    # Step 1: Load data (filter out periods based on hourly orphan activity)
    print("Step 1: Loading data...")
    default_variant = HOURLY_VALIDITY_CONFIG
    print(f"  Using hourly validity criteria: {format_hourly_variant(default_variant)}")
    data, filter_results, segments_info = load_data(hourly_variant=default_variant)
    print(f"  Loaded {len(data)} runs in active selfish mining periods")
    print(f"  Date range: {data['start_ts'].min()} to {data['start_ts'].max()}")
    print()
    
    # Load original data for visualization
    original_data = pd.read_csv('data/selfish_mining_blocks.csv')
    original_data['start_ts'] = pd.to_datetime(original_data['start_ts'])
    # Make tz-naive to match filter_results
    if original_data['start_ts'].dt.tz is not None:
        original_data['start_ts'] = original_data['start_ts'].dt.tz_localize(None)
    
    # Create visualizations for EXCLUDED and VALID periods
    create_period_visualizations_by_status(original_data, filter_results)
    
    if len(data) < 10:
        print("ERROR: Not enough data for period analysis (need at least 10 runs)")
        return
    
    # Step 2: Change Point Detection based on orphan/run length ratio
    print("Step 2: Change Point Detection...")
    print("  Detecting change points based on orphan/run length ratio pattern...")
    print("  Only considering windows with sufficient orphan activity...")
    cp_ratio = detect_change_points(data, 'orphans_per_length', min_segment_size=5, penalty=10, min_orphans_per_window=30)
    
    all_cp = sorted(list(set(cp_ratio)))
    print(f"  Found {len(all_cp)-1} potential segments from change point detection")
    print(f"  Change points (indices): {all_cp}")
    print()
    
    # Step 3: Compute segment statistics
    print("Step 3: Computing segment statistics...")
    segments = []
    for i in range(len(all_cp) - 1):
        start_idx = all_cp[i]
        end_idx = all_cp[i + 1]
        segment_data = data.iloc[start_idx:end_idx]
        
        stats = compute_segment_statistics(data, start_idx, end_idx)
        if stats:
            segments.append({
                'start_idx': start_idx,
                'end_idx': end_idx,
                'data': data,
                'stats': stats
            })
    
    print(f"  Computed statistics for {len(segments)} segments")
    print()
    
    # Step 4: Merge similar segments
    print("Step 4: Merging statistically similar segments...")
    print("  Similarity threshold: 0.7")
    merged_segments = merge_similar_segments(segments, similarity_threshold=0.7, min_segment_size=3)
    print(f"  Merged to {len(merged_segments)} segments")
    print()
    
    # Step 5: Validate segments (exclude periods with insufficient orphan activity)
    print("Step 5: Validating segments...")
    print("  Minimum requirements: 3 runs, 5 total orphan blocks")
    print("  (Inactive periods already filtered by hourly orphan threshold)")
    validated_segments = validate_segments(merged_segments, min_runs=3, min_orphans_per_period=5)
    print(f"  Validated {len(validated_segments)} segments with sufficient orphan activity")
    print()
    
    # Step 6: Generate detailed report
    print("=" * 80)
    print("DETAILED ANALYSIS REPORT")
    print("=" * 80)
    print()
    
    print(f"Total periods identified: {len(validated_segments)}")
    print()
    
    for idx, seg in enumerate(validated_segments, 1):
        stats = seg['stats']
        print(f"Period {idx}:")
        print(f"  Time Range: {stats['start_time'].strftime('%Y-%m-%d')} to {stats['end_time'].strftime('%Y-%m-%d')}")
        print(f"  Duration: {stats['duration_days']} days")
        print(f"  Number of Runs: {stats['num_runs']}")
        print()
        print("  Orphan/Run Length Ratio Statistics (Primary Focus):")
        print(f"    Mean Ratio: {stats['mean_ratio']:.3f}")
        print(f"    Median Ratio: {stats['median_ratio']:.3f}")
        print(f"    Std Dev: {stats['std_ratio']:.3f}")
        print(f"    Range: [{stats['min_ratio']:.3f}, {stats['max_ratio']:.3f}]")
        print()
        print("  Ratio Trend (1차 함수 패턴):")
        print(f"    Slope (변화율): {stats['ratio_slope']:.6f} {'(증가)' if stats['ratio_slope'] > 0 else '(감소)' if stats['ratio_slope'] < 0 else '(일정)'}")
        print(f"    Intercept (시작점): {stats['ratio_intercept']:.3f}")
        print(f"    R² (선형성): {stats['ratio_r_squared']:.3f}")
        print(f"    P-value (유의성): {stats['ratio_p_value']:.4f} {'(유의함)' if stats['ratio_p_value'] < 0.05 else '(유의하지 않음)'}")
        print()
        # Calculate total orphans in this period
        segment_data = seg['data'].iloc[seg['start_idx']:seg['end_idx']]
        total_orphans = segment_data['total_orphans_on_run'].sum()
        
        print("  Supporting Statistics:")
        print(f"    Mean Run Length: {stats['mean_run_length']:.2f}")
        print(f"    Mean Orphan Count: {stats['mean_orphans']:.2f}")
        print(f"    Total Orphan Blocks: {total_orphans}")
        print()
        
        # Compare with overall statistics
        overall_mean_ratio = data['orphans_per_length'].mean()
        ratio_diff = ((stats['mean_ratio'] - overall_mean_ratio) / overall_mean_ratio) * 100 if overall_mean_ratio > 0 else 0
        
        print("  Comparison to Overall Average:")
        print(f"    Orphan/Run Length Ratio: {ratio_diff:+.1f}% {'(above)' if ratio_diff > 0 else '(below)'}")
        print()
        print("-" * 80)
        print()
    
    # Summary statistics
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print()
    
    if len(validated_segments) > 0:
        period_durations = [s['stats']['duration_days'] for s in validated_segments]
        period_runs = [s['stats']['num_runs'] for s in validated_segments]
        period_mean_ratios = [s['stats']['mean_ratio'] for s in validated_segments]
        period_slopes = [s['stats']['ratio_slope'] for s in validated_segments]
        
        print(f"Period Count: {len(validated_segments)}")
        print(f"Total Coverage: {sum(period_durations)} days")
        print()
        print("Period Duration Statistics:")
        print(f"  Mean: {np.mean(period_durations):.1f} days")
        print(f"  Median: {np.median(period_durations):.1f} days")
        print(f"  Range: [{min(period_durations)}, {max(period_durations)}] days")
        print()
        print("Runs per Period Statistics:")
        print(f"  Mean: {np.mean(period_runs):.1f} runs")
        print(f"  Median: {np.median(period_runs):.1f} runs")
        print(f"  Range: [{min(period_runs)}, {max(period_runs)}] runs")
        print()
        print("Orphan/Run Length Ratio Variation Across Periods:")
        print(f"  Mean: {np.mean(period_mean_ratios):.3f}")
        print(f"  Std Dev: {np.std(period_mean_ratios):.3f}")
        print(f"  Range: [{min(period_mean_ratios):.3f}, {max(period_mean_ratios):.3f}]")
        print()
        print("Ratio Trend Slopes (1차 함수 기울기) Across Periods:")
        print(f"  Mean: {np.mean(period_slopes):.6f}")
        print(f"  Std Dev: {np.std(period_slopes):.6f}")
        print(f"  Range: [{min(period_slopes):.6f}, {max(period_slopes):.6f}]")
        print(f"  Positive slopes (증가): {sum(1 for s in period_slopes if s > 0)} periods")
        print(f"  Negative slopes (감소): {sum(1 for s in period_slopes if s < 0)} periods")
        print(f"  Zero slopes (일정): {sum(1 for s in period_slopes if abs(s) < 1e-6)} periods")
        print()
        
        # Period differences
        if len(validated_segments) > 1:
            print("Period-to-Period Ratio Pattern Changes:")
            for i in range(len(validated_segments) - 1):
                curr = validated_segments[i]['stats']
                next_seg = validated_segments[i + 1]['stats']
                
                ratio_change = ((next_seg['mean_ratio'] - curr['mean_ratio']) / 
                               curr['mean_ratio']) * 100 if curr['mean_ratio'] > 0 else 0
                slope_change = next_seg['ratio_slope'] - curr['ratio_slope']
                
                print(f"  Period {i+1} -> Period {i+2}:")
                print(f"    Mean Ratio Change: {ratio_change:+.1f}%")
                print(f"    Slope Change: {slope_change:+.6f} {'(더 가파름)' if abs(slope_change) > 0.0001 else '(비슷함)'}")
                print(f"    Pattern: {curr['mean_ratio']:.3f} (slope={curr['ratio_slope']:.6f}) -> {next_seg['mean_ratio']:.3f} (slope={next_seg['ratio_slope']:.6f})")
            print()
    
    print("=" * 80)
    print("Analysis Complete")
    print("=" * 80)
    
    return validated_segments


def verify_orphan_counting():
    """
    Verify if orphan blocks are being counted multiple times across different runs.
    Check if the same orphan block appears in multiple runs.
    """
    print("\n" + "=" * 80)
    print("VERIFYING ORPHAN COUNTING METHODOLOGY")
    print("=" * 80)
    
    # Load run data
    df = pd.read_csv('data/selfish_mining_blocks.csv')
    print(f"\nTotal runs in dataset: {len(df)}")
    
    # Load all blocks to get actual orphan blocks
    all_blocks_df = load_blocks()
    all_blocks_df['timestamp'] = pd.to_datetime(all_blocks_df['timestamp'])
    
    # Get Qubic orphan blocks
    qubic_orphan_blocks = all_blocks_df[
        (all_blocks_df['is_qubic'] == True) & 
        (all_blocks_df['is_orphan'] == True)
    ].copy()
    qubic_orphan_blocks = qubic_orphan_blocks.sort_values('height').reset_index(drop=True)
    
    print(f"Total Qubic orphan blocks: {len(qubic_orphan_blocks)}")
    
    # Check if same orphan blocks appear in multiple runs
    print("\nChecking if same orphan blocks appear in multiple runs...")
    orphan_to_runs = {}  # Map orphan height to list of run indices
    
    for idx, run in df.iterrows():
        start_h = int(run['start_height'])
        end_h = int(run['end_height'])
        
        # Get orphan blocks in this height range
        orphans_in_range = qubic_orphan_blocks[
            (qubic_orphan_blocks['height'] >= start_h) & 
            (qubic_orphan_blocks['height'] <= end_h)
        ]
        
        for _, orphan in orphans_in_range.iterrows():
            orphan_h = int(orphan['height'])
            if orphan_h not in orphan_to_runs:
                orphan_to_runs[orphan_h] = []
            orphan_to_runs[orphan_h].append(idx)
    
    # Count orphans that appear in multiple runs
    multi_count_orphans = {h: runs for h, runs in orphan_to_runs.items() if len(runs) > 1}
    
    print(f"  Total unique orphan heights: {len(orphan_to_runs)}")
    print(f"  Orphan heights appearing in multiple runs: {len(multi_count_orphans)}")
    
    if len(multi_count_orphans) > 0:
        print(f"\n  ⚠️  WARNING: {len(multi_count_orphans)} orphan heights are counted in multiple runs!")
        print("\n  Example orphan blocks counted multiple times:")
        example_count = 0
        for orphan_h, run_indices in list(multi_count_orphans.items())[:5]:
            example_count += 1
            print(f"\n    Orphan at height {orphan_h} appears in {len(run_indices)} runs:")
            for run_idx in run_indices[:3]:
                run = df.iloc[run_idx]
                print(f"      Run {run_idx}: height {run['start_height']}-{run['end_height']}, "
                      f"orphans={run['total_orphans_on_run']}")
            if len(run_indices) > 3:
                print(f"      ... and {len(run_indices) - 3} more runs")
        
        # Calculate total duplicate count
        total_duplicate_count = sum(len(runs) - 1 for runs in multi_count_orphans.values())
        print(f"\n  Total duplicate counts: {total_duplicate_count} (each orphan counted {total_duplicate_count / len(multi_count_orphans):.1f} times on average)")
    else:
        print("\n  ✓ No orphan blocks are counted multiple times. Each orphan is counted exactly once.")
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    if len(multi_count_orphans) > 0:
        print("⚠️  ISSUE DETECTED: Same orphan blocks are being counted in multiple runs.")
        print("   This means the current methodology counts each orphan multiple times")
        print("   when it appears in overlapping runs.")
    else:
        print("✓ No issues detected: Each orphan block is counted only once.")
    print("=" * 80)


if __name__ == '__main__':
    # First verify the counting methodology
    verify_orphan_counting()
    
    segments = analyze_periods()
