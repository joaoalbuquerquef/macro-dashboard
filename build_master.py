"""
Build master DataFrame.

Merges FRED + BLS (inner join on date) then left-joins BCB data when available.

Derived columns added:
  cpi_yoy      — US CPI year-over-year % (from FRED CPIAUCSL, 12-month pct change)
  payrolls_mom — Total nonfarm payrolls MoM change (thousands)
  ipca_yoy     — Already provided by BCB series 13522 (12-month accumulated IPCA)
                 No further computation needed.

BCB merge is optional: if bcb_raw.csv is missing or empty the pipeline
continues and the dashboard degrades gracefully for Brazil data.

Run:
    python build_master.py
"""

import os
import pandas as pd

FRED_PATH   = os.path.join("data", "fred_raw.csv")
BLS_PATH    = os.path.join("data", "bls_raw.csv")
BCB_PATH    = os.path.join("data", "bcb_raw.csv")
MASTER_PATH = os.path.join("data", "master.csv")


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def main():
    fred = load_csv(FRED_PATH)
    bls  = load_csv(BLS_PATH)

    print(f"FRED shape : {fred.shape}  ({fred['date'].min().date()} → {fred['date'].max().date()})")
    print(f"BLS  shape : {bls.shape}  ({bls['date'].min().date()} → {bls['date'].max().date()})")

    # Inner join keeps only months present in both US sources
    master = pd.merge(fred, bls, on="date", how="inner")
    master.sort_values("date", inplace=True)
    master.reset_index(drop=True, inplace=True)

    # US derived columns
    master["cpi_yoy"]      = master["CPIAUCSL"].pct_change(periods=12, fill_method=None) * 100
    master["payrolls_mom"] = master["payrolls_total"].diff()

    # BCB merge (optional — left join so US rows are never dropped)
    if os.path.exists(BCB_PATH):
        bcb = load_csv(BCB_PATH)
        bcb_cols = [c for c in ("selic", "ipca_yoy") if c in bcb.columns]
        if not bcb.empty and bcb_cols:
            master = pd.merge(master, bcb[["date"] + bcb_cols], on="date", how="left")
            print(f"BCB  shape : {bcb.shape}  — merged columns: {bcb_cols}")
        else:
            print("BCB  file found but empty — skipping Brazil merge.")
    else:
        print("BCB  file not found — skipping Brazil merge.")

    print(f"\nMaster shape : {master.shape}")
    print(f"Columns      : {list(master.columns)}")
    print(f"Date range   : {master['date'].min().date()} → {master['date'].max().date()}")
    print(f"\nNulls per column:\n{master.isnull().sum()}")
    print("\n--- Last 5 rows ---")
    print(master.tail(5).to_string(index=False))

    master.to_csv(MASTER_PATH, index=False)
    print(f"\nSaved to {MASTER_PATH}")


if __name__ == "__main__":
    main()
