"""
Denial Intelligence — Pre-Submission Risk Analysis & Denial Prediction

Two modes:
  1. Pre-Submission Scan  — Upload an 837P file and get risk scores BEFORE submitting
  2. Historical Analysis  — Visualize denial patterns from past 835 ERA data
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from storage.file_store import list_files, ensure_db

st.title("🤖 Denial Intelligence")
st.caption("Pre-submission risk scanning + historical denial pattern analysis")

ensure_db()

# ── Tab layout ────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🔍 Pre-Submission Risk Scan", "📈 Historical Denial Patterns"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Pre-Submission Risk Scan
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Pre-Submission Denial Risk Scan")
    st.markdown(
        "Upload an **837P** file to evaluate each service line for common denial "
        "triggers **before** submitting to the payer. The engine checks "
        "modifiers, diagnosis pointers, NDC requirements, place-of-service rules, "
        "and more."
    )

    uploaded = st.file_uploader(
        "Upload 837P EDI file for risk analysis",
        type=["edi", "x12", "txt", "837"],
        key="denial_upload",
    )

    # Optional: enrich with historical 835 data
    all_files_835 = [f for f in list_files() if f["tx_type"] == "835"]
    use_history = False
    if all_files_835:
        use_history = st.checkbox(
            "Enrich predictions with historical denial rates from parsed 835 files",
            value=True,
        )

    if uploaded:
        with st.spinner("Parsing 837P and running denial prediction rules…"):
            try:
                from app.services.parse_service import parse_edi
                from analytics.denial_predictor import predict_from_837p, prediction_summary
                from analytics.aggregator import get_adjustments_df

                file_bytes = uploaded.read()
                result = parse_edi(file_bytes, uploaded.name)

                if not result.success:
                    st.error(f"Parse failed: {result.error}")
                    st.stop()

                if result.tx_type != "837P":
                    st.warning(f"Expected 837P, got {result.tx_type}. Risk scan is optimised for professional claims.")

                # Load historical adjustments for enrichment
                adj_df = get_adjustments_df() if use_history else None

                predictions = predict_from_837p(result.data, adj_df)
                summary     = prediction_summary(predictions)

            except Exception as exc:
                st.error(f"Risk analysis failed: {exc}")
                st.stop()

        # ── Summary metrics ────────────────────────────────────────────────────
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Service Lines", f"{summary['total']:,}")
        s2.metric("🔴 HIGH Risk",    f"{summary['high']:,}",
                  delta=f"{summary['high']/max(summary['total'],1)*100:.1f}%",
                  delta_color="inverse")
        s3.metric("🟡 MEDIUM Risk",  f"{summary['medium']:,}")
        s4.metric("🟢 LOW Risk",     f"{summary['low']:,}")

        # Risk distribution donut
        risk_counts = pd.DataFrame([
            {"Risk Level": "HIGH",   "Count": summary["high"]},
            {"Risk Level": "MEDIUM", "Count": summary["medium"]},
            {"Risk Level": "LOW",    "Count": summary["low"]},
        ])
        fig_risk = px.pie(
            risk_counts, values="Count", names="Risk Level",
            title="Risk Distribution",
            color="Risk Level",
            color_discrete_map={"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "LOW": "#2ecc71"},
            hole=0.4,
        )
        fig_risk.update_layout(height=300)

        col_donut, col_factors = st.columns([1, 1])
        with col_donut:
            st.plotly_chart(fig_risk, use_container_width=True)

        with col_factors:
            st.markdown("**Top Risk Factors**")
            for item in summary.get("top_factors", []):
                st.markdown(f"- {item['factor']} *(×{item['count']})*")

        st.divider()

        # ── Detailed results table ─────────────────────────────────────────────
        st.subheader("Service Line Detail")

        if predictions:
            rows = []
            for p in predictions:
                rows.append({
                    "CPT/HCPCS":         p.cpt_hcpcs,
                    "Modifier":          p.modifier_1 or "—",
                    "Risk Score":        p.risk_score,
                    "Risk Level":        p.risk_level,
                    "Risk Factors":      " | ".join(p.risk_factors) if p.risk_factors else "None",
                    "Recommendations":   " | ".join(p.recommendations) if p.recommendations else "—",
                    "Historical Denial %": f"{p.historical_denial_rate:.1f}%" if p.historical_denial_rate is not None else "N/A",
                })

            pred_df = pd.DataFrame(rows)

            # Filter controls
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                level_filter = st.multiselect(
                    "Filter by Risk Level:",
                    options=["HIGH", "MEDIUM", "LOW"],
                    default=["HIGH", "MEDIUM"],
                )
            with col_f2:
                cpt_filter = st.text_input("Filter by CPT:", "")

            filtered = pred_df[pred_df["Risk Level"].isin(level_filter)] if level_filter else pred_df
            if cpt_filter:
                filtered = filtered[filtered["CPT/HCPCS"].str.contains(cpt_filter.upper(), na=False)]

            def _color_risk(val):
                colors = {"HIGH": "background-color: #fde8e8", "MEDIUM": "background-color: #fff3cd", "LOW": ""}
                return colors.get(val, "")

            styled = filtered.style.applymap(_color_risk, subset=["Risk Level"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

            # Export predictions as Excel
            if st.button("📥 Export Risk Report to Excel"):
                import io
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    pred_df.to_excel(writer, sheet_name="Risk Analysis", index=False)
                    risk_counts.to_excel(writer, sheet_name="Summary", index=False)
                st.download_button(
                    "⬇️ Download Risk Report",
                    data=buf.getvalue(),
                    file_name=f"denial_risk_{uploaded.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.success("✅ No risk factors identified across all service lines.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Historical Denial Patterns
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Historical Denial Pattern Analysis")

    all_files = list_files()
    files_835 = [f for f in all_files if f["tx_type"] == "835"]

    if not files_835:
        st.info("📭 No 835 ERA files parsed yet. Upload remittance files to see denial patterns.")
        st.stop()

    from analytics.aggregator    import get_adjustments_df, get_payments_df
    from analytics.denial_analyzer import denial_summary, top_denial_categories

    @st.cache_data(ttl=120)
    def load_denial_data():
        return get_adjustments_df(), get_payments_df()

    adj_df, pay_df = load_denial_data()

    if adj_df.empty:
        st.info("No adjustment data found in parsed 835 files.")
        st.stop()

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.sidebar:
        group_filter = st.multiselect(
            "Adjustment Group Code:",
            options=["CO", "PR", "OA", "PI", "CR"],
            default=["CO"],
            help="CO=Contractual, PR=Patient Responsibility, OA=Other Adjustment",
        )

    if group_filter:
        adj_filtered = adj_df[adj_df["group_code"].isin(group_filter)] \
            if "group_code" in adj_df.columns else adj_df
    else:
        adj_filtered = adj_df

    # ── Top denial reason codes ────────────────────────────────────────────────
    st.markdown("### Top Denial Reason Codes (CARC)")

    denial_df  = denial_summary()
    if not denial_df.empty:
        top_n = denial_df.head(15)

        fig_carc = px.bar(
            top_n,
            x="reason_code",
            y="count",
            color="category",
            title="Top 15 Denial Reason Codes by Frequency",
            labels={"count": "# Occurrences", "reason_code": "CARC"},
            hover_data=["description", "total_amount"],
        )
        fig_carc.update_layout(height=400, legend_title="Category")
        st.plotly_chart(fig_carc, use_container_width=True)

        # Trend: denials by month (if payment_date available)
        if not pay_df.empty and "payment_date" in pay_df.columns and "id" in pay_df.columns:
            if "payment_id" in adj_df.columns:
                trend_data = (
                    adj_df[adj_df["group_code"].isin(["CO"])]
                    .merge(pay_df[["id", "payment_date"]], left_on="payment_id", right_on="id", how="left")
                    .dropna(subset=["payment_date"])
                )
                if not trend_data.empty:
                    trend_data["payment_date"] = pd.to_datetime(trend_data["payment_date"], errors="coerce")
                    trend_data["month"] = trend_data["payment_date"].dt.to_period("M").astype(str)
                    monthly = trend_data.groupby(["month", "reason_code"])["amount"].count().reset_index()
                    monthly.columns = ["month", "reason_code", "count"]

                    top_reasons = denial_df["reason_code"].head(5).tolist()
                    monthly_top = monthly[monthly["reason_code"].isin(top_reasons)]

                    if not monthly_top.empty:
                        fig_trend = px.line(
                            monthly_top,
                            x="month", y="count", color="reason_code",
                            title="Denial Trend — Top 5 Reason Codes (Monthly)",
                            labels={"count": "# Denials", "month": "Month", "reason_code": "CARC"},
                            markers=True,
                        )
                        fig_trend.update_layout(height=350)
                        st.plotly_chart(fig_trend, use_container_width=True)

        st.dataframe(
            denial_df[["reason_code", "description", "category", "group_code",
                        "count", "total_amount", "pct_of_total"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No denial data found.")

    st.divider()

    # ── Denial by CPT (service line level) ────────────────────────────────────
    st.markdown("### Denial Rate by CPT/HCPCS Code")

    if "cpt_hcpcs" in adj_df.columns and "group_code" in adj_df.columns:
        co_by_cpt = (
            adj_df[adj_df["group_code"] == "CO"]
            .groupby("cpt_hcpcs")
            .agg(denial_count=("amount", "count"), total_denied=("amount", "sum"))
            .reset_index()
            .sort_values("denial_count", ascending=False)
            .head(20)
        )

        if not co_by_cpt.empty:
            fig_cpt_denial = px.bar(
                co_by_cpt,
                x="cpt_hcpcs", y="denial_count",
                title="Top 20 CPT Codes by Denial Count",
                labels={"denial_count": "# Denials", "cpt_hcpcs": "CPT/HCPCS"},
                color="total_denied",
                color_continuous_scale="Reds",
            )
            fig_cpt_denial.update_layout(height=380, coloraxis_showscale=True)
            st.plotly_chart(fig_cpt_denial, use_container_width=True)

    # ── Denial by Payer ────────────────────────────────────────────────────────
    st.markdown("### Denial Rate by Payer")

    if not pay_df.empty and "payer_name" in pay_df.columns and "status_code" in pay_df.columns:
        payer_denial = (
            pay_df.groupby("payer_name")
            .agg(
                total=("id", "count"),
                denied=("status_code", lambda x: (x == "4").sum()),
            )
            .reset_index()
        )
        payer_denial["denial_rate_pct"] = (
            payer_denial["denied"] / payer_denial["total"].replace(0, float("nan")) * 100
        ).round(2)
        payer_denial = payer_denial.sort_values("denial_rate_pct", ascending=False).head(15)

        if not payer_denial.empty:
            fig_payer = px.bar(
                payer_denial,
                x="payer_name", y="denial_rate_pct",
                title="Denial Rate by Payer (%)",
                labels={"denial_rate_pct": "Denial Rate (%)", "payer_name": "Payer"},
                color="denial_rate_pct",
                color_continuous_scale=[[0,"#2ecc71"],[0.1,"#f39c12"],[1.0,"#e74c3c"]],
            )
            fig_payer.add_hline(y=5, line_dash="dot", line_color="orange",
                                annotation_text="5% target")
            fig_payer.update_layout(height=380, coloraxis_showscale=False,
                                    xaxis_tickangle=-30)
            st.plotly_chart(fig_payer, use_container_width=True)
