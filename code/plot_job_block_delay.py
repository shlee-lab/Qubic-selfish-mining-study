import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# Use SHOW_PLOTS=1 for interactive windows
SHOW_PLOTS = os.environ.get("SHOW_PLOTS", "").strip() in {"1", "true", "TRUE", "yes", "YES"}

def calculate_job_fetch_period(jobs_df):
    """
    Calculate the actual job fetch period from raw_jobs.csv.
    Excludes network interruptions (very long intervals).
    Returns mean and std for visualization.
    """
    # Sort by timestamp
    sorted_jobs = jobs_df.sort_values('job_timestamp').reset_index(drop=True)
    
    # Calculate intervals between consecutive jobs
    job_intervals = []
    for i in range(1, len(sorted_jobs)):
        interval = (sorted_jobs.iloc[i]['job_timestamp'] - 
                   sorted_jobs.iloc[i-1]['job_timestamp']).total_seconds()
        job_intervals.append(interval)
    
    job_intervals = np.array(job_intervals)
    
    # Filter out network interruptions: exclude intervals > 60 seconds
    # This removes cases where job fetching was interrupted
    normal_intervals = job_intervals[job_intervals <= 60]
    
    if len(normal_intervals) == 0:
        # Fallback to median if no normal intervals found
        fallback_intervals = job_intervals[job_intervals > 0]
        return np.median(fallback_intervals), np.std(fallback_intervals)
    
    # Calculate mean and std for visualization
    job_fetch_mean = np.mean(normal_intervals)
    job_fetch_std = np.std(normal_intervals)
    
    print(f"Job fetch period calculation:")
    print(f"  Total intervals: {len(job_intervals)}")
    print(f"  Normal intervals (<=60s): {len(normal_intervals)} ({len(normal_intervals)/len(job_intervals)*100:.1f}%)")
    print(f"  Mean job fetch period: {job_fetch_mean:.2f} ± {job_fetch_std:.2f} seconds")
    
    return job_fetch_mean, job_fetch_std

def load_data():
    """Load raw_jobs.csv and all_blocks.csv"""
    print("Loading raw_jobs.csv...")
    raw_jobs_df = pd.read_csv('data/raw_jobs.csv')
    
    # Filter only 'job' events (exclude 'login-result' etc.)
    jobs_df = raw_jobs_df[raw_jobs_df['event'] == 'job'].copy()
    print(f"  Total rows: {len(raw_jobs_df)}, Job events: {len(jobs_df)}")
    
    # Convert Unix timestamp to datetime
    jobs_df['job_timestamp'] = pd.to_datetime(jobs_df['ts'], unit='s')
    
    # Rename prev_raw to job_prev_hash for consistency
    jobs_df['job_prev_hash'] = jobs_df['prev_raw'].str.strip()
    
    # Calculate actual job fetch period (excluding network interruptions)
    job_fetch_mean, job_fetch_std = calculate_job_fetch_period(jobs_df)
    
    print("Loading all_blocks.csv...")
    blocks_df = pd.read_csv('data/all_blocks.csv')
    blocks_df['timestamp'] = pd.to_datetime(blocks_df['timestamp'], utc=True)
    # Make tz-naive to match jobs_df
    if blocks_df['timestamp'].dt.tz is not None:
        blocks_df['timestamp'] = blocks_df['timestamp'].dt.tz_localize(None)
    
    # Create a mapping from block hash to block info for faster lookup
    blocks_df['block hash'] = blocks_df['block hash'].str.strip()
    
    # Get Qubic-mined blocks
    qubic_blocks = blocks_df[blocks_df['is_qubic'] == True].copy()
    
    # Create a mapping from prev_hash to jobs for faster lookup
    # Group jobs by prev_hash to find the first job that references each block
    jobs_by_prev_hash = jobs_df.groupby('job_prev_hash').first().reset_index()
    
    return jobs_df, blocks_df, qubic_blocks, jobs_by_prev_hash, job_fetch_mean, job_fetch_std

def calculate_delays(jobs_df, blocks_df, qubic_blocks, jobs_by_prev_hash):
    """
    Calculate time delays between when a Qubic block was mined and when the next job was fetched.
    
    For each Qubic-mined block:
    1. Find the first job AFTER the block was mined that has this block's hash as its prev_hash
    2. Calculate: job_timestamp - block_timestamp
    This measures how quickly a new job was fetched after a block was mined.
    
    Important: 
    - Only consider jobs that were fetched AFTER the block was mined.
    - Exclude blocks mined before jobs data collection started (we can't verify the delay).
    """
    delays = []
    matched_count = 0
    no_job_count = 0
    job_before_block_count = 0
    before_jobs_start_count = 0
    
    print("Calculating delays...")
    print(f"Total Qubic-mined blocks: {len(qubic_blocks)}")
    
    # Get the first job timestamp to exclude blocks mined before jobs data started
    first_job_timestamp = jobs_df['job_timestamp'].min()
    print(f"Jobs data starts at: {first_job_timestamp}")
    
    # Group jobs by prev_hash, but we'll filter by timestamp later
    # Create a mapping for faster lookup: block_hash -> list of jobs
    jobs_by_hash = jobs_df.groupby('job_prev_hash')
    
    for idx, block in qubic_blocks.iterrows():
        block_hash = block['block hash']
        block_timestamp = block['timestamp']
        block_height = block['height']
        
        # Exclude blocks mined before jobs data collection started
        if block_timestamp < first_job_timestamp:
            before_jobs_start_count += 1
            continue
        
        # Find all jobs that have this block's hash as their prev_hash
        if block_hash not in jobs_by_hash.groups:
            no_job_count += 1
            continue
        
        # Get jobs for this block hash, sorted by timestamp
        jobs_for_block = jobs_by_hash.get_group(block_hash).sort_values('job_timestamp')
        
        # Find the first job AFTER the block was mined
        jobs_after_block = jobs_for_block[jobs_for_block['job_timestamp'] > block_timestamp]
        
        if len(jobs_after_block) == 0:
            # All jobs for this block were fetched before the block was mined
            # This shouldn't happen if block_timestamp >= first_job_timestamp, but check anyway
            job_before_block_count += 1
            continue
        
        matched_count += 1
        first_job_after = jobs_after_block.iloc[0]
        job_timestamp = first_job_after['job_timestamp']
        
        # Calculate delay: time between when block was mined and when next job was fetched
        delay_seconds = (job_timestamp - block_timestamp).total_seconds()
        delays.append(delay_seconds)
        
        if matched_count % 5000 == 0:
            print(f"  Processed {matched_count} blocks, found {len(delays)} matches")
    
    print(f"Total Qubic-mined blocks: {len(qubic_blocks)}")
    print(f"Blocks mined before jobs data started (excluded): {before_jobs_start_count}")
    print(f"Blocks with job fetched AFTER block was mined: {matched_count}")
    print(f"Blocks with job fetched BEFORE block was mined (excluded): {job_before_block_count}")
    print(f"Blocks without matching job: {no_job_count}")
    print(f"Valid delays calculated: {len(delays)}")
    
    return np.array(delays)

def plot_delay_distribution(delays, job_fetch_mean, job_fetch_std, output_path):
    """
    Plot histogram of delay distribution.
    Style similar to existing plots.
    """
    if len(delays) == 0:
        print("No delays to plot!")
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Filter out extreme outliers for better visualization
    # Keep delays between -3600 and 7200 seconds (1 hour before to 2 hours after)
    filtered_delays = delays[(delays >= -3600) & (delays <= 7200)]
    
    if len(filtered_delays) == 0:
        print("No delays in reasonable range!")
        return
    
    # Create histogram with light gray bars (contiguous bins, no gaps)
    bin_width = 1
    min_edge = np.floor(filtered_delays.min())
    max_edge = np.ceil(filtered_delays.max())
    bins = np.arange(min_edge, max_edge + bin_width, bin_width)
    counts, bin_edges, patches = ax.hist(filtered_delays, bins=bins, 
                                         color='lightgray', alpha=0.8, 
                                         edgecolor='black')
    
    # Add statistics
    mean_delay = np.mean(filtered_delays)
    
    # Add vertical reference lines (muted colors for publication style)
    ax.axvline(mean_delay, color='#1f77b4', linestyle='-', linewidth=2.5, 
               alpha=0.95, zorder=10,
               label=f'Mean delay: {mean_delay:.2f} s')
    
    # Job fetch period reference (box plot style: mean ± std)
    # 표준편차는 job fetch 간격의 변동성을 나타냄 (약 68%의 간격이 평균 ± 표준편차 범위 내)
    job_fetch_lower = job_fetch_mean - job_fetch_std
    job_fetch_upper = job_fetch_mean + job_fetch_std
    
    # Draw box (shaded region for mean ± std)
    ax.axvspan(job_fetch_lower, job_fetch_upper, 
               color='#d62728', alpha=0.2, zorder=5,
               label=f'Job fetch period: {job_fetch_mean:.1f} s (std: {job_fetch_std:.1f} s)')
    
    # Draw mean line
    ax.axvline(job_fetch_mean, color='#d62728', linestyle='--', linewidth=2.5, 
               alpha=0.95, zorder=10)
    
    ax.set_xlabel('Time Delay (seconds)', fontsize=14)
    ax.set_ylabel('Frequency', fontsize=14)
    # ax.set_title('Distribution of Time Delay Between Block Mining and Next Job Fetch', fontsize=14)
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.8)
    ax.legend(loc='upper right', fontsize=13)
    
    plt.tight_layout()
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    print(f"Saved plot to {output_path}")
    if SHOW_PLOTS:
        plt.show()
    plt.close(fig)

def main():
    """Main function"""
    jobs_df, blocks_df, qubic_blocks, jobs_by_prev_hash, job_fetch_mean, job_fetch_std = load_data()
    delays = calculate_delays(jobs_df, blocks_df, qubic_blocks, jobs_by_prev_hash)
    
    if len(delays) > 0:
        output_path = 'fig/job_block_delay_distribution.pdf'
        plot_delay_distribution(delays, job_fetch_mean, job_fetch_std, output_path)
        
        # Print summary statistics
        print("\n" + "=" * 80)
        print("DELAY STATISTICS")
        print("=" * 80)
        print(f"Total valid delays: {len(delays)}")
        print(f"Mean delay: {np.mean(delays):.2f} seconds")
        print(f"Median delay: {np.median(delays):.2f} seconds")
        print(f"Std deviation: {np.std(delays):.2f} seconds")
        print(f"Min delay: {np.min(delays):.2f} seconds")
        print(f"Max delay: {np.max(delays):.2f} seconds")
        print(f"25th percentile: {np.percentile(delays, 25):.2f} seconds")
        print(f"75th percentile: {np.percentile(delays, 75):.2f} seconds")
    else:
        print("No delays calculated. Check data matching.")

if __name__ == '__main__':
    main()

