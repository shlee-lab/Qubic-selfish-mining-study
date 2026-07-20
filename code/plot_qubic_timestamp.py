import pandas as pd
import matplotlib.pyplot as plt

from data_utils import load_blocks
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np

# Font settings for better display
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

def analyze_qubic_timestamp_manipulation():
    """
    Analyze Qubic's orphan blocks timestamp manipulation by comparing with main chain blocks.
    """
    
    # Load CSV file
    print("Loading data...")
    df = load_blocks()
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print(f"Total blocks: {len(df)}")
    print(f"Data period: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    
    # Filter Qubic orphan blocks
    qubic_orphan_blocks = df[(df['is_qubic'] == True) & (df['is_orphan'] == True)]
    print(f"Qubic orphan blocks: {len(qubic_orphan_blocks)}")
    
    # Analyze timestamp relationships with fork analysis
    analysis_results = []
    
    # Group orphan blocks by fork (same timestamp and consecutive heights)
    orphan_forks = []
    current_fork = []
    
    # Sort by timestamp to identify forks
    qubic_orphan_sorted = qubic_orphan_blocks.sort_values('timestamp')
    
    for _, qubic_orphan in qubic_orphan_sorted.iterrows():
        if len(current_fork) == 0:
            current_fork.append(qubic_orphan)
        else:
            # Check if this block is part of the same fork (within 5 minutes and consecutive height)
            last_block = current_fork[-1]
            time_diff = (qubic_orphan['timestamp'] - last_block['timestamp']).total_seconds()
            height_diff = qubic_orphan['height'] - last_block['height']
            
            if time_diff <= 300 and height_diff == 1:  # Same fork (5 minutes window)
                current_fork.append(qubic_orphan)
            else:  # New fork
                if len(current_fork) > 0:
                    orphan_forks.append(current_fork)
                current_fork = [qubic_orphan]
    
    # Add the last fork
    if len(current_fork) > 0:
        orphan_forks.append(current_fork)
    
    print(f"Identified {len(orphan_forks)} orphan forks")
    
    # Print fork length distribution
    fork_lengths = [len(fork) for fork in orphan_forks]
    fork_length_counts = pd.Series(fork_lengths).value_counts().sort_index()
    print(f"Fork length distribution: {dict(fork_length_counts)}")
    
    for fork_idx, fork in enumerate(orphan_forks):
        fork_length = len(fork)
        
        for block_idx, qubic_orphan in enumerate(fork):
            height = qubic_orphan['height']
            qubic_timestamp = qubic_orphan['timestamp']
            
            # Find main chain blocks at the same height
            main_chain_blocks = df[(df['height'] == height) & (df['is_orphan'] == False)]
            
            if len(main_chain_blocks) > 0:
                # Get the main chain block (should be only one)
                main_block = main_chain_blocks.iloc[0]
                main_timestamp = main_block['timestamp']
                
                # Calculate time difference
                time_diff = (qubic_timestamp - main_timestamp).total_seconds()
                
                # Determine relationship
                if time_diff < 0:
                    relationship = "Qubic block mined before main chain"
                elif time_diff == 0:
                    relationship = "Same timestamp"
                else:
                    relationship = "Qubic block mined after main chain"
                
                analysis_results.append({
                    'height': height,
                    'qubic_timestamp': qubic_timestamp,
                    'main_timestamp': main_timestamp,
                    'time_diff_seconds': time_diff,
                    'relationship': relationship,
                    'qubic_block_hash': qubic_orphan['block hash'],
                    'main_block_hash': main_block['block hash'],
                    'fork_id': fork_idx,
                    'fork_length': fork_length,
                    'block_position_in_fork': block_idx + 1,  # 1-based position
                    'is_first_block_in_fork': block_idx == 0,
                    'is_last_block_in_fork': block_idx == fork_length - 1
                })
    
    # Convert to DataFrame
    results_df = pd.DataFrame(analysis_results)
    
    if len(results_df) == 0:
        print("No Qubic orphan blocks found for analysis.")
        return
    
    print(f"Analyzed {len(results_df)} Qubic orphan blocks")
    
    # Create visualization: Only timestamp latency summary
    fig, ax1 = plt.subplots(1, 1, figsize=(8, 6))
    
    # Time difference distribution (latency summary)
    ax1.hist(results_df['time_diff_seconds'], bins=50, alpha=0.7, color='lightgray', edgecolor='black')
    ax1.axvline(x=0, color='black', linestyle='--', alpha=0.7, label='Same timestamp')
    ax1.set_xlabel('Time Difference (seconds)', fontsize=16)
    ax1.set_ylabel('Frequency', fontsize=16)
    ax1.legend(fontsize=16)
    ax1.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save graph
    plt.savefig('fig/qubic_timestamp.pdf', dpi=300, bbox_inches='tight')
    print("timestamp.pdf saved.")
    
    # Print analysis summary
    print("\n=== Timestamp Analysis Results ===")
    print(f"Total Qubic orphan blocks analyzed: {len(results_df)}")
    print(f"Total orphan forks identified: {len(orphan_forks)}")
    print(f"Average time difference: {results_df['time_diff_seconds'].mean():.2f} seconds")
    print(f"Median time difference: {results_df['time_diff_seconds'].median():.2f} seconds")
    print(f"Standard deviation: {results_df['time_diff_seconds'].std():.2f} seconds")
    print(f"Min time difference: {results_df['time_diff_seconds'].min():.2f} seconds")
    print(f"Max time difference: {results_df['time_diff_seconds'].max():.2f} seconds")
    
    print("\n=== Fork Length Analysis ===")
    fork_length_stats = results_df.groupby('fork_length').agg({
        'time_diff_seconds': ['mean', 'std', 'count'],
        'block_position_in_fork': 'max'
    }).round(2)
    
    for fork_len in sorted(results_df['fork_length'].unique()):
        fork_data = results_df[results_df['fork_length'] == fork_len]
        avg_time_diff = fork_data['time_diff_seconds'].mean()
        std_time_diff = fork_data['time_diff_seconds'].std()
        count = len(fork_data)
        print(f"Fork length {fork_len}: {count} blocks, avg time diff: {avg_time_diff:.2f}s (짹{std_time_diff:.2f}s)")
    
    print("\n=== Position in Fork Analysis ===")
    position_stats = results_df.groupby('block_position_in_fork')['time_diff_seconds'].agg(['mean', 'std', 'count']).round(2)
    
    for pos in sorted(results_df['block_position_in_fork'].unique()):
        pos_data = results_df[results_df['block_position_in_fork'] == pos]
        avg_time_diff = pos_data['time_diff_seconds'].mean()
        std_time_diff = pos_data['time_diff_seconds'].std()
        count = len(pos_data)
        print(f"Position {pos}: {count} blocks, avg time diff: {avg_time_diff:.2f}s (짹{std_time_diff:.2f}s)")
    
    print("\n=== Relationship Categories ===")
    relationship_counts = results_df['relationship'].value_counts()
    for relationship, count in relationship_counts.items():
        percentage = (count / len(results_df)) * 100
        print(f"{relationship}: {count} blocks ({percentage:.1f}%)")
    
    # Check for suspicious patterns
    before_main = results_df[results_df['time_diff_seconds'] < 0]
    after_main = results_df[results_df['time_diff_seconds'] > 0]
    
    print(f"\n=== Suspicious Patterns ===")
    print(f"Blocks mined before main chain: {len(before_main)} ({len(before_main)/len(results_df)*100:.1f}%)")
    print(f"Blocks mined after main chain: {len(after_main)} ({len(after_main)/len(results_df)*100:.1f}%)")
    
    if len(before_main) > 0:
        print(f"Average time before main chain: {before_main['time_diff_seconds'].mean():.2f} seconds")
    if len(after_main) > 0:
        print(f"Average time after main chain: {after_main['time_diff_seconds'].mean():.2f} seconds")
    
    # Analyze first vs last blocks in forks
    first_blocks = results_df[results_df['is_first_block_in_fork']]
    last_blocks = results_df[results_df['is_last_block_in_fork']]
    
    print(f"\n=== First vs Last Blocks in Forks ===")
    print(f"First blocks in forks: {len(first_blocks)} blocks, avg time diff: {first_blocks['time_diff_seconds'].mean():.2f}s")
    print(f"Last blocks in forks: {len(last_blocks)} blocks, avg time diff: {last_blocks['time_diff_seconds'].mean():.2f}s")
    
    
    return results_df

if __name__ == "__main__":
    results = analyze_qubic_timestamp_manipulation()
