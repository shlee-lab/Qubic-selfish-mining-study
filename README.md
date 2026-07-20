# Qubic Selfish Mining on Monero

Reproducibility repository for:

> **Inside Qubic’s Selfish Mining Campaign on Monero: Evidence, Tactics, and Limits**
> Accepted at AFT 2026 · [Paper](https://arxiv.org/abs/2512.01437)

## Repository structure

- `code/`: analysis and plotting scripts
- `data/`: input and processed datasets
- `fig/`: reproduced paper figures
- `visualizer/`: interactive data visualizer

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Revised run analysis

```bash
python code/plot_orphan_run_length.py
python code/plot_period_orphan_blocks.py
```

These scripts regenerate `data/selfish_mining_blocks.csv` and the corresponding period-level figure.

The revised pipeline combines Qubic labels from node observations and the community-shared block dataset before run detection. It uses height-inclusive run construction and records parent-verified Qubic main/orphan pairs as self-forks rather than successful private-chain extensions.

See [`code/README.md`](code/README.md) for the remaining figure scripts and [`data/README.md`](data/README.md) for data provenance.
