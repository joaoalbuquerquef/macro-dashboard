"""
Session 2 — First Plotly charts.

Reads data/master.csv and produces three standalone HTML charts:
  static/chart_rates.html      — Fed Funds Rate vs Unemployment Rate
  static/chart_inflation.html  — CPI YoY % (inflation)
  static/chart_payrolls.html   — Total Nonfarm Payrolls + MoM change

Run:
    python charts.py
"""

import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

MASTER_PATH = os.path.join("data", "master.csv")
STATIC_DIR = "static"

COLORS = {
    "fed_funds":    "#E63946",  # red
    "unemployment": "#457B9D",  # blue
    "inflation":    "#F4A261",  # orange
    "payrolls":     "#2A9D8F",  # teal
    "payrolls_mom": "#264653",  # dark slate
}


def load_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_PATH, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Chart 1: Fed Funds Rate vs Unemployment Rate (dual y-axis)
# ---------------------------------------------------------------------------
def chart_rates(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["FEDFUNDS"],
            name="Fed Funds Rate (%)",
            line=dict(color=COLORS["fed_funds"], width=2),
            hovertemplate="%{x|%b %Y}<br>Fed Funds: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["UNRATE"],
            name="Unemployment Rate (%)",
            line=dict(color=COLORS["unemployment"], width=2, dash="dot"),
            hovertemplate="%{x|%b %Y}<br>Unemployment: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Fed Funds Rate vs Unemployment Rate",
        hovermode="x unified",
        # Legend below the chart — avoids collision with the title at top-left
        # and the two y-axis labels occupying both top corners.
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(title_text="Fed Funds Rate (%)", secondary_y=False,
                     showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(title_text="Unemployment Rate (%)", secondary_y=True,
                     showgrid=False)

    return fig


# ---------------------------------------------------------------------------
# Chart 2: CPI YoY inflation
# ---------------------------------------------------------------------------
def chart_inflation(df: pd.DataFrame) -> go.Figure:
    plot_df = df.dropna(subset=["cpi_yoy"])

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=plot_df["date"],
            y=plot_df["cpi_yoy"],
            name="CPI YoY %",
            fill="tozeroy",
            fillcolor="rgba(244, 162, 97, 0.2)",
            line=dict(color=COLORS["inflation"], width=2),
            hovertemplate="%{x|%b %Y}<br>CPI YoY: %{y:.2f}%<extra></extra>",
        )
    )

    # 2% Fed target reference line
    fig.add_hline(
        y=2.0,
        line_dash="dash",
        line_color="#888888",
        annotation_text="2% target",
        annotation_position="bottom right",
    )

    fig.update_layout(
        title="CPI Inflation (Year-over-Year %)",
        yaxis_title="YoY Change (%)",
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE")

    return fig


# ---------------------------------------------------------------------------
# Chart 3: Nonfarm Payrolls level + MoM change (stacked subplots)
# ---------------------------------------------------------------------------
def chart_payrolls(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.08,
        subplot_titles=("Total Nonfarm Payrolls (thousands)", "Monthly Change (thousands)"),
    )

    # Top: payrolls level
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["payrolls_total"],
            name="Total Payrolls",
            line=dict(color=COLORS["payrolls"], width=2),
            hovertemplate="%{x|%b %Y}<br>Payrolls: %{y:,.0f}k<extra></extra>",
        ),
        row=1, col=1,
    )

    # Bottom: MoM bar chart
    mom = df.dropna(subset=["payrolls_mom"])
    bar_colors = [COLORS["payrolls"] if v >= 0 else COLORS["fed_funds"]
                  for v in mom["payrolls_mom"]]

    fig.add_trace(
        go.Bar(
            x=mom["date"],
            y=mom["payrolls_mom"],
            name="MoM Change",
            marker_color=bar_colors,
            hovertemplate="%{x|%b %Y}<br>MoM: %{y:+,.0f}k<extra></extra>",
        ),
        row=2, col=1,
    )

    fig.update_layout(
        title="Nonfarm Payrolls",
        hovermode="x unified",
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE")

    return fig


# ---------------------------------------------------------------------------
# Chart 4: Payrolls sector breakdown — stacked area (goods vs private services)
# ---------------------------------------------------------------------------
def chart_payrolls_sector(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    # Goods-producing (bottom of stack)
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["payrolls_goods"],
            name="Goods-Producing",
            stackgroup="sector",
            fillcolor="rgba(38, 70, 83, 0.65)",
            line=dict(color=COLORS["payrolls_mom"], width=1.5),
            hovertemplate="%{x|%b %Y}<br>Goods: %{y:,.0f}k<extra></extra>",
        )
    )

    # Private services (stacked on top)
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["payrolls_private_services"],
            name="Private Services",
            stackgroup="sector",
            fillcolor="rgba(42, 157, 143, 0.55)",
            line=dict(color=COLORS["payrolls"], width=1.5),
            hovertemplate="%{x|%b %Y}<br>Private Services: %{y:,.0f}k<extra></extra>",
        )
    )

    fig.update_layout(
        title="Private Employment by Sector — Goods vs Services (thousands)",
        yaxis_title="Employees (thousands)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE")

    return fig


# ---------------------------------------------------------------------------
# Chart 5: Brazil — Selic rate vs IPCA YoY (same dual-axis pattern as chart_rates)
# ---------------------------------------------------------------------------
def chart_selic(df: pd.DataFrame) -> go.Figure:
    """
    Selic rate (left axis) vs Brazil IPCA 12-month YoY (right axis).
    Returns an annotated empty figure if BCB data is absent so the dashboard
    degrades gracefully without raising an exception.
    """
    has_selic = "selic"    in df.columns and not df["selic"].isna().all()
    has_ipca  = "ipca_yoy" in df.columns and not df["ipca_yoy"].isna().all()

    if not has_selic and not has_ipca:
        fig = go.Figure()
        fig.update_layout(
            title="Brazil: Selic Rate vs IPCA Inflation — Data unavailable",
            annotations=[dict(
                text="Brazil data could not be loaded from the BCB API.",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(size=13, color="#6B7280"),
            )],
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        return fig

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if has_selic:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["selic"],
                name="Selic Rate (% p.a.)",
                line=dict(color="#E76F51", width=2),   # burnt orange — distinct from US red
                hovertemplate="%{x|%b %Y}<br>Selic: %{y:.2f}% p.a.<extra></extra>",
            ),
            secondary_y=False,
        )

    if has_ipca:
        plot_df = df.dropna(subset=["ipca_yoy"])
        fig.add_trace(
            go.Scatter(
                x=plot_df["date"],
                y=plot_df["ipca_yoy"],
                name="IPCA YoY (%)",
                line=dict(color="#52B788", width=2, dash="dot"),  # sage green
                hovertemplate="%{x|%b %Y}<br>IPCA YoY: %{y:.2f}%<extra></extra>",
            ),
            secondary_y=True,
        )

    fig.update_layout(
        title="Brazil: Selic Rate vs IPCA Inflation (YoY)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(title_text="Selic Rate (% p.a.)", secondary_y=False,
                     showgrid=True, gridcolor="#EEEEEE")
    fig.update_yaxes(title_text="IPCA YoY (%)", secondary_y=True, showgrid=False)

    return fig


def main():
    os.makedirs(STATIC_DIR, exist_ok=True)
    df = load_master()

    charts = [
        ("chart_rates.html",          chart_rates(df),           "Fed Funds vs Unemployment"),
        ("chart_inflation.html",      chart_inflation(df),       "CPI Inflation YoY"),
        ("chart_payrolls.html",       chart_payrolls(df),        "Nonfarm Payrolls"),
        ("chart_sector.html",         chart_payrolls_sector(df), "Payrolls Sector Breakdown"),
    ]

    for filename, fig, label in charts:
        path = os.path.join(STATIC_DIR, filename)
        fig.write_html(path, include_plotlyjs="cdn", full_html=True)
        print(f"Saved {label} → {path}")


if __name__ == "__main__":
    main()
