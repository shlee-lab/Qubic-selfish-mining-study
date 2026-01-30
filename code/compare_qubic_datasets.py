import pandas as pd
import numpy as np
from datetime import datetime
import os

OUT_DIR = os.path.join("data", "derived")

def compare_qubic_datasets():
    """
    Compare Qubic blocks identified in all_blocks.csv vs blocks-proof.csv
    """
    print("=" * 80)
    print("Qubic 블록 데이터셋 비교 분석")
    print("=" * 80)
    
    # Load datasets
    print("\n1. 데이터 로딩 중...")
    all_blocks = pd.read_csv('data/all_blocks.csv')
    proof_blocks = pd.read_csv('data/blocks-proof.csv')
    
    # Convert timestamps
    all_blocks['timestamp'] = pd.to_datetime(all_blocks['timestamp'])
    proof_blocks['timestamp_dt'] = pd.to_datetime(proof_blocks['Timestamp'], unit='s', utc=True)
    
    # Filter Qubic blocks from all_blocks
    qubic_all = all_blocks[all_blocks['is_qubic'] == True].copy()
    
    print(f"   - all_blocks.csv 전체: {len(all_blocks):,} 블록")
    print(f"   - all_blocks.csv의 Qubic 블록: {len(qubic_all):,} 블록")
    print(f"   - blocks-proof.csv: {len(proof_blocks):,} 블록 (모두 Qubic)")
    
    # Normalize block hashes first (before filtering)
    qubic_all['block_hash_norm'] = qubic_all['block hash'].astype(str).str.lower().str.strip()
    proof_blocks['block_hash_norm'] = proof_blocks['Id'].astype(str).str.lower().str.strip()
    
    # Basic statistics
    print("\n2. 기본 통계")
    print("-" * 80)
    
    # Orphan statistics (after adding block_hash_norm)
    qubic_orphan_all = qubic_all[qubic_all['is_orphan'] == True].copy()
    proof_orphan = proof_blocks[proof_blocks['Status'] == 'ORPHAN'].copy()
    proof_chain = proof_blocks[proof_blocks['Status'] == 'CHAIN'].copy()
    
    print(f"   all_blocks.csv Qubic 블록:")
    print(f"     - Regular (non-orphan): {len(qubic_all) - len(qubic_orphan_all):,}")
    print(f"     - Orphan: {len(qubic_orphan_all):,}")
    
    print(f"   blocks-proof.csv:")
    print(f"     - CHAIN: {len(proof_chain):,}")
    print(f"     - ORPHAN: {len(proof_orphan):,}")
    
    # Time range comparison
    print("\n3. 시간 범위 비교")
    print("-" * 80)
    all_start = qubic_all['timestamp'].min()
    all_end = qubic_all['timestamp'].max()
    proof_start = proof_blocks['timestamp_dt'].min()
    proof_end = proof_blocks['timestamp_dt'].max()
    
    print(f"   all_blocks.csv Qubic:")
    print(f"     - 시작: {all_start}")
    print(f"     - 종료: {all_end}")
    print(f"   blocks-proof.csv:")
    print(f"     - 시작: {proof_start}")
    print(f"     - 종료: {proof_end}")
    
    # Find overlapping period
    overlap_start = max(all_start, proof_start)
    overlap_end = min(all_end, proof_end)
    print(f"\n   교집합 기간 (같은 기간):")
    print(f"     - 시작: {overlap_start}")
    print(f"     - 종료: {overlap_end}")
    
    # Filter to overlapping period
    qubic_overlap = qubic_all[
        (qubic_all['timestamp'] >= overlap_start) & 
        (qubic_all['timestamp'] <= overlap_end)
    ].copy()
    proof_overlap = proof_blocks[
        (proof_blocks['timestamp_dt'] >= overlap_start) & 
        (proof_blocks['timestamp_dt'] <= overlap_end)
    ].copy()
    
    print(f"   교집합 기간 내 블록 수:")
    print(f"     - all_blocks: {len(qubic_overlap):,} 블록")
    print(f"     - blocks-proof: {len(proof_overlap):,} 블록")
    
    # Block hash matching (FULL PERIOD)
    print("\n4. 블록 해시 매칭 분석 (전체 기간)")
    print("-" * 80)
    
    # Find matches (block_hash_norm already added above)
    matched = qubic_all[qubic_all['block_hash_norm'].isin(proof_blocks['block_hash_norm'])]
    unmatched_all = qubic_all[~qubic_all['block_hash_norm'].isin(proof_blocks['block_hash_norm'])]
    unmatched_proof = proof_blocks[~proof_blocks['block_hash_norm'].isin(qubic_all['block_hash_norm'])]
    
    print(f"   매칭된 블록: {len(matched):,} 블록")
    print(f"   all_blocks에만 있는 Qubic 블록: {len(unmatched_all):,} 블록")
    print(f"   blocks-proof에만 있는 블록: {len(unmatched_proof):,} 블록")
    
    # Analyze unmatched blocks
    if len(unmatched_all) > 0:
        print(f"\n   all_blocks에만 있는 Qubic 블록 분석:")
        unmatched_all_copy = unmatched_all.copy()
        print(f"     - Regular: {len(unmatched_all_copy[~unmatched_all_copy['is_orphan']]):,}")
        print(f"     - Orphan: {len(unmatched_all_copy[unmatched_all_copy['is_orphan']]):,}")
        
        # Time distribution of unmatched
        unmatched_all_copy['date'] = unmatched_all_copy['timestamp'].dt.date
        unmatched_by_date = unmatched_all_copy.groupby('date').size()
        print(f"     - 날짜별 분포 (상위 10일):")
        for date, count in unmatched_by_date.nlargest(10).items():
            print(f"       {date}: {count} 블록")
    
    if len(unmatched_proof) > 0:
        print(f"\n   blocks-proof에만 있는 블록 분석:")
        print(f"     - CHAIN: {len(unmatched_proof[unmatched_proof['Status'] == 'CHAIN']):,}")
        print(f"     - ORPHAN: {len(unmatched_proof[unmatched_proof['Status'] == 'ORPHAN']):,}")
        
        # Time distribution
        unmatched_proof_copy = unmatched_proof.copy()
        unmatched_proof_copy['date'] = unmatched_proof_copy['timestamp_dt'].dt.date
        unmatched_by_date = unmatched_proof_copy.groupby('date').size()
        print(f"     - 날짜별 분포 (상위 10일):")
        for date, count in unmatched_by_date.nlargest(10).items():
            print(f"       {date}: {count} 블록")
    
    # Orphan block comparison
    print("\n5. Orphan 블록 상세 비교")
    print("-" * 80)
    
    # Match orphans (need to get hashes from the full qubic_all dataframe)
    qubic_orphan_all_with_hash = qubic_all[qubic_all['is_orphan'] == True]
    qubic_orphan_hashes = set(qubic_orphan_all_with_hash['block_hash_norm'])
    proof_orphan_hashes = set(proof_orphan['block_hash_norm'])
    
    orphan_matched = qubic_orphan_hashes & proof_orphan_hashes
    orphan_only_all = qubic_orphan_hashes - proof_orphan_hashes
    orphan_only_proof = proof_orphan_hashes - qubic_orphan_hashes
    
    print(f"   양쪽 모두에서 Orphan으로 식별: {len(orphan_matched):,} 블록")
    print(f"   all_blocks에만 Orphan으로 식별: {len(orphan_only_all):,} 블록")
    print(f"   blocks-proof에만 Orphan으로 식별: {len(orphan_only_proof):,} 블록")
    
    # Regular block comparison
    print("\n6. Regular (CHAIN) 블록 상세 비교")
    print("-" * 80)
    
    qubic_regular = qubic_all[~qubic_all['is_orphan']].copy()
    qubic_regular_hashes = set(qubic_regular['block_hash_norm'])
    proof_chain_hashes = set(proof_chain['block_hash_norm'])
    
    regular_matched = qubic_regular_hashes & proof_chain_hashes
    regular_only_all = qubic_regular_hashes - proof_chain_hashes
    regular_only_proof = proof_chain_hashes - qubic_regular_hashes
    
    print(f"   양쪽 모두에서 Regular/CHAIN으로 식별: {len(regular_matched):,} 블록")
    print(f"   all_blocks에만 Regular: {len(regular_only_all):,} 블록")
    print(f"   blocks-proof에만 CHAIN: {len(regular_only_proof):,} 블록")
    
    # Status mismatch analysis
    print("\n7. 상태 불일치 분석 (매칭된 블록 중)")
    print("-" * 80)
    
    matched_merged = matched.merge(
        proof_blocks[['block_hash_norm', 'Status']],
        on='block_hash_norm',
        how='left',
        suffixes=('_all', '_proof')
    )
    
    # Check status consistency
    status_mismatch = []
    for _, row in matched_merged.iterrows():
        is_orphan_all = row['is_orphan']
        # Status column should be renamed to Status_proof due to suffixes
        status_proof = row.get('Status_proof', row.get('Status', None))
        
        if is_orphan_all and status_proof != 'ORPHAN':
            status_mismatch.append({
                'block_hash': row['block hash'],
                'height': row['height'],
                'all_blocks_status': 'ORPHAN',
                'proof_status': status_proof
            })
        elif not is_orphan_all and status_proof != 'CHAIN':
            status_mismatch.append({
                'block_hash': row['block hash'],
                'height': row['height'],
                'all_blocks_status': 'REGULAR',
                'proof_status': status_proof
            })
    
    if len(status_mismatch) > 0:
        print(f"   상태 불일치 블록: {len(status_mismatch):,} 블록")
        mismatch_df = pd.DataFrame(status_mismatch)
        print(f"   - all_blocks=ORPHAN, proof=CHAIN: {len(mismatch_df[(mismatch_df['all_blocks_status'] == 'ORPHAN') & (mismatch_df['proof_status'] == 'CHAIN')]):,}")
        print(f"   - all_blocks=REGULAR, proof=ORPHAN: {len(mismatch_df[(mismatch_df['all_blocks_status'] == 'REGULAR') & (mismatch_df['proof_status'] == 'ORPHAN')]):,}")
    else:
        print("   상태 불일치 없음 - 모든 매칭된 블록의 상태가 일치합니다.")
    
    # OVERLAPPING PERIOD COMPARISON
    print("\n" + "=" * 80)
    print("같은 기간 동안 비교 (교집합 기간: {} ~ {})".format(
        overlap_start.strftime('%Y-%m-%d'), 
        overlap_end.strftime('%Y-%m-%d')
    ))
    print("=" * 80)
    
    # Block hash matching in overlapping period
    print("\n8-1. 교집합 기간 블록 해시 매칭")
    print("-" * 80)
    
    matched_overlap = qubic_overlap[qubic_overlap['block_hash_norm'].isin(proof_overlap['block_hash_norm'])]
    unmatched_all_overlap = qubic_overlap[~qubic_overlap['block_hash_norm'].isin(proof_overlap['block_hash_norm'])]
    unmatched_proof_overlap = proof_overlap[~proof_overlap['block_hash_norm'].isin(qubic_overlap['block_hash_norm'])]
    
    print(f"   매칭된 블록: {len(matched_overlap):,} 블록")
    print(f"   all_blocks에만 있는 Qubic 블록: {len(unmatched_all_overlap):,} 블록")
    print(f"   blocks-proof에만 있는 블록: {len(unmatched_proof_overlap):,} 블록")
    
    # Orphan comparison in overlapping period
    print("\n8-2. 교집합 기간 Orphan 블록 비교")
    print("-" * 80)
    
    qubic_orphan_overlap = qubic_overlap[qubic_overlap['is_orphan'] == True].copy()
    proof_orphan_overlap = proof_overlap[proof_overlap['Status'] == 'ORPHAN'].copy()
    proof_chain_overlap = proof_overlap[proof_overlap['Status'] == 'CHAIN'].copy()
    
    print(f"   all_blocks.csv Qubic 블록:")
    print(f"     - Regular (non-orphan): {len(qubic_overlap) - len(qubic_orphan_overlap):,}")
    print(f"     - Orphan: {len(qubic_orphan_overlap):,}")
    
    print(f"   blocks-proof.csv:")
    print(f"     - CHAIN: {len(proof_chain_overlap):,}")
    print(f"     - ORPHAN: {len(proof_orphan_overlap):,}")
    
    qubic_orphan_overlap_hashes = set(qubic_orphan_overlap['block_hash_norm'])
    proof_orphan_overlap_hashes = set(proof_orphan_overlap['block_hash_norm'])
    
    orphan_matched_overlap = qubic_orphan_overlap_hashes & proof_orphan_overlap_hashes
    orphan_only_all_overlap = qubic_orphan_overlap_hashes - proof_orphan_overlap_hashes
    orphan_only_proof_overlap = proof_orphan_overlap_hashes - qubic_orphan_overlap_hashes
    
    print(f"\n   Orphan 블록 매칭:")
    print(f"     - 양쪽 모두에서 Orphan으로 식별: {len(orphan_matched_overlap):,} 블록")
    print(f"     - all_blocks에만 Orphan: {len(orphan_only_all_overlap):,} 블록")
    print(f"     - blocks-proof에만 Orphan: {len(orphan_only_proof_overlap):,} 블록")
    
    # Regular block comparison in overlapping period
    print("\n8-3. 교집합 기간 Regular (CHAIN) 블록 비교")
    print("-" * 80)
    
    qubic_regular_overlap = qubic_overlap[~qubic_overlap['is_orphan']].copy()
    qubic_regular_overlap_hashes = set(qubic_regular_overlap['block_hash_norm'])
    proof_chain_overlap_hashes = set(proof_chain_overlap['block_hash_norm'])
    
    regular_matched_overlap = qubic_regular_overlap_hashes & proof_chain_overlap_hashes
    regular_only_all_overlap = qubic_regular_overlap_hashes - proof_chain_overlap_hashes
    regular_only_proof_overlap = proof_chain_overlap_hashes - qubic_regular_overlap_hashes
    
    print(f"   Regular/CHAIN 블록 매칭:")
    print(f"     - 양쪽 모두에서 Regular/CHAIN으로 식별: {len(regular_matched_overlap):,} 블록")
    print(f"     - all_blocks에만 Regular: {len(regular_only_all_overlap):,} 블록")
    print(f"     - blocks-proof에만 CHAIN: {len(regular_only_proof_overlap):,} 블록")
    
    # Daily comparison in overlapping period
    print("\n8-4. 교집합 기간 일별 블록 수 비교")
    print("-" * 80)
    
    qubic_overlap['date'] = qubic_overlap['timestamp'].dt.date
    proof_overlap['date'] = proof_overlap['timestamp_dt'].dt.date
    
    daily_all_overlap = qubic_overlap.groupby('date').size().rename('all_blocks_count')
    daily_proof_overlap = proof_overlap.groupby('date').size().rename('proof_count')
    
    daily_comparison_overlap = pd.DataFrame({
        'all_blocks': daily_all_overlap,
        'proof': daily_proof_overlap
    }).fillna(0)
    
    daily_comparison_overlap['difference'] = daily_comparison_overlap['proof'] - daily_comparison_overlap['all_blocks']
    daily_comparison_overlap['diff_pct'] = (
        daily_comparison_overlap['difference'] / daily_comparison_overlap['all_blocks'] * 100
    ).round(2)
    daily_comparison_overlap.loc[daily_comparison_overlap['all_blocks'] == 0, 'diff_pct'] = np.nan
    
    print(f"   일별 평균 차이: {daily_comparison_overlap['difference'].mean():.2f} 블록")
    print(f"   일별 최대 차이: {daily_comparison_overlap['difference'].max():.0f} 블록")
    print(f"   일별 최소 차이: {daily_comparison_overlap['difference'].min():.0f} 블록")
    print(f"   일별 평균 차이율: {daily_comparison_overlap['diff_pct'].mean():.2f}%")
    
    # Show days with largest differences
    print(f"\n   차이가 큰 날짜 (상위 10일):")
    for date, row in daily_comparison_overlap.nlargest(10, 'difference').iterrows():
        diff_pct_str = f"{row['diff_pct']:.1f}%" if not pd.isna(row['diff_pct']) else "N/A"
        print(f"     {date}: all_blocks={row['all_blocks']:.0f}, proof={row['proof']:.0f}, 차이={row['difference']:.0f} ({diff_pct_str})")
    
    # Summary for overlapping period
    print("\n8-5. 교집합 기간 요약")
    print("-" * 80)
    print(f"   전체 블록 수:")
    print(f"     - all_blocks: {len(qubic_overlap):,} 블록")
    print(f"     - blocks-proof: {len(proof_overlap):,} 블록")
    print(f"     - 차이: {abs(len(qubic_overlap) - len(proof_overlap)):,} 블록")
    print(f"     - blocks-proof가 {len(proof_overlap) - len(qubic_overlap):,}개 더 많음")
    
    match_rate_overlap = len(matched_overlap) / len(qubic_overlap) * 100 if len(qubic_overlap) > 0 else 0
    match_rate_proof_overlap = len(matched_overlap) / len(proof_overlap) * 100 if len(proof_overlap) > 0 else 0
    print(f"\n   매칭률:")
    print(f"     - all_blocks의 {match_rate_overlap:.2f}%가 blocks-proof에 매칭됨")
    print(f"     - blocks-proof의 {match_rate_proof_overlap:.2f}%가 all_blocks에 매칭됨")
    
    print(f"\n   Orphan 블록:")
    print(f"     - all_blocks: {len(qubic_orphan_overlap):,} 블록")
    print(f"     - blocks-proof: {len(proof_orphan_overlap):,} 블록")
    print(f"     - 차이: {abs(len(qubic_orphan_overlap) - len(proof_orphan_overlap)):,} 블록")
    
    # Daily comparison (FULL PERIOD - for reference)
    print("\n9. 일별 블록 수 비교 (전체 기간)")
    print("-" * 80)
    
    qubic_all['date'] = qubic_all['timestamp'].dt.date
    proof_blocks['date'] = proof_blocks['timestamp_dt'].dt.date
    
    daily_all = qubic_all.groupby('date').size().rename('all_blocks_count')
    daily_proof = proof_blocks.groupby('date').size().rename('proof_count')
    
    daily_comparison = pd.DataFrame({
        'all_blocks': daily_all,
        'proof': daily_proof
    }).fillna(0)
    
    daily_comparison['difference'] = daily_comparison['proof'] - daily_comparison['all_blocks']
    daily_comparison['diff_pct'] = (daily_comparison['difference'] / daily_comparison['all_blocks'] * 100).round(2)
    
    print(f"   일별 평균 차이: {daily_comparison['difference'].mean():.2f} 블록")
    print(f"   일별 최대 차이: {daily_comparison['difference'].max():.0f} 블록")
    print(f"   일별 최소 차이: {daily_comparison['difference'].min():.0f} 블록")
    
    # Show days with largest differences
    print(f"\n   차이가 큰 날짜 (상위 10일):")
    for date, row in daily_comparison.nlargest(10, 'difference').iterrows():
        print(f"     {date}: all_blocks={row['all_blocks']:.0f}, proof={row['proof']:.0f}, 차이={row['difference']:.0f}")
    
    # Summary
    print("\n" + "=" * 80)
    print("요약")
    print("=" * 80)
    print(f"1. 전체 Qubic 블록 수:")
    print(f"   - all_blocks.csv: {len(qubic_all):,} 블록")
    print(f"   - blocks-proof.csv: {len(proof_blocks):,} 블록")
    print(f"   - 차이: {abs(len(qubic_all) - len(proof_blocks)):,} 블록")
    
    print(f"\n2. 매칭률:")
    match_rate = len(matched) / len(qubic_all) * 100 if len(qubic_all) > 0 else 0
    print(f"   - all_blocks의 {match_rate:.2f}%가 blocks-proof에 매칭됨")
    
    match_rate_proof = len(matched) / len(proof_blocks) * 100 if len(proof_blocks) > 0 else 0
    print(f"   - blocks-proof의 {match_rate_proof:.2f}%가 all_blocks에 매칭됨")
    
    print(f"\n3. Orphan 블록:")
    print(f"   - all_blocks: {len(qubic_orphan_all):,} 블록")
    print(f"   - blocks-proof: {len(proof_orphan):,} 블록")
    print(f"   - 차이: {abs(len(qubic_orphan_all) - len(proof_orphan)):,} 블록")
    
    # Save detailed comparison
    print("\n10. 상세 비교 결과 저장 중...")
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # Save unmatched blocks (full period)
    if len(unmatched_all) > 0:
        unmatched_all[['timestamp', 'height', 'block hash', 'is_orphan']].to_csv(
            os.path.join(OUT_DIR, 'qubic_blocks_only_in_all_blocks.csv'), index=False
        )
        print(f"   - all_blocks에만 있는 블록 (전체 기간): {OUT_DIR}/qubic_blocks_only_in_all_blocks.csv")
    
    if len(unmatched_proof) > 0:
        unmatched_proof[['Timestamp', 'Height', 'Id', 'Status']].to_csv(
            os.path.join(OUT_DIR, 'qubic_blocks_only_in_proof.csv'), index=False
        )
        print(f"   - blocks-proof에만 있는 블록 (전체 기간): {OUT_DIR}/qubic_blocks_only_in_proof.csv")
    
    # Save unmatched blocks (overlapping period)
    if len(unmatched_all_overlap) > 0:
        unmatched_all_overlap[['timestamp', 'height', 'block hash', 'is_orphan']].to_csv(
            os.path.join(OUT_DIR, 'qubic_blocks_only_in_all_blocks_overlap.csv'), index=False
        )
        print(f"   - all_blocks에만 있는 블록 (교집합 기간): {OUT_DIR}/qubic_blocks_only_in_all_blocks_overlap.csv")
    
    if len(unmatched_proof_overlap) > 0:
        unmatched_proof_overlap[['Timestamp', 'Height', 'Id', 'Status']].to_csv(
            os.path.join(OUT_DIR, 'qubic_blocks_only_in_proof_overlap.csv'), index=False
        )
        print(f"   - blocks-proof에만 있는 블록 (교집합 기간): {OUT_DIR}/qubic_blocks_only_in_proof_overlap.csv")
    
    # Save daily comparison
    daily_comparison.to_csv(os.path.join(OUT_DIR, 'daily_qubic_comparison.csv'))
    print(f"   - 일별 비교 (전체 기간): {OUT_DIR}/daily_qubic_comparison.csv")
    
    daily_comparison_overlap.to_csv(os.path.join(OUT_DIR, 'daily_qubic_comparison_overlap.csv'))
    print(f"   - 일별 비교 (교집합 기간): {OUT_DIR}/daily_qubic_comparison_overlap.csv")
    
    print("\n분석 완료!")

if __name__ == "__main__":
    compare_qubic_datasets()

