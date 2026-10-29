"""Tests for generator/generate.py: determinism, injected DQ issues, referential integrity."""

import copy
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from generator import generate as gen

ISO_TIMESTAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


def file_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def read_receipts(root: Path) -> pd.DataFrame:
    parts = [
        pd.read_csv(path, dtype=str).assign(recorded_date=path.parent.name.split("=", 1)[1])
        for path in sorted((root / "receipts").glob("recorded_date=*/receipts.csv"))
    ]
    return pd.concat(parts, ignore_index=True)


@pytest.fixture(scope="module")
def config():
    return gen.load_config(gen.DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def run_a(config, tmp_path_factory):
    out = tmp_path_factory.mktemp("run_a")
    return out, gen.generate(config, out)


@pytest.fixture(scope="module")
def run_b(config, tmp_path_factory):
    out = tmp_path_factory.mktemp("run_b")
    return out, gen.generate(config, out)


@pytest.fixture(scope="module")
def run_other_seed(config, tmp_path_factory):
    cfg = copy.deepcopy(config)
    cfg["seed"] = config["seed"] + 1
    out = tmp_path_factory.mktemp("run_other_seed")
    return out, gen.generate(cfg, out)


def test_same_seed_produces_identical_files(run_a, run_b):
    hashes_a, hashes_b = file_hashes(run_a[0]), file_hashes(run_b[0])
    assert len(hashes_a) > 5
    assert hashes_a == hashes_b


def test_different_seed_produces_different_output(run_a, run_other_seed):
    hashes_a, hashes_other = file_hashes(run_a[0]), file_hashes(run_other_seed[0])
    assert hashes_a != hashes_other
    assert hashes_a["po_lines.csv"] != hashes_other["po_lines.csv"]


def test_injected_dq_counts_match_manifest(run_a):
    out, manifest = run_a
    receipts = read_receipts(out)
    po_line_ids = set(pd.read_csv(out / "po_lines.csv", dtype=str)["po_line_id"])

    unique = receipts.drop_duplicates("receipt_id")
    missing_ts = unique["received_at"].isna()
    iso_ts = unique["received_at"].str.fullmatch(ISO_TIMESTAMP, na=False)
    measured = {
        "duplicate_receipts": len(receipts) - len(unique),
        "orphan_receipts": int((~unique["po_line_id"].isin(po_line_ids)).sum()),
        "late_posted_receipts": int((iso_ts & (unique["recorded_date"] > unique["received_at"].str[:10])).sum()),
        "missing_received_at": int(missing_ts.sum()),
        "nonstandard_received_at": int((~missing_ts & ~iso_ts).sum()),
        "nonpositive_received_cases": int((pd.to_numeric(unique["received_cases"]) <= 0).sum()),
        "sku_format_drift": int((unique["sku"] != unique["sku"].str.strip().str.upper()).sum()),
    }

    assert measured == manifest["dq_issues"]
    assert all(n > 0 for n in measured.values()), "every DQ issue should actually be injected"
    assert len(receipts) == manifest["row_counts"]["receipts"]
    for name in ["suppliers.csv", "products.csv", "distribution_centers.csv", "purchase_orders.csv", "po_lines.csv"]:
        assert len(pd.read_csv(out / name)) == manifest["row_counts"][name], name


def test_non_orphan_receipts_reference_existing_po_lines(run_a):
    out, manifest = run_a
    receipts = read_receipts(out)
    po_line_ids = set(pd.read_csv(out / "po_lines.csv", dtype=str)["po_line_id"])
    is_orphan = receipts["receipt_id"].isin(manifest["orphan_receipt_ids"])

    assert receipts.loc[~is_orphan, "po_line_id"].isin(po_line_ids).all()
    assert not receipts.loc[is_orphan, "po_line_id"].isin(po_line_ids).any()
