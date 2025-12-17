import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from sklearn.linear_model import LinearRegression

def load_blocks():
    """Load and preprocess block data"""
    print("Loading blocks data...")
    blocks = pd.read_csv('data/all_blocks.csv')
    blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
    if blocks['timestamp'].dt.tz is not None:
        blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
    return blocks

def analyze_head_start_global():
    print(f"Analyzing Head Start (Global, Positive Only)")
    
    all_blocks = load_blocks()
    
    # Identify Races across ALL blocks
    height_counts = all_blocks['height'].value_counts()
    contested_heights = height_counts[height_counts > 1].index.sort_values()
    
    race_data = []
    
    for h in contested_heights:
        h_blocks = all_blocks[all_blocks['height'] == h]
        
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            qubic_block = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
            honest_block = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
            
            # Calculate Head Start (Honest Time - Qubic Time)
            head_start_seconds = (honest_block['timestamp'] - qubic_block['timestamp']).total_seconds()
            
            # Filter: Only Positive Head Starts (Qubic found first)
            if head_start_seconds > 0:
                # Did Qubic win?
                qubic_won = not qubic_block['is_orphan']
                
                # Did Qubic self-extend?
                self_extended = False
                if qubic_won:
                    next_h = h + 1
                    next_blocks = all_blocks[all_blocks['height'] == next_h]
                    if len(next_blocks) > 0:
                        main_next = next_blocks[next_blocks['is_orphan'] == False]
                        if len(main_next) > 0:
                            next_block = main_next.iloc[0]
                            if next_block['is_qubic']:
                                # Check for State 2 Leakage
                                # If Qubic mined H+1 BEFORE Honest mined H, it's State 2.
                                if next_block['timestamp'] < honest_block['timestamp']:
                                    continue # Skip State 2 cases (guaranteed wins)
                                
                                self_extended = True
                
                race_data.append({
                    'head_start': head_start_seconds,
                    'qubic_won': qubic_won,
                    'self_extended': self_extended
                })
    
    df = pd.DataFrame(race_data)
    print(f"\nTotal Positive Head Start Races: {len(df)}")
    
    # Filter outliers for cleaner plot (e.g., > 300s is rare and noisy)
    df = df[df['head_start'] <= 180] 
    
    # Binning (Fine-grained: 5 seconds)
    bin_width = 5
    df['bin'] = (df['head_start'] // bin_width) * bin_width + (bin_width / 2) # Center of bin
    
    # Group Analysis
    grouped = df.groupby('bin').agg(
        count=('head_start', 'count'),
        win_rate=('self_extended', 'mean')
    ).reset_index()
    
    # Filter bins with too few samples to avoid noise
    grouped = grouped[grouped['count'] >= 5]
    
    print(grouped.head())
    
    # Linear Regression (Weighted by count)
    X = grouped['bin'].values.reshape(-1, 1)
    y = grouped['win_rate'].values
    weights = grouped['count'].values
    
    reg = LinearRegression()
    reg.fit(X, y, sample_weight=weights)
    
    r2 = reg.score(X, y, sample_weight=weights)
    slope = reg.coef_[0]
    intercept = reg.intercept_
    
    print(f"\nRegression Results:")
    print(f"  Slope: {slope:.4f}")
    print(f"  Intercept: {intercept:.4f}")
    print(f"  R^2: {r2:.4f}")
    
    # --- Plotting (Top Conference Style) ---
    plt.style.use('seaborn-v0_8-paper')
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 14,
        'axes.labelsize': 16,
        'axes.titlesize': 18,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 14,
        'figure.figsize': (10, 6),
        'lines.linewidth': 2,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'grid.linestyle': '--'
    })

    fig, ax = plt.subplots()
    
    # Scatter plot of binned averages (size proportional to count)
    sizes = grouped['count'] * 2  # Scale factor
    scatter = ax.scatter(grouped['bin'], grouped['win_rate'], s=sizes, color='#4C72B0', alpha=0.7, edgecolors='black', label='Observed Win Rate (Binned)')
    
    # Regression Line
    x_range = np.linspace(grouped['bin'].min(), grouped['bin'].max(), 100).reshape(-1, 1)
    y_pred = reg.predict(x_range)
    ax.plot(x_range, y_pred, color='#C44E52', linewidth=3, linestyle='-', label=f'Linear Fit ($R^2={r2:.2f}$)')

    ax.set_xlabel('Head Start Duration (seconds)')
    ax.set_ylabel('Win Rate (Self-Extension)')
    ax.set_title('Linear Relationship: Head Start vs. Win Rate')
    ax.set_ylim(0, 1.05)
    
    # Add equation text
    equation = f'$y = {slope:.4f}x + {intercept:.2f}$'
    ax.text(0.05, 0.9, equation, transform=ax.transAxes, fontsize=16, fontweight='bold', color='#333333')

    ax.legend(loc='lower right', frameon=True, framealpha=0.9, edgecolor='gray')
    
    plt.tight_layout()
        
    os.makedirs('fig', exist_ok=True)
    filename = 'fig/head_start_linear_analysis.pdf'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"\nSaved publication-quality plot to {filename}")

if __name__ == "__main__":
    analyze_head_start_global()
