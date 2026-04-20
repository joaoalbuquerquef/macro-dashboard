"""
Session 2 — BLS API exploration script.

Goals:
  - Understand the BLS API response structure
  - Fetch payroll (CES) and unemployment (LNS) series
  - Store each series in a tidy DataFrame
  - Save combined BLS data to data/bls_raw.csv

BLS series used:
  CES0000000001  Total Nonfarm Payrolls (thousands, SA)
  CES0500000001  Total Private Payrolls (thousands, SA)
  CES0600000001  Goods-Producing Payrolls (thousands, SA)
  CES0800000001  Private Service-Providing Payrolls (thousands, SA)
  LNS14000000    Unemployment Rate (%, SA) — cross-check vs FRED UNRATE

API versions:
  v1 (no key) — free, last ~3 years only, 25 queries/day
  v2 (key)    — date range control, 500 queries/day; set BLS_API_KEY in .env

Run:
    python explore_bls.py
"""

import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

_raw_key = os.getenv("BLS_API_KEY", "")
# Treat placeholder values as absent so we fall back to v1
BLS_API_KEY = _raw_key if _raw_key and not _raw_key.startswith("your_") else None

BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_V2_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Series to fetch with friendly column names
SERIES = {
    "CES0000000001": "payrolls_total",
    "CES0500000001": "payrolls_private",
    "CES0600000001": "payrolls_goods",
    "CES0800000001": "payrolls_private_services",
    "LNS14000000":   "unemployment_rate_bls",
}

# Used only with v2 (key required); v1 returns the last ~3 years automatically
START_YEAR = "2021"
END_YEAR = "2026"


def fetch_bls_series(series_ids: list[str], start_year: str, end_year: str) -> dict:
    """
    Fetch multiple BLS series in a single POST request.

    Uses v2 (with date range) when BLS_API_KEY is set, otherwise falls back
    to v1 which returns the last ~3 years without requiring a key.

    Both versions share the same response envelope:
    {
      "status": "REQUEST_SUCCEEDED",
      "Results": {
        "series": [
          {
            "seriesID": "CES0000000001",
            "data": [
              {"year": "2024", "period": "M12", "periodName": "December",
               "value": "159507", "footnotes": [...]},
              ...
            ]
          },
          ...
        ]
      }
    }

    Parameters
    ----------
    series_ids : list[str]  BLS series identifiers
    start_year : str        e.g. "2021" (v2 only)
    end_year   : str        e.g. "2026" (v2 only)

    Returns
    -------
    dict  Raw JSON response from the BLS API
    """
    if BLS_API_KEY:
        url = BLS_V2_URL
        payload = {
            "seriesid": series_ids,
            "startyear": start_year,
            "endyear": end_year,
            "calculations": False,
            "annualaverage": False,
            "registrationkey": BLS_API_KEY,
        }
        print("  (using v2 API with registration key)")
    else:
        url = BLS_V1_URL
        payload = {"seriesid": series_ids}
        print("  (using v1 API — no key, last ~3 years returned)")

    headers = {"Content-type": "application/json"}
    response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def bls_series_to_dataframe(series_data: dict, col_name: str) -> pd.DataFrame:
    """
    Convert a single BLS series dict (from Results.series[i]) into a tidy DataFrame.

    BLS periods are "M01"–"M12" for monthly data. We convert:
        year="2024", period="M03"  →  date=2024-03-01

    Annual averages have period="M13"; we drop those.

    Parameters
    ----------
    series_data : dict   One element from raw["Results"]["series"]
    col_name    : str    Column name to use for the value

    Returns
    -------
    pd.DataFrame  Columns: date, <col_name>
    """
    rows = []
    for obs in series_data.get("data", []):
        period = obs["period"]
        if not period.startswith("M") or period == "M13":
            continue  # skip annual averages or non-monthly
        month = int(period[1:])  # "M03" → 3
        year = int(obs["year"])
        value = pd.to_numeric(obs["value"], errors="coerce")
        rows.append({"date": pd.Timestamp(year=year, month=month, day=1), col_name: value})

    df = pd.DataFrame(rows)
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def main():
    series_ids = list(SERIES.keys())

    print(f"Fetching {len(series_ids)} BLS series for {START_YEAR}–{END_YEAR} …")
    raw = fetch_bls_series(series_ids, START_YEAR, END_YEAR)

    # --- Inspect response structure ---
    print(f"\nStatus  : {raw.get('status')}")
    print(f"Message : {raw.get('message', [])}")

    results = raw.get("Results", {})
    series_list = results.get("series", [])
    print(f"Series returned: {len(series_list)}")

    dataframes = []
    for series_data in series_list:
        sid = series_data["seriesID"]
        col_name = SERIES.get(sid, sid)

        print(f"\n--- {sid} → '{col_name}' ---")
        print(f"  Observations: {len(series_data.get('data', []))}")
        if series_data.get("data"):
            # API returns newest-first; show first (newest) and last (oldest) raw entries
            print(f"  Newest raw : {series_data['data'][0]}")
            print(f"  Oldest raw : {series_data['data'][-1]}")

        df = bls_series_to_dataframe(series_data, col_name)
        print(f"  DataFrame shape: {df.shape}")
        print(df.tail(3).to_string(index=False))
        dataframes.append(df)

    if not dataframes:
        print("No data returned — check your series IDs and API key.")
        return

    # Merge all series on 'date'
    combined = dataframes[0]
    for df in dataframes[1:]:
        combined = pd.merge(combined, df, on="date", how="outer")

    combined.sort_values("date", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    print("\n--- Combined BLS DataFrame (last 5 rows) ---")
    print(combined.tail(5).to_string(index=False))
    print(f"\nShape    : {combined.shape}")
    print(f"Columns  : {list(combined.columns)}")
    print(f"Date range: {combined['date'].min().date()} → {combined['date'].max().date()}")
    print(f"Nulls:\n{combined.isnull().sum()}")

    output_path = os.path.join("data", "bls_raw.csv")
    combined.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
