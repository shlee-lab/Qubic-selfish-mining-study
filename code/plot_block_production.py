import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
from matplotlib.ticker import ScalarFormatter

# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# spacing constants
LABEL_PAD = 10   # distance between axis and axis label
TICK_PAD  = 6    # distance between ticks and axis

# difficulty 0x-hex -> int
def hex_to_int(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s.startswith(('0x', '0X')):
        s = s[2:]
    if s == '':
        return np.nan
    try:
        return int(s, 16)
    except Exception:
        return np.nan

def analyze_qubic_mining():
    """
    Analyze Qubic's Monero mining power share on a daily basis and generate graphs.
    """
    # Ensure output dir
    os.makedirs('fig', exist_ok=True)

    # Load CSV file
    print("Loading data...")
    df = pd.read_csv('data/all_blocks.csv')

    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    df['week'] = df['timestamp'].dt.to_period('W-WED')
    df['hour'] = df['timestamp'].dt.floor('H')

    print(f"Total blocks: {len(df)}")
    print(f"Data period: {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    # difficulty: 0x-hex -> int -> scale
    df['difficulty_hex'] = df['difficulty'].astype(str)
    df['difficulty'] = df['difficulty_hex'].apply(hex_to_int)

    # scale for readability (tune if needed)
    DIFF_SCALE = 1e12
    df['difficulty_scaled'] = df['difficulty'] / DIFF_SCALE

    # Check Qubic-mined blocks and orphan blocks
    qubic_blocks = df[df['is_qubic'] == True]
    orphan_blocks = df[df['is_orphan'] == True]
    qubic_orphan_blocks = df[(df['is_qubic'] == True) & (df['is_orphan'] == True)]

    print(f"Qubic-mined blocks: {len(qubic_blocks)}")
    print(f"Orphan blocks: {len(orphan_blocks)}")
    print(f"Qubic-mined orphan blocks: {len(qubic_orphan_blocks)}")

    # Overall statistics
    total_blocks_overall = len(df)
    qubic_blocks_overall = len(df[df['is_qubic'] == True])
    qubic_power_overall = (qubic_blocks_overall / total_blocks_overall) * 100 if total_blocks_overall > 0 else 0

    # Daily statistics
    daily_stats = []
    for date in df['date'].unique():
        date_data = df[df['date'] == date]

        total_blocks = len(date_data)
        qubic_blocks_count = len(date_data[date_data['is_qubic'] == True])
        orphan_blocks_count = len(date_data[date_data['is_orphan'] == True])
        qubic_orphan_count = len(date_data[(date_data['is_qubic'] == True) & (date_data['is_orphan'] == True)])

        non_qubic_orphan_count = orphan_blocks_count - qubic_orphan_count
        non_qubic_regular_count = total_blocks - qubic_blocks_count - non_qubic_orphan_count
        qubic_power_ratio = (qubic_blocks_count / total_blocks) * 100 if total_blocks > 0 else 0

        daily_stats.append({
            'date': date,
            'total_blocks': total_blocks,
            'qubic_blocks': qubic_blocks_count,
            'orphan_blocks': orphan_blocks_count,
            'qubic_orphan_blocks': qubic_orphan_count,
            'non_qubic_orphan_blocks': non_qubic_orphan_count,
            'non_qubic_regular_blocks': non_qubic_regular_count,
            'qubic_power_ratio': qubic_power_ratio
        })

    # Weekly statistics (W-WED)
    weekly_stats = []
    for week in df['week'].unique():
        week_data = df[df['week'] == week]
        total_blocks = len(week_data)
        qubic_blocks_count = len(week_data[week_data['is_qubic'] == True])
        qubic_power_ratio = (qubic_blocks_count / total_blocks) * 100 if total_blocks > 0 else 0
        weekly_stats.append({
            'week': week,
            'total_blocks': total_blocks,
            'qubic_blocks': qubic_blocks_count,
            'qubic_power_ratio': qubic_power_ratio
        })

    # Hourly statistics
    hourly_stats = []
    for hour in df['hour'].unique():
        hour_data = df[df['hour'] == hour]
        total_blocks = len(hour_data)
        qubic_blocks_count = len(hour_data[hour_data['is_qubic'] == True])
        qubic_power_ratio = (qubic_blocks_count / total_blocks) * 100 if total_blocks > 0 else 0
        hourly_stats.append({
            'hour': hour,
            'total_blocks': total_blocks,
            'qubic_blocks': qubic_blocks_count,
            'qubic_power_ratio': qubic_power_ratio
        })

    # Daily average difficulty (scaled)
    daily_difficulty = (
        df.groupby(df['timestamp'].dt.date)['difficulty_scaled']
          .mean()
          .rename('avg_difficulty_scaled')
          .reset_index()
          .rename(columns={'timestamp': 'date'})
    )

    # To DataFrames
    daily_df = pd.DataFrame(daily_stats)
    daily_df['date'] = pd.to_datetime(daily_df['date'])

    daily_difficulty['date'] = pd.to_datetime(daily_difficulty['date'])
    daily_df = daily_df.merge(daily_difficulty, on='date', how='left')

    weekly_df = pd.DataFrame(weekly_stats)
    weekly_df['week_end'] = weekly_df['week'].dt.end_time

    hourly_df = pd.DataFrame(hourly_stats)
    hourly_df['hour'] = pd.to_datetime(hourly_df['hour'])

    # x-axis formatting
    total_days = len(daily_df)
    if total_days <= 30:
        interval = 3
    elif total_days <= 60:
        interval = 5
    elif total_days <= 90:
        interval = 7
    else:
        interval = 14

    date_min = daily_df['date'].min()
    date_max = daily_df['date'].max()
    padding = pd.Timedelta(days=2)

    # ===== Figure 1: Power share lines =====
    fig1, ax1 = plt.subplots(1, 1, figsize=(15, 6))

    ax1.plot(hourly_df['hour'], hourly_df['qubic_power_ratio'],
             linewidth=1, color='darkgray', alpha=0.7, label='Hourly Mining Power Share')

    ax1.plot(daily_df['date'], daily_df['qubic_power_ratio'],
             marker='o', linewidth=2, markersize=4, color='red', label='Daily Mining Power Share')

    ax1.plot(weekly_df['week_end'], weekly_df['qubic_power_ratio'],
             marker='s', linewidth=2, markersize=6, color='blue', label='Weekly Mining Power Share')



    ax1.axhline(y=qubic_power_overall, color='black', linestyle='--', linewidth=2,
                label=f'Overall Average ({qubic_power_overall:.2f}%)')

    ax1.set_xlabel('Date', fontsize=14, labelpad=LABEL_PAD)
    ax1.set_ylabel('Share (%)', fontsize=14, labelpad=LABEL_PAD)
    ax1.tick_params(axis='both', pad=TICK_PAD)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')

    ax1.set_xlim(date_min - padding, date_max + padding)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.WEDNESDAY, interval=1))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    fig1.tight_layout()
    fig1.savefig('fig/mining_share.pdf', dpi=300, bbox_inches='tight')
    print("Saved fig/mining_share.pdf")
    plt.show()  # Display the plot
    plt.close(fig1)

    # ===== Figure 2: Stacked bars + daily avg difficulty line (twin y-axis) =====
    fig2, ax2 = plt.subplots(1, 1, figsize=(15, 6))

    non_qubic_orphan_blocks = daily_df['non_qubic_orphan_blocks']
    qubic_orphan_blocks = daily_df['qubic_orphan_blocks']
    qubic_regular_blocks = daily_df['qubic_blocks'] - daily_df['qubic_orphan_blocks']
    non_qubic_regular_blocks = daily_df['non_qubic_regular_blocks']

    # Stack order: Non-Qubic Regular (bottom) -> Non-Qubic Orphan -> Qubic Regular -> Qubic Orphan (top)
    # Qubic blocks use skyblue color scheme
    ax2.bar(daily_df['date'], non_qubic_regular_blocks,
            alpha=0.9, label='Non-Qubic Regular Blocks', color='#E0E0E0', edgecolor='black', linewidth=0.5)
    ax2.bar(daily_df['date'], non_qubic_orphan_blocks,
            bottom=non_qubic_regular_blocks,
            alpha=0.9, label='Non-Qubic Orphan Blocks', color='#9E9E9E', edgecolor='black', linewidth=0.5)
    ax2.bar(daily_df['date'], qubic_regular_blocks,
            bottom=non_qubic_regular_blocks + non_qubic_orphan_blocks,
            alpha=0.9, label='Qubic Regular Blocks', color='#87CEEB', edgecolor='black', linewidth=0.5)  # Skyblue
    ax2.bar(daily_df['date'], qubic_orphan_blocks,
            bottom=non_qubic_regular_blocks + non_qubic_orphan_blocks + qubic_regular_blocks,
            alpha=0.9, label='Qubic Orphan Blocks', color='#4682B4', edgecolor='black', linewidth=0.5)  # Steelblue (darker skyblue)

    ax2.set_xlabel('Date', fontsize=14, labelpad=LABEL_PAD)
    ax2.set_ylabel('Number of Blocks', fontsize=14, labelpad=LABEL_PAD)
    ax2.tick_params(axis='both', pad=TICK_PAD)
    ax2.grid(True, alpha=0.3)

    ax2.set_xlim(date_min - padding, date_max + padding)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.WEDNESDAY, interval=1))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    ax2b = ax2.twinx()
    difficulty_color = 'crimson'  
    
    ax2b.plot(daily_df['date'], daily_df['avg_difficulty_scaled'] * 10,
              marker='o', linewidth=1.8, color=difficulty_color, label='Daily Avg Difficulty')
    ax2b.set_ylabel(f'Avg Difficulty (daily) / 10¹¹', fontsize=14, labelpad=LABEL_PAD + 2)
    ax2b.tick_params(axis='both', pad=TICK_PAD)
    # Remove scientific notation since we already have / 10¹¹ in the label
    ax2b.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.1f}'))

    handles1, labels1 = ax2.get_legend_handles_labels()
    handles2, labels2 = ax2b.get_legend_handles_labels()
    # Legend order: match the bar stacking order (bottom to top)
    # Stack order: Non-Qubic Regular -> Non-Qubic Orphan -> Qubic Regular -> Qubic Orphan
    # Reverse handles1 to match visual order (bottom to top)
    handles1_reversed = handles1[::-1]
    labels1_reversed = labels1[::-1]
    ax2.legend(handles1_reversed + handles2, labels1_reversed + labels2, loc='lower left')

    fig2.tight_layout()
    fig2.savefig('fig/block_production.pdf', dpi=300, bbox_inches='tight')
    print("Saved fig/block_production.pdf")
    plt.show()  # Display the plot
    plt.close(fig2)

    print("\n=== Analysis Results Summary ===")
    print(f"Total period: {daily_df['date'].min().strftime('%Y-%m-%d')} ~ {daily_df['date'].max().strftime('%Y-%m-%d')}")
    print(f"Average Qubic mining power share: {daily_df['qubic_power_ratio'].mean():.2f}%")
    print(f"Maximum Qubic mining power share: {daily_df['qubic_power_ratio'].max():.2f}%")
    print(f"Minimum Qubic mining power share: {daily_df['qubic_power_ratio'].min():.2f}%")
    print(f"Total Qubic blocks: {daily_df['qubic_blocks'].sum()}")
    print(f"Total blocks: {daily_df['total_blocks'].sum()}")
    print(f"Overall Qubic share: {(daily_df['qubic_blocks'].sum() / daily_df['total_blocks'].sum()) * 100:.2f}%")

    return daily_df

if __name__ == "__main__":
    daily_stats = analyze_qubic_mining()
