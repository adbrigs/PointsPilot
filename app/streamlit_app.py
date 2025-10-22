"""
PointsPilot Dashboard
---------------------
Streamlit dashboard to visualize transactions,
earned points, and optimization insights.
"""

import os
import sys
import time
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# ==========================================================
# PATH FIX (for Streamlit Cloud + local compatibility)
# ==========================================================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# ==========================================================
# IMPORT BACKEND MODULES
# ==========================================================
from points_engine import compute_points, load_rules, best_card_per_category
from insights import generate_insights
from visuals.charts import points_per_card_chart
from visuals.ui_sections import render_best_card_snapshot

# ==========================================================
# PATHS
# ==========================================================
DATA_DIR = os.path.join(BASE_DIR, "data")
POINTS_PATH = os.path.join(DATA_DIR, "transactions_with_points.csv")
COPILOT_PATH = os.path.join(DATA_DIR, "copilot_transactions.csv")

# ==========================================================
# STREAMLIT CONFIG
# ==========================================================
st.set_page_config(
    page_title="PointsPilot Dashboard",
    layout="wide",
    page_icon="✈️"
)

# ==========================================================
# HELPER: LOAD DATA
# ==========================================================
@st.cache_data
def load_data():
    """
    Load computed transactions_with_points.csv, or compute it
    from copilot_transactions.csv if missing.
    """
    if not os.path.exists(POINTS_PATH):
        if not os.path.exists(COPILOT_PATH):
            st.error("❌ No data file found. Please place copilot_transactions.csv in /data.")
            st.stop()
        st.info("⚙️ Generating transactions_with_points.csv from Copilot data...")
        compute_points()
    return pd.read_csv(POINTS_PATH)


# ==========================================================
# SIDEBAR
# ==========================================================
st.sidebar.title("✈️ PointsPilot")
st.sidebar.markdown("**Optimize your cards and maximize every purchase.**")

# Manual refresh
if st.sidebar.button("🔁 Recalculate Points"):
    with st.spinner("Recomputing from copilot_transactions.csv..."):
        try:
            compute_points()
            st.success("✅ Points recalculated successfully!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error recalculating: {e}")

st.sidebar.markdown("---")

# Load data for filters
df = load_data()

# ==========================================================
# CATEGORY FILTER
# ==========================================================
categories = sorted(df["category"].dropna().unique())
selected_categories = st.sidebar.multiselect(
    "📂 Filter by Category",
    options=categories,
    default=categories,
)

# Apply filter
if selected_categories:
    df = df[df["category"].isin(selected_categories)]

# ==========================================================
# DATE FILTER (default = last 30 days)
# ==========================================================
if "date" in df.columns and not df.empty:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    st.sidebar.markdown("### 📅 Filter by Date")

    # ✅ Default to last 30 days
    default_end = max_date
    default_start = max(min_date, default_end - timedelta(days=30))

    # ✅ Safely handle date input
    try:
        start_date, end_date = st.sidebar.date_input(
            "Select date range:",
            [default_start, default_end],
            min_value=min_date,
            max_value=max_date
        )
    except Exception:
        start_date = default_start
        end_date = default_end

    # ✅ Handle Streamlit returning tuple/list
    if isinstance(start_date, (list, tuple)):
        start_date, end_date = start_date

    # ✅ Filter dataframe
    df = df[
        (df["date"].dt.date >= start_date)
        & (df["date"].dt.date <= end_date)
    ]

    st.sidebar.markdown(
        f"🗓 Showing data from **{start_date.strftime('%b %d, %Y')}** to **{end_date.strftime('%b %d, %Y')}**"
    )

# ==========================================================
# LAST UPDATED TIMESTAMP
# ==========================================================
st.sidebar.markdown("---")
st.sidebar.markdown("**Last Updated:**")
if os.path.exists(POINTS_PATH):
    last_updated = datetime.fromtimestamp(os.path.getmtime(POINTS_PATH)).strftime("%b %d, %Y %I:%M %p")
    st.sidebar.markdown(f"🕒 {last_updated}")
else:
    st.sidebar.markdown("No file yet.")


# ==========================================================
# MAIN DASHBOARD
# ==========================================================
st.title("💳 PointsPilot Dashboard")
st.markdown("Visualize your reward earnings, missed points, and top optimization opportunities.")

if df.empty:
    st.warning("No transactions found for the selected filters.")
    st.stop()

# ==========================================================
# KPI SECTION
# ==========================================================
st.subheader("💳 Points Overview")

total_spent = df["amount"].sum()
total_points_earned = df["points_earned"].sum()
total_optimal_points = df["optimal_points"].sum()
optimization_rate = (total_points_earned / total_optimal_points * 100) if total_optimal_points > 0 else 0
missed_points = total_optimal_points - total_points_earned
points_per_dollar = (total_points_earned / total_spent) if total_spent > 0 else 0
optimal_points_per_dollar = (total_optimal_points / total_spent) if total_spent > 0 else 0

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("✅ Points Earned", f"{int(total_points_earned):,}")
col2.metric("🌟 Optimal Points", f"{int(total_optimal_points):,}")
col3.metric("⚠️ Points Missed", f"{int(missed_points):,}")
col4.metric("% Optimized", f"{optimization_rate:.1f}%")
col5.metric("💸 Points per $", f"{points_per_dollar:.2f}")
col6.metric("🚀 Optimal Points per $", f"{optimal_points_per_dollar:.2f}")

# ==========================================================
# INSIGHTS SECTION
# ==========================================================
st.markdown("### 💡 Smart Insights")

with st.expander("View Smart Insights", expanded=True):
    try:
        insights_df = generate_insights(df)
        if not insights_df.empty:
            st.markdown("#### 🔍 Personalized Optimization Tips")
            for _, r in insights_df.iterrows():
                icon = (
                    "💳" if r["type"] == "card"
                    else "⚠️" if r["type"] == "missed"
                    else "🎯" if r["type"] == "category"
                    else "✈️" if r["type"] == "redemption"
                    else "✅"
                )
                st.info(f"{icon} {r['insight']}")
        else:
            st.info("No insights available yet — add more transactions or refresh data.")
    except Exception as e:
        st.warning(f"⚠️ Insights unavailable: {e}")

    # ======================================================
    # QUICK WIN CATEGORY (safe mode)
    # ======================================================
    cat_summary = (
        df.groupby("category")[["points_earned", "optimal_points", "missed_points"]]
        .sum()
        .reset_index()
        .sort_values("points_earned", ascending=False)
    )

    if not cat_summary.empty:
        most_missed_cat = cat_summary.loc[cat_summary["missed_points"].idxmax(), "category"]

        best_card_for_cat = "top-earning card"
        if "best_card" in df.columns:
            best_card_series = df.loc[df["category"] == most_missed_cat, "best_card"]
            if not best_card_series.empty and len(best_card_series.mode()) > 0:
                best_card_for_cat = best_card_series.mode()[0]

        st.markdown("#### ⚡ Quick Win")
        st.info(
            f"You're missing the most points in **{most_missed_cat}**. "
            f"Try using your **{best_card_for_cat}** there."
        )

# ==========================================================
# CATEGORY BREAKDOWN
# ==========================================================
st.subheader("📊 Category Breakdown")

if "points_earned" in df.columns:
    cat_summary = (
        df.groupby("category")[["points_earned", "optimal_points", "missed_points"]]
        .sum()
        .reset_index()
        .sort_values("points_earned", ascending=False)
    )
    st.dataframe(
        cat_summary.style.format({
            "points_earned": "{:,.0f}",
            "optimal_points": "{:,.0f}",
            "missed_points": "{:,.0f}"
        })
    )
else:
    st.warning("No points data available. Try recalculating.")

# ==========================================================
# POINTS PER CARD VISUAL
# ==========================================================
st.subheader("📈 Points per Card")

try:
    fig_points = points_per_card_chart(df)
    if fig_points is not None:
        st.plotly_chart(fig_points, use_container_width=True)
    else:
        st.warning("No data available for card visualization.")
except Exception as e:
    st.warning(f"⚠️ Could not load points per card chart: {e}")

# ==========================================================
# BEST CARD SNAPSHOT
# ==========================================================
try:
    reward_rules_df = load_rules()
    if reward_rules_df.empty:
        st.warning("⚠️ No reward rules found. Check src/earn_rules.yaml.")
    else:
        best_cards_df = best_card_per_category(reward_rules_df)
        if best_cards_df.empty:
            st.info("ℹ️ No category data to display.")
        else:
            render_best_card_snapshot(best_cards_df)
except Exception as e:
    st.warning(f"⚠️ Could not load best card snapshot: {e}")

# ==========================================================
# TRANSACTION DETAILS
# ==========================================================
st.subheader("💸 Transaction Details")

try:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date", ascending=False)
    display_cols = [
        "date", "name", "amount", "category", "account",
        "best_card", "optimal_used", "points_earned", "optimal_points", "missed_points"
    ]
    # Filter existing columns only (in case of variations)
    display_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(
        df[display_cols].style.format({
            "amount": "${:,.2f}",
            "points_earned": "{:,.0f}",
            "optimal_points": "{:,.0f}",
            "missed_points": "{:,.0f}"
        }),
        height=600
    )
except Exception as e:
    st.warning(f"⚠️ Could not display transactions: {e}")

st.success("✅ Dashboard ready — using Copilot CSV data!")