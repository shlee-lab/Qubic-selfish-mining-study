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


def identify_state_transitions(blocks):
	"""Identify state transitions based on proper state machine logic"""
	# Sort blocks by height and timestamp
	blocks = blocks.sort_values(['height', 'timestamp']).reset_index(drop=True)
	
	states = []
	prev_state = 0  # Start with state 0
	
	for i, block in blocks.iterrows():
		if not block['is_qubic']:
			continue
		
		height = block['height']
		current_timestamp = block['timestamp']
		
		# Get all blocks at this height
		height_blocks = blocks[blocks['height'] == height].sort_values('timestamp')
		qubic_blocks = height_blocks[height_blocks['is_qubic'] == True]
		non_qubic_blocks = height_blocks[height_blocks['is_qubic'] == False]
		
		# Check if there are orphans at this height
		has_orphans = len(height_blocks) > 1
		
		# Determine current state based on state machine logic
		current_state = 0
		transition = "N/A"
		
		if not has_orphans:
			# No orphans - state 0
			current_state = 0
			transition = f"{prev_state}->0"
		else:
			# There are orphans - need to determine state
			first_qubic = qubic_blocks.iloc[0]
			first_non_qubic = non_qubic_blocks.iloc[0] if len(non_qubic_blocks) > 0 else None
			
			if first_non_qubic is not None:
				if first_qubic['timestamp'] < first_non_qubic['timestamp']:
					# Qubic mined first
					if prev_state == 0:
						current_state = 1  # 0 -> 1 (start private chain)
						transition = "0->1"
					else:
						current_state = prev_state + 1  # Extend private chain
						transition = f"{prev_state}->{current_state}"
				else:
					# Others mined first
					if prev_state == 1:
						current_state = -1  # 1 -> -1 (catch-up)
						transition = "1->-1"
					elif prev_state == -1:
						current_state = 0  # -1 -> 0'' (0'' state)
						transition = "-1->0''"
					else:
						current_state = 0  # Reset to 0
						transition = f"{prev_state}->0"
			else:
				# Only Qubic blocks
				current_state = prev_state + 1 if prev_state > 0 else 1
				transition = f"{prev_state}->{current_state}"
		
		states.append({
			'height': height,
			'timestamp': current_timestamp,
			'state': current_state,
			'transition': transition,
			'prev_state': prev_state,
			'is_orphan': block['is_orphan'],
			'block_hash': block['block hash']
		})
		
		prev_state = current_state
	
	return pd.DataFrame(states)


def calculate_weekly_gamma_with_0_prime_estimation(states_df, blocks_df):
	"""Calculate weekly gamma values and estimate 0' state counts using robust logic"""
	
	# Add weekly time unit
	blocks_df['week'] = blocks_df['timestamp'].dt.to_period('W-TUE').apply(lambda p: p.start_time.date())
	
	results = []
	
	for week in blocks_df['week'].unique():
		# Filter data for this week
		week_blocks = blocks_df[blocks_df['week'] == week]
		
		# Calculate alpha (Qubic's mining power share)
		total_blocks = len(week_blocks)
		qubic_blocks = len(week_blocks[week_blocks['is_qubic'] == True])
		alpha = qubic_blocks / total_blocks if total_blocks > 0 else 0
		
		# Identify contested heights (Qubic vs Honest)
		height_counts = week_blocks['height'].value_counts()
		potential_contested = height_counts[height_counts > 1].index
		
		total_0_prime = 0
		gamma_opportunities = 0
		gamma_successes = 0
		
		for h in potential_contested:
			h_blocks = week_blocks[week_blocks['height'] == h]
			
			# Check if it's Qubic vs Honest (at least one of each)
			has_qubic = h_blocks['is_qubic'].any()
			has_honest = (~h_blocks['is_qubic']).any()
			
			if has_qubic and has_honest:
				# 1. Check if it ended as 2:1 (Next block exists)
				next_h = h + 1
				next_blocks = blocks_df[blocks_df['height'] == next_h]
				main_next = next_blocks[next_blocks['is_orphan'] == False]
				
				if len(main_next) == 0:
					continue # Not a resolved 2:1 case, skip.

				next_block = main_next.iloc[0]
				
				# 2. Determine if it's a valid Race (State 0')
				# Default is True (Honest winning is always a Race)
				is_race = True
				
				if next_block['is_qubic']:
					# Qubic won (Qubic H -> Qubic H+1). 
					# Check for State 2: Did Qubic find H+1 BEFORE Honest found H?
					honest_block_at_h = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
					if next_block['timestamp'] < honest_block_at_h['timestamp']:
						is_race = False # State 2 (Already had H+1), not a Race.
				
				if is_race:
					total_0_prime += 1
					
					# Calculate Gamma
					# Gamma is the probability Honest miners choose Qubic's block
					# We look at cases where the NEXT block is Honest
					if not next_block['is_qubic']:
						gamma_opportunities += 1
						
						# Did it extend Qubic?
						# If Qubic block at H is NOT orphan, then it was extended.
						qubic_block_at_h = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
						if not qubic_block_at_h['is_orphan']:
							gamma_successes += 1
		
		# Calculate gamma rate
		# Gamma = P(Honest extends Qubic | Honest finds next)
		gamma_rate = gamma_successes / gamma_opportunities if gamma_opportunities > 0 else 0
		
		results.append({
			'week': week,
			'alpha': alpha,
			'gamma': gamma_rate,
			'total_0_prime': total_0_prime, # This is the count of ALL races
			'gamma_successes': gamma_successes,
			'estimated_0_prime_count': total_0_prime,
			'blocks': len(week_blocks)
		})
	
	return pd.DataFrame(results)


def create_weekly_dual_axis_chart(weekly_stats):
	"""Create weekly chart with dual y-axis showing gamma and 0' state counts"""
	fig, ax1 = plt.subplots(figsize=(10, 6))
	
	# Convert week to string for better x-axis display
	weekly_stats['week_str'] = weekly_stats['week'].astype(str)
	
	# Create bars for 0' state counts (left y-axis)
	bars = ax1.bar(weekly_stats['week_str'], weekly_stats['estimated_0_prime_count'], width=0.7,
				   alpha=0.7, color='lightgray', edgecolor='black', linewidth=1, label='Estimated 0\' State Count')
	ax1.set_xlabel('Week', fontsize=18)
	ax1.set_ylabel('Estimated 0\' State Count', fontsize=18)
	ax1.tick_params(axis='x', rotation=45)
	
	# Create a second y-axis for Gamma Rate
	ax2 = ax1.twinx()
	
	# Filter for valid gamma points (Min 10 races)
	MIN_RACES = 10
	valid_gamma_stats = weekly_stats[weekly_stats['total_0_prime'] >= MIN_RACES]
	
	# Plot Gamma Line only for valid points
	line = ax2.plot(valid_gamma_stats['week_str'], valid_gamma_stats['gamma'], 'ro-', linewidth=2, markersize=6, label='γ Rate')
	ax2.set_ylabel('γ Rate', fontsize=18)
	ax2.set_ylim(-0.01, 0.2)  # Set y-axis range with slight offset from 0 for better visibility

	ax1.grid(True, alpha=0.3)
	
	# Add legend in upper right corner
	lines1, labels1 = ax1.get_legend_handles_labels()
	lines2, labels2 = ax2.get_legend_handles_labels()
	ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=15)
	
	# Add value labels on gamma line only (with larger font)
	for i, row in valid_gamma_stats.iterrows():
		# Find the index in the original dataframe to get the correct x-position
		idx = weekly_stats.index.get_loc(i)
		gamma = row['gamma']
		if not pd.isna(gamma) and gamma > 0:
			# Position gamma values slightly above the line for better visibility
			ax2.text(idx, gamma + 0.005, f'{gamma:.3f}', ha='center', va='bottom', 
					fontsize=10, fontweight='bold')
	
	plt.tight_layout()
	plt.savefig('fig/gamma.pdf', dpi=300, bbox_inches='tight')


def main():
	"""Main analysis function"""
	print("Loading data...")
	blocks_df = load_blocks()
	
	print("Identifying state transitions...")
	states_df = identify_state_transitions(blocks_df.copy())
	
	print("Calculating weekly gamma values with 0' state estimation...")
	weekly_df = calculate_weekly_gamma_with_0_prime_estimation(states_df.copy(), blocks_df.copy())

	# Print summary statistics
	print("=== Weekly Summary Statistics ===")
	print(f"Total weeks analyzed: {len(weekly_df)}")
	print(f"Average gamma rate: {weekly_df['gamma'].mean():.6f} ({weekly_df['gamma'].mean()*100:.4f}%)")
	print(f"Total estimated 0' states: {weekly_df['estimated_0_prime_count'].sum()}")
	print(f"Average 0' states per week: {weekly_df['estimated_0_prime_count'].mean():.2f}")
	print(f"Max 0' states in a week: {weekly_df['estimated_0_prime_count'].max()}")
	print(f"Weeks with 0' states: {len(weekly_df[weekly_df['estimated_0_prime_count'] > 0])}")
	
	# Save results
	weekly_df.to_csv('qubic_gamma_weekly_analysis.csv', index=False)
	
	print("\nCreating weekly dual-axis chart...")
	create_weekly_dual_axis_chart(weekly_df)
	
	print("Analysis complete!")


if __name__ == '__main__':
	main()