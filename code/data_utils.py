"""Shared block-data loading for the paper analyses."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_BLOCKS_PATH = Path("data/all_blocks.csv")
DEFAULT_PROOF_PATH = Path("data/blocks-proof.csv")


def _coerce_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.isin({"true", "1", "yes"})


def load_blocks(
    blocks_path: str | Path = DEFAULT_BLOCKS_PATH,
    proof_path: str | Path = DEFAULT_PROOF_PATH,
) -> pd.DataFrame:
    """Load node observations augmented with community-shared Qubic evidence.

    A proof-dataset hash is an additional positive Qubic label. Proof-only
    orphan blocks inside the node observation window are also retained. The
    original node-derived labels remain positive even when a hash is absent
    from the community dataset, which is not assumed to be complete.
    """

    blocks = pd.read_csv(blocks_path)
    proof = pd.read_csv(proof_path)

    required_blocks = {
        "timestamp",
        "height",
        "block hash",
        "extra nonce",
        "is_orphan",
        "is_qubic",
        "difficulty",
        "is_proofed",
    }
    required_proof = {"Height", "Id", "Timestamp", "Status"}
    missing_blocks = required_blocks.difference(blocks.columns)
    missing_proof = required_proof.difference(proof.columns)
    if missing_blocks or missing_proof:
        raise ValueError(
            "Missing required columns: "
            f"all_blocks={sorted(missing_blocks)}, proof={sorted(missing_proof)}"
        )

    blocks = blocks.copy()
    blocks["height"] = pd.to_numeric(blocks["height"], errors="raise").astype("int64")
    blocks["is_orphan"] = _coerce_bool(blocks["is_orphan"])
    blocks["is_qubic"] = _coerce_bool(blocks["is_qubic"])

    proof_hashes = set(proof["Id"].dropna().astype(str))
    proof_matches = blocks["block hash"].astype(str).isin(proof_hashes)
    blocks["is_qubic"] = blocks["is_qubic"] | proof_matches
    blocks.loc[proof_matches, "is_proofed"] = True

    observed_time = pd.to_datetime(blocks["timestamp"], utc=True, errors="raise")
    proof_orphans = proof.loc[
        proof["Status"].astype("string").str.upper().eq("ORPHAN")
    ].copy()
    proof_orphans["proof_time"] = pd.to_datetime(
        pd.to_numeric(proof_orphans["Timestamp"], errors="raise"),
        unit="s",
        utc=True,
    )
    proof_orphans["Height"] = pd.to_numeric(
        proof_orphans["Height"], errors="raise"
    ).astype("int64")

    known_hashes = set(blocks["block hash"].dropna().astype(str))
    proof_orphans = proof_orphans.loc[
        ~proof_orphans["Id"].astype(str).isin(known_hashes)
        & proof_orphans["proof_time"].between(
            observed_time.min(), observed_time.max(), inclusive="both"
        )
    ].copy()

    if not proof_orphans.empty:
        main_difficulty = (
            blocks.loc[~blocks["is_orphan"], ["height", "difficulty"]]
            .drop_duplicates("height")
            .set_index("height")["difficulty"]
        )
        proof_orphans["difficulty"] = proof_orphans["Height"].map(main_difficulty)
        if proof_orphans["difficulty"].isna().any():
            missing_heights = sorted(
                proof_orphans.loc[proof_orphans["difficulty"].isna(), "Height"].unique()
            )
            raise ValueError(
                "No main-chain difficulty for proof-only orphan heights: "
                f"{missing_heights}"
            )

        additions = pd.DataFrame(
            {
                "timestamp": proof_orphans["proof_time"].dt.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "height": proof_orphans["Height"].to_numpy(),
                "block hash": proof_orphans["Id"].astype(str).to_numpy(),
                "extra nonce": pd.NA,
                "is_orphan": True,
                "is_qubic": True,
                "difficulty": proof_orphans["difficulty"].to_numpy(),
                "is_proofed": True,
            }
        )
        blocks = pd.concat([blocks, additions[blocks.columns]], ignore_index=True)

    blocks = blocks.assign(
        _sort_time=pd.to_datetime(blocks["timestamp"], utc=True, errors="raise")
    )
    return (
        blocks.sort_values(["_sort_time", "height", "block hash"], kind="mergesort")
        .drop(columns="_sort_time")
        .reset_index(drop=True)
    )


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("Invalid Monero varint in block blob")


def _parent_hash_from_blob(blob: object) -> str | None:
    if not isinstance(blob, str) or not blob:
        return None
    data = bytes.fromhex(blob)
    _, offset = _read_varint(data, 0)  # major version
    _, offset = _read_varint(data, offset)  # minor version
    _, offset = _read_varint(data, offset)  # timestamp
    return data[offset : offset + 32].hex()


def verified_qubic_self_fork_heights(
    blocks: pd.DataFrame | None = None,
    proof_path: str | Path = DEFAULT_PROOF_PATH,
) -> set[int]:
    """Return heights with a parent-verified Qubic main/orphan self fork."""

    if blocks is None:
        blocks = load_blocks(proof_path=proof_path)
    proof = pd.read_csv(proof_path)
    proof_orphans = proof.loc[
        proof["Status"].astype("string").str.upper().eq("ORPHAN")
    ].copy()
    proof_orphans["parent_hash"] = proof_orphans["Blob"].map(
        _parent_hash_from_blob
    )

    main = (
        blocks.loc[~blocks["is_orphan"]]
        .assign(_time=pd.to_datetime(blocks.loc[~blocks["is_orphan"], "timestamp"], utc=True))
        .sort_values(["height", "_time"], kind="mergesort")
        .drop_duplicates("height")
        .set_index("height")
    )

    verified: set[int] = set()
    for orphan in proof_orphans.dropna(subset=["parent_hash"]).itertuples(index=False):
        height = int(orphan.Height)
        if height not in main.index or height - 1 not in main.index:
            continue
        winner = main.loc[height]
        parent = main.loc[height - 1]
        if bool(winner["is_qubic"]) and str(parent["block hash"]) == orphan.parent_hash:
            verified.add(height)
    return verified


if __name__ == "__main__":
    augmented = load_blocks()
    output = Path("data/derived/all_blocks_augmented.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(output, index=False)
    print(
        f"Wrote {len(augmented):,} rows to {output} "
        f"({int(augmented['is_qubic'].sum()):,} Qubic-attributed rows)."
    )
