import os
import sys
import json
import subprocess
import threading
from datetime import datetime, timedelta
import anthropic
import pandas as pd
from flask import Flask, render_template, jsonify

from auth import init_auth

from charts import (
    load_master,
    chart_rates,
    chart_inflation,
    chart_payrolls,
    chart_payrolls_sector,
    chart_selic,
)

app = Flask(__name__)
init_auth(app, "Painel Macro")

_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
_MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _br(txt: str) -> str:
    """Troca o ponto decimal por vírgula."""
    return txt.replace(".", ",")


def _mes_ano(ts) -> str:
    """Ex.: 'setembro de 2026'."""
    ts = pd.Timestamp(ts)
    return f"{_MESES[ts.month - 1]} de {ts.year}"

# Ensure the data directory exists (Railway containers start with a clean filesystem)
os.makedirs("data", exist_ok=True)

# ── Commentary cache (in-memory, 12-hour TTL) ────────────────────────────────
_CACHE_TTL = timedelta(hours=12)
_commentary_cache: dict = {"text": None, "generated_at": None}

_SYSTEM_PROMPT = """\
Você é um estrategista macro sênior de uma grande gestora de recursos.
A partir dos dados econômicos fornecidos, escreva exatamente três seções de comentário profissional, \
adequado a uma carta a clientes, em português do Brasil.
Cada seção deve começar com o título em negrito, sozinho numa linha. \
Seja denso e preciso: cite os números fornecidos e diga a implicação diretamente. \
Sem enchimento, sem rodeios, sem frases de abertura.
Use exatamente esta estrutura:

**Estados Unidos**
4 a 5 frases. Aborde: (1) onde está a Fed Funds em termos reais frente ao CPI atual, \
(2) a direção e o ritmo da trajetória da inflação e o que isso implica para o calendário de cortes, \
(3) o momento do mercado de trabalho — tendência do payroll e nível de desemprego — e o que sinalizam \
sobre consumo e pressão salarial, (4) um ou dois riscos concretos para o cenário.

**Brasil**
4 a 5 frases. Aborde: (1) a Selic em termos reais frente ao IPCA e o que isso diz sobre \
o grau de aperto da política do BCB, (2) o ritmo de convergência do IPCA à meta e se ela está \
travando ou acelerando, (3) a restrição fiscal sobre o ciclo de afrouxamento, \
(4) como o ciclo do BCB se compara ao do Fed — mesma direção ou divergente — e a implicação para o real. \
Se os dados do Brasil não forem fornecidos, escreva apenas uma frase registrando a ausência.

**Implicações para a gestão de recursos**
Exatamente 3 frases, uma por classe de ativo. Renda fixa: uma recomendação direcional de duration com a \
justificativa de juros. Ações: cíclicas versus defensivas, com uma razão. \
Ativos emergentes: apetite ou aversão a risco, com uma razão tirada da divergência de política acima.

Regras: apenas prosa corrida — sem marcadores dentro das seções, sem introdução, sem despedidas. \
Comece a primeira seção logo após o título. Use vírgula como separador decimal.\
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
    as_of    = _mes_ano(df["date"].max())

    lines = [f"Panorama econômico dos EUA — {as_of}"]
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
        lines.append("Panorama econômico do Brasil")
        lines.append(f"• Selic Rate: {selic:.2f}% p.a."  if selic    is not None else "• Selic Rate: N/A")
        lines.append(f"• IPCA (12-month YoY): {ipca_yoy:.2f}%" if ipca_yoy is not None else "• IPCA YoY: N/A")

    return "\n".join(lines)


# ── Async refresh pipeline ────────────────────────────────────────────────────
# Each tuple: (script, label, optional)
# optional=True → a non-zero exit is logged but does not abort the pipeline.
_PIPELINE_STEPS = [
    ("explore_fred.py", "Buscando dados do FRED…",  False),
    ("explore_bls.py",  "Buscando dados do BLS…",   False),
    ("explore_bcb.py",  "Buscando dados do BCB…",   True),
    ("build_master.py", "Reconstruindo a base…",  False),
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
                    "step":        f"Falhou em {script}",
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
            "step":         "Concluído",
            "finished_at":  datetime.now(),
            "last_updated": _mes_ano(df["date"].max()),
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
        month = _MESES_ABREV[prev_ts.month - 1]

        # Treat micro-changes as unchanged (< 0.005pp or < 500 jobs)
        neutral_threshold = 0.5 if unit == "k" else 0.005
        if abs(ch) < neutral_threshold:
            return {"label": f"→ estável vs {month}", "cls": "change-neutral"}

        arrow   = "↑" if ch > 0 else "↓"
        is_good = (ch < 0) if good == "down" else (ch > 0)

        if unit == "pp":
            label = f"{arrow} {abs(ch):.2f} p.p. vs {month}".replace(".", ",", 1)
        else:
            sign  = "+" if ch > 0 else ""
            label = f"{arrow} {sign}{ch:,.0f} mil vs {month}".replace(",", ".")

        return {"label": label, "cls": "change-pos" if is_good else "change-neg"}

    ff_c, ff_p, ff_pd = _last_two("FEDFUNDS")
    ur_c, ur_p, ur_pd = _last_two("UNRATE")
    cy_c, cy_p, cy_pd = _last_two("cpi_yoy")
    pt_c, pt_p, pt_pd = _last_two("payrolls_total")
    pp_c, pp_p, pp_pd = _last_two("payrolls_private")

    # Brazil stats — graceful fallback when BCB data is absent
    _BCB_UNAVAIL = {"label": "Dados indisponíveis", "cls": "change-neutral"}
    has_selic    = "selic"    in df.columns and not df["selic"].isna().all()
    has_ipca_yoy = "ipca_yoy" in df.columns and not df["ipca_yoy"].isna().all()

    if has_selic:
        sl_c, sl_p, sl_pd = _last_two("selic")
        selic_val   = _br(f"{sl_c:.2f}% a.a.") if sl_c is not None else "N/D"
        selic_delta = _delta(sl_c, sl_p, sl_pd, good="down", unit="pp")
    else:
        selic_val   = "Indisponível"
        selic_delta = _BCB_UNAVAIL

    if has_ipca_yoy:
        iy_c, iy_p, iy_pd = _last_two("ipca_yoy")
        ipca_val   = _br(f"{iy_c:.2f}%") if iy_c is not None else "N/D"
        ipca_delta = _delta(iy_c, iy_p, iy_pd, good="down", unit="pp")
    else:
        ipca_val   = "Indisponível"
        ipca_delta = _BCB_UNAVAIL

    return {
        "fed_funds":              _br(f"{ff_c:.2f}%")   if ff_c is not None else "N/D",
        "fed_funds_delta":        _delta(ff_c, ff_p, ff_pd, good="down", unit="pp"),
        "unrate":                 _br(f"{ur_c:.1f}%")   if ur_c is not None else "N/D",
        "unrate_delta":           _delta(ur_c, ur_p, ur_pd, good="down", unit="pp"),
        "cpi_yoy":                _br(f"{cy_c:.2f}%")   if cy_c is not None else "N/D",
        "cpi_yoy_delta":          _delta(cy_c, cy_p, cy_pd, good="down", unit="pp"),
        "payrolls":               f"{pt_c:,.0f} mil".replace(",", ".")  if pt_c is not None else "N/D",
        "payrolls_delta":         _delta(pt_c, pt_p, pt_pd, good="up", unit="k"),
        "payrolls_private":       f"{pp_c:,.0f} mil".replace(",", ".")  if pp_c is not None else "N/D",
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
        last_updated=_mes_ano(df["date"].max()),
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
            "step":        "Iniciando…",
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
        return jsonify({"error": "A chave ANTHROPIC_API_KEY não está configurada"}), 503

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


# No Railway o contêiner começa com o master.csv do último deploy: atualiza em segundo plano ao subir.
if os.getenv("RAILWAY_ENVIRONMENT") and os.getenv("AUTO_REFRESH", "1") == "1":
    with _refresh_lock:
        _refresh_job.update({"status": "running", "step": "Iniciando…", "started_at": datetime.now()})
    threading.Thread(target=_run_pipeline, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
