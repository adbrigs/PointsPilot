"""
PointsPilot - Points Engine (Local CSV Mode)
--------------------------------------------
Uses local data/copilot_transactions.csv as input,
filters for credit-card transactions only,
applies earning rules from YAML, and saves an enriched
transactions_with_points.csv for the Streamlit dashboard.
"""

import os
import pandas as pd
import yaml


# --------------------------------------------------
# Load earning rules (YAML)
# --------------------------------------------------
def load_rules():
    yaml_path = os.path.join(os.path.dirname(__file__), "earn_rules.yaml")
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"earn_rules.yaml not found at {yaml_path}")

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    records = []
    for card in data.get("cards", []):
        card_name = card.get("card_name")
        for category, multiplier in card.get("rewards", {}).items():
            records.append(
                {"card_name": card_name, "category": category, "multiplier": multiplier}
            )
    return pd.DataFrame(records)


# --------------------------------------------------
# Load merchant-based overrides (from YAML)
# --------------------------------------------------
def load_merchant_overrides():
    yaml_path = os.path.join(os.path.dirname(__file__), "earn_rules.yaml")
    if not os.path.exists(yaml_path):
        return []
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("merchant_overrides", [])


# --------------------------------------------------
# Normalize card names
# --------------------------------------------------
def normalize_card_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    aliases = {
        "freedom unlimited": "chase freedom unlimited",
        "chase freedom unlimited": "chase freedom unlimited",
        "freedom flex": "chase freedom flex",
        "chase freedom flex": "chase freedom flex",
        "sapphire preferred": "chase sapphire preferred",
        "chase sapphire preferred": "chase sapphire preferred",
        "aadvantage": "citi aadvantage platinum select",
        "citi aadvantage": "citi aadvantage platinum select",
        "citi aa": "citi aadvantage platinum select",
        "citi aadvantage platinum": "citi aadvantage platinum select",
        "citi aadvantage platinum select": "citi aadvantage platinum select",
    }
    for key in sorted(aliases, key=len, reverse=True):
        if key in name:
            return aliases[key]
    return name


# --------------------------------------------------
# Normalize category names (Copilot → YAML)
# --------------------------------------------------
def normalize_category_name(cat: str) -> str:
    if not isinstance(cat, str):
        return "Other"
    cat = cat.strip().lower()
    mapping = {
        "bars & nightlife": "Restaurants & Bars",
        "restaurants & bars": "Restaurants & Bars",
        "car/gas": "Car/Gas",
        "groceries": "Groceries",
        "drugstores": "Drugstores",
        "uobers/septa": "Ubers/Septa",
        "ubers/septa": "Ubers/Septa",
        "travel & vacation": "Travel & Vacation",
        "shops": "Shops",
        "clothing": "Clothing",
        "entertainment": "Entertainment",
        "recreation": "Recreation",
        "gifts": "Shopping",
        "subscriptions": "Misc",
        "insurance": "Misc",
        "health care": "Drugstores",
        "home improvement": "Shopping",
        "loans": "Misc",
        "rent/utilities": "Misc",
        "gym": "Recreation",
        "personal care": "Personal Care",
        "misc": "Other",
    }
    return mapping.get(cat, cat.replace("_", " ").title())


# --------------------------------------------------
# Fallback rate logic
# --------------------------------------------------
def get_card_rate(card_norm: str, cat_norm: str, rules_df: pd.DataFrame) -> float:
    match = rules_df[
        (rules_df["card_name"].apply(normalize_card_name) == card_norm)
        & (rules_df["category"].str.lower() == cat_norm.lower())
    ]
    if not match.empty:
        return float(match["multiplier"].max())

    if "freedom unlimited" in card_norm:
        return 1.5
    if any(x in card_norm for x in ["sapphire preferred", "freedom flex", "aadvantage"]):
        return 1.0
    return 1.0


# --------------------------------------------------
# Compute points using local CSV only
# --------------------------------------------------
def compute_points(transactions_path: str = None):
    base_path = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base_path, "data")
    os.makedirs(data_dir, exist_ok=True)

    transactions_path = transactions_path or os.path.join(data_dir, "copilot_transactions.csv")
    output_path = os.path.join(data_dir, "transactions_with_points.csv")

    if not os.path.exists(transactions_path):
        raise FileNotFoundError(f"Transactions file not found: {transactions_path}")

    # --- Load data ---
    df = pd.read_csv(transactions_path)
    df.columns = df.columns.str.strip().str.lower()

    # Map key fields
    df["merchant"] = df.get("name", "")
    df["card_used"] = df.get("account", "")
    df["category"] = df.get("category", "")
    df["amount"] = df.get("amount", 0)
    df["date"] = df.get("date", "")

    # ✅ Filter to recognized cards
    recognized_cards = [
        "Chase Sapphire",
        "Freedom Unlimited",
        "Freedom Flex",
        "Citi®/AAdvantage® Platinum Select® World Elite Mastercard®",
    ]
    df = df[df["card_used"].str.contains("|".join(recognized_cards), case=False, na=False)]
    if df.empty:
        raise ValueError("No recognized credit-card transactions found.")
    print(f"✅ Loaded {len(df)} transactions from recognized credit cards.")

    rules_df = load_rules()
    merchant_overrides = load_merchant_overrides()

    # Predefine columns
    for col in ["best_cards_list", "best_card", "best_rate", "points_earned"]:
        if col not in df.columns:
            df[col] = None

    # ------------------------------------------------------------
    # --- Core computation loop ---------------------------------
    # ------------------------------------------------------------
    for i, row in df.iterrows():
        merchant = str(row.get("merchant", "")).lower()
        cat = normalize_category_name(str(row["category"]))
        amt = float(row["amount"])
        card_norm = normalize_card_name(str(row["card_used"]))

        used_rate = get_card_rate(card_norm, cat, rules_df)
        best_card = None
        best_rate = 0.0
        override_applied = False

        # --- Merchant overrides ---
        for override in merchant_overrides:
            merch_match = override["merchant"].lower() in merchant
            if merch_match:
                best_card = override["card_name"]
                best_rate = override["multiplier"]
                if override["card_name"].lower() in card_norm:
                    used_rate = override["multiplier"]
                    print(f"🎯 Override applied: {merchant} → {override['card_name']} @ {override['multiplier']}×")
                override_applied = True
                break

        # --- Determine best card(s) normally ---
        if not override_applied:
            best = rules_df[rules_df["category"].str.lower() == cat.lower()]
            if not best.empty:
                max_mult = best["multiplier"].max()
                top_cards = best.loc[best["multiplier"] == max_mult, "card_name"].tolist()
                df.at[i, "best_cards_list"] = [normalize_card_name(c) for c in top_cards]
                df.at[i, "best_card"] = ", ".join(top_cards)
                df.at[i, "best_rate"] = max_mult
            else:
                df.at[i, "best_cards_list"] = []
                df.at[i, "best_card"] = "Unmatched"
                df.at[i, "best_rate"] = 1.0
        else:
            df.at[i, "best_card"] = best_card
            df.at[i, "best_rate"] = best_rate

        # --- Points earned ---
        df.at[i, "points_earned"] = round(amt * used_rate, 2)

    # ------------------------------------------------------------
    # --- Optimal card check (multi-card aware) ------------------
    # ------------------------------------------------------------
    def is_optimal(x):
        used = normalize_card_name(x["card_used"])
        best_cards = x.get("best_cards_list", [])
        if isinstance(best_cards, list) and best_cards:
            return used in best_cards
        return normalize_card_name(x["card_used"]) == normalize_card_name(x.get("best_card", ""))

    df["optimal_used"] = df.apply(is_optimal, axis=1)

    # ------------------------------------------------------------
    # --- Points math (safe numeric conversion) ------------------
    # ------------------------------------------------------------
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["best_rate"] = pd.to_numeric(df["best_rate"], errors="coerce").fillna(1.0)
    df["points_earned"] = pd.to_numeric(df["points_earned"], errors="coerce").fillna(0)

    df["optimal_points"] = (df["amount"] * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).round(2)
    df.loc[df["missed_points"] < 0, "missed_points"] = 0

    # Cleanup
    if "best_cards_list" in df.columns:
        df.drop(columns=["best_cards_list"], inplace=True)

    # --- Save ---
    df.to_csv(output_path, index=False)

    # --- Summary ---
    total_points = df["points_earned"].sum()
    total_missed = df["missed_points"].sum()
    opt_rate = round(100 * (1 - (total_missed / (total_points + total_missed + 1e-9))), 2)

    print("\n✅ Points Summary")
    print(f"   • Transactions processed: {len(df)}")
    print(f"   • Total points earned: {total_points:,.0f}")
    print(f"   • Missed points: {total_missed:,.0f}")
    print(f"   • Optimization rate: {opt_rate}%")
    print(f"   → Saved to {output_path}\n")

    return df


# --------------------------------------------------
# Best Card per Category
# --------------------------------------------------
def best_card_per_category(reward_rules_df: pd.DataFrame) -> pd.DataFrame:
    if reward_rules_df.empty:
        return pd.DataFrame(columns=["category", "card_name", "multiplier"])

    best_cards = (
        reward_rules_df.loc[reward_rules_df.groupby("category")["multiplier"].idxmax()]
        .reset_index(drop=True)
        .sort_values("category")
    )
    return best_cards[["category", "card_name", "multiplier"]]


# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    print("📂 Running in Local CSV Mode (Copilot format detected)...")
    compute_points()