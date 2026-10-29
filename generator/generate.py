"""Generate deterministic synthetic raw data for the Northfield OTIF scorecard.

All randomness comes from a single numpy default_rng(seed) and every date is
derived from the config's end_date, so one config always produces
byte-identical output.

Outputs (under --out-dir):
    suppliers.csv, products.csv, distribution_centers.csv,
    purchase_orders.csv, po_lines.csv,
    receipts/recorded_date=YYYY-MM-DD/receipts.csv,
    _manifest.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "generator.yml"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "raw"

DATE_FORMAT = "%Y-%m-%d"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
NONSTANDARD_TIMESTAMP_FORMAT = "%m/%d/%Y %H:%M"

RECEIPT_COLUMNS = [
    "receipt_id", "po_line_id", "po_number", "dc_id", "sku",
    "received_at", "received_cases", "rejected_cases",
]
ORPHAN_PO_NUMBER_START = 9_000_000

NAME_PREFIXES = [
    "North Star", "Lakeside", "Heartland", "Red River", "Cedar", "Great Plains",
    "Riverbend", "Twin Pines", "Bluff Country", "Golden Valley", "Iron Range",
    "Driftless", "Maple Ridge", "Big Woods", "Cannon Valley", "Sandhill",
]
NAME_SUFFIXES = [
    "Foods", "Provisions", "Farms", "Brands", "Supply Co.", "Packing",
    "Distributing", "Trading Co.",
]
CATEGORY_ITEMS = {
    "dry_grocery": ["Pasta", "Rice", "Cereal", "Peanut Butter", "Canned Beans", "Crackers", "Flour", "Coffee"],
    "frozen": ["Frozen Pizza", "Frozen Peas", "Ice Cream", "Waffles", "Fish Sticks", "Frozen Berries"],
    "refrigerated": ["Hummus", "Salsa", "Fresh Pasta", "Deli Salad", "Tortillas", "Pickles"],
    "produce": ["Apples", "Potatoes", "Onions", "Carrots", "Lettuce", "Bananas", "Tomatoes"],
    "meat_seafood": ["Ground Beef", "Chicken Thighs", "Pork Chops", "Salmon Fillet", "Bratwurst"],
    "household": ["Paper Towels", "Dish Soap", "Trash Bags", "Laundry Detergent", "Foil"],
    "health_beauty": ["Shampoo", "Toothpaste", "Body Wash", "Lotion", "Vitamins"],
}
GENERIC_ITEMS = ["Assorted Item"]
PACK_SIZES = ["8 oz", "12 oz", "16 oz", "32 oz", "1 lb", "2 lb", "5 lb", "12 ct", "24 ct"]


# --------------------------------------------------------------------------- config

def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normalize(values) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    return arr / arr.sum()


def _days(values) -> pd.TimedeltaIndex:
    return pd.to_timedelta(np.asarray(values, dtype="int64"), unit="D")


def _week_start(ts: pd.Timestamp) -> pd.Timestamp:
    return (ts - pd.Timedelta(days=ts.weekday())).normalize()


def make_calendar(cfg: dict) -> dict:
    """History window, ISO week starts (incl. open-PO horizon), and holiday weeks."""
    end = pd.Timestamp(cfg["end_date"])
    start = end - pd.DateOffset(months=cfg["months"]) + pd.Timedelta(days=1)
    horizon = pd.Timedelta(weeks=cfg["orders"]["open_po_horizon_weeks"])
    week_starts = pd.date_range(_week_start(start), _week_start(end) + horizon, freq="7D")
    holiday_weeks = sorted(_week_start(pd.Timestamp(d)) for d in cfg["holiday_weeks"])
    return {"start": start, "end": end, "week_starts": week_starts, "holiday_weeks": holiday_weeks}


# --------------------------------------------------------------------------- master data

def make_distribution_centers(cfg: dict) -> pd.DataFrame:
    dcs = pd.DataFrame(cfg["distribution_centers"])
    return dcs.rename(columns={"volume_share": "_volume_share"})


def make_suppliers(rng: np.random.Generator, cfg: dict) -> pd.DataFrame:
    n = cfg["counts"]["suppliers"]
    combos = [f"{p} {s}" for p in NAME_PREFIXES for s in NAME_SUFFIXES]
    names = [combos[i] for i in rng.choice(len(combos), size=n, replace=False)]
    tiers = cfg["supplier_tiers"]
    lo, hi = cfg["suppliers"]["lead_time_days"]
    suppliers = pd.DataFrame({
        "supplier_id": [f"SUP{i:03d}" for i in range(1, n + 1)],
        "supplier_name": names,
        "category": rng.choice(list(cfg["categories"]), size=n, p=_normalize(cfg["categories"].values())),
        "lead_time_days": rng.integers(lo, hi + 1, size=n),
        "_tier": rng.choice(list(tiers), size=n, p=_normalize(t["share"] for t in tiers.values())),
        "_order_frequency": rng.lognormal(0.0, cfg["suppliers"]["order_frequency_sigma"], size=n),
    })
    return assign_storyline_supplier(cfg, suppliers)


def assign_storyline_supplier(cfg: dict, suppliers: pd.DataFrame) -> pd.DataFrame:
    story = cfg["storyline"]
    is_story = suppliers["supplier_id"] == story["supplier_id"]
    if not is_story.any():
        raise ValueError(f"storyline supplier {story['supplier_id']} not among generated suppliers")
    suppliers.loc[is_story, "supplier_name"] = story["supplier_name"]
    suppliers.loc[is_story, "_tier"] = story["baseline_tier"]
    return suppliers


def make_products(rng: np.random.Generator, cfg: dict, suppliers: pd.DataFrame) -> pd.DataFrame:
    n = cfg["counts"]["products"]
    pcfg = cfg["products"]
    n_suppliers = len(suppliers)
    floor = pcfg["min_per_supplier"]
    weights = rng.lognormal(0.0, 0.6, size=n_suppliers)
    per_supplier = floor + rng.multinomial(n - floor * n_suppliers, weights / weights.sum())
    supplier_idx = np.repeat(np.arange(n_suppliers), per_supplier)

    category = suppliers["category"].to_numpy()[supplier_idx]
    brand = suppliers["supplier_name"].str.split().str[0].to_numpy()[supplier_idx]
    item_pick = rng.integers(0, 1_000_000, size=n)
    size_pick = rng.choice(PACK_SIZES, size=n)
    names = []
    for b, c, k, s in zip(brand, category, item_pick, size_pick):
        items = CATEGORY_ITEMS.get(c, GENERIC_ITEMS)
        names.append(f"{b} {items[k % len(items)]} {s}")

    return pd.DataFrame({
        "sku": [f"SKU{i:05d}" for i in range(1, n + 1)],
        "product_name": names,
        "supplier_id": suppliers["supplier_id"].to_numpy()[supplier_idx],
        "category": category,
        "case_pack": rng.choice(pcfg["case_packs"], size=n),
        "case_cost": np.round(rng.lognormal(np.log(pcfg["median_case_cost"]), 0.5, size=n), 2),
    })


# --------------------------------------------------------------------------- orders

def make_purchase_orders(rng, cfg, cal, suppliers, dcs) -> pd.DataFrame:
    """Poisson number of POs per (week, supplier, DC); only POs placed by end_date exist."""
    ocfg = cfg["orders"]
    weeks = cal["week_starts"]
    w, s, d = (a.ravel() for a in np.meshgrid(
        np.arange(len(weeks)), np.arange(len(suppliers)), np.arange(len(dcs)), indexing="ij"))
    is_holiday_week = np.isin(weeks, cal["holiday_weeks"])
    dc_weight = dcs["_volume_share"].to_numpy() * len(dcs)
    rate = (ocfg["pos_per_supplier_dc_week"]
            * suppliers["_order_frequency"].to_numpy()[s]
            * dc_weight[d]
            * np.where(is_holiday_week[w], cfg["holiday"]["volume_multiplier"], 1.0))
    cell = np.repeat(np.arange(rate.size), rng.poisson(rate))

    requested = weeks[w[cell]] + _days(rng.integers(0, ocfg["receiving_days_per_week"], size=cell.size))
    slack_lo, slack_hi = ocfg["order_slack_days"]
    lead = suppliers["lead_time_days"].to_numpy()[s[cell]] + rng.integers(slack_lo, slack_hi + 1, size=cell.size)
    pos = pd.DataFrame({
        "supplier_id": suppliers["supplier_id"].to_numpy()[s[cell]],
        "dc_id": dcs["dc_id"].to_numpy()[d[cell]],
        "order_date": requested - _days(lead),
        "requested_delivery_date": requested,
        "_is_holiday_week": is_holiday_week[w[cell]],
    })
    pos = pos[pos["order_date"] <= cal["end"]]
    pos = pos.sort_values(["order_date", "dc_id", "supplier_id", "requested_delivery_date"], kind="stable")
    pos = pos.reset_index(drop=True)
    pos.insert(0, "po_number", [f"PO{1_000_000 + i:07d}" for i in range(1, len(pos) + 1)])
    return pos


def make_po_lines(rng, cfg, pos, products) -> pd.DataFrame:
    """Each PO orders a random subset of its supplier's SKUs."""
    ocfg = cfg["orders"]
    skus_by_supplier = {sid: grp["sku"].to_numpy() for sid, grp in products.groupby("supplier_id", sort=True)}
    n_lines = 1 + rng.poisson(ocfg["mean_lines_per_po"] - 1, size=len(pos))

    po_numbers, line_numbers, skus = [], [], []
    for po_number, supplier_id, k in zip(pos["po_number"], pos["supplier_id"], n_lines):
        pool = skus_by_supplier[supplier_id]
        chosen = rng.choice(pool, size=min(k, len(pool)), replace=False)
        po_numbers.extend([po_number] * len(chosen))
        line_numbers.extend(range(1, len(chosen) + 1))
        skus.extend(chosen)

    lines = pd.DataFrame({"po_number": po_numbers, "line_number": line_numbers, "sku": skus})
    holiday = lines["po_number"].map(pos.set_index("po_number")["_is_holiday_week"]).to_numpy()
    cases = rng.lognormal(np.log(ocfg["median_ordered_cases"]), ocfg["ordered_cases_sigma"], size=len(lines))
    cases = cases * np.where(holiday, ocfg["holiday_case_multiplier"], 1.0)
    lines["ordered_cases"] = np.maximum(1, np.round(cases)).astype(int)
    lines.insert(0, "po_line_id", [f"{p}-{n:03d}" for p, n in zip(lines["po_number"], lines["line_number"])])
    return lines


def apply_cancellations(rng, cfg, cal, lines, pos) -> pd.DataFrame:
    """Mark lines cancelled by Northfield or by the supplier, a few days before due."""
    c = cfg["cancellations"]
    header = lines[["po_number"]].merge(
        pos[["po_number", "order_date", "requested_delivery_date"]], on="po_number", how="left", validate="many_to_one")
    u = rng.random(len(lines))
    nf, sup = c["northfield_rate"], c["supplier_rate"]
    status = np.select([u < nf, u < nf + sup], ["cancelled_by_northfield", "cancelled_by_supplier"], default="active")
    days_before = rng.integers(0, c["max_days_before_due"] + 1, size=len(lines))
    cancelled = np.maximum(header["requested_delivery_date"] - _days(days_before), header["order_date"])
    status = np.where(cancelled > cal["end"], "active", status)  # cancellation hasn't happened yet

    lines["line_status"] = status
    lines["cancelled_date"] = cancelled.where(status != "active")
    return lines


# --------------------------------------------------------------------------- receipts

def supplier_reliability(cfg, active: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per-line probability of on-time and in-full, from tier, storyline, and holidays."""
    tiers = cfg["supplier_tiers"]
    p_on_time = active["_tier"].map({t: v["on_time"] for t, v in tiers.items()}).to_numpy(float)
    p_in_full = active["_tier"].map({t: v["in_full"] for t, v in tiers.items()}).to_numpy(float)

    story = cfg["storyline"]
    degraded = ((active["supplier_id"] == story["supplier_id"])
                & (active["requested_delivery_date"] >= pd.Timestamp(story["degrade_from"]))).to_numpy()
    p_on_time = np.where(degraded, story["on_time"], p_on_time)
    p_in_full = np.where(degraded, story["in_full"], p_in_full)

    p_on_time = p_on_time - np.where(active["_is_holiday_week"].to_numpy(), cfg["holiday"]["on_time_penalty"], 0.0)
    return np.clip(p_on_time, 0, 1), np.clip(p_in_full, 0, 1)


def draw_delivery_offsets(rng, dcfg, p_on_time) -> np.ndarray:
    """Days between requested date and first receipt; NaN when nothing ever arrives."""
    n = len(p_on_time)
    on_time = rng.random(n) < p_on_time
    kinds = np.array(list(dcfg["miss_mix"]))
    kind = kinds[rng.choice(len(kinds), size=n, p=_normalize(dcfg["miss_mix"].values()))]
    on_time_offset = np.where(rng.random(n) < dcfg["one_day_early_share"], -1, 0)
    early = -rng.integers(2, dcfg["max_early_days"] + 1, size=n)
    late = rng.integers(1, dcfg["max_late_days"] + 1, size=n)
    very_late = rng.integers(dcfg["max_late_days"] + 1, dcfg["max_very_late_days"] + 1, size=n)
    missed_offset = np.select(
        [kind == "early", kind == "late", kind == "very_late"], [early, late, very_late], default=0).astype(float)
    missed_offset[kind == "never"] = np.nan
    return np.where(on_time, on_time_offset, missed_offset)


def draw_received_quantities(rng, qcfg, ordered, p_in_full) -> np.ndarray:
    """Total cases the supplier delivers: full, short, or over-shipped."""
    n = len(ordered)
    full = (rng.random(n) < p_in_full) | (ordered < 2)
    short = np.maximum(1, np.floor(ordered * rng.uniform(*qcfg["short_fill_range"], size=n))).astype(int)
    over = rng.random(n) < qcfg["over_ship_rate"]
    over_qty = np.ceil(ordered * rng.uniform(*qcfg["over_ship_range"], size=n)).astype(int)
    return np.where(full, np.where(over, over_qty, ordered), short)


def draw_receipt_times(rng, dcfg, dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    m = len(dates)
    hour = rng.integers(dcfg["first_hour"], dcfg["last_hour"] + 1, size=m)
    hour = np.where(rng.random(m) < dcfg["late_night_rate"], 23, hour)
    minute = rng.integers(0, 60, size=m)
    second = rng.integers(0, 60, size=m)
    return dates + pd.to_timedelta(hour * 3600 + minute * 60 + second, unit="s")


def draw_rejections(rng, dcfg, cases) -> np.ndarray:
    m = len(cases)
    rejected = np.clip(np.ceil(cases * rng.uniform(0.05, 0.5, size=m)), 1, cases).astype(int)
    return np.where(rng.random(m) < dcfg["rejection_rate"], rejected, 0)


def simulate_receipts(rng, cfg, cal, pos, lines, suppliers) -> pd.DataFrame:
    """Turn active PO lines into dock receipts (some split, some never arriving)."""
    dcfg, qcfg = cfg["delivery"], cfg["quantities"]
    active = (lines.loc[lines["line_status"] == "active", ["po_line_id", "po_number", "sku", "ordered_cases"]]
              .merge(pos[["po_number", "supplier_id", "dc_id", "requested_delivery_date", "_is_holiday_week"]],
                     on="po_number", how="left", validate="many_to_one")
              .merge(suppliers[["supplier_id", "_tier"]], on="supplier_id", how="left", validate="many_to_one"))
    n = len(active)
    p_on_time, p_in_full = supplier_reliability(cfg, active)
    offset = draw_delivery_offsets(rng, dcfg, p_on_time)
    total = draw_received_quantities(rng, qcfg, active["ordered_cases"].to_numpy(), p_in_full)

    split = (rng.random(n) < dcfg["split_rate"]) & (total >= 2)
    first_qty = np.where(split, np.clip(np.round(total * rng.uniform(0.4, 0.8, size=n)), 1, total - 1), total)
    gap = rng.integers(1, dcfg["split_max_gap_days"] + 1, size=n)

    arrives = ~np.isnan(offset)
    first = np.flatnonzero(arrives)
    second = np.flatnonzero(arrives & split)
    row = np.concatenate([first, second])
    day_offset = np.concatenate([offset[first], offset[second] + gap[second]]).astype(int)
    cases = np.concatenate([first_qty[first], total[second] - first_qty[second]]).astype(int)

    dates = pd.DatetimeIndex(active["requested_delivery_date"].to_numpy()[row]) + _days(day_offset)
    dates = dates + _days(dates.day_of_week == 6)  # DCs don't receive on Sunday
    receipts = pd.DataFrame({
        "po_line_id": active["po_line_id"].to_numpy()[row],
        "po_number": active["po_number"].to_numpy()[row],
        "dc_id": active["dc_id"].to_numpy()[row],
        "sku": active["sku"].to_numpy()[row],
        "received_at": draw_receipt_times(rng, dcfg, dates),
        "received_cases": cases,
        "rejected_cases": draw_rejections(rng, dcfg, cases),
    })
    receipts = receipts[receipts["received_at"].dt.normalize() <= cal["end"]]  # data is as of end_date
    receipts = receipts.sort_values(["received_at", "dc_id", "po_line_id"], kind="stable").reset_index(drop=True)
    receipts.insert(0, "receipt_id", [f"RCV{i:08d}" for i in range(1, len(receipts) + 1)])

    receipts["_received_date"] = receipts["received_at"].dt.normalize()
    receipts["recorded_date"] = receipts["_received_date"]
    receipts["received_at"] = receipts["received_at"].dt.strftime(TIMESTAMP_FORMAT)
    receipts["_touched"] = False
    return receipts


# --------------------------------------------------------------------------- data quality

def pick_clean_receipts(rng, receipts, k, eligible=None) -> np.ndarray:
    """Choose k receipts no other DQ issue has touched, and mark them touched."""
    mask = ~receipts["_touched"].to_numpy()
    if eligible is not None:
        mask &= eligible
    pool = np.flatnonzero(mask)
    if k > len(pool):
        raise ValueError(f"cannot inject {k} issues into {len(pool)} clean receipts")
    picked = np.sort(rng.choice(pool, size=k, replace=False))
    receipts.loc[picked, "_touched"] = True
    return picked


def inject_late_postings(rng, receipts, k, max_days, end) -> pd.DataFrame:
    eligible = (receipts["_received_date"] <= end - pd.Timedelta(days=max_days)).to_numpy()
    idx = pick_clean_receipts(rng, receipts, k, eligible)
    receipts.loc[idx, "recorded_date"] = receipts.loc[idx, "_received_date"] + _days(rng.integers(1, max_days + 1, size=k))
    return receipts


def inject_missing_timestamps(rng, receipts, k) -> pd.DataFrame:
    idx = pick_clean_receipts(rng, receipts, k)
    receipts.loc[idx, "received_at"] = None
    return receipts


def inject_nonstandard_timestamps(rng, receipts, k) -> pd.DataFrame:
    idx = pick_clean_receipts(rng, receipts, k)
    parsed = pd.to_datetime(receipts.loc[idx, "received_at"], format=TIMESTAMP_FORMAT)
    receipts.loc[idx, "received_at"] = parsed.dt.strftime(NONSTANDARD_TIMESTAMP_FORMAT)
    return receipts


def inject_nonpositive_quantities(rng, receipts, k) -> pd.DataFrame:
    idx = pick_clean_receipts(rng, receipts, k)
    cases = receipts.loc[idx, "received_cases"].to_numpy()
    receipts.loc[idx, "received_cases"] = np.where(rng.random(k) < 0.5, 0, -cases)
    receipts.loc[idx, "rejected_cases"] = 0
    return receipts


def inject_sku_format_drift(rng, receipts, k) -> pd.DataFrame:
    idx = pick_clean_receipts(rng, receipts, k)
    lowercase = rng.random(k) < 0.5
    skus = receipts.loc[idx, "sku"].to_numpy()
    receipts.loc[idx, "sku"] = [s.lower() if low else f"{s} " for s, low in zip(skus, lowercase)]
    return receipts


def inject_orphan_receipts(rng, receipts, k) -> tuple[pd.DataFrame, list[str]]:
    """Add receipts that point at PO lines that don't exist."""
    idx = pick_clean_receipts(rng, receipts, k)
    orphans = receipts.loc[idx].copy()
    po_numbers = [f"PO{ORPHAN_PO_NUMBER_START + i:07d}" for i in range(1, k + 1)]
    next_id = len(receipts) + 1
    receipt_ids = [f"RCV{next_id + i:08d}" for i in range(k)]
    orphans["po_number"] = po_numbers
    orphans["po_line_id"] = [f"{p}-001" for p in po_numbers]
    orphans["receipt_id"] = receipt_ids
    return pd.concat([receipts, orphans], ignore_index=True), receipt_ids


def inject_duplicates(rng, receipts, k) -> pd.DataFrame:
    idx = pick_clean_receipts(rng, receipts, k)
    return pd.concat([receipts, receipts.loc[idx]], ignore_index=True)


def inject_data_quality_issues(rng, cfg, cal, receipts) -> tuple[pd.DataFrame, dict, list[str]]:
    dq = cfg["data_quality"]
    n_clean = len(receipts)
    k = {issue: int(round(rate * n_clean)) for issue, rate in dq["rates"].items()}

    receipts = inject_late_postings(rng, receipts, k["late_posted_receipts"], dq["late_posting_max_days"], cal["end"])
    receipts = inject_missing_timestamps(rng, receipts, k["missing_received_at"])
    receipts = inject_nonstandard_timestamps(rng, receipts, k["nonstandard_received_at"])
    receipts = inject_nonpositive_quantities(rng, receipts, k["nonpositive_received_cases"])
    receipts = inject_sku_format_drift(rng, receipts, k["sku_format_drift"])
    receipts, orphan_ids = inject_orphan_receipts(rng, receipts, k["orphan_receipts"])
    receipts = inject_duplicates(rng, receipts, k["duplicate_receipts"])
    return receipts, k, orphan_ids


# --------------------------------------------------------------------------- output

def _public(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in df.columns if not c.startswith("_")]]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime(DATE_FORMAT)
    out.to_csv(path, index=False, lineterminator="\n")


def write_receipt_partitions(receipts: pd.DataFrame, out_dir: Path) -> int:
    receipts_dir = out_dir / "receipts"
    if receipts_dir.exists():
        shutil.rmtree(receipts_dir)  # stale partitions from an earlier run would corrupt the output
    receipts = receipts.sort_values(["recorded_date", "receipt_id"], kind="stable")
    recorded = receipts["recorded_date"].dt.strftime(DATE_FORMAT)
    n_partitions = 0
    for day, part in receipts.groupby(recorded, sort=True):
        path = receipts_dir / f"recorded_date={day}" / "receipts.csv"
        path.parent.mkdir(parents=True)
        write_csv(part[RECEIPT_COLUMNS], path)
        n_partitions += 1
    return n_partitions


def build_manifest(cfg, cal, tables, receipts, n_partitions, dq_counts, orphan_ids) -> dict:
    row_counts = {name: len(df) for name, df in tables.items()}
    row_counts["receipts"] = len(receipts)
    return {
        "seed": cfg["seed"],
        "start_date": cal["start"].strftime(DATE_FORMAT),
        "end_date": cal["end"].strftime(DATE_FORMAT),
        "row_counts": row_counts,
        "receipt_partitions": n_partitions,
        "dq_issues": dq_counts,
        "orphan_receipt_ids": orphan_ids,
    }


def print_summary(manifest: dict) -> None:
    print(f"Generated data {manifest['start_date']} .. {manifest['end_date']} (seed {manifest['seed']})")
    print("Row counts:")
    for name, n in manifest["row_counts"].items():
        print(f"  {name:<28} {n:>8,}")
    print(f"  {'receipt partitions':<28} {manifest['receipt_partitions']:>8,}")
    print("Injected data-quality issues:")
    for issue, n in manifest["dq_issues"].items():
        print(f"  {issue:<28} {n:>8,}")


def generate(cfg: dict, out_dir: Path) -> dict:
    rng = np.random.default_rng(cfg["seed"])
    cal = make_calendar(cfg)
    dcs = make_distribution_centers(cfg)
    suppliers = make_suppliers(rng, cfg)
    products = make_products(rng, cfg, suppliers)
    pos = make_purchase_orders(rng, cfg, cal, suppliers, dcs)
    lines = make_po_lines(rng, cfg, pos, products)
    lines = apply_cancellations(rng, cfg, cal, lines, pos)
    receipts = simulate_receipts(rng, cfg, cal, pos, lines, suppliers)
    receipts, dq_counts, orphan_ids = inject_data_quality_issues(rng, cfg, cal, receipts)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "suppliers.csv": suppliers,
        "products.csv": products,
        "distribution_centers.csv": dcs,
        "purchase_orders.csv": pos,
        "po_lines.csv": lines,
    }
    for name, df in tables.items():
        write_csv(_public(df), out_dir / name)
    n_partitions = write_receipt_partitions(receipts, out_dir)

    manifest = build_manifest(cfg, cal, tables, receipts, n_partitions, dq_counts, orphan_ids)
    with open(out_dir / "_manifest.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    print_summary(generate(load_config(args.config), args.out_dir))


if __name__ == "__main__":
    main()
