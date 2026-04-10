"""Plotly chart builders for the analytics dashboard."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


BRAND_COLORS = ["#1F4E79", "#2E75B6", "#9DC3E6", "#F4B942", "#E8543A", "#5BA854", "#8E44AD"]


def claims_volume_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart: claim count and total billed by period."""
    if df.empty:
        return _empty_fig("No claim data available")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["period"], y=df["total_billed"],
        name="Total Billed ($)", marker_color=BRAND_COLORS[1], yaxis="y2", opacity=0.4,
    ))
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["claim_count"],
        name="Claim Count", mode="lines+markers",
        line=dict(color=BRAND_COLORS[0], width=2),
    ))
    fig.update_layout(
        title="Claim Volume Over Time",
        xaxis_title="Period",
        yaxis=dict(title="Claim Count"),
        yaxis2=dict(title="Total Billed ($)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=-0.2),
        height=380,
    )
    return fig


def denial_rate_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart: denial rate % over time."""
    if df.empty or "denial_rate_pct" not in df.columns:
        return _empty_fig("No payment data available")
    fig = px.line(
        df, x="period", y="denial_rate_pct",
        title="Denial Rate Over Time (%)",
        labels={"period":"Period","denial_rate_pct":"Denial Rate (%)"},
        color_discrete_sequence=[BRAND_COLORS[4]],
        markers=True,
    )
    fig.update_layout(height=360)
    return fig


def payer_mix_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart: total billed per payer."""
    if df.empty:
        return _empty_fig("No payer data")
    df_sorted = df.nlargest(15, "total_billed")
    fig = px.bar(
        df_sorted, x="total_billed", y="payer_name", orientation="h",
        title="Payer Mix by Total Billed",
        labels={"total_billed":"Total Billed ($)","payer_name":"Payer"},
        color_discrete_sequence=[BRAND_COLORS[0]],
    )
    fig.update_layout(height=420, yaxis=dict(autorange="reversed"))
    return fig


def denial_category_donut(df: pd.DataFrame) -> go.Figure:
    """Donut chart: denial breakdown by category."""
    if df.empty:
        return _empty_fig("No denial data")
    fig = go.Figure(go.Pie(
        labels=df["category"], values=df["count"],
        hole=0.45, marker=dict(colors=BRAND_COLORS),
        textinfo="label+percent",
    ))
    fig.update_layout(title="Denial Categories", height=360, showlegend=True)
    return fig


def cpt_charge_vs_cms_scatter(comparisons: list[dict]) -> go.Figure:
    """Scatter: billed amount vs Medicare non-facility rate per CPT."""
    if not comparisons:
        return _empty_fig("No CMS comparison data")
    df = pd.DataFrame(comparisons)
    df = df.dropna(subset=["billed_amount","pfs_non_facility_rate"])
    if df.empty:
        return _empty_fig("No matched CPT codes")

    color_map = {
        "OVER_300PCT":  BRAND_COLORS[4],
        "UNDER_100PCT": BRAND_COLORS[3],
        "WITHIN_RANGE": BRAND_COLORS[5],
        "NO_RATE":      "#AAAAAA",
    }
    df["color"] = df["flag"].map(color_map).fillna("#AAAAAA")

    fig = go.Figure()
    for flag, grp in df.groupby("flag"):
        fig.add_trace(go.Scatter(
            x=grp["pfs_non_facility_rate"], y=grp["billed_amount"],
            mode="markers", name=flag,
            marker=dict(color=color_map.get(flag,"#AAA"), size=7, opacity=0.75),
            text=grp["cpt_hcpcs"],
            hovertemplate="<b>%{text}</b><br>Medicare Rate: $%{x:.2f}<br>Billed: $%{y:.2f}<extra></extra>",
        ))
    # Add 1:1 reference lines for 100% and 300%
    max_rate = df["pfs_non_facility_rate"].max()
    fig.add_trace(go.Scatter(
        x=[0, max_rate], y=[0, max_rate],
        mode="lines", name="100% of Medicare",
        line=dict(dash="dash", color="green", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=[0, max_rate], y=[0, max_rate * 3],
        mode="lines", name="300% of Medicare",
        line=dict(dash="dot", color="red", width=1),
    ))
    fig.update_layout(
        title="Billed Amount vs Medicare Non-Facility Rate",
        xaxis_title="Medicare Non-Facility Rate ($)",
        yaxis_title="Billed Amount ($)",
        height=450,
    )
    return fig


def ar_aging_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart: AR aging buckets."""
    if df.empty:
        return _empty_fig("No AR aging data")
    fig = px.bar(
        df, x="bucket", y="total_billed",
        title="AR Aging by Days Outstanding",
        labels={"bucket":"Age Bucket","total_billed":"Total Billed ($)"},
        color="bucket",
        color_discrete_sequence=BRAND_COLORS,
    )
    fig.update_layout(height=360, showlegend=False)
    return fig


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False, font=dict(size=14))
    fig.update_layout(height=320)
    return fig
