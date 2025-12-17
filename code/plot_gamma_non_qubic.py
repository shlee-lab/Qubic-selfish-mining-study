import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


def load_blocks():
	"""Load and preprocess block data"""
	blocks = pd.read_csv('data/all_blocks.csv')
	blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
	if blocks['timestamp'].dt.tz is not None:
		blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
	return blocks


def find_non_qubic_competitions(blocks):
	"""Find fork depth 1 situations where both competing blocks are non-Qubic"""
	# Sort blocks by height and timestamp
	blocks = blocks.sort_values(['height', 'timestamp']).reset_index(drop=True)
	
	competitions = []
	
	# Group by height to find forks
	for height in blocks['height'].unique():
		height_blocks = blocks[blocks['height'] == height].sort_values('timestamp')
		
		# Fork depth 1: exactly 2 blocks at this height
		if len(height_blocks) == 2:
			block1 = height_blocks.iloc[0]
			block2 = height_blocks.iloc[1]
			
			# Both blocks must be non-Qubic
			if not block1['is_qubic'] and not block2['is_qubic']:
				# Timestamp가 더 늦은 블록 (block2)
				late_block = block2
				early_block = block1
				
				# Check if late block wins (is on main chain)
				late_wins = not late_block['is_orphan']
				
				# Gamma case: late block wins
				# (timestamp가 더 늦은 블록이 이긴 경우)
				is_gamma_case = late_wins
				
				competitions.append({
					'height': height,
					'timestamp': late_block['timestamp'],
					'early_block_hash': early_block['block hash'],
					'late_block_hash': late_block['block hash'],
					'early_timestamp': early_block['timestamp'],
					'late_timestamp': late_block['timestamp'],
					'late_wins': late_wins,
					'is_gamma_case': is_gamma_case
				})
	
	return pd.DataFrame(competitions)


def calculate_weekly_gamma(competitions_df, blocks_df):
	"""Calculate weekly gamma values for non-Qubic competitions"""
	
	# Add weekly time unit
	competitions_df['week'] = competitions_df['timestamp'].dt.to_period('W-TUE').apply(lambda p: p.start_time.date())
	blocks_df['week'] = blocks_df['timestamp'].dt.to_period('W-TUE').apply(lambda p: p.start_time.date())
	
	results = []
	
	for week in competitions_df['week'].unique():
		# Filter data for this week
		week_competitions = competitions_df[competitions_df['week'] == week]
		week_blocks = blocks_df[blocks_df['week'] == week]
		
		# Calculate total competitions where late block wins
		winning_competitions = week_competitions[week_competitions['late_wins'] == True]
		total_wins = len(winning_competitions)
		total_competitions = len(week_competitions)
		
		# Calculate gamma cases: late block wins
		gamma_cases = winning_competitions[winning_competitions['is_gamma_case'] == True]
		gamma_successes = len(gamma_cases)
		
		# Calculate gamma rate: late block wins / total competitions
		gamma_rate = total_wins / total_competitions if total_competitions > 0 else 0
		
		results.append({
			'week': week,
			'gamma': gamma_rate,
			'total_competitions': len(week_competitions),
			'total_wins': total_wins,
			'gamma_successes': gamma_successes,
			'blocks': len(week_blocks)
		})
	
	return pd.DataFrame(results)


def create_weekly_dual_axis_chart(weekly_df):
	"""Create weekly chart with dual y-axis showing gamma and competition counts"""
	fig, ax1 = plt.subplots(figsize=(10, 6))
	
	# Convert week to string for better x-axis display
	weekly_df['week_str'] = weekly_df['week'].astype(str)
	
	# Create bars for competition counts (left y-axis)
	bars = ax1.bar(weekly_df['week_str'], weekly_df['total_competitions'], width=0.7,
				   alpha=0.7, color='lightgray', edgecolor='black', linewidth=1, label='Non-Qubic Competition Cases')
	ax1.set_xlabel('Week', fontsize=18)
	ax1.set_ylabel('Non-Qubic Competition Cases', fontsize=18)
	ax1.tick_params(axis='x', rotation=45)
	
	# Create line for gamma values (right y-axis)
	ax2 = ax1.twinx()
	line = ax2.plot(weekly_df['week_str'], weekly_df['gamma'], 'ro-', linewidth=2, markersize=6, label='γ Rate')
	ax2.set_ylabel('γ Rate', fontsize=18)
	ax2.set_ylim(-0.01, 1)  # Set y-axis range with slight offset from 0 for better visibility

	ax1.grid(True, alpha=0.3)
	
	# Add legend in upper right corner
	lines1, labels1 = ax1.get_legend_handles_labels()
	lines2, labels2 = ax2.get_legend_handles_labels()
	ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=15)
	
	# Add value labels on gamma line only (with larger font)
	for i, (week, gamma) in enumerate(zip(weekly_df['week_str'], weekly_df['gamma'])):
		if not pd.isna(gamma) and gamma > 0:
			# Position gamma values slightly above the line for better visibility
			ax2.text(i, gamma + 0.005, f'{gamma:.3f}', ha='center', va='bottom', 
					fontsize=10, fontweight='bold')
	
	plt.tight_layout()
	plt.savefig('fig/gamma_non_qubic.pdf', dpi=300, bbox_inches='tight')


def main():
	"""Main analysis function"""
	print("Loading data...")
	blocks_df = load_blocks()
	
	print("Finding non-Qubic competitions (fork depth 1)...")
	competitions_df = find_non_qubic_competitions(blocks_df.copy())
	
	print(f"Found {len(competitions_df)} non-Qubic competitions")
	
	print("Calculating weekly gamma values...")
	weekly_df = calculate_weekly_gamma(competitions_df.copy(), blocks_df.copy())

	# Print summary statistics
	print("=== Weekly Summary Statistics ===")
	print(f"Total weeks analyzed: {len(weekly_df)}")
	print(f"Average gamma rate: {weekly_df['gamma'].mean():.6f} ({weekly_df['gamma'].mean()*100:.4f}%)")
	print(f"Total competitions: {weekly_df['total_competitions'].sum()}")
	print(f"Total wins: {weekly_df['total_wins'].sum()}")
	print(f"Total gamma successes: {weekly_df['gamma_successes'].sum()}")
	print(f"Average competitions per week: {weekly_df['total_competitions'].mean():.2f}")
	print(f"Max competitions in a week: {weekly_df['total_competitions'].max()}")
	print(f"Weeks with competitions: {len(weekly_df[weekly_df['total_competitions'] > 0])}")
	
	# Save results
	competitions_df.to_csv('non_qubic_competitions.csv', index=False)
	weekly_df.to_csv('non_qubic_gamma_weekly_analysis.csv', index=False)
	
	print("\nCreating weekly dual-axis chart...")
	create_weekly_dual_axis_chart(weekly_df)
	
	print("Analysis complete!")


if __name__ == '__main__':
	main()

