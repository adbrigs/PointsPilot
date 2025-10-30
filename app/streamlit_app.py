"""
PointsPilot Dashboard (Auto-Refresh + Overrides)
-------------------------------------------------
✅ Removes manual "Recalculate Points" button
✅ Auto-runs points_engine.compute_points() on load
✅ Displays correct override and best_rate columns
✅ Always up-to-date with latest raw_transactions.csv
✅ Now uses tabs for Transactions & Card Summary
"""

import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date

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

if "date" in df.columns and not df.empty:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    valid_dates = df["date"].dropna()
    if not valid_dates.empty:
        data_min = valid_dates.min().date()
        data_max = valid_dates.max().date()
        today = date.today()

        st.sidebar.markdown("### 📅 Filter by Date")
        default_end = today
        default_start = max(data_min, today - timedelta(days=7))

        start_end = st.sidebar.date_input(
            "Select date range:",
            [default_start, default_end],
            min_value=data_min,
            max_value=today
        )
        if isinstance(start_end, (list, tuple)) and len(start_end) == 2:
            start_date, end_date = start_end
        else:
            start_date, end_date = default_start, default_end
        if start_date > end_date:
            start_date, end_date = end_date, end_date

        clamp_end = min(end_date, data_max)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(clamp_end) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]

# Category filter
categories = sorted(df.get("CC_Category", df.get("category", pd.Series([]))).dropna().unique())
selected_categories = st.sidebar.multiselect("📂 Filter by Category", categories, default=categories)
if selected_categories:
    df = df[df["CC_Category"].isin(selected_categories)]

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
# MAIN DASHBOARD - TABS
# ==========================================================
st.title("💳 PointsPilot Dashboard")
st.markdown("Visualize your reward earnings, overrides, and optimization opportunities.")

if df.empty:
    st.warning("No transactions found for the selected filters.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📊 Transactions", "💳 Card Summary","🧰 Tools"])

# ==========================================================
# TAB 1 → TRANSACTIONS
# ==========================================================
with tab1:
    # ==========================================================
    # 📈 KPI SECTION
    # ==========================================================
    st.subheader("📈 Points Overview")

    total_spent = df["amount"].sum()
    total_points_earned = df["points_earned"].sum()
    total_optimal_points = df["optimal_points"].sum()
    missed_points = total_optimal_points - total_points_earned
    optimization_rate = (total_points_earned / total_optimal_points * 100) if total_optimal_points > 0 else 0
    points_per_dollar = (total_points_earned / total_spent) if total_spent > 0 else 0
    optimal_points_per_dollar = (total_optimal_points / total_spent) if total_spent > 0 else 0

    if "used_best_card" in df.columns and len(df) > 0:
        optimized_tx = df["used_best_card"].sum()
        total_tx = len(df)
        transactions_optimized_rate = (optimized_tx / total_tx * 100)
    else:
        transactions_optimized_rate = 0

    # ======================
    # Row 1 → Spend & Points Metrics
    # ======================
    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("💵 Total Spend", f"${total_spent:,.0f}")
    row1_col2.metric("✅ Points Earned", f"{int(total_points_earned):,}")
    row1_col3.metric("🌟 Optimal Points", f"{int(total_optimal_points):,}")
    row1_col4.metric("⚠️ Points Missed", f"{int(missed_points):,}")

    # ======================
    # Row 2 → Efficiency Metrics
    # ======================
    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
    row2_col1.metric("% Points Optimized", f"{optimization_rate:.1f}%")
    row2_col2.metric("💳 % Transactions Optimized", f"{transactions_optimized_rate:.1f}%")
    row2_col3.metric("💸 Points per $", f"{points_per_dollar:.2f}")
    row2_col4.metric("🚀 Optimal Points per $", f"{optimal_points_per_dollar:.2f}")

    # ==========================================================
    # 💡 INSIGHTS SECTION (Collapsible)
    # ==========================================================
    with st.expander("💡 Points Insights", expanded=True):
        insights = []

        # Insight 1: Overall optimization rate
        if optimization_rate < 90:
            insights.append(
                f"⚠️ You're optimizing **{optimization_rate:.1f}%** of your total possible points — review recent missed transactions to capture more value."
            )
        else:
            insights.append(f"✅ Excellent! You’re optimizing **{optimization_rate:.1f}%** of your available points.")

        # Insight 2: Top missed card
        if "card_mapped" in df.columns and "missed_points" in df.columns:
            top_card = (
                df.groupby("card_mapped")["missed_points"].sum().sort_values(ascending=False).head(1)
            )
            if not top_card.empty and top_card.iloc[0] > 0:
                insights.append(
                    f"💳 You’ve missed the most points on **{top_card.index[0]}** — review your recent usage."
                )

        # Insight 3: Top missed category
        if "CC_Category" in df.columns and "missed_points" in df.columns:
            top_cat = (
                df.groupby("CC_Category")["missed_points"].sum().sort_values(ascending=False).head(1)
            )
            if not top_cat.empty and top_cat.iloc[0] > 0:
                insights.append(
                    f"📂 Your most missed category is **{top_cat.index[0]}**, with {int(top_cat.iloc[0]):,} points left on the table."
                )

        # Insight 4: Suggest overall improvement strategy
        if optimization_rate < 80:
            insights.append("🚀 Focus on aligning your card choice by category — e.g., use CSP for travel and dining, CFF for drugstores.")
        elif 80 <= optimization_rate < 95:
            insights.append("🔍 You’re close to max efficiency — check overrides and recurring bills for hidden opportunities.")
        else:
            insights.append("🌟 Stellar optimization — keep using your current strategy!")

        # Insight 5: Top single missed transaction
        if "missed_points" in df.columns and "name" in df.columns:
            missed_tx = (
                df[df["missed_points"] > 0]
                .sort_values("missed_points", ascending=False)
                .head(1)
            )
            if not missed_tx.empty:
                top_tx = missed_tx.iloc[0]
                merchant = str(top_tx.get("name", "Unknown Merchant"))
                missed_val = int(top_tx.get("missed_points", 0))
                best_card = top_tx.get("best_cards", "N/A")
                insights.append(
                    f"🔥 Your #1 missed points opportunity was **{merchant}**, where you left **{missed_val:,} points** on the table. "
                    f"Next time, use **{best_card}**."
                )

        # Display Insights
        for insight in insights:
            st.markdown(f"- {insight}")

    st.markdown("---")

    # ==========================================================
    # 💸 TRANSACTION DETAILS
    # ==========================================================
    st.subheader("💸 Transaction Details")

    show_only_missed = st.checkbox("Check to show only missed transactions", value=False)
    search_query = st.text_input("🔍 Search transactions", placeholder="Type a merchant or keyword...")

    filtered_df = df.copy().drop_duplicates(subset=["name", "amount", "date"], keep="first")

    if search_query:
        mask = (
            filtered_df["name"].astype(str).str.contains(search_query, case=False, na=False)
            | filtered_df["CC_Category"].astype(str).str.contains(search_query, case=False, na=False)
            | filtered_df["card_mapped"].astype(str).str.contains(search_query, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    if show_only_missed:
        filtered_df = filtered_df[filtered_df["used_best_card"] == False]

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    filtered_df["date_formatted"] = filtered_df["date"].dt.strftime("%b %d, %Y")

    if filtered_df.empty:
        st.warning("No transactions match the selected filters.")
        st.stop()

    card_abbrev = {
        "Chase Sapphire Preferred": "CSP",
        "Chase Freedom Unlimited": "CFU",
        "Chase Freedom Flex": "CFF",
        "Citi AAdvantage Platinum Select": "AAdv",
    }

    display_cols = [
        "date_formatted", "name", "amount", "CC_Category", "used_best_card",
        "card_mapped", "best_cards", "best_rate", "used_rate",
        "points_earned", "optimal_points", "missed_points"
    ]
    display_df = filtered_df[display_cols].copy()

    display_df.rename(columns={
        "date_formatted": "Date",
        "name": "Merchant",
        "amount": "Amount ($)",
        "CC_Category": "CC Category",
        "used_best_card": "Used Best Card?",
        "card_mapped": "Card Used",
        "best_cards": "Best Card(s)",
        "used_rate": "Used Rate",
        "best_rate": "Best Rate",
        "points_earned": "Points Earned",
        "optimal_points": "Optimal Points",
        "missed_points": "Missed Points"
    }, inplace=True)

    display_df["Card Used"] = display_df["Card Used"].replace(card_abbrev)
    display_df["Best Card(s)"] = display_df["Best Card(s)"].replace(card_abbrev, regex=True)
    display_df["Used Best Card?"] = display_df["Used Best Card?"].apply(lambda x: "✅" if x else "❌")

    if "override_applied" in filtered_df.columns:
        display_df["⚡"] = filtered_df["override_applied"].apply(lambda x: "⚡" if x else "")

    styled_df = (
        display_df.style
        .format({
            "Amount ($)": "${:,.2f}",
            "Used Rate": "{:,.1f}×",
            "Best Rate": "{:,.1f}×",
            "Points Earned": "{:,.0f}",
            "Optimal Points": "{:,.0f}",
            "Missed Points": "{:,.0f}",
        })
        .map(lambda v: "color: green;" if v == "✅" else ("color: red;" if v == "❌" else None),
             subset=["Used Best Card?"])
    )

    num_rows = len(display_df)
    if num_rows <= 20:
        st.dataframe(styled_df, use_container_width=True, height="auto")
    else:
        est_row_height = 35
        max_height = 800
        table_height = min(max_height, int(num_rows * est_row_height + 80))
        st.dataframe(styled_df, use_container_width=True, height=table_height)


    st.markdown("---")
    st.info("💡 Use the search bar to find merchants quickly. ⚡ indicates a transaction that had an override rule applied.")

# ==========================================================
# TAB 2 → CARD SUMMARY
# ==========================================================
with tab2:
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

        num_rows_summary = len(summary)
        if num_rows_summary <= 8:
            st.dataframe(
                summary.style.format({
                    "# of Transactions": "{:,.0f}",
                    "Total Spend ($)": "${:,.0f}",
                    "Points Earned": "{:,.0f}",
                    "Missed Points": "{:,.0f}",
                    "% Missed": "{:,.1f}%"
                }),
                use_container_width=True,
                height="auto"
            )
        else:
            est_row_height = 38
            max_height = 500
            table_height = min(max_height, int(num_rows_summary * est_row_height + 80))
            st.dataframe(
                summary.style.format({
                    "# of Transactions": "{:,.0f}",
                    "Total Spend ($)": "${:,.0f}",
                    "Points Earned": "{:,.0f}",
                    "Missed Points": "{:,.0f}",
                    "% Missed": "{:,.1f}%"
                }),
                use_container_width=True,
                height=table_height
            )
    else:
        st.info("No missed points data available for summary.")

    # ==========================================================
# TAB 3 → TOOLS
# ==========================================================
with tab3:
    st.markdown("### 🧭 Best Card Finder")
    st.write("Select a spend category below to instantly see which card earns you the most points.")

    # --- Define categories from your YAML or hardcoded fallback ---
    categories = [
        "Dining", "Travel", "Groceries", "Gas", "Drugstores",
        "Streaming", "Transit", "Other"
    ]

    selected_category = st.selectbox("📂 Choose a category:", categories)

    # --- Reference your known reward rates ---
    best_card_rules = {
        "Dining": {"card": "Chase Sapphire Preferred", "multiplier": 3},
        "Travel": {"card": "Chase Sapphire Preferred", "multiplier": 2},
        "Groceries": {"card": "Chase Freedom Unlimited", "multiplier": 1.5},
        "Gas": {"card": "Citi AAdvantage Platinum Select", "multiplier": 2},
        "Drugstores": {"card": "Chase Freedom Flex", "multiplier": 3},
        "Streaming": {"card": "Chase Sapphire Preferred", "multiplier": 3},
        "Transit": {"card": "Chase Sapphire Preferred", "multiplier": 2},
        "Other": {"card": "Chase Freedom Unlimited", "multiplier": 1.5},
    }

    best_info = best_card_rules.get(selected_category, {"card": "Unknown", "multiplier": 1})
    best_card = best_info["card"]
    best_rate = best_info["multiplier"]

    # --- Display results dynamically ---
    st.markdown(f"""
    ### 💳 Best Card for *{selected_category}*:
    **{best_card}** — earns **{best_rate}× points per $1**

    💡 *Tip:* Use this card whenever you spend in the **{selected_category}** category to maximize your points.
    """)

    st.markdown("---")