import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from analyze_periods import (
    HOURLY_VALIDITY_CONFIG,
    compute_hourly_valid_segments,
)

# Store derived CSV outputs outside repo root
DERIVED_DIR = "derived"
# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

def load_blocks():
    """Load and preprocess block data"""
    print("Loading blocks data...")
    blocks = pd.read_csv('data/all_blocks.csv')
    blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
    if blocks['timestamp'].dt.tz is not None:
        blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
    return blocks

def calculate_gamma_for_period(period_blocks, all_blocks_df):
    """Calculate gamma and 0' state count for a specific period using robust logic"""
    
    # Calculate alpha (Qubic's mining power share)
    total_blocks = len(period_blocks)
    qubic_blocks = len(period_blocks[period_blocks['is_qubic'] == True])
    alpha = qubic_blocks / total_blocks if total_blocks > 0 else 0
    
    # Identify contested heights (Qubic vs Honest)
    height_counts = period_blocks['height'].value_counts()
    potential_contested = height_counts[height_counts > 1].index
    
    total_0_prime = 0
    gamma_opportunities = 0
    gamma_successes = 0
    
    for h in potential_contested:
        h_blocks = period_blocks[period_blocks['height'] == h]
        
        # Check if it's Qubic vs Honest (at least one of each)
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            total_0_prime += 1
            
            # Check next block (H+1) to determine Gamma
            # Gamma is the probability Honest miners choose Qubic's block
            # We look at cases where the NEXT block is Honest
            next_h = h + 1
            # Use global blocks to find next even if it falls outside period boundary slightly
            next_blocks = all_blocks_df[all_blocks_df['height'] == next_h] 
            
            # Find the main chain block at H+1
            main_next = next_blocks[next_blocks['is_orphan'] == False]
            
            if len(main_next) > 0:
                next_block = main_next.iloc[0]
                
                # We only care if the next block is Honest (to measure Honest choice)
                if not next_block['is_qubic']:
                    gamma_opportunities += 1
                    
                    # Did it extend Qubic?
                    # If Qubic block at H is NOT orphan, then it was extended.
                    qubic_block_at_h = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
                    if not qubic_block_at_h['is_orphan']:
                        gamma_successes += 1
    
    # Calculate gamma rate
    # Gamma = P(Honest extends Qubic | Honest finds next)
    gamma_rate = gamma_successes / gamma_opportunities if gamma_opportunities > 0 else 0
    
    return {
        'alpha': alpha,
        'gamma': gamma_rate,
        'total_0_prime': total_0_prime,
        'gamma_opportunities': gamma_opportunities,
        'gamma_successes': gamma_successes,
        'blocks': total_blocks
    }

def create_period_dual_axis_chart(results):
    """Create chart with dual y-axis showing gamma and 0' state counts by period"""
    if not results:
        print("No results to plot.")
        return

    df = pd.DataFrame(results)
    
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # Create bars for 0' state counts (left y-axis)
    bars = ax1.bar(df['period'], df['total_0_prime'], width=0.6,
                   alpha=0.7, color='lightgray', edgecolor='black', linewidth=1, label='Estimated 0\' State Count')
    ax1.set_xlabel('Period', fontsize=14)
    ax1.set_ylabel('Estimated 0\' State Count', fontsize=14)
    
    # Create line for gamma values (right y-axis)
    ax2 = ax1.twinx()
    line = ax2.plot(df['period'], df['gamma'], 'ro-', linewidth=2, markersize=8, label='γ Rate')
    ax2.set_ylabel('γ Rate', fontsize=14)
    ax2.set_ylim(-0.01, 0.25)  # Set y-axis range
    
    ax1.grid(True, alpha=0.3)
    
    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=12)
    
    # Add value labels on gamma line
    for i, gamma in enumerate(df['gamma']):
        if not pd.isna(gamma) and gamma > 0:
            ax2.text(i, gamma + 0.005, f'{gamma:.3f}', ha='center', va='bottom', 
                    fontsize=10, fontweight='bold')
            
    # Add value labels on bars
    for i, count in enumerate(df['total_0_prime']):
        if count > 0:
            ax1.text(i, count + 1, str(count), ha='center', va='bottom', fontsize=9)
    
    plt.title('Gamma and Race Conditions by Selfish Mining Period', fontsize=16)
    plt.tight_layout()
    
    os.makedirs('fig', exist_ok=True)
    filename = 'fig/period_gamma.pdf'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Saved plot to {filename}")

def main():
    print("=" * 80)
    print("PERIOD-BASED GAMMA ANALYSIS")
    print("=" * 80)
    
    # Load blocks
    all_blocks_df = load_blocks()
    
    # Identify periods
    print("\nIdentifying selfish mining periods...")
    segments_info = compute_hourly_valid_segments(
        all_blocks_df,
        min_per_hour=HOURLY_VALIDITY_CONFIG['min_per_hour'],
        min_duration_hours=HOURLY_VALIDITY_CONFIG['min_duration_hours'],
        merge_gap_hours=HOURLY_VALIDITY_CONFIG['merge_gap_hours'],
    )
    merged_spans = segments_info['merged_spans']
    
    if not merged_spans:
        print("No validity segments found.")
        return
        
    print(f"Found {len(merged_spans)} periods.")
    
    results = []
    
    # Calculate gamma for each period
    print("\nCalculating gamma for each period...")
    for idx, (start, end) in enumerate(merged_spans, 1):
        period_label = f"P{idx}"
        print(f"  Processing {period_label}: {start} -> {end}")
        
        # Filter blocks for this period
        mask = (all_blocks_df['timestamp'] >= start) & (all_blocks_df['timestamp'] < end)
        period_blocks = all_blocks_df[mask].copy()
        
        if len(period_blocks) == 0:
            print(f"    No blocks in period {period_label}")
            continue
            
        stats = calculate_gamma_for_period(period_blocks, all_blocks_df)
        stats['period'] = period_label
        stats['start'] = start
        stats['end'] = end
        
        results.append(stats)
        
        print(f"    Gamma: {stats['gamma']:.4f} (Success: {stats['gamma_successes']}/{stats['gamma_opportunities']})")
        print(f"    Races (0'): {stats['total_0_prime']}")
        
    # Create plot
    print("\nGenerating plot...")
    create_period_dual_axis_chart(results)
    
    # Save CSV
    df = pd.DataFrame(results)
    os.makedirs(DERIVED_DIR, exist_ok=True)
    out_csv = f'{DERIVED_DIR}/qubic_gamma_period_analysis.csv'
    df.to_csv(out_csv, index=False)
    print(f"Saved analysis data to {out_csv}")
    
    print("\nAnalysis complete!")

if __name__ == '__main__':
    main()
