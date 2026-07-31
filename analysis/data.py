"""Load and combine the public block datasets used by the analyses."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
VALIDATION_DIR = ROOT / "data" / "validation"

NODE_BLOCKS = RAW_DIR / "node_observed_blocks.csv"
COMMUNITY_BLOCKS = RAW_DIR / "community_observed_qubic_blocks.csv"
ATTRIBUTED_BLOCKS = PROCESSED_DIR / "attributed_blocks.csv"


def attribution_validation_tables(
    node_path: Path = NODE_BLOCKS,
    community_path: Path = COMMUNITY_BLOCKS,
) -> dict[str, pd.DataFrame]:
    """Compare the initial node labels with the community hash set."""

    node = pd.read_csv(node_path)
    community = pd.read_csv(community_path)

    node["timestamp"] = pd.to_datetime(
        node["timestamp"], utc=True, errors="raise"
    )
    node["is_qubic"] = coerce_bool(node["is_qubic"])
    node["is_orphan"] = coerce_bool(node["is_orphan"])
    node = node.loc[node["is_qubic"]].copy()
    node["_hash"] = (
        node["block hash"].astype(str).str.lower().str.strip()
    )

    community["timestamp_dt"] = pd.to_datetime(
        pd.to_numeric(community["Timestamp"], errors="raise"),
        unit="s",
        utc=True,
    )
    community["_hash"] = (
        community["Id"].astype(str).str.lower().str.strip()
    )

    overlap_start = max(
        node["timestamp"].min(), community["timestamp_dt"].min()
    )
    overlap_end = min(
        node["timestamp"].max(), community["timestamp_dt"].max()
    )
    node_overlap = node.loc[
        node["timestamp"].between(
            overlap_start, overlap_end, inclusive="both"
        )
    ].copy()
    community_overlap = community.loc[
        community["timestamp_dt"].between(
            overlap_start, overlap_end, inclusive="both"
        )
    ].copy()

    def unmatched(
        node_frame: pd.DataFrame,
        community_frame: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        node_hashes = set(node_frame["_hash"])
        community_hashes = set(community_frame["_hash"])
        node_only = node_frame.loc[
            ~node_frame["_hash"].isin(community_hashes),
            ["timestamp", "height", "block hash", "is_orphan"],
        ].copy()
        community_only = community_frame.loc[
            ~community_frame["_hash"].isin(node_hashes),
            ["Timestamp", "Height", "Id", "Status"],
        ].copy()
        return node_only, community_only

    def daily(
        node_frame: pd.DataFrame,
        community_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        node_counts = (
            node_frame.assign(date=node_frame["timestamp"].dt.date)
            .groupby("date")
            .size()
            .rename("all_blocks")
        )
        community_counts = (
            community_frame.assign(
                date=community_frame["timestamp_dt"].dt.date
            )
            .groupby("date")
            .size()
            .rename("proof")
        )
        result = pd.concat(
            [node_counts, community_counts], axis=1
        ).fillna(0)
        result["difference"] = (
            result["proof"] - result["all_blocks"]
        )
        result["diff_pct"] = (
            result["difference"] / result["all_blocks"] * 100
        ).round(2)
        result.loc[result["all_blocks"].eq(0), "diff_pct"] = pd.NA
        return result.sort_index().reset_index()

    node_only, community_only = unmatched(node, community)
    node_only_overlap, community_only_overlap = unmatched(
        node_overlap, community_overlap
    )
    return {
        "node_only_qubic_blocks.csv": node_only,
        "community_only_qubic_blocks.csv": community_only,
        "node_only_qubic_blocks_overlap.csv": node_only_overlap,
        "community_only_qubic_blocks_overlap.csv": (
            community_only_overlap
        ),
        "attribution_daily_comparison.csv": daily(node, community),
        "attribution_daily_comparison_overlap.csv": daily(
            node_overlap, community_overlap
        ),
    }


def coerce_bool(series: pd.Series) -> pd.Series:
    """Convert common CSV boolean encodings to a strict boolean series."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.isin({"true", "1", "yes"})


def load_attributed_blocks(
    node_path: Path = NODE_BLOCKS,
    community_path: Path = COMMUNITY_BLOCKS,
) -> pd.DataFrame:
    """Return the node table augmented with community-observed Qubic blocks.

    Community hashes add positive Qubic labels. Community-only orphan blocks
    inside the node table's observation window are also added. Existing
    node-derived Qubic labels remain positive because the community dataset is
    an independent observation source rather than an exhaustive ground truth.
    """

    blocks = pd.read_csv(node_path)
    community = pd.read_csv(community_path)

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
    required_community = {"Height", "Id", "Timestamp", "Status"}
    missing_blocks = required_blocks.difference(blocks.columns)
    missing_community = required_community.difference(community.columns)
    if missing_blocks or missing_community:
        raise ValueError(
            "Missing required columns: "
            f"node={sorted(missing_blocks)}, "
            f"community={sorted(missing_community)}"
        )

    blocks = blocks.copy()
    blocks["height"] = pd.to_numeric(
        blocks["height"], errors="raise"
    ).astype("int64")
    blocks["is_orphan"] = coerce_bool(blocks["is_orphan"])
    blocks["is_qubic"] = coerce_bool(blocks["is_qubic"])

    community_hashes = set(community["Id"].dropna().astype(str))
    community_matches = blocks["block hash"].astype(str).isin(community_hashes)
    blocks["is_qubic"] = blocks["is_qubic"] | community_matches
    blocks.loc[community_matches, "is_proofed"] = True

    observed_time = pd.to_datetime(
        blocks["timestamp"], utc=True, errors="raise"
    )
    community_orphans = community.loc[
        community["Status"].astype("string").str.upper().eq("ORPHAN")
    ].copy()
    community_orphans["community_time"] = pd.to_datetime(
        pd.to_numeric(community_orphans["Timestamp"], errors="raise"),
        unit="s",
        utc=True,
    )
    community_orphans["Height"] = pd.to_numeric(
        community_orphans["Height"], errors="raise"
    ).astype("int64")

    known_hashes = set(blocks["block hash"].dropna().astype(str))
    community_orphans = community_orphans.loc[
        ~community_orphans["Id"].astype(str).isin(known_hashes)
        & community_orphans["community_time"].between(
            observed_time.min(), observed_time.max(), inclusive="both"
        )
    ].copy()

    if not community_orphans.empty:
        main_difficulty = (
            blocks.loc[~blocks["is_orphan"], ["height", "difficulty"]]
            .drop_duplicates("height")
            .set_index("height")["difficulty"]
        )
        community_orphans["difficulty"] = community_orphans["Height"].map(
            main_difficulty
        )
        if community_orphans["difficulty"].isna().any():
            missing_heights = sorted(
                community_orphans.loc[
                    community_orphans["difficulty"].isna(), "Height"
                ].unique()
            )
            raise ValueError(
                "No main-chain difficulty for community-only orphan heights: "
                f"{missing_heights}"
            )

        additions = pd.DataFrame(
            {
                "timestamp": community_orphans["community_time"].dt.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "height": community_orphans["Height"].to_numpy(),
                "block hash": community_orphans["Id"].astype(str).to_numpy(),
                "extra nonce": pd.NA,
                "is_orphan": True,
                "is_qubic": True,
                "difficulty": community_orphans["difficulty"].to_numpy(),
                "is_proofed": True,
            }
        )
        blocks = pd.concat(
            [blocks, additions[blocks.columns]], ignore_index=True
        )

    blocks = blocks.assign(
        _sort_time=pd.to_datetime(
            blocks["timestamp"], utc=True, errors="raise"
        )
    )
    return (
        blocks.sort_values(
            ["_sort_time", "height", "block hash"], kind="mergesort"
        )
        .drop(columns="_sort_time")
        .reset_index(drop=True)
    )


def write_attributed_blocks(
    output_path: Path = ATTRIBUTED_BLOCKS,
) -> pd.DataFrame:
    blocks = load_attributed_blocks()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    blocks.to_csv(output_path, index=False)
    return blocks


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
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


def parent_hash_from_blob(blob: object) -> str | None:
    if not isinstance(blob, str) or not blob:
        return None
    data = bytes.fromhex(blob)
    _, offset = read_varint(data, 0)
    _, offset = read_varint(data, offset)
    _, offset = read_varint(data, offset)
    return data[offset : offset + 32].hex()


def parent_linkage_validation_tables(
    node_path: Path = NODE_BLOCKS,
    community_path: Path = COMMUNITY_BLOCKS,
) -> dict[str, pd.DataFrame]:
    """Validate parents of community-observed Qubic orphan blocks."""

    node = pd.read_csv(node_path)
    community = pd.read_csv(community_path)

    node["timestamp_dt"] = pd.to_datetime(
        node["timestamp"], utc=True, errors="raise"
    )
    node["_hash"] = (
        node["block hash"].astype(str).str.lower().str.strip()
    )
    community["timestamp_dt"] = pd.to_datetime(
        pd.to_numeric(community["Timestamp"], errors="raise"),
        unit="s",
        utc=True,
    )
    community["_hash"] = (
        community["Id"].astype(str).str.lower().str.strip()
    )

    orphans = community.loc[
        community["Status"].astype("string").str.upper().eq("ORPHAN")
    ].drop_duplicates(["Height", "Id"]).copy()
    orphans["parent_hash"] = orphans["Blob"].map(parent_hash_from_blob)

    node_hashes = set(node["_hash"])
    community_hashes = set(community["_hash"])
    orphans["orphan_observed_by_node"] = orphans["_hash"].isin(
        node_hashes
    )
    orphans["parent_in_node_data"] = orphans["parent_hash"].isin(
        node_hashes
    )
    orphans["parent_in_community_data"] = orphans[
        "parent_hash"
    ].isin(community_hashes)
    orphans["parent_known"] = (
        orphans["parent_in_node_data"]
        | orphans["parent_in_community_data"]
    )
    orphans["in_node_observation_window"] = orphans[
        "timestamp_dt"
    ].between(
        node["timestamp_dt"].min(),
        node["timestamp_dt"].max(),
        inclusive="both",
    )

    scope_masks = [
        (
            "all_community_qubic_orphans",
            pd.Series(True, index=orphans.index),
        ),
        (
            "orphans_in_node_observation_window",
            orphans["in_node_observation_window"],
        ),
        (
            "orphans_also_observed_by_nodes",
            orphans["orphan_observed_by_node"],
        ),
    ]
    summary_rows = []
    for scope, mask in scope_masks:
        selected = orphans.loc[mask]
        parent_known = int(selected["parent_known"].sum())
        summary_rows.append(
            {
                "scope": scope,
                "community_qubic_orphans": len(selected),
                "parent_known": parent_known,
                "coverage": parent_known / len(selected),
                "parent_in_nodes": int(
                    selected["parent_in_node_data"].sum()
                ),
                "parent_in_community_set": int(
                    selected["parent_in_community_data"].sum()
                ),
                "missing": int((~selected["parent_known"]).sum()),
            }
        )

    records = orphans[
        [
            "Height",
            "Id",
            "timestamp_dt",
            "parent_hash",
            "orphan_observed_by_node",
            "in_node_observation_window",
            "parent_in_node_data",
            "parent_in_community_data",
            "parent_known",
        ]
    ].rename(
        columns={
            "Height": "height",
            "Id": "block_hash",
            "timestamp_dt": "timestamp",
        }
    )
    return {
        "community_orphan_parent_coverage.csv": pd.DataFrame(
            summary_rows
        ),
        "community_orphan_parent_linkage.csv": (
            records.sort_values(
                ["timestamp", "height", "block_hash"],
                kind="mergesort",
            ).reset_index(drop=True)
        ),
    }


def verified_qubic_self_fork_heights(
    blocks: pd.DataFrame,
    community_path: Path = COMMUNITY_BLOCKS,
) -> set[int]:
    """Return heights with at least two parent-linked Qubic blocks."""

    community = pd.read_csv(community_path)
    orphans = community.loc[
        community["Status"].astype("string").str.upper().eq("ORPHAN")
    ].drop_duplicates(["Height", "Id"]).copy()
    orphans["parent_hash"] = orphans["Blob"].map(parent_hash_from_blob)

    main = blocks.loc[~coerce_bool(blocks["is_orphan"])].copy()
    main["_time"] = pd.to_datetime(main["timestamp"], utc=True)
    main = (
        main.sort_values(["height", "_time"], kind="mergesort")
        .drop_duplicates("height")
        .set_index("height")
    )

    linked_orphans = orphans.dropna(subset=["parent_hash"])
    verified: set[int] = set(
        int(height)
        for (height, _), count in linked_orphans.groupby(
            ["Height", "parent_hash"]
        ).size().items()
        if count >= 2
    )
    for orphan in linked_orphans.itertuples(index=False):
        height = int(orphan.Height)
        if height not in main.index or height - 1 not in main.index:
            continue
        winner = main.loc[height]
        parent = main.loc[height - 1]
        if bool(winner["is_qubic"]) and (
            str(parent["block hash"]) == orphan.parent_hash
        ):
            verified.add(height)
    return verified
