# Macro Dashboard

🇺🇸 **English** · 🇧🇷 [Português](README.pt-BR.md)

**A live macroeconomic dashboard covering U.S. and Brazilian indicators — with AI-generated commentary written in the style of a sell-side macro strategist.**

![Python](https://img.shields.io/badge/Python-3.11+-informational?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?style=flat-square)
![Plotly](https://img.shields.io/badge/Plotly-5.x-3F4F75?style=flat-square)

---

## What it does

- **Pulls live macro data** from three public APIs — the Federal Reserve (FRED), the Bureau of Labor Statistics (BLS), and the Banco Central do Brasil (BCB) — and merges them into a single master dataset on demand.
- **Renders five interactive charts**: Fed Funds Rate vs Unemployment, CPI inflation (YoY), Nonfarm Payrolls level and MoM momentum, private employment by sector (goods vs services stacked area), and Selic Rate vs Brazilian IPCA inflation.
- **Displays seven real-time stat cards** — Fed Funds Rate, Unemployment, CPI, Total and Private Payrolls (US), Selic Rate, and Brazil CPI — each with a color-coded month-over-month delta indicating whether the reading is improving or deteriorating relative to the prior period.
- **Generates structured AI commentary** via the Anthropic API (Claude): a three-section client-note paragraph covering the U.S. macro backdrop, the Brazilian policy cycle, and cross-asset positioning implications.

---

## Why it matters for portfolio managers

The indicators tracked here are the exact data points that drive fixed income and equity allocation decisions at Brazilian asset managers active in both domestic and international markets:

**Federal Funds Rate and CPI (US)** determine the real rate environment in the world's largest bond market. When U.S. real rates are deeply positive, they pull capital away from EM assets and put pressure on the BRL — directly relevant for any fund with cross-border exposure.

**Nonfarm Payrolls and Unemployment (US)** are the Fed's second mandate. A labor market that refuses to cool forces the FOMC to hold rates higher for longer, compressing risk appetite globally and tightening financial conditions for emerging economies.

**Selic Rate and IPCA (Brazil)** set the domestic risk-free rate and define the real yield that Brazilian fixed income offers relative to the U.S. The spread between Selic and Fed Funds — and its direction of travel — is a key input for duration positioning in local-currency bonds and for BRL carry trades.

For a portfolio manager at a Brazilian asset manager, being able to read all seven figures simultaneously — and understand their interplay — is the starting point for every allocation discussion.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask |
| Data pipeline | Pandas, Requests |
| Visualisation | Plotly (graph_objects, make_subplots) |
| AI commentary | Anthropic Python SDK (Claude claude-sonnet-4-6) |
| Frontend | Vanilla JS, HTML/CSS (no framework) |
| Serving | Gunicorn (production), Flask dev server (local) |
| Environment | python-dotenv |

---

## Data sources

| Source | What it provides | API |
|---|---|---|
| [FRED](https://fred.stlouisfed.org) — Federal Reserve Bank of St. Louis | Federal Funds Rate (`FEDFUNDS`), Unemployment Rate (`UNRATE`), CPI (`CPIAUCSL`) | [FRED API](https://fred.stlouisfed.org/docs/api/fred/) |
| [BLS](https://www.bls.gov) — Bureau of Labor Statistics | Total nonfarm payrolls, private sector payrolls, goods-producing and private services employment | [BLS Public Data API](https://www.bls.gov/developers/) |
| [BCB](https://www.bcb.gov.br) — Banco Central do Brasil | Selic target rate (series 432), IPCA 12-month accumulated inflation (series 13522) | [BCB SGS API](https://www.bcb.gov.br/content/config/docs/APISeries_en.pdf) |

All three APIs are free and require no authentication key for the series used here (a BLS registered key unlocks higher rate limits but is optional).

---

## How the AI commentary works

When you click **Generate Commentary**, the dashboard:

1. Reads the latest row from the merged master dataset and formats a concise data block — Fed Funds Rate, Unemployment, CPI YoY, Payrolls MoM, Selic Rate, and IPCA YoY.
2. Sends that block to Claude via the Anthropic API with a carefully engineered system prompt that instructs it to write three distinct sections:
   - **United States** — 4–5 sentences covering the real rate level, the inflation trajectory and what it implies for the easing timeline, labor market momentum, and near-term risks.
   - **Brazil** — 4–5 sentences covering the real Selic rate, IPCA convergence pace, fiscal constraints on the easing cycle, and a direct comparison of the BCB and Fed policy cycles with the BRL implication.
   - **Asset Management Implications** — exactly three sentences, one per asset class: a duration call for fixed income, a cyclicals-vs-defensives view for equities, and a risk-on/risk-off stance for EM assets.
3. Caches the result for 12 hours (configurable) to avoid redundant API calls on each page load. The cache is invalidated automatically on data refresh.

The prompt uses `cache_control: ephemeral` on the system prompt, which pins it to Anthropic's prompt cache and reduces latency and cost on repeated calls with the same instructions.

---

## How to run locally

**Prerequisites:** Python 3.11+, a FRED API key (free), and an Anthropic API key (for AI commentary).

```bash
# 1. Clone the repo
git clone https://github.com/joaoalbuquerquef/macro-dashboard.git
cd macro-dashboard

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Edit .env and fill in:
#   FRED_API_KEY=your_fred_key
#   ANTHROPIC_API_KEY=your_anthropic_key
#   BLS_API_KEY=your_bls_key   # optional — public tier works without it

# 5. Fetch data and build the master dataset
python explore_fred.py
python explore_bls.py
python explore_bcb.py           # optional — dashboard degrades gracefully if BCB is unavailable
python build_master.py

# 6. Start the Flask development server
python app.py
```

Open [http://localhost:5000](http://localhost:5000). Use the **Refresh Data** button in the header to re-run the full pipeline in the background and reload automatically when complete.

---

## Project structure

```
macro-dashboard/
├── app.py              # Flask app — routes, async refresh pipeline, AI commentary
├── charts.py           # Five Plotly chart functions
├── build_master.py     # Merges FRED + BLS + BCB into data/master.csv
├── explore_fred.py     # FRED API client → data/fred_raw.csv
├── explore_bls.py      # BLS API client → data/bls_raw.csv
├── explore_bcb.py      # BCB SGS API client → data/bcb_raw.csv
├── templates/
│   └── index.html      # Single-page dashboard (Jinja2 + vanilla JS)
├── data/               # Auto-generated CSV files (gitignored)
├── requirements.txt
└── .env.example
```

---

## Author

Built as part of a quantitative finance portfolio while studying at Sciences Po Paris and preparing for a career in asset management in Brazil.

The project is intentionally end-to-end — data pipeline, visualisation, and AI integration — to reflect the kind of work that sits at the intersection of macro research, technology, and client communication in a modern asset management context.
