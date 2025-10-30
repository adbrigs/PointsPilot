"""
PointsPilot Dashboard (Auto-Refresh + Overrides)
-------------------------------------------------
✅ Removes manual "Recalculate Points" button
✅ Auto-runs points_engine.compute_points() on load
✅ Displays correct override and best_rate columns
✅ Always up-to-date with latest raw_transactions.csv
"""

import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# ==========================================================
# PATH FIX
# ==========================================================
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from points_engine import compute_points  # import after path setup

# ==========================================================
# PATHS
# ==========================================================
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_PATH = os.path.join(DATA_DIR, "raw_transactions.csv")
REVIEW_PATH = os.path.join(DATA_DIR, "transactions_review.csv")

# ==========================================================
# STREAMLIT CONFIG
# ==========================================================
st.set_page_config(page_title="PointsPilot Dashboard", layout="wide", page_icon="✈️")

# ==========================================================
# AUTO-REFRESH DATA
# ==========================================================
if not os.path.exists(REVIEW_PATH):
    st.info("⚙️ Generating transactions_review.csv from raw data...")
    compute_points()
else:
    # If the raw file is newer, re-compute automatically
    if os.path.getmtime(RAW_PATH) > os.path.getmtime(REVIEW_PATH):
        st.info("🔄 Detected updated raw_transactions.csv — refreshing data...")
        compute_points()

df = pd.read_csv(REVIEW_PATH)
print("Updated Data via Points Engine")

# ==========================================================
# CLEANUP
# ==========================================================
if "used_best_card" in df.columns:
    df["used_best_card"] = df["used_best_card"].astype(str).str.lower().isin(["true", "1", "yes"])
else:
    df["used_best_card"] = False

# ==========================================================
# SIDEBAR FILTERS
# ==========================================================
st.sidebar.title("✈️ PointsPilot")
st.sidebar.markdown("**Optimize your cards and maximize every purchase.**")

# Category filter
categories = sorted(df.get("CC_Category", df.get("category", pd.Series([]))).dropna().unique())
selected_categories = st.sidebar.multiselect("📂 Filter by Category", categories, default=categories)
if selected_categories:
    df = df[df["CC_Category"].isin(selected_categories)]

# =========================
# Robust Date Range Filter
# =========================
from datetime import date

if "date" in df.columns and not df.empty:
    # Normalize to datetime (naive)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    valid_dates = df["date"].dropna()

    # If there are no valid dates, just skip date filtering
    if valid_dates.empty:
        st.sidebar.markdown("### 📅 Filter by Date")
    else:
        data_min = valid_dates.min().date()
        data_max = valid_dates.max().date()
        today = date.today()

        st.sidebar.markdown("### 📅 Filter by Date")

        # Defaults: last 7 days ending today (even if data_max < today)
        default_end = today
        default_start = max(data_min, today - timedelta(days=7))

        # Allow selecting through today (even if no data that day)
        start_end = st.sidebar.date_input(
            "Select date range:",
            [default_start, default_end],
            min_value=data_min,               # earliest the dataset goes
            max_value=today                   # UI can pick up to today
        )

        # Normalize return
        if isinstance(start_end, (list, tuple)) and len(start_end) == 2:
            start_date, end_date = start_end
        else:
            start_date, end_date = default_start, default_end

        # If user inverted, fix it
        if start_date > end_date:
            start_date, end_date = end_date, end_date

        # Clamp the filter upper bound to the data's max date,
        # but keep UI selection as-is.
        clamp_end = min(end_date, data_max)

        # Build inclusive bounds: [start_date, clamp_end]
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(clamp_end) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

        df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]

# Card filter
if "card_mapped" in df.columns:
    cards = sorted(df["card_mapped"].dropna().unique())
    selected_cards = st.sidebar.multiselect("💳 Filter by Card Used", cards, default=cards)
    df = df[df["card_mapped"].isin(selected_cards)]

# Last updated
if os.path.exists(REVIEW_PATH):
    last_updated = datetime.fromtimestamp(os.path.getmtime(REVIEW_PATH)).strftime("%b %d, %Y %I:%M %p")
    st.sidebar.markdown(f"---\n**Last Updated:** 🕒 {last_updated}")
else:
    st.sidebar.markdown("---\nNo file yet.")

# ==========================================================
# MAIN DASHBOARD
# ==========================================================
st.title("💳 PointsPilot Dashboard")
st.markdown("Visualize your reward earnings, overrides, and optimization opportunities.")

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
missed_points = total_optimal_points - total_points_earned
optimization_rate = (total_points_earned / total_optimal_points * 100) if total_optimal_points > 0 else 0
points_per_dollar = (total_points_earned / total_spent) if total_spent > 0 else 0
optimal_points_per_dollar = (total_optimal_points / total_spent) if total_spent > 0 else 0

# 🧮 Calculate Transactions Optimized %
if "used_best_card" in df.columns and len(df) > 0:
    optimized_tx = df["used_best_card"].sum()
    total_tx = len(df)
    transactions_optimized_rate = (optimized_tx / total_tx * 100)
else:
    transactions_optimized_rate = 0

# ======================
# Row 1 → Points Metrics
# ======================
row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
row1_col1.metric("✅ Points Earned", f"{int(total_points_earned):,}")
row1_col2.metric("🌟 Optimal Points", f"{int(total_optimal_points):,}")
row1_col3.metric("⚠️ Points Missed", f"{int(missed_points):,}")
row1_col4.metric("% Points Optimized", f"{optimization_rate:.1f}%")

# ======================
# Row 2 → Efficiency Metrics
# ======================
row2_col1, row2_col2, row2_col3 = st.columns(3)
row2_col1.metric("💳 % Transactions Optimized", f"{transactions_optimized_rate:.1f}%")
row2_col2.metric("💸 Points per $", f"{points_per_dollar:.2f}")
row2_col3.metric("🚀 Optimal Points per $", f"{optimal_points_per_dollar:.2f}")

# ==========================================================
# TRANSACTION TABLE + FILTER
# ==========================================================
st.subheader("💸 Transaction Details")

# --- Filters ---
show_only_missed = st.checkbox("⚠️ Show only transactions that didn’t use the best card", value=False)

# --- Search bar below it ---
search_query = st.text_input("🔍 Search transactions", placeholder="Type a merchant or keyword...")

# --- Filter logic ---
filtered_df = df.copy()

# Filter by search
if search_query:
    mask = (
        filtered_df["name"].astype(str).str.contains(search_query, case=False, na=False)
        | filtered_df["CC_Category"].astype(str).str.contains(search_query, case=False, na=False)
        | filtered_df["card_mapped"].astype(str).str.contains(search_query, case=False, na=False)
    )
    filtered_df = filtered_df[mask]

# Filter by missed optimization
if show_only_missed:
    filtered_df = filtered_df[filtered_df["used_best_card"] == False]

df["date"] = pd.to_datetime(df["date"], errors="coerce")
filtered_df["date_formatted"] = filtered_df["date"].dt.strftime("%b %d, %Y")

if filtered_df.empty:
    st.warning("No transactions match the selected filters.")
else:
    display_cols = [
        "date_formatted", "name", "amount", "CC_Category", "card_mapped",
        "points_earned", "best_cards", "best_rate", "optimal_points", "missed_points"
    ]
    display_df = filtered_df[display_cols].copy()
    display_df.rename(columns={
        "date_formatted": "Date",
        "name": "Merchant",
        "amount": "Amount ($)",
        "CC_Category": "CC Category",
        "card_mapped": "Card Used",
        "best_cards": "Best Card(s)",
        "best_rate": "Best Rate"
    }, inplace=True)

    # --- Override icon with tooltip ---
    if "override_applied" in filtered_df.columns:
        display_df["Override?"] = filtered_df.apply(
            lambda x: "⚡" if x.get("override_applied") else "",
            axis=1
        )
        override_tooltips = filtered_df["override_reason"].fillna("")

    # --- Best card indicator ---
    display_df["Used Best Card?"] = filtered_df["used_best_card"].apply(lambda x: "✅" if x else "❌")

    # --- Style & tooltip integration (cleaned for Streamlit) ---
if "Override?" in display_df.columns:
    # Create custom hover tooltip rendering using markdown instead of HTML spans
    tooltip_col = "Override?"
    display_df[tooltip_col] = display_df[tooltip_col].where(display_df[tooltip_col] != "", None)

    def render_tooltip(val, reason):
        if pd.notna(val):
            return f"⚡ ({reason})" if reason else "⚡"
        return ""

    display_df["Override?"] = [
        render_tooltip(val, reason)
        for val, reason in zip(display_df["Override?"], filtered_df.get("override_reason", ""))
    ]

# --- Format and render safely ---
st.dataframe(
    display_df.style.format({
        "Amount ($)": "${:,.2f}",
        "points_earned": "{:,.0f}",
        "optimal_points": "{:,.0f}",
        "missed_points": "{:,.0f}",
        "Best Rate": "{:,.1f}×"
    }),
    height=600,
    width=1200
)

st.markdown("---")
st.info("💡 Use the search bar to quickly find merchants, or hover ⚡ to see which rule triggered an override.")

# ==========================================================
# SUMMARY TABLE
# ==========================================================
st.markdown("### 💳 Missed Points by Card Used")

if "card_mapped" in df.columns and "missed_points" in df.columns:
    summary = (
        df.groupby("card_mapped", as_index=False)
        .agg(
            Transactions=("amount", "count"),
            Total_Spend=("amount", "sum"),
            Points_Earned=("points_earned", "sum"),
            Missed_Points=("missed_points", "sum")
        )
        .sort_values("Missed_Points", ascending=False)
    )
    summary["% Missed"] = (
        (summary["Missed_Points"] / (summary["Points_Earned"] + summary["Missed_Points"])) * 100
    ).fillna(0).round(1)

    summary.rename(columns={
        "card_mapped": "Card Used",
        "Transactions": "# of Transactions",
        "Total_Spend": "Total Spend ($)",
        "Points_Earned": "Points Earned",
        "Missed_Points": "Missed Points",
        "% Missed": "% Missed"
    }, inplace=True)

    st.dataframe(
        summary.style.format({
            "# of Transactions": "{:,.0f}",
            "Total Spend ($)": "${:,.0f}",
            "Points Earned": "{:,.0f}",
            "Missed Points": "{:,.0f}",
            "% Missed": "{:,.1f}%"
        }),
        height=280
    )
else:
    st.info("No missed points data available for summary.")