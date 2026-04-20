"""
BCB API exploration script.

Fetches Brazilian economic series from the BCB SGS (Sistema Gerenciador de
Séries Temporais) public API — no registration key required.

Series fetched:
  432   — Taxa Selic (target rate, % p.a.)
            Daily series — deduplicated to last reading of each month.
  13522 — IPCA acumulado 12 meses (12-month accumulated consumer inflation, %)
            Already a YoY figure — no further computation needed.

BCB API format:
  GET https://api.bcb.gov.br/dados/serie/bcdata.sgs.{id}/dados
      ?formato=json&dataInicial=DD/MM/YYYY&dataFinal=DD/MM/YYYY

Response: [{"data": "DD/MM/YYYY", "valor": "X.XX"}, ...]
  Dates use Brazilian day-first format; valor may use comma as decimal sep.

All dates are normalised to the first of each month so they align with the
FRED/BLS data already in the pipeline. For daily series (Selic) the last
observation of each month is kept — capturing the rate in effect at month-end.

On any network or parse error the script writes an empty CSV (headers only)
and exits 0 — BCB is an optional data source; the pipeline must not abort.

Run:
    python explore_bcb.py
"""

import os
import requests
import pandas as pd

BCB_BASE   = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{sid}/dados"
START_DATE = "01/01/2021"
END_DATE   = "31/12/2026"

# series_id → column name in output CSV
# Note: 13522 is the 12-month accumulated IPCA (already YoY), not monthly pct.
SERIES = {
    432:   "selic",
    13522: "ipca_yoy",
}

OUTPUT_PATH = os.path.join("data", "bcb_raw.csv")


def fetch_bcb(series_id: int, start: str, end: str) -> list:
    """
    Fetch one BCB SGS series as a list of raw observation dicts.

    Parameters
    ----------
    series_id : int   BCB SGS series identifier
    start     : str   Start date in DD/MM/YYYY format
    end       : str   End date in DD/MM/YYYY format

    Returns
    -------
    list  Raw JSON list — [{"data": "DD/MM/YYYY", "valor": "X.XX"}, ...]
    """
    url    = BCB_BASE.format(sid=series_id)
    params = {"formato": "json", "dataInicial": start, "dataFinal": end}
    resp   = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def to_dataframe(raw: list, col_name: str) -> pd.DataFrame:
    """
    Convert a BCB raw observation list to a tidy monthly DataFrame.

    All observation dates are snapped to the first of their month so the
    resulting series aligns with FRED/BLS data. When multiple raw observations
    fall in the same month (e.g. daily Selic), only the last is retained.

    Parameters
    ----------
    raw      : list   Output of fetch_bcb()
    col_name : str    Column name to use for the value

    Returns
    -------
    pd.DataFrame  Columns: date, <col_name>  (one row per month)
    """
    rows = []
    for obs in raw:
        try:
            date  = pd.to_datetime(obs["data"], dayfirst=True).to_period("M").to_timestamp()
            valor = str(obs["valor"]).replace(",", ".")   # BRL locale uses comma
            value = pd.to_numeric(valor, errors="coerce")
            rows.append({"date": date, col_name: value})
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return pd.DataFrame(columns=["date", col_name])

    df = pd.DataFrame(rows)
    # Keep the last reading of each month (matters for daily Selic)
    df = df.groupby("date", as_index=False).last()
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _write_empty() -> None:
    """Write headers-only CSV so build_master can skip BCB gracefully."""
    pd.DataFrame(columns=["date"] + list(SERIES.values())).to_csv(OUTPUT_PATH, index=False)


def main() -> None:
    os.makedirs("data", exist_ok=True)

    labels = {432: "Selic rate (% p.a., daily → monthly last)", 13522: "IPCA 12-month YoY (%)"}
    dataframes: list[pd.DataFrame] = []
    any_failed = False

    for series_id, col_name in SERIES.items():
        print(f"\nFetching BCB series {series_id} — {labels[series_id]}")
        try:
            raw = fetch_bcb(series_id, START_DATE, END_DATE)
            print(f"  Raw observations : {len(raw)}")
            if raw:
                print(f"  Oldest raw entry : {raw[0]}")
                print(f"  Newest raw entry : {raw[-1]}")

            df = to_dataframe(raw, col_name)
            print(f"  Monthly rows     : {len(df)}")
            if not df.empty:
                print(f"  Date range       : {df['date'].min().date()} → {df['date'].max().date()}")
                print(df.tail(3).to_string(index=False))
            dataframes.append(df)

        except Exception as exc:
            print(f"  ERROR: {exc}")
            any_failed = True
            dataframes.append(pd.DataFrame(columns=["date", col_name]))

    # Merge all series (outer join — preserves all dates)
    combined = dataframes[0]
    for df in dataframes[1:]:
        combined = pd.merge(combined, df, on="date", how="outer")
    combined.sort_values("date", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    combined.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}  (shape: {combined.shape})")

    if any_failed:
        print(
            "\nWARNING: one or more BCB series failed. "
            "Dashboard will show 'Data unavailable' for Brazil cards."
        )
    # Always exits 0 — BCB is optional; the pipeline must not abort on BCB failure.


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"BCB fetch aborted unexpectedly: {exc}")
        _write_empty()
