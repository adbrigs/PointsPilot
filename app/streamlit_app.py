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
from datetime import datetime

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
from plaid_pull import get_sandbox_transactions
from points_engine import compute_points, load_rules, best_card_per_category
from insights import generate_insights
from visuals.charts import points_per_card_chart
from visuals.ui_sections import render_best_card_snapshot

# ==========================================================
# PATHS
# ==========================================================
DATA_DIR = os.path.join(BASE_DIR, "data")
POINTS_PATH = os.path.join(DATA_DIR, "transactions_with_points.csv")

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
    if not os.path.exists(POINTS_PATH):
        st.warning("No data file found — generating from Plaid Sandbox...")
        compute_points()
    df = pd.read_csv(POINTS_PATH)
    return df


# ==========================================================
# SIDEBAR
# ==========================================================
st.sidebar.title("✈️ PointsPilot")
st.sidebar.markdown("**Manage your points & optimize every purchase.**")

if st.sidebar.button("🔁 Refresh All Data"):
    with st.spinner("Refreshing Plaid sandbox data..."):
        try:
            get_sandbox_transactions()
            compute_points()
            st.success("✅ Data refreshed successfully!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error refreshing data: {e}")

st.sidebar.markdown("---")

# Load data so filters can populate
df = load_data()

# Category filter (multi-select)
categories = sorted(df["category"].dropna().unique())
selected_categories = st.sidebar.multiselect(
    "📂 Filter by Category",
    options=categories,
    default=categories,
)

# Apply filter
if selected_categories:
    df = df[df["category"].isin(selected_categories)]

# Show last updated time
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
st.markdown("Visualize your reward earnings per transaction, and gain insights into how you can earn more!")

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

    # Quick category improvement tip
    cat_summary = (
        df.groupby("category")[["points_earned", "optimal_points", "missed_points"]]
        .sum()
        .reset_index()
        .sort_values("points_earned", ascending=False)
    )

    if not cat_summary.empty:
        most_missed_cat = cat_summary.loc[cat_summary["missed_points"].idxmax(), "category"]
        st.markdown("#### ⚡ Quick Win")
        st.info(
            f"You're missing the most points in **{most_missed_cat}**. "
            f"Try using your **{df.loc[df['category'] == most_missed_cat, 'best_card'].mode()[0]}** there."
        )

# ==========================================================
# CATEGORY BREAKDOWN
# ==========================================================
st.subheader("📊 Category Breakdown")

st.dataframe(
    cat_summary.style.format({
        "points_earned": "{:,.0f}",
        "optimal_points": "{:,.0f}",
        "missed_points": "{:,.0f}"
    })
)

# ==========================================================
# POINTS PER CARD VISUAL
# ==========================================================
st.subheader("📈 Points per Card")

view_mode = st.radio("View as:", ["Points", "Cash Value"], horizontal=True, label_visibility="collapsed")

fig_points = points_per_card_chart(df)

if fig_points is not None:
    st.plotly_chart(fig_points, use_container_width=True)
else:
    st.warning("No data available for card visualization.")

# ==========================================================
# BEST CARD SNAPSHOT (YAML-based)
# ==========================================================
st.subheader("🏆 Best Card by Category")

try:
    reward_rules_df = load_rules()  # YAML → DataFrame
    if reward_rules_df.empty:
        st.warning("⚠️ No reward rules found. Check src/earn_rules.yaml.")
    else:
        best_cards_df = best_card_per_category(reward_rules_df)
        if best_cards_df.empty:
            st.info("ℹ️ No category data to display from earn_rules.yaml.")
        else:
            render_best_card_snapshot(best_cards_df)
except FileNotFoundError as e:
    st.warning(f"⚠️ {e}")
except Exception as e:
    st.error(f"❌ Error loading best card snapshot: {e}")

# ==========================================================
# TRANSACTION DETAILS
# ==========================================================
st.subheader("💸 Transaction Details")

df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date", ascending=False)

display_cols = [
    "date", "merchant", "amount", "category",
    "card_used", "best_card", "optimal_used",
    "points_earned", "optimal_points", "missed_points"
]

st.dataframe(
    df[display_cols]
    .style.format({
        "amount": "${:,.2f}",
        "points_earned": "{:,.0f}",
        "optimal_points": "{:,.0f}",
        "missed_points": "{:,.0f}"
    }),
    height=600
)

st.success("✅ Dashboard ready — all data synced with PointsPilot backend!")