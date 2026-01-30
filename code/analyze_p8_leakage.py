import pandas as pd

DERIVED_DIR = "derived"

def analyze_p8_leakage():
    print("Analyzing P8 Leakage...")
    
    # Load leakage data
    df = pd.read_csv(f'{DERIVED_DIR}/state_2_leakage_analysis.csv')
    df['honest_h_time'] = pd.to_datetime(df['honest_h_time'])
    
    # P8 Timestamps
    start_time = pd.Timestamp("2025-09-04 17:00:00")
    end_time = pd.Timestamp("2025-09-15 04:00:00")
    
    # Filter for P8
    p8_df = df[(df['honest_h_time'] >= start_time) & (df['honest_h_time'] < end_time)]
    
    total_wins = len(p8_df)
    leakage_wins = p8_df['is_leakage'].sum()
    true_wins = total_wins - leakage_wins
    
    print(f"P8 Apparent Wins: {total_wins}")
    print(f"P8 State 2 Leakage: {leakage_wins}")
    print(f"P8 True Race Wins: {true_wins}")
    print(f"P8 Leakage Rate: {leakage_wins/total_wins*100:.2f}%")
    
    # We need Total Races in P8 to calculate True Win Rate
    # From previous analysis (race_resolution_stats.csv), P8 Total Races was 1496.
    # Let's hardcode or re-calculate? 
    # Re-calculating is safer but I don't want to load all blocks again.
    # I'll trust the previous number 1496 for now, or just report the leakage % of wins.
    
    total_races_p8 = 1496
    apparent_win_rate = total_wins / total_races_p8
    true_win_rate = true_wins / total_races_p8
    
    print(f"\n[P8 Corrected Stats]")
    print(f"Original Win Rate: {apparent_win_rate*100:.2f}%")
    print(f"Corrected Win Rate: {true_win_rate*100:.2f}%")

if __name__ == "__main__":
    analyze_p8_leakage()
