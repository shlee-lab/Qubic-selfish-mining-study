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

def analyze_race_resolution(period_blocks, all_blocks_df):
    """Analyze race resolution efficiency for a specific period"""
    
    # Calculate alpha (Qubic's mining power share)
    total_blocks = len(period_blocks)
    qubic_blocks = len(period_blocks[period_blocks['is_qubic'] == True])
    alpha = qubic_blocks / total_blocks if total_blocks > 0 else 0
    
    # Identify contested heights (Qubic vs Honest)
    height_counts = period_blocks['height'].value_counts()
    potential_contested = height_counts[height_counts > 1].index
    
    total_races = 0
    qubic_won_race = 0
    qubic_self_extended = 0
    
    for h in potential_contested:
        h_blocks = period_blocks[period_blocks['height'] == h]
        
        # Check if it's Qubic vs Honest (at least one of each)
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            # 1. Check if it ended as 2:1 (Next block exists)
            next_h = h + 1
            next_blocks = all_blocks_df[all_blocks_df['height'] == next_h]
            main_next = next_blocks[next_blocks['is_orphan'] == False]
            
            if len(main_next) == 0:
                continue # Not a resolved 2:1 case, skip.

            next_block = main_next.iloc[0]
            
            # 2. Determine if it's a valid Race (State 0')
            # Default is True (Honest winning is always a Race)
            is_race = True
            
            if next_block['is_qubic']:
                # Qubic won (Qubic H -> Qubic H+1). 
                # Check for State 2: Did Qubic find H+1 BEFORE Honest found H?
                honest_block_at_h = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
                if next_block['timestamp'] < honest_block_at_h['timestamp']:
                    is_race = False # State 2 (Already had H+1), not a Race.
            
            if is_race:
                total_races += 1
                
                # Did Qubic win the race?
                if next_block['is_qubic']:
                    qubic_won_race += 1
                    qubic_self_extended += 1 # In this simplified view, winning a race is self-extension
    
    race_win_rate = qubic_won_race / total_races if total_races > 0 else 0
    self_extension_rate = qubic_self_extended / total_races if total_races > 0 else 0
    
    return {
        'alpha': alpha,
        'total_races': total_races,
        'qubic_won_race': qubic_won_race,
        'race_win_rate': race_win_rate,
        'qubic_self_extended': qubic_self_extended,
        'self_extension_rate': self_extension_rate
    }

def create_race_resolution_chart(results):
    """Create chart comparing Alpha vs Race Win Rate"""
    if not results:
        print("No results to plot.")
        return

    df = pd.DataFrame(results)
    
    fig, ax = plt.subplots(figsize=(9, 6))
    
    x = np.arange(len(df))
    width = 0.35
    
    # Bar 1: Expected Win Rate (Alpha)
    # Style: White, black edge, no hatch
    rects1 = ax.bar(x - width/2, df['alpha'], width, 
                    label=r'Expected Win Rate ($\alpha$)', 
                    color='white', edgecolor='black')
    
    # Bar 2: Observed Race Win Rate
    # Style: Light gray, black edge, diagonal hatch
    rects2 = ax.bar(x + width/2, df['race_win_rate'], width, 
                    label='Observed Race Win Rate', 
                    color='#d9d9d9', edgecolor='black', hatch='///')
    
    ax.set_ylabel('Rate / Probability', fontsize=18)
    # Title removed as requested
    # ax.set_title('Race Resolution Efficiency: Expected vs Observed', fontsize=16)
    
    ax.set_xticks(x)
    ax.set_xticklabels(df['period'], fontsize=14)
    ax.tick_params(axis='y', labelsize=14)
    
    ax.legend(fontsize=14)
    ax.grid(True, axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(0, 1.1) # Increased ylim to make room for labels
    
    # Add value labels
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.2f}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

    autolabel(rects1)
    autolabel(rects2)
    
    # Add race count annotation above the bars
    for i in range(len(df)):
        alpha_val = df.iloc[i]['alpha']
        win_rate_val = df.iloc[i]['race_win_rate']
        races = df.iloc[i]['total_races']
        
        # Place label above the higher of the two bars
        max_height = max(alpha_val, win_rate_val)
        ax.text(i, max_height + 0.08, f'n={races}', ha='center', va='bottom', fontsize=13)

    plt.tight_layout()
    
    os.makedirs('fig', exist_ok=True)
    filename = 'fig/race_resolution.pdf'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Saved plot to {filename}")

def main():
    print("=" * 80)
    print("RACE RESOLUTION ANALYSIS")
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
        
    results = []
    
    # Analyze each period
    print("\nAnalyzing race resolution for each period...")
    for idx, (start, end) in enumerate(merged_spans, 1):
        period_label = f"P{idx}"
        
        # Filter blocks for this period
        mask = (all_blocks_df['timestamp'] >= start) & (all_blocks_df['timestamp'] < end)
        period_blocks = all_blocks_df[mask].copy()
        
        if len(period_blocks) == 0:
            continue
            
        stats = analyze_race_resolution(period_blocks, all_blocks_df)
        stats['period'] = period_label
        
        results.append(stats)
        
        print(f"  {period_label}: Alpha={stats['alpha']:.3f}, Win Rate={stats['race_win_rate']:.3f} (Races: {stats['total_races']})")
        
    # Create plot
    print("\nGenerating plot...")
    create_race_resolution_chart(results)
    
    # Save CSV
    df = pd.DataFrame(results)
    os.makedirs(DERIVED_DIR, exist_ok=True)
    out_csv = f"{DERIVED_DIR}/race_resolution_stats.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved analysis data to {out_csv}")
    
    print("\nAnalysis complete!")

if __name__ == '__main__':
    main()
