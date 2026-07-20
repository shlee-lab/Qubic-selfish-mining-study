import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from data_utils import load_blocks
import matplotlib.dates as mdates
from datetime import datetime, timedelta

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

def build_orphan_forks(df: pd.DataFrame):
    orphans = df[df['is_orphan'] == True].sort_values('timestamp').copy()
    orphans['timestamp'] = pd.to_datetime(orphans['timestamp'])
    forks = []
    cur = []
    for _, blk in orphans.iterrows():
        if not cur:
            cur.append(blk)
            continue
        last = cur[-1]
        td = (blk['timestamp'] - last['timestamp']).total_seconds()
        hd = blk['height'] - last['height']
        if td <= 300 and hd == 1:
            cur.append(blk)
        else:
            forks.append(pd.DataFrame(cur))
            cur = [blk]
    if cur:
        forks.append(pd.DataFrame(cur))
    return forks

def week_label(ts):
    return pd.Timestamp(ts).to_period('W-TUE').start_time

def prepare_weekly_tables(df: pd.DataFrame):
    forks = build_orphan_forks(df)
    rows = []
    for fk in forks:
        length_val = len(fk)
        wk = week_label(fk['timestamp'].min())
        is_qubic = bool((fk['is_qubic'] == True).any())
        rows.append({'week': wk, 'length': length_val, 'is_qubic': is_qubic})
    weekly = pd.DataFrame(rows)
    if weekly.empty:
        return weekly, forks
    weekly['length_bin_6'] = weekly['length'].apply(lambda x: x if x <= 5 else 6)
    return weekly, forks

def method_dodged_log(ax, weekly: pd.DataFrame):

    import matplotlib.patches as mpatches

    weeks = sorted(weekly['week'].unique())
    bins = [1, 2, 3, 4, 5, 6]   # '6' == '6+'
    x = np.arange(len(weeks))
    width = 0.12

    styles = [
        {"face": "white",    "hatch": ""},      # White
        {"face": "#f5f5f5",  "hatch": ""},      # Very light gray
        {"face": "#d0d0d0",  "hatch": ""},      # Light gray
        {"face": "#a0a0a0",  "hatch": ""},      # Medium gray
        {"face": "#707070",  "hatch": ""},      # Dark gray
        {"face": "#404040",  "hatch": ""},      # Very dark gray
    ]

    legend_handles = []
    ax.set_facecolor("white")

    for i, b in enumerate(bins):
        vals = np.array([
            (weekly[(weekly['week'] == w) & (weekly['length_bin_6'] == b)].shape[0])
            for w in weeks
        ])
        mask = vals > 0
        if np.any(mask):
            st = styles[i]
            ax.bar(
                x[mask] + (i - (len(bins)-1)/2.0) * width,
                vals[mask],
                width=width,
                color=st["face"],
                edgecolor="black",
                hatch=st["hatch"],
                linewidth=0.8
            )
            legend_handles.append(
                mpatches.Patch(
                    facecolor=st["face"], edgecolor="black",
                    hatch=st["hatch"], linewidth=0.8,
                    label=f"{b if b != 6 else '6+'}"
                )
            )

    ax.set_yscale('log')
    ax.set_ylabel("Number of Orphan Forks (log scale)", fontsize=14)
    ax.set_xlabel("Date", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels([pd.to_datetime(w).strftime('%Y-%m-%d') for w in weeks],
                       rotation=40, ha='right')
    ax.legend(handles=legend_handles, ncol=6, fontsize=8, frameon=False)
    ax.grid(True, axis='y', alpha=0.3, color="black", linewidth=0.5)

def main():
    df = load_blocks()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    weekly, forks = prepare_weekly_tables(df)

    if weekly.empty:
        print('No orphan forks to visualize.')
        return

    weeks_sorted = sorted(weekly['week'].unique())
    recent_weeks = weeks_sorted[-12:] if len(weeks_sorted) > 12 else weeks_sorted
    weekly = weekly[weekly['week'].isin(recent_weeks)]

    fig, ax = plt.subplots(1, 1, figsize=(14, 6))
    method_dodged_log(ax, weekly)

    plt.tight_layout()

    plt.savefig('fig/orphan_length.pdf', bbox_inches='tight')
    print("Saved 'orphan_length.pdf'.")


if __name__ == '__main__':
    main()
