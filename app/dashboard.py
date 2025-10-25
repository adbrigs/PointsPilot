"""
PointsPilot Dashboard
---------------------
Streamlit dashboard to visualize transactions, earned points,
and optimization opportunities.
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
from points_engine import compute_points, load_rules

# ==========================================================
# PATHS
# ==========================================================
DATA_DIR = os.path.join(BASE_DIR, "data")
REVIEW_PATH = os.path.join(DATA_DIR, "transactions_review.csv")
RAW_PATH = os.path.join(DATA_DIR, "raw_transactions.csv")

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
    """Load transactions_review.csv or compute if missing."""
    if not os.path.exists(REVIEW_PATH):
        if not os.path.exists(RAW_PATH):
            st.error("❌ No data file found. Please place raw_transactions.csv in /data.")
            st.stop()
        st.info("⚙️ Generating transactions_review.csv from raw data...")
        compute_points()
    return pd.read_csv(REVIEW_PATH)

# ==========================================================
# SIDEBAR
# ==========================================================
st.sidebar.title("✈️ PointsPilot")
st.sidebar.markdown("**Optimize your cards and maximize every purchase.**")

if st.sidebar.button("🔁 Recalculate Points"):
    with st.spinner("Recomputing from raw_transactions.csv..."):
        try:
            compute_points()
            st.success("✅ Points recalculated successfully!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error recalculating: {e}")

st.sidebar.markdown("---")

# Load data
df = load_data()

# ==========================================================
# Add normalized optimal_used flag
# ==========================================================
def normalize_card(card):
    name = str(card).lower()
    if "sapphire" in name:
        return "sapphire preferred"
    if "freedom unlimited" in name:
        return "freedom unlimited"
    if "freedom flex" in name:
        return "freedom flex"
    if "aadvantage" in name or "aa" in name:
        return "aadvantage platinum select"
    return name.strip()

if "best_card" in df.columns and "card_used" in df.columns:
    df["optimal_used"] = df.apply(
        lambda x: normalize_card(x["card_used"]) == normalize_card(x["best_card"]),
        axis=1
    )
else:
    df["optimal_used"] = False

# ==========================================================
# FILTERS
# ==========================================================
# Category filter
categories = sorted(df["category"].dropna().unique())
selected_categories = st.sidebar.multiselect(
    "📂 Filter by Category",
    options=categories,
    default=categories,
)
if selected_categories:
    df = df[df["category"].isin(selected_categories)]

# Date filter (default = last 3 months)
if "date" in df.columns and not df.empty:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    st.sidebar.markdown("### 📅 Filter by Date")

    default_end = max_date
    default_start = max(min_date, default_end - timedelta(days=90))

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

    if isinstance(start_date, (list, tuple)):
        start_date, end_date = start_date

    df = df[
        (df["date"].dt.date >= start_date)
        & (df["date"].dt.date <= end_date)
    ]

# Credit card filter
if "card_used" in df.columns:
    cards = sorted(df["card_used"].dropna().unique())
    selected_cards = st.sidebar.multiselect("💳 Filter by Card Used", cards, default=cards)
    df = df[df["card_used"].isin(selected_cards)]

# Last updated
st.sidebar.markdown("---")
if os.path.exists(REVIEW_PATH):
    last_updated = datetime.fromtimestamp(os.path.getmtime(REVIEW_PATH)).strftime("%b %d, %Y %I:%M %p")
    st.sidebar.markdown(f"**Last Updated:** 🕒 {last_updated}")
else:
    st.sidebar.markdown("No file yet.")

# ==========================================================
# MAIN DASHBOARD
# ==========================================================
st.title("💳 PointsPilot Dashboard")
st.markdown("Visualize your reward earnings, missed points, and optimization opportunities.")

if df.empty:
    st.warning("No transactions found for the selected filters.")
    st.stop()

# ==========================================================
# KPI SECTION
# ==========================================================
st.subheader("📈 Points Overview")

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
# TRANSACTION TABLE + FILTER
# ==========================================================
st.subheader("💸 Transaction Details")

# ✅ Only one inline filter (checkbox)
show_only_missed = st.checkbox("Show only transactions that didn’t use the best card", value=False)

filtered_df = df.copy()
if show_only_missed:
    filtered_df = filtered_df[filtered_df["optimal_used"] == False]

df["date"] = pd.to_datetime(df["date"], errors="coerce")
filtered_df["date_formatted"] = filtered_df["date"].dt.strftime("%b %d, %Y")

if filtered_df.empty:
    st.warning("No transactions match the selected filters.")
else:
    display_cols = [
        "date_formatted", "name", "amount", "category", "card_used",
        "points_earned", "best_card", "optimal_points", "missed_points"
    ]
    display_df = filtered_df[display_cols].copy()
    display_df.rename(columns={"date_formatted": "Date"}, inplace=True)
    display_df["Used Best Card?"] = filtered_df["optimal_used"].apply(lambda x: "✅" if x else "❌")
    display_df["Amount ($)"] = display_df["amount"]
    display_df.drop(columns=["amount"], inplace=True)

    styled_df = (
        display_df.style
        .format({
            "Amount ($)": "${:,.2f}",
            "points_earned": "{:,.0f}",
            "optimal_points": "{:,.0f}",
            "missed_points": "{:,.0f}"
        })
        .map(
            lambda v: "color: green;" if v == "✅" else ("color: red;" if v == "❌" else None),
            subset=["Used Best Card?"]
        )
    )

    st.dataframe(styled_df, height=600, width="stretch")

st.markdown("---")
st.info("💡 Tip: Use the checkbox above to quickly find missed optimization opportunities.")