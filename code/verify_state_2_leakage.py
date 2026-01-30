import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

DERIVED_DIR = "derived"

def load_blocks():
    """Load and preprocess block data"""
    print("Loading blocks data...")
    blocks = pd.read_csv('data/all_blocks.csv')
    blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
    if blocks['timestamp'].dt.tz is not None:
        blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
    return blocks

def verify_state_2_leakage():
    print("Verifying State 2 Leakage in Race Analysis...")
    
    all_blocks = load_blocks()
    
    # Identify Races across ALL blocks
    height_counts = all_blocks['height'].value_counts()
    contested_heights = height_counts[height_counts > 1].index.sort_values()
    
    total_races = 0
    qubic_won_race = 0
    qubic_self_extended = 0
    
    state_2_leakage_count = 0
    true_race_wins = 0
    
    leakage_data = []
    
    for h in contested_heights:
        h_blocks = all_blocks[all_blocks['height'] == h]
        
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            total_races += 1
            
            qubic_block = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
            honest_block = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
            
            # Did Qubic win?
            if not qubic_block['is_orphan']:
                qubic_won_race += 1
                
                # Did Qubic self-extend?
                next_h = h + 1
                next_blocks = all_blocks[all_blocks['height'] == next_h]
                
                if len(next_blocks) > 0:
                    main_next = next_blocks[next_blocks['is_orphan'] == False]
                    if len(main_next) > 0:
                        next_block = main_next.iloc[0]
                        
                        if next_block['is_qubic']:
                            qubic_self_extended += 1
                            
                            # CHECK: Was this actually State 2?
                            # Condition: Qubic(H+1).timestamp < Honest(H).timestamp
                            # If Qubic already had H+1 when Honest found H, it's State 2.
                            
                            time_diff = (honest_block['timestamp'] - next_block['timestamp']).total_seconds()
                            
                            if time_diff > 0:
                                # Honest(H) came AFTER Qubic(H+1) -> State 2
                                state_2_leakage_count += 1
                                is_leakage = True
                            else:
                                # Honest(H) came BEFORE Qubic(H+1) -> True Race Win
                                true_race_wins += 1
                                is_leakage = False
                                
                            leakage_data.append({
                                'height': h,
                                'honest_h_time': honest_block['timestamp'],
                                'qubic_h1_time': next_block['timestamp'],
                                'diff_seconds': time_diff,
                                'is_leakage': is_leakage
                            })

    print(f"\n--- Analysis Results ---")
    print(f"Total Races: {total_races}")
    print(f"Qubic Won Race: {qubic_won_race}")
    print(f"Qubic Self-Extended (Total Apparent Wins): {qubic_self_extended}")
    print(f"\n[Leakage Check]")
    print(f"State 2 Wins (Misclassified): {state_2_leakage_count}")
    print(f"True Race Wins (Mined during Race): {true_race_wins}")
    
    if qubic_self_extended > 0:
        leakage_rate = state_2_leakage_count / qubic_self_extended
        print(f"Leakage Rate: {leakage_rate*100:.2f}% of apparent wins were actually State 2.")
    
    # Recalculate Win Rates
    apparent_win_rate = qubic_self_extended / total_races if total_races > 0 else 0
    true_win_rate = true_race_wins / total_races if total_races > 0 else 0
    
    print(f"\n[Win Rates]")
    print(f"Apparent Win Rate: {apparent_win_rate*100:.2f}%")
    print(f"True Race Win Rate: {true_win_rate*100:.2f}%")
    
    # Save leakage data
    df = pd.DataFrame(leakage_data)
    os.makedirs(DERIVED_DIR, exist_ok=True)
    out_csv = f"{DERIVED_DIR}/state_2_leakage_analysis.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved detailed leakage data to {out_csv}")

if __name__ == "__main__":
    verify_state_2_leakage()
