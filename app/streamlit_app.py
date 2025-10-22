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

# Ensure project root is in import path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import backend modules
from src.points_engine import compute_points
from src.plaid_pull import get_sandbox_transactions

# -------------------------------------------------
# Paths
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
POINTS_PATH = os.path.join(DATA_DIR, "transactions_with_points.csv")

st.set_page_config(
    page_title="PointsPilot Dashboard",
    layout="wide",
    page_icon="✈️"
)

# -------------------------------------------------
# Helper: Load Data
# -------------------------------------------------
@st.cache_data
def load_data():
    if not os.path.exists(POINTS_PATH):
        st.warning("No data file found — generating from Plaid Sandbox...")
        compute_points()
    df = pd.read_csv(POINTS_PATH)
    return df


# -------------------------------------------------
# Sidebar
# -------------------------------------------------
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

# -------------------------------------------------
# Main Dashboard
# -------------------------------------------------
st.title("💳 PointsPilot Dashboard")
st.markdown("Visualize your reward earnings per transaction, and gain insights into how you can earn more!")

if df.empty:
    st.warning("No transactions found for the selected filters.")
    st.stop()

# ===========================
# KPI SECTION
# ===========================

# Compute KPIs
total_spent = df["amount"].sum()
total_points_earned = df["points_earned"].sum()
total_optimal_points = df["optimal_points"].sum()

# Avoid division by zero
optimization_rate = (total_points_earned / total_optimal_points * 100) if total_optimal_points > 0 else 0
missed_points = total_optimal_points - total_points_earned
points_per_dollar = (total_points_earned / total_spent) if total_spent > 0 else 0
optimal_points_per_dollar = (total_optimal_points / total_spent) if total_spent > 0 else 0

# KPI layout
col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("✅ Points Earned", f"{int(total_points_earned):,}")
col2.metric("🌟 Optimal Points", f"{int(total_optimal_points):,}")
col3.metric("⚠️ Missed Points", f"{int(missed_points):,}")
col4.metric("% Optimized", f"{optimization_rate:.1f}%")
col5.metric("💸 Points per $", f"{points_per_dollar:.2f}")
col6.metric("🚀 Optimal Points per $", f"{optimal_points_per_dollar:.2f}")

# -------------------------------------------------
# Insights Section (moved up)
# -------------------------------------------------
st.markdown("### 💡 Insights")

cat_summary = (
    df.groupby("category")[["points_earned", "optimal_points", "missed_points"]]
    .sum()
    .reset_index()
    .sort_values("points_earned", ascending=False)
)

if not cat_summary.empty:
    most_missed_cat = cat_summary.loc[cat_summary["missed_points"].idxmax(), "category"]
    st.info(
        f"You're missing the most points in **{most_missed_cat}**. "
        f"Try using your **{df.loc[df['category'] == most_missed_cat, 'best_card'].mode()[0]}** there."
    )

# -------------------------------------------------
# Category Breakdown
# -------------------------------------------------
st.subheader("📊 Category Breakdown")

st.dataframe(
    cat_summary.style.format({
        "points_earned": "{:,.0f}",
        "optimal_points": "{:,.0f}",
        "missed_points": "{:,.0f}"
    })
)

# -------------------------------------------------
# Transaction Detail Table
# -------------------------------------------------
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
    })
    .map(lambda v: "color: green; font-weight: bold" if v is True else "", subset=["optimal_used"]),
    height=600
)

# -------------------------------------------------
# Completion message
# -------------------------------------------------
st.success("Dashboard ready — all data synced with PointsPilot backend!")