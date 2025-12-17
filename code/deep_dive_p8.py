import pandas as pd
import numpy as np

def load_blocks():
    """Load and preprocess block data"""
    print("Loading blocks data...")
    blocks = pd.read_csv('data/all_blocks.csv')
    blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
    if blocks['timestamp'].dt.tz is not None:
        blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
    return blocks

def analyze_p8():
    # P8 Timestamps from CSV
    start_time = pd.Timestamp("2025-09-04 17:00:00")
    end_time = pd.Timestamp("2025-09-15 04:00:00")
    
    print(f"Analyzing Period 8: {start_time} to {end_time}")
    
    all_blocks = load_blocks()
    
    # Filter for P8
    mask = (all_blocks['timestamp'] >= start_time) & (all_blocks['timestamp'] < end_time)
    p8_blocks = all_blocks[mask].copy()
    
    total_blocks = len(p8_blocks)
    qubic_blocks = p8_blocks[p8_blocks['is_qubic'] == True]
    honest_blocks = p8_blocks[p8_blocks['is_qubic'] == False]
    
    qubic_count = len(qubic_blocks)
    honest_count = len(honest_blocks)
    alpha_observed = qubic_count / total_blocks
    
    print(f"\nTotal Blocks: {total_blocks}")
    print(f"Qubic Blocks: {qubic_count} ({alpha_observed*100:.2f}%)")
    print(f"Honest Blocks: {honest_count}")
    
    # Analyze Races
    print("\n--- Race Analysis ---")
    height_counts = p8_blocks['height'].value_counts()
    contested_heights = height_counts[height_counts > 1].index.sort_values()
    
    total_races = 0
    qubic_won_race = 0
    honest_won_race = 0
    
    qubic_self_extended = 0
    honest_extended_qubic = 0 # This is Gamma success
    
    for h in contested_heights:
        h_blocks = p8_blocks[p8_blocks['height'] == h]
        
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            total_races += 1
            
            # Who won? (Whose block is NOT orphan)
            qubic_block = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
            honest_block = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
            
            if not qubic_block['is_orphan']:
                qubic_won_race += 1
                
                # Who mined the NEXT block? (Extension)
                next_h = h + 1
                next_blocks = all_blocks[all_blocks['height'] == next_h]
                if len(next_blocks) > 0:
                    # Check the main chain block at next height
                    main_next = next_blocks[next_blocks['is_orphan'] == False]
                    if len(main_next) > 0:
                        winner_next = main_next.iloc[0]
                        if winner_next['is_qubic']:
                            qubic_self_extended += 1
                        else:
                            honest_extended_qubic += 1
            else:
                honest_won_race += 1

    print(f"Total Races: {total_races}")
    print(f"Honest Won: {honest_won_race} ({honest_won_race/total_races*100:.1f}%)")
    print(f"Qubic Won: {qubic_won_race} ({qubic_won_race/total_races*100:.1f}%)")
    print(f"  - via Honest Extension (Gamma): {honest_extended_qubic}")
    print(f"  - via Self Extension (Luck/Strategy): {qubic_self_extended}")
    
    # Analyze Uncontested Private Chains
    print("\n--- Uncontested Private Chain Analysis ---")
    # Identify Qubic blocks that are NOT orphans and NOT part of a race
    # And are part of a sequence of Qubic blocks
    
    # Simple heuristic: Count Qubic main chain blocks that are NOT at contested heights
    qubic_main_chain = qubic_blocks[qubic_blocks['is_orphan'] == False]
    uncontested_wins = 0
    for idx, block in qubic_main_chain.iterrows():
        if block['height'] not in contested_heights:
            uncontested_wins += 1
            
    print(f"Uncontested Qubic Wins: {uncontested_wins}")
    print(f"Contested Qubic Wins: {qubic_won_race}")
    
    # Conclusion on Mechanism
    print("\n--- Mechanism Conclusion ---")
    if qubic_self_extended > honest_extended_qubic * 2:
        print("DOMINANT FACTOR: Qubic Self-Extension.")
        print("Qubic won races by mining the next block themselves, bypassing the low gamma.")
    elif alpha_observed > 0.30: # Assuming average is ~22%
        print("DOMINANT FACTOR: High Luck (Alpha).")
        print(f"Observed hashrate ({alpha_observed*100:.1f}%) is significantly higher than average.")
    else:
        print("FACTOR: Mixed / Uncontested Wins.")

if __name__ == "__main__":
    analyze_p8()
