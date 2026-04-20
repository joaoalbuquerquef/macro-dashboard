"""
Session 1 — FRED API exploration script.

Goals:
  - Understand the FRED observations endpoint response structure
  - Fetch three series: FEDFUNDS, UNRATE, CPIAUCSL
  - Store each series in a pandas DataFrame
  - Save the combined DataFrame to data/fred_raw.csv for later use

Run:
    python explore_fred.py
"""

import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # reads .env from the project root

FRED_API_KEY = os.getenv("FRED_API_KEY")
if not FRED_API_KEY:
    raise EnvironmentError("FRED_API_KEY is not set. Add it to your .env file.")

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Series we want to explore
SERIES = {
    "FEDFUNDS": "Federal Funds Effective Rate (%)",
    "UNRATE": "Unemployment Rate (%)",
    "CPIAUCSL": "CPI — All Urban Consumers (Index 1982-84=100)",
}


def fetch_series(series_id: str, limit: int = 60) -> dict:
    """
    Fetch raw observations for a FRED series.

    Parameters
    ----------
    series_id : str   FRED series identifier
    limit     : int   Number of most-recent observations to return

    Returns
    -------
    dict  Raw JSON response from the FRED API
    """
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    response = requests.get(FRED_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def observations_to_dataframe(raw: dict, series_id: str) -> pd.DataFrame:
    """
    Convert the 'observations' list from a FRED response into a tidy DataFrame.

    The FRED response looks like:
    {
      "realtime_start": "...",
      "observations": [
        {"realtime_start": "...", "realtime_end": "...", "date": "YYYY-MM-DD", "value": "3.14"},
        ...
      ]
    }

    We keep only 'date' and 'value', rename value to the series_id, and parse types.
    """
    observations = raw.get("observations", [])
    df = pd.DataFrame(observations)[["date", "value"]]
    df.rename(columns={"value": series_id}, inplace=True)

    # FRED uses "." for missing values — replace with NaN
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def main():
    dataframes = []

    for series_id, description in SERIES.items():
        print(f"\nFetching {series_id} — {description}")
        raw = fetch_series(series_id)

        # --- Inspect response structure on first run ---
        print(f"  Top-level keys   : {list(raw.keys())}")
        print(f"  Observations count: {len(raw.get('observations', []))}")
        if raw.get("observations"):
            print(f"  First observation : {raw['observations'][-1]}")  # oldest (sorted asc after our df sort)
            print(f"  Last  observation : {raw['observations'][0]}")   # most recent (desc from API)

        df = observations_to_dataframe(raw, series_id)
        print(f"  DataFrame shape  : {df.shape}")
        print(df.tail(3).to_string(index=False))
        dataframes.append(df)

    # Merge all series on 'date' (outer join keeps all dates)
    combined = dataframes[0]
    for df in dataframes[1:]:
        combined = pd.merge(combined, df, on="date", how="outer")

    combined.sort_values("date", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    print("\n--- Combined DataFrame (last 5 rows) ---")
    print(combined.tail(5).to_string(index=False))
    print(f"\nShape: {combined.shape}")
    print(f"Columns: {list(combined.columns)}")
    print(f"Date range: {combined['date'].min().date()} → {combined['date'].max().date()}")
    print(f"Nulls per column:\n{combined.isnull().sum()}")

    # Persist to CSV for use in later sessions
    output_path = os.path.join("data", "fred_raw.csv")
    combined.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
