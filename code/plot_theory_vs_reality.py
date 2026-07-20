import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from data_utils import load_blocks as load_augmented_blocks

from analyze_periods import (
    HOURLY_VALIDITY_CONFIG,
    compute_hourly_valid_segments,
)

# Store derived CSV outputs outside repo root
DERIVED_DIR = "derived"
# Try to import adjustText for better label placement
try:
    from adjustText import adjust_text  # type: ignore
    HAS_ADJUST_TEXT = True
except ImportError:
    HAS_ADJUST_TEXT = False
    print("Warning: adjustText not available. Using manual label placement.")

# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


def load_blocks():
    """Load all blocks data."""
    print("Loading blocks data...")
    all_blocks_df = load_augmented_blocks()
    all_blocks_df['timestamp'] = pd.to_datetime(all_blocks_df['timestamp'])
    
    # Normalize timezone: remove timezone info if present
    if all_blocks_df['timestamp'].dt.tz is not None:
        all_blocks_df['timestamp'] = all_blocks_df['timestamp'].dt.tz_localize(None)
    
    return all_blocks_df


def compute_stats_for_spans(df, spans, label, category='period', aggregate_type=None):
    """
    Helper to compute statistics for one or more time spans.
    """
    if not spans:
        return None
    
    df = df.sort_values('timestamp').reset_index(drop=True)
    mask = pd.Series(False, index=df.index)
    total_duration = 0.0
    
    for start, end in spans:
        if start is None or end is None or end <= start:
            continue
        total_duration += (end - start).total_seconds()
        mask |= (df['timestamp'] >= start) & (df['timestamp'] < end)
    
    if total_duration <= 0:
        return None
    
    period_blocks = df[mask].copy()
    if len(period_blocks) == 0:
        return None
    
    total_blocks = len(period_blocks)
    qubic_blocks = len(period_blocks[period_blocks['is_qubic'] == True])
    alpha = qubic_blocks / total_blocks if total_blocks > 0 else 0
    
    main_chain_blocks = period_blocks[period_blocks['is_orphan'] == False]
    total_main_chain = len(main_chain_blocks)
    qubic_main_chain = len(main_chain_blocks[main_chain_blocks['is_qubic'] == True])
    
    expected_main_chain = total_duration / 120 if total_duration > 0 else 0
    R = qubic_main_chain / expected_main_chain if expected_main_chain > 0 else 0
    
    start_time = min(start for start, _ in spans if start is not None)
    end_time = max(end for _, end in spans if end is not None)
    
    return {
        'label': label,
        'start': start_time,
        'end': end_time,
        'alpha': alpha,
        'R': R,
        'total_blocks': total_blocks,
        'qubic_blocks': qubic_blocks,
        'total_main_chain': total_main_chain,
        'qubic_main_chain': qubic_main_chain,
        'expected_main_chain': expected_main_chain,
        'period_duration_seconds': total_duration,
        'category': category,
        'aggregate_type': aggregate_type,
        'spans': spans,
    }


def compute_period_statistics(all_blocks_df, merged_spans):
    """
    Calculate statistics for individual periods plus aggregated summaries.
    """
    df = all_blocks_df.sort_values('timestamp').reset_index(drop=True)
    period_stats = []
    
    for idx, span in enumerate(merged_spans, start=1):
        stat = compute_stats_for_spans(df, [span], label=f'P{idx}', category='period')
        if stat:
            period_stats.append(stat)
            print(
                f"  {stat['label']}: alpha={stat['alpha']:.4f}, "
                f"R={stat['R']:.4f} (total={stat['total_blocks']}, qubic={stat['qubic_blocks']}, "
                f"main_chain={stat['total_main_chain']}, qubic_main={stat['qubic_main_chain']}, "
                f"expected_main={stat['expected_main_chain']:.1f})"
            )
    
    # Aggregate: entire dataset
    overall_span = [(df['timestamp'].min(), df['timestamp'].max())]
    overall_stat = compute_stats_for_spans(
        df, overall_span, label='ALL', category='aggregate', aggregate_type='overall'
    )
    if overall_stat:
        period_stats.append(overall_stat)
        print(
            f"  {overall_stat['label']}: alpha={overall_stat['alpha']:.4f}, "
            f"R={overall_stat['R']:.4f} (total={overall_stat['total_blocks']}, "
            f"qubic={overall_stat['qubic_blocks']}, main_chain={overall_stat['total_main_chain']}, "
            f"qubic_main={overall_stat['qubic_main_chain']}, "
            f"expected_main={overall_stat['expected_main_chain']:.1f})"
        )
    
    # Aggregate: selfish mining periods (P1-P10 as requested)
    selfish_spans = merged_spans[:10]
    if selfish_spans:
        selfish_stat = compute_stats_for_spans(
            df, selfish_spans, label='P1-P10', category='aggregate', aggregate_type='selfish'
        )
        if selfish_stat:
            period_stats.append(selfish_stat)
            print(
                f"  {selfish_stat['label']}: alpha={selfish_stat['alpha']:.4f}, "
                f"R={selfish_stat['R']:.4f} (total={selfish_stat['total_blocks']}, "
                f"qubic={selfish_stat['qubic_blocks']}, main_chain={selfish_stat['total_main_chain']}, "
                f"qubic_main={selfish_stat['qubic_main_chain']}, "
                f"expected_main={selfish_stat['expected_main_chain']:.1f})"
            )
    
    # Save to CSV
    stats_df = pd.DataFrame(period_stats)
    os.makedirs(DERIVED_DIR, exist_ok=True)
    out_csv = f"{DERIVED_DIR}/period_revenue_stats.csv"
    stats_df.to_csv(out_csv, index=False)
    print(f"Saved period statistics to {out_csv}")
    
    return period_stats


def R_honest(alpha):
    return alpha


def R_original_selfish(alpha, gamma):
    a = alpha
    num = a*(1-a)**2*(4*a + gamma*(1-2*a)) - a**3
    den = 1 - a*(1 + (2-a)*a)
    return num / den


def R_modified(alpha, gamma):
    a = alpha
    num = a * (a**3*gamma - 3*a**2*gamma + a**2 + 3*a*gamma - 2*a - gamma)
    den = a**4 - 2*a**3 + a - 1
    return num / den


def plot_theory_vs_reality(period_stats):
    """
    Plot theoretical curves and actual period data points.
    """
    # Generate theoretical curves
    alphas = np.linspace(0.0, 0.4999, 500)
    gammas = [1.0, 0.5, 0.0]
    colors = ['#2166ac', '#4393c3', '#92c5de']  # Color-blind friendly palette
    
    plt.figure(figsize=(10, 10))
    
    # Plot theoretical curves
    # Honest mining line (gamma-independent) - black solid line
    plt.plot(alphas, R_honest(alphas),
             color='k', linestyle='-', linewidth=2.5, 
             label="Honest mining")
    
    for color, gamma in zip(colors, gammas):
        R_orig = R_original_selfish(alphas, gamma)
        R_mod = R_modified(alphas, gamma)
        
        # Selfish mining: solid line
        plt.plot(alphas, R_orig,
                 color=color, linewidth=2.5,
                 label=f"Selfish mining γ={gamma}")
        # Modified strategy: dashed line
        plt.plot(alphas, R_mod,
                 color=color, linewidth=2,
                 alpha=0.85, linestyle=(0, (8, 4)),
                 label=f"Modified strategy γ={gamma}")
        
        # gamma=0일 때 selfish mining과 modified strategy 사이 영역 음영처리
        if gamma == 0.0:
            plt.fill_between(alphas, R_mod, R_orig, 
                            color=color, alpha=0.15, 
                            label="Estimated profit region (γ=0)")
    
    period_points = [p for p in period_stats if p.get('category') == 'period']
    aggregate_points = [p for p in period_stats if p.get('category') == 'aggregate']
    
    # Plot actual period data points
    if period_points:
        alphas_actual = [p['alpha'] for p in period_points]
        Rs_actual = [p['R'] for p in period_points]
        total_blocks_list = [p['total_blocks'] for p in period_points]
        
        # Calculate point sizes based on total_blocks (normalized)
        min_blocks = min(total_blocks_list)
        max_blocks = max(total_blocks_list)
        # Scale sizes between 100 and 1000
        sizes = [100 + (blocks - min_blocks) / (max_blocks - min_blocks) * 900 
                if max_blocks > min_blocks else 500 
                for blocks in total_blocks_list]
        
        # Plot points with sizes proportional to total_blocks
        # User requested NO labels for individual periods, just red dots.
        # We remove the label from scatter so it doesn't clutter the legend, 
        # or we can add a single "Individual Periods" entry.
        scatter = plt.scatter(alphas_actual, Rs_actual, 
                            s=sizes, color='red', marker='o', 
                            edgecolors='black', linewidths=2,
                            zorder=5, label='Individual Periods (P1-P10)', alpha=0.7)
        
        # NO text annotations for individual periods as requested.
    
    # Plot aggregate points (overall, selfish combined)
    overall_stat = None
    selfish_stat = None
    if aggregate_points:
        aggregate_styles = {
            'overall': {'color': '#FF9800', 'marker': 'X', 'size': 400, 'label': 'Global Average'},
            'selfish': {'color': '#6A0DAD', 'marker': 'D', 'size': 350, 'label': 'Average (P1-P10)'},
        }
        used_labels = set()
        
        for agg in aggregate_points:
            style = aggregate_styles.get(
                agg.get('aggregate_type'),
                {'color': '#444444', 'marker': 's', 'size': 300, 'label': agg['label']}
            )
            lbl = style['label']
            show_label = lbl not in used_labels
            if agg.get('aggregate_type') == 'overall':
                overall_stat = agg
            elif agg.get('aggregate_type') == 'selfish':
                selfish_stat = agg
            
            scatter = plt.scatter(
                [agg['alpha']], [agg['R']],
                s=style['size'],
                color=style['color'],
                marker=style['marker'],
                edgecolors='black',
                linewidths=2,
                zorder=7,
                label=lbl if show_label else None,
            )
            if show_label:
                used_labels.add(lbl)
            
            if show_label:
                used_labels.add(lbl)
            
            # Annotation removed as per user request (legend is sufficient)
    
    plt.xlabel("Miner hash power", fontsize=16)
    plt.ylabel("Revenue ratio", fontsize=16)
    plt.xlim(0, 0.5)
    plt.ylim(0, 1.0)
    
    # Qubic's average hashrate share (use data if available)
    qubic_alpha = overall_stat['alpha'] if overall_stat else 0.2209
    plt.axvline(x=qubic_alpha, color='#666666', linestyle=':', linewidth=2, 
                label="Qubic's average hashrate share")
    
    # Qubic's average hashrate share during selfish mining (use data if available)
    qubic_selfish_alpha = selfish_stat['alpha'] if selfish_stat else 0.2802
    plt.axvline(x=qubic_selfish_alpha, color='black', linestyle=':', linewidth=2, 
                label="Qubic's selfish mining hashrate share")
    
    plt.grid(True, alpha=0.3, linestyle=':', linewidth=0.8)
    plt.legend(loc='upper left', fontsize=12, framealpha=0.95)
    
    os.makedirs('fig', exist_ok=True)
    fname = "fig/theory_vs_reality.pdf"
    plt.savefig(fname, bbox_inches="tight", dpi=300)
    print(f"\nSaved comparison plot to: {fname}")
    
    # --- Print Data Table for Paper ---
    print("\n" + "="*100)
    print("DATA TABLE FOR PAPER")
    print("="*100)
    # Columns: Period, Alpha, Revenue, Main Chain Blocks, Qubic Blocks, Qubic Blocks in Main Chain
    header = f"{'Period':<15} | {'Alpha':<8} | {'Revenue':<8} | {'Main Chain':<10} | {'Qubic Total':<11} | {'Qubic Main':<10}"
    print(header)
    print("-" * len(header))
    
    # Sort: Periods first, then Aggregates
    sorted_stats = sorted(period_stats, key=lambda x: (
        0 if x['category'] == 'period' else 1, 
        int(x['label'][1:]) if x['category'] == 'period' and x['label'][1:].isdigit() else 0
    ))
    
    for p in sorted_stats:
        label = p['label']
        if p['category'] == 'aggregate':
            if p['aggregate_type'] == 'overall':
                label = "Global Average"
            elif p['aggregate_type'] == 'selfish':
                label = "Avg (P1-P10)"
        
        print(f"{label:<15} | {p['alpha']:.4f}   | {p['R']:.4f}   | {p['total_main_chain']:<10} | {p['qubic_blocks']:<11} | {p['qubic_main_chain']:<10}")
    print("="*100 + "\n")



def main():
    print("=" * 80)
    print("THEORY VS REALITY COMPARISON")
    print("=" * 80)
    print()
    
    # Load blocks data
    all_blocks_df = load_blocks()
    print()
    
    # Compute hourly validity segments (same as plot_period_orphan_blocks.py)
    print("Computing hourly validity segments...")
    segments_info = compute_hourly_valid_segments(
        all_blocks_df,
        min_per_hour=HOURLY_VALIDITY_CONFIG['min_per_hour'],
        min_duration_hours=HOURLY_VALIDITY_CONFIG['min_duration_hours'],
        merge_gap_hours=HOURLY_VALIDITY_CONFIG['merge_gap_hours'],
    )
    merged_spans = segments_info['merged_spans']
    
    if not merged_spans:
        print("  No validity segments detected.")
        return
    
    print(f"  Found {len(merged_spans)} validity segments:")
    for seg_start, seg_end in merged_spans:
        print(f"    {seg_start} -> {seg_end} (duration {seg_end - seg_start})")
    print()
    
    # Compute period statistics
    print("Computing period statistics...")
    period_stats = compute_period_statistics(all_blocks_df, merged_spans)
    print()
    
    if not period_stats:
        print("No period statistics computed. Exiting.")
        return
    
    # Plot theory vs reality
    print("Generating theory vs reality comparison plot...")
    plot_theory_vs_reality(period_stats)
    
    print("\n" + "=" * 80)
    print("Comparison Complete")
    print("=" * 80)


if __name__ == '__main__':
    main()
