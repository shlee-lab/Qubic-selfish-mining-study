"""Cryptographically verify Qubic coinbase outputs with disclosed view keys."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from Cryptodome.Hash import keccak
from monero import ed25519
from monero.address import address as parse_address

from data import COMMUNITY_BLOCKS, NODE_BLOCKS, RAW_DIR, read_varint


VIEW_KEYS = RAW_DIR / "qubic_disclosed_view_keys.csv"


def encode_varint(value: int) -> bytes:
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def keccak_256(data: bytes) -> bytes:
    digest = keccak.new(digest_bits=256)
    digest.update(data)
    return digest.digest()


def parse_transaction_public_keys(extra: bytes) -> list[bytes]:
    """Extract primary and additional transaction public keys."""

    keys: list[bytes] = []
    offset = 0
    while offset < len(extra):
        tag = extra[offset]
        offset += 1
        if tag == 0x00:
            continue
        if tag == 0x01:
            key = extra[offset : offset + 32]
            if len(key) != 32:
                raise ValueError("Truncated transaction public key")
            keys.append(key)
            offset += 32
            continue
        if tag in {0x02, 0x03}:
            length, offset = read_varint(extra, offset)
            offset += length
            if offset > len(extra):
                raise ValueError("Truncated transaction extra field")
            continue
        if tag == 0x04:
            count, offset = read_varint(extra, offset)
            end = offset + 32 * count
            if end > len(extra):
                raise ValueError("Truncated additional public keys")
            keys.extend(
                extra[index : index + 32]
                for index in range(offset, end, 32)
            )
            offset = end
            continue
        raise ValueError(f"Unknown transaction extra tag 0x{tag:02x}")
    return keys


def parse_miner_transaction(blob: object) -> dict[str, object]:
    """Parse the miner transaction fields needed for output recognition."""

    if not isinstance(blob, str) or not blob:
        raise ValueError("Missing block blob")
    data = bytes.fromhex(blob)
    offset = 0

    for _ in range(3):
        _, offset = read_varint(data, offset)
    offset += 32  # previous block hash
    offset += 4  # nonce
    if offset > len(data):
        raise ValueError("Truncated block header")

    tx_version, offset = read_varint(data, offset)
    _, offset = read_varint(data, offset)  # unlock time
    input_count, offset = read_varint(data, offset)
    miner_height: int | None = None
    for _ in range(input_count):
        input_tag = data[offset]
        offset += 1
        if input_tag != 0xFF:
            raise ValueError(
                f"Unexpected miner transaction input tag 0x{input_tag:02x}"
            )
        miner_height, offset = read_varint(data, offset)

    output_count, offset = read_varint(data, offset)
    outputs = []
    for index in range(output_count):
        amount, offset = read_varint(data, offset)
        output_tag = data[offset]
        offset += 1
        output_key = data[offset : offset + 32]
        if len(output_key) != 32:
            raise ValueError("Truncated miner transaction output key")
        offset += 32
        if output_tag == 0x02:
            view_tag = None
        elif output_tag == 0x03:
            view_tag = data[offset : offset + 1]
            if len(view_tag) != 1:
                raise ValueError("Truncated miner transaction view tag")
            offset += 1
        else:
            raise ValueError(
                f"Unexpected miner transaction output tag 0x{output_tag:02x}"
            )
        outputs.append(
            {
                "index": index,
                "amount": amount,
                "key": output_key,
                "view_tag": view_tag,
            }
        )

    extra_length, offset = read_varint(data, offset)
    extra = data[offset : offset + extra_length]
    if len(extra) != extra_length:
        raise ValueError("Truncated miner transaction extra")
    return {
        "tx_version": tx_version,
        "miner_height": miner_height,
        "outputs": outputs,
        "transaction_public_keys": parse_transaction_public_keys(extra),
    }


def output_belongs_to_address(
    output_key: bytes,
    output_index: int,
    view_tag: bytes | None,
    transaction_public_keys: list[bytes],
    public_spend_key: bytes,
    private_view_key: bytes,
) -> bool:
    view_key_times_eight = private_view_key
    for _ in range(3):
        view_key_times_eight = ed25519.scalar_add(
            view_key_times_eight,
            view_key_times_eight,
        )

    for transaction_public_key in transaction_public_keys:
        shared_secret = ed25519.scalarmult(
            view_key_times_eight,
            transaction_public_key,
        )
        encoded_index = encode_varint(output_index)
        if view_tag is not None:
            expected_tag = keccak_256(
                b"view_tag" + shared_secret + encoded_index
            )[:1]
            if expected_tag != view_tag:
                continue
        scalar = ed25519.scalar_reduce(
            keccak_256(shared_secret + encoded_index)
        )
        expected_output_key = ed25519.edwards_add(
            ed25519.scalarmult_B(scalar),
            public_spend_key,
        )
        if expected_output_key == output_key:
            return True
    return False


def validate_disclosed_view_keys(
    key_path: Path = VIEW_KEYS,
) -> pd.DataFrame:
    keys = pd.read_csv(key_path)
    rows = []
    for key in keys.itertuples(index=False):
        parsed = parse_address(key.address)
        rows.append(
            {
                "epoch": int(key.epoch),
                "address": key.address,
                "private_view_key_matches_address": (
                    parsed.check_private_view_key(key.private_view_key)
                ),
                "public_spend_key": parsed.spend_key(),
                "public_view_key": parsed.view_key(),
            }
        )
    return pd.DataFrame(rows)


def view_key_validation_tables(
    community_path: Path = COMMUNITY_BLOCKS,
    key_path: Path = VIEW_KEYS,
    node_path: Path = NODE_BLOCKS,
) -> dict[str, pd.DataFrame]:
    community = pd.read_csv(community_path)
    keys = pd.read_csv(key_path)
    node = pd.read_csv(node_path)
    key_validation = validate_disclosed_view_keys(key_path)
    key_lookup = {
        (int(row.epoch), row.address): row.private_view_key
        for row in keys.itertuples(index=False)
    }

    orphans = community.loc[
        community["Status"].astype("string").str.upper().eq("ORPHAN")
    ].drop_duplicates(["Height", "Id"]).copy()
    rows = []
    for orphan in orphans.itertuples(index=False):
        epoch = int(orphan.Epoch)
        lookup_key = (epoch, orphan.Address)
        private_view_key_hex = key_lookup.get(lookup_key)
        has_key = private_view_key_hex is not None
        matched_index: int | None = None
        parse_error: str | None = None
        parsed: dict[str, object] | None = None
        address_key_matches: bool | None = None
        try:
            parsed = parse_miner_transaction(orphan.Blob)
            if has_key:
                recipient = parse_address(orphan.Address)
                address_key_matches = recipient.check_private_view_key(
                    private_view_key_hex
                )
                public_spend_key = bytes.fromhex(recipient.spend_key())
                private_view_key = bytes.fromhex(private_view_key_hex)
                for output in parsed["outputs"]:
                    if output_belongs_to_address(
                        output["key"],
                        output["index"],
                        output["view_tag"],
                        parsed["transaction_public_keys"],
                        public_spend_key,
                        private_view_key,
                    ):
                        matched_index = int(output["index"])
                        break
        except (IndexError, TypeError, ValueError) as error:
            parse_error = str(error)

        verified = has_key and matched_index is not None
        if not has_key:
            status = "no_disclosed_key"
        elif parse_error is not None:
            status = "parse_error"
        elif not address_key_matches:
            status = "address_key_mismatch"
        elif verified:
            status = "verified"
        else:
            status = "output_not_matched"
        rows.append(
            {
                "height": int(orphan.Height),
                "block_hash": orphan.Id,
                "epoch": epoch,
                "timestamp": pd.to_datetime(
                    int(orphan.Timestamp),
                    unit="s",
                    utc=True,
                ),
                "address": orphan.Address,
                "coinbase_tx_hash": orphan.Coinbase,
                "has_disclosed_view_key": has_key,
                "address_key_matches": address_key_matches,
                "miner_tx_height": (
                    parsed["miner_height"] if parsed else pd.NA
                ),
                "output_count": (
                    len(parsed["outputs"]) if parsed else pd.NA
                ),
                "transaction_public_key_count": (
                    len(parsed["transaction_public_keys"])
                    if parsed
                    else pd.NA
                ),
                "matching_output_index": (
                    matched_index if matched_index is not None else pd.NA
                ),
                "view_key_verified": verified,
                "status": status,
                "parse_error": parse_error,
            }
        )
    records = pd.DataFrame(rows).sort_values(
        ["timestamp", "height", "block_hash"],
        kind="mergesort",
    )
    node_hashes = set(
        node["block hash"].astype(str).str.lower().str.strip()
    )
    node_timestamps = pd.to_datetime(
        node["timestamp"], utc=True, errors="raise"
    )
    records["orphan_observed_by_node"] = (
        records["block_hash"]
        .astype(str)
        .str.lower()
        .str.strip()
        .isin(node_hashes)
    )
    records["in_node_observation_window"] = records[
        "timestamp"
    ].between(
        node_timestamps.min(),
        node_timestamps.max(),
        inclusive="both",
    )

    def summary_row(
        scope: str,
        selected: pd.DataFrame,
        epoch: int | None,
    ) -> dict[str, object]:
        eligible = selected["has_disclosed_view_key"]
        verified = selected["view_key_verified"]
        eligible_count = int(eligible.sum())
        verified_count = int(verified.sum())
        return {
            "scope": scope,
            "epoch": epoch if epoch is not None else pd.NA,
            "total_orphans": len(selected),
            "eligible_with_disclosed_key": eligible_count,
            "verified_outputs": verified_count,
            "eligible_not_verified": eligible_count - verified_count,
            "no_disclosed_key": int((~eligible).sum()),
            "verification_rate": (
                verified_count / eligible_count
                if eligible_count
                else pd.NA
            ),
        }

    community_only_in_window = records.loc[
        ~records["orphan_observed_by_node"]
        & records["in_node_observation_window"]
    ]
    summary_rows = [
        summary_row("all", records, None),
        summary_row(
            "community_only_in_node_observation_window",
            community_only_in_window,
            None,
        ),
    ]
    for epoch, selected in records.groupby("epoch", sort=True):
        summary_rows.append(
            summary_row("epoch", selected, int(epoch))
        )
    return {
        "view_key_address_validation.csv": key_validation,
        "view_key_orphan_output_validation.csv": records.reset_index(
            drop=True
        ),
        "view_key_validation_summary.csv": pd.DataFrame(summary_rows),
    }
