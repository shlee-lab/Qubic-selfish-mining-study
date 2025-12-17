import pandas as pd
import numpy as np

def check_average_head_start():
    print("Checking Average Head Start for True Races...")
    
    blocks = pd.read_csv('data/all_blocks.csv')
    blocks['timestamp'] = pd.to_datetime(blocks['timestamp'])
    if blocks['timestamp'].dt.tz is not None:
        blocks['timestamp'] = blocks['timestamp'].dt.tz_localize(None)
        
    height_counts = blocks['height'].value_counts()
    contested_heights = height_counts[height_counts > 1].index.sort_values()
    
    head_starts = []
    
    for h in contested_heights:
        h_blocks = blocks[blocks['height'] == h]
        
        has_qubic = h_blocks['is_qubic'].any()
        has_honest = (~h_blocks['is_qubic']).any()
        
        if has_qubic and has_honest:
            # 1. Check if it ended as 2:1 (Next block exists)
            next_h = h + 1
            next_blocks = blocks[blocks['height'] == next_h]
            main_next = next_blocks[next_blocks['is_orphan'] == False]
            
            if len(main_next) == 0:
                continue

            next_block = main_next.iloc[0]
            
            # Get timestamps at H
            qubic_block_at_h = h_blocks[h_blocks['is_qubic'] == True].iloc[0]
            honest_block_at_h = h_blocks[h_blocks['is_qubic'] == False].iloc[0]
            
            # Calculate Head Start
            # Positive = Qubic found H first (Private Mining)
            head_start = (honest_block_at_h['timestamp'] - qubic_block_at_h['timestamp']).total_seconds()
            
            # 2. Apply State 2 Filter
            is_valid_race = True
            if next_block['is_qubic']:
                # If Qubic won, check if it was State 2
                if next_block['timestamp'] < honest_block_at_h['timestamp']:
                    is_valid_race = False
            
            if is_valid_race:
                head_starts.append(head_start)
                
    df = pd.DataFrame(head_starts, columns=['head_start'])
    
    print(f"\nAnalysis of {len(df)} True Races:")
    print(df['head_start'].describe())
    
    avg_head_start = df['head_start'].mean()
    print(f"\nAverage Head Start: {avg_head_start:.4f} seconds")
    
    if abs(avg_head_start - 63) < 10:
        print("Conclusion: The implied 63s advantage MATCHES the observed Average Head Start.")
    else:
        print("Conclusion: The implied advantage does NOT match the observed Head Start.")

if __name__ == "__main__":
    check_average_head_start()
