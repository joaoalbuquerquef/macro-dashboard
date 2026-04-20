import os
import sys
import json
import subprocess
import threading
from datetime import datetime, timedelta
import anthropic
import pandas as pd
from flask import Flask, render_template, jsonify

from charts import (
    load_master,
    chart_rates,
    chart_inflation,
    chart_payrolls,
    chart_payrolls_sector,
    chart_selic,
)

app = Flask(__name__)

# Ensure the data directory exists (Railway containers start with a clean filesystem)
os.makedirs("data", exist_ok=True)

# ── Commentary cache (in-memory, 12-hour TTL) ────────────────────────────────
_CACHE_TTL = timedelta(hours=12)
_commentary_cache: dict = {"text": None, "generated_at": None}

_SYSTEM_PROMPT = """\
You are a senior macro strategist at a major asset management firm.
Given economic data, write exactly three sections of professional commentary suitable for a client note.
Each section must begin with its title as a bold header on its own line. \
Be dense and precise — cite the specific figures provided and state the implication directly. \
No padding, no hedging phrases, no throat-clearing.
Use this exact structure:

**United States**
4–5 sentences. Cover: (1) where the Fed Funds Rate stands in real terms against current CPI, \
(2) the direction and pace of the inflation trajectory and what it implies for the easing timeline, \
(3) labor market momentum — payroll trend and unemployment level and what they signal about \
consumer spending and wage pressure, (4) one or two concrete forward risks to the outlook.

**Brazil**
4–5 sentences. Cover: (1) the Selic rate in real terms against IPCA and what that implies about \
the restrictiveness of BCB policy, (2) the pace of IPCA convergence toward target and whether it \
is stalling or accelerating, (3) the fiscal constraint on the easing cycle, \
(4) how the BCB cycle compares with the Fed — same direction or diverging — and the BRL implication. \
If Brazil data is not provided, write one sentence only noting its absence.

**Asset Management Implications**
Exactly 3 sentences — one per asset class. Fixed income: a directional duration call with the rate \
rationale. Equities: cyclicals vs defensives with one reason. \
EM assets: risk-on or risk-off with one reason drawn from the policy divergence above.

Rules: flowing prose only — no bullet points within sections, no preamble, no closing pleasantries. \
Begin the first section immediately after its header.\
"""


def _build_data_block(df: pd.DataFrame) -> str:
    def last(col):
        s = df[col].dropna()
        return s.iloc[-1] if not s.empty else None

    fedfunds = last("FEDFUNDS")
    unrate   = last("UNRATE")
    cpi      = last("CPIAUCSL")
    cpi_yoy  = last("cpi_yoy")
    pmom     = last("payrolls_mom")
    as_of    = df["date"].max().strftime("%B %Y")

    lines = [f"U.S. Economic Snapshot — {as_of}"]
    lines.append(f"• Federal Funds Rate: {fedfunds:.2f}%"          if fedfunds is not None else "• Federal Funds Rate: N/A")
    lines.append(f"• Unemployment Rate: {unrate:.1f}%"             if unrate   is not None else "• Unemployment Rate: N/A")
    lines.append(f"• CPI (All Urban Consumers): {cpi:.3f} (Index)" if cpi      is not None else "• CPI: N/A")
    lines.append(f"• CPI Year-over-Year: {cpi_yoy:.2f}%"           if cpi_yoy  is not None else "• CPI YoY: N/A")
    lines.append(f"• Nonfarm Payrolls (MoM change): {pmom:+,.0f}k" if pmom     is not None else "• Nonfarm Payrolls MoM: N/A")

    # Brazil section — appended only when BCB data is present
    selic    = last("selic")    if "selic"    in df.columns else None
    ipca_yoy = last("ipca_yoy") if "ipca_yoy" in df.columns else None
    if selic is not None or ipca_yoy is not None:
        lines.append("")
        lines.append("Brazil Economic Snapshot")
        lines.append(f"• Selic Rate: {selic:.2f}% p.a."  if selic    is not None else "• Selic Rate: N/A")
        lines.append(f"• IPCA (12-month YoY): {ipca_yoy:.2f}%" if ipca_yoy is not None else "• IPCA YoY: N/A")

    return "\n".join(lines)


# ── Async refresh pipeline ────────────────────────────────────────────────────
# Each tuple: (script, label, optional)
# optional=True → a non-zero exit is logged but does not abort the pipeline.
_PIPELINE_STEPS = [
    ("explore_fred.py", "Fetching FRED data…",  False),
    ("explore_bls.py",  "Fetching BLS data…",   False),
    ("explore_bcb.py",  "Fetching BCB data…",   True),
    ("build_master.py", "Rebuilding dataset…",  False),
]

_refresh_lock = threading.Lock()
_refresh_job: dict = {
    "status":      "idle",   # "idle" | "running" | "done" | "error"
    "step":        "",
    "started_at":  None,
    "finished_at": None,
    "last_updated": None,
    "error":       None,
}


def _run_pipeline() -> None:
    """Runs in a background daemon thread; updates _refresh_job as it goes."""
    global _commentary_cache

    for script, label, optional in _PIPELINE_STEPS:
        with _refresh_lock:
            _refresh_job["step"] = label

        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            if optional:
                # Non-zero exit from an optional step is tolerated — log and continue.
                print(f"[refresh] Optional step {script} exited {result.returncode}: "
                      f"{result.stderr.strip() or result.stdout.strip()}", flush=True)
                continue
            with _refresh_lock:
                _refresh_job.update({
                    "status":      "error",
                    "step":        f"Failed at {script}",
                    "finished_at": datetime.now(),
                    "error":       result.stderr.strip() or result.stdout.strip(),
                })
            return

    # Fresh data invalidates the commentary cache
    _commentary_cache = {"text": None, "generated_at": None}

    df = load_master()
    with _refresh_lock:
        _refresh_job.update({
            "status":       "done",
            "step":         "Complete",
            "finished_at":  datetime.now(),
            "last_updated": df["date"].max().strftime("%B %Y"),
            "error":        None,
        })


# ── Helpers ──────────────────────────────────────────────────────────────────
def _get_stats(df: pd.DataFrame) -> dict:
    def _last_two(col):
        """Return (curr, prev, prev_date) for the most recent two non-null rows."""
        s = df.dropna(subset=[col])
        if s.empty:
            return None, None, None
        curr = float(s.iloc[-1][col])
        if len(s) < 2:
            return curr, None, None
        return curr, float(s.iloc[-2][col]), pd.Timestamp(s.iloc[-2]["date"])

    def _delta(curr, prev, prev_ts, good="down", unit="pp"):
        """
        Format a period-over-period change as {"label": str, "cls": str}.

        good  — "down" = falling is an improvement (rates, unemployment, inflation)
                "up"   = rising is an improvement (payrolls)
        unit  — "pp" formats as percentage points; "k" formats as thousands
        """
        if curr is None or prev is None or prev_ts is None:
            return {"label": "—", "cls": "change-neutral"}

        ch    = curr - prev
        month = prev_ts.strftime("%b")

        # Treat micro-changes as unchanged (< 0.005pp or < 500 jobs)
        neutral_threshold = 0.5 if unit == "k" else 0.005
        if abs(ch) < neutral_threshold:
            return {"label": f"→ unch. vs {month}", "cls": "change-neutral"}

        arrow   = "↑" if ch > 0 else "↓"
        is_good = (ch < 0) if good == "down" else (ch > 0)

        if unit == "pp":
            label = f"{arrow} {abs(ch):.2f}pp vs {month}"
        else:
            sign  = "+" if ch > 0 else ""
            label = f"{arrow} {sign}{ch:,.0f}k vs {month}"

        return {"label": label, "cls": "change-pos" if is_good else "change-neg"}

    ff_c, ff_p, ff_pd = _last_two("FEDFUNDS")
    ur_c, ur_p, ur_pd = _last_two("UNRATE")
    cy_c, cy_p, cy_pd = _last_two("cpi_yoy")
    pt_c, pt_p, pt_pd = _last_two("payrolls_total")
    pp_c, pp_p, pp_pd = _last_two("payrolls_private")

    # Brazil stats — graceful fallback when BCB data is absent
    _BCB_UNAVAIL = {"label": "Data unavailable", "cls": "change-neutral"}
    has_selic    = "selic"    in df.columns and not df["selic"].isna().all()
    has_ipca_yoy = "ipca_yoy" in df.columns and not df["ipca_yoy"].isna().all()

    if has_selic:
        sl_c, sl_p, sl_pd = _last_two("selic")
        selic_val   = f"{sl_c:.2f}% p.a." if sl_c is not None else "N/A"
        selic_delta = _delta(sl_c, sl_p, sl_pd, good="down", unit="pp")
    else:
        selic_val   = "Unavailable"
        selic_delta = _BCB_UNAVAIL

    if has_ipca_yoy:
        iy_c, iy_p, iy_pd = _last_two("ipca_yoy")
        ipca_val   = f"{iy_c:.2f}%" if iy_c is not None else "N/A"
        ipca_delta = _delta(iy_c, iy_p, iy_pd, good="down", unit="pp")
    else:
        ipca_val   = "Unavailable"
        ipca_delta = _BCB_UNAVAIL

    return {
        "fed_funds":              f"{ff_c:.2f}%"   if ff_c is not None else "N/A",
        "fed_funds_delta":        _delta(ff_c, ff_p, ff_pd, good="down", unit="pp"),
        "unrate":                 f"{ur_c:.1f}%"   if ur_c is not None else "N/A",
        "unrate_delta":           _delta(ur_c, ur_p, ur_pd, good="down", unit="pp"),
        "cpi_yoy":                f"{cy_c:.2f}%"   if cy_c is not None else "N/A",
        "cpi_yoy_delta":          _delta(cy_c, cy_p, cy_pd, good="down", unit="pp"),
        "payrolls":               f"{pt_c:,.0f}k"  if pt_c is not None else "N/A",
        "payrolls_delta":         _delta(pt_c, pt_p, pt_pd, good="up", unit="k"),
        "payrolls_private":       f"{pp_c:,.0f}k"  if pp_c is not None else "N/A",
        "payrolls_private_delta": _delta(pp_c, pp_p, pp_pd, good="up", unit="k"),
        "selic":                  selic_val,
        "selic_delta":            selic_delta,
        "ipca_yoy":               ipca_val,
        "ipca_yoy_delta":         ipca_delta,
    }


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    df = load_master()
    charts = {
        "rates":     json.loads(chart_rates(df).to_json()),
        "inflation": json.loads(chart_inflation(df).to_json()),
        "payrolls":  json.loads(chart_payrolls(df).to_json()),
        "sector":    json.loads(chart_payrolls_sector(df).to_json()),
        "selic":     json.loads(chart_selic(df).to_json()),
    }
    return render_template(
        "index.html",
        charts=charts,
        stats=_get_stats(df),
        last_updated=df["date"].max().strftime("%B %Y"),
    )


@app.route("/api/data")
def api_data():
    df = load_master()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return jsonify(df.where(df.notna(), None).to_dict(orient="records"))


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Start the refresh pipeline in a background thread (non-blocking)."""
    with _refresh_lock:
        if _refresh_job["status"] == "running":
            return jsonify({"status": "running", "step": _refresh_job["step"]}), 409

        _refresh_job.update({
            "status":      "running",
            "step":        "Starting…",
            "started_at":  datetime.now(),
            "finished_at": None,
            "last_updated": None,
            "error":       None,
        })

    threading.Thread(target=_run_pipeline, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/api/refresh/status")
def api_refresh_status():
    """Return the current state of the refresh pipeline."""
    with _refresh_lock:
        job = dict(_refresh_job)

    for key in ("started_at", "finished_at"):
        if job[key] is not None:
            job[key] = job[key].isoformat()

    return jsonify(job)


@app.route("/api/commentary", methods=["POST"])
def api_commentary():
    global _commentary_cache

    if not os.getenv("ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured"}), 503

    now = datetime.now()
    cached_at = _commentary_cache["generated_at"]
    if _commentary_cache["text"] and cached_at and (now - cached_at) < _CACHE_TTL:
        return jsonify({
            "commentary":   _commentary_cache["text"],
            "generated_at": cached_at.isoformat(),
            "cached":       True,
        })

    df = load_master()
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=[{
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_data_block(df)}],
        )
        text = message.content[0].text.strip()
    except anthropic.APIError as exc:
        return jsonify({"error": str(exc)}), 502

    _commentary_cache = {"text": text, "generated_at": now}
    return jsonify({
        "commentary":   text,
        "generated_at": now.isoformat(),
        "cached":       False,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
