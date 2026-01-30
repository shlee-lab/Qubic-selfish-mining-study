import pandas as pd
import matplotlib.pyplot as plt
import os

DERIVED_DIR = "derived"

def analyze_race_timing():
    print("Analyzing Race Timing Distribution...")
    
    # Load leakage data (which contains time diffs)
    # We want to look at cases that were NOT classified as leakage (is_leakage=False)
    # but Qubic still won (self-extended).
    
    # Actually, verify_state_2_leakage.py saved 'state_2_leakage_analysis.csv'
    # Let's load that.
    
    in_csv = os.path.join(DERIVED_DIR, 'state_2_leakage_analysis.csv')
    if not os.path.exists(in_csv):
        print(f"Error: {in_csv} not found. Run verify_state_2_leakage.py first.")
        return

    df = pd.read_csv(in_csv)
    
    # Filter for "True Race Wins" (Qubic won, but not State 2)
    # In the CSV, 'is_leakage' is True if Qubic(H+1) < Honest(H).
    # So 'is_leakage' == False means Qubic(H+1) >= Honest(H).
    # These are the "True Race Wins" we counted.
    
    true_wins = df[df['is_leakage'] == False].copy()
    
    # The 'diff_seconds' in CSV is (Honest(H) - Qubic(H+1)).
    # For True Wins, Honest(H) <= Qubic(H+1), so diff_seconds <= 0.
    # Let's convert to "Time After Honest" = Qubic(H+1) - Honest(H) = -diff_seconds
    true_wins['time_after_honest'] = -true_wins['diff_seconds']
    
    print(f"Total True Race Wins: {len(true_wins)}")
    print(true_wins['time_after_honest'].describe())
    
    # Plot histogram
    plt.figure(figsize=(10, 6))
    plt.hist(true_wins['time_after_honest'], bins=range(0, 60, 1), color='#4C72B0', edgecolor='black', alpha=0.7)
    plt.xlabel('Seconds after Honest Block found')
    plt.ylabel('Number of Qubic Wins')
    plt.title('Timing Distribution of "True" Race Wins')
    plt.grid(True, alpha=0.3)
    
    # Add annotation for the first bin
    first_bin_count = len(true_wins[true_wins['time_after_honest'] < 1])
    plt.text(0.5, first_bin_count, f'<1s: {first_bin_count}', ha='center', va='bottom', fontweight='bold')
    
    plt.savefig('fig/race_timing_distribution.pdf')
    print("Saved plot to fig/race_timing_distribution.pdf")

if __name__ == "__main__":
    analyze_race_timing()
