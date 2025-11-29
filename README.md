# Qubic-Monero Selfish Mining Analysis Dataset

This repository contains the raw dataset used to analyze the mining behavior of the **Qubic** pool on the **Monero** network. The analysis investigates anomalies in Qubic's profitability and identifies evidence of **Selfish Mining** strategies.

## Authors
* **Suhyeon Lee** 
* **Hyeongyeong Kim** 

## Dataset Contents

*   **`all_blocks.csv`**: A comprehensive record of Monero blocks mined during the analysis period (August - October 2025).
    *   **Columns**: `height`, `timestamp`, `difficulty`, `miner_address`, `is_qubic`, `is_orphan`, etc.
    *   **Purpose**: Used to calculate network hashrate share (Alpha), revenue, and identify race conditions (orphan blocks).

*   **`raw_jobs.csv`**: (Optional/If applicable) Raw mining job data collected from the pool or node, providing granular timestamps for job distribution.
    *   **Purpose**: Used to analyze propagation delays and job latency.


## Usage

This data is provided for reproducibility and further academic research into Proof-of-Work mining attacks and network security.

---
*Note: Timestamps are in UTC. "Qubic" blocks are identified by their specific coinbase tag or view-key revealed.*

