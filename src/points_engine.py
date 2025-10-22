"""
PointsPilot - Points Engine
---------------------------
Loads Plaid transaction data, applies earning rules from YAML,
and saves an enriched CSV (transactions_with_points.csv)
for the Streamlit dashboard.
"""

import os
import pandas as pd
import yaml


# --------------------------------------------------
# Load earning rules (YAML)
# --------------------------------------------------
def load_rules():
    """
    Loads YAML reward rules and flattens into a DataFrame
    with columns: [card_name, category, multiplier].
    """
    yaml_path = os.path.join(os.path.dirname(__file__), "earn_rules.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"earn_rules.yaml not found at {yaml_path}")

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    # Flatten structure
    records = []
    for card in data.get("cards", []):
        card_name = card.get("card_name")
        for category, multiplier in card.get("rewards", {}).items():
            records.append({
                "card_name": card_name,
                "category": category,
                "multiplier": multiplier
            })

    return pd.DataFrame(records)


# --------------------------------------------------
# Normalize card names for comparison
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
# Normalize category names (Plaid → YAML)
# --------------------------------------------------
def normalize_category_name(cat: str) -> str:
    if not isinstance(cat, str):
        return "Other"
    cat = cat.strip().lower()

    mapping = {
        # 🥗 Food & Drink
        "food_and_drink": "Restaurants",
        "food_and_drink_fast_food": "Restaurants",
        "food_and_drink_restaurant": "Restaurants",
        "food_and_drink_coffee_shop": "Restaurants",
        "food_and_drink_bar": "Restaurants",

        # 🛍️ Shopping / Retail
        "general_merchandise": "Shopping",
        "general_merchandise_sporting_goods": "Shopping",
        "general_merchandise_clothing": "Shopping",
        "general_merchandise_home_improvement": "Shopping",
        "general_merchandise_online": "Shopping",
        "general_merchandise_other": "Shopping",

        # ✈️ Travel
        "travel": "Travel",
        "travel_air": "Travel",
        "travel_car_rental": "Travel",
        "travel_lodging": "Travel",
        "travel_cruise": "Travel",
        "travel_other": "Travel",

        # 🎭 Entertainment & Recreation
        "entertainment": "Entertainment",
        "recreation": "Entertainment",
        "arts_and_entertainment": "Entertainment",
        "movies_and_music": "Entertainment",

        # ⛽ Gas / Auto
        "gas": "Gas",
        "automotive_fuel": "Gas",
        "auto": "Gas",
        "auto_transportation": "Gas",

        # 💊 Drugstores / Health
        "drugstores": "Drugstores",
        "pharmacy": "Drugstores",
        "healthcare": "Drugstores",
        "medical_services": "Drugstores",

        # 🧖 Personal Care / General Services → fallback "Other"
        "personal_care": "Other",
        "personal_care_hair_salon": "Other",
        "personal_care_spa": "Other",
        "general_services": "Other",
        "general_services_other": "Other",
        "service": "Other",
        "service_financial": "Other",

        # 💼 Business / Government / Uncategorized
        "government": "Other",
        "bank_fees": "Other",
        "loans": "Other",
        "income": "Other",
        "none": "Other",
        "other": "Other",
    }

    return mapping.get(cat, cat.replace("_", " ").title())


# --------------------------------------------------
# Simple fallback rate logic per card
# --------------------------------------------------
def get_card_rate(card_norm: str, cat_norm: str, rules_df: pd.DataFrame) -> float:
    """
    Returns the multiplier for a given card/category, with simple fallbacks:
    - Exact category match → use YAML value
    - Otherwise:
        Freedom Unlimited → 1.5×
        Sapphire Preferred / Flex / AAdvantage → 1×
    """
    # Try exact match first
    match = rules_df[
        (rules_df["card_name"].apply(normalize_card_name) == card_norm)
        & (rules_df["category"].str.lower() == cat_norm.lower())
    ]
    if not match.empty:
        return float(match["multiplier"].max())

    # Simple fallback defaults
    if "freedom unlimited" in card_norm:
        return 1.5
    if any(x in card_norm for x in ["sapphire preferred", "freedom flex", "aadvantage"]):
        return 1.0

    return 1.0


# --------------------------------------------------
# Compute points from transactions and save CSV
# --------------------------------------------------
def compute_points(transactions_path: str = None):
    base_path = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base_path, "data")
    os.makedirs(data_dir, exist_ok=True)

    transactions_path = transactions_path or os.path.join(data_dir, "transactions.csv")
    output_path = os.path.join(data_dir, "transactions_with_points.csv")

    # Load transactions
    if not os.path.exists(transactions_path):
        raise FileNotFoundError(f"Transactions file not found: {transactions_path}")

    df = pd.read_csv(transactions_path)
    required_cols = ["date", "merchant", "amount", "category", "card_used"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing column '{col}' in transactions.csv")

    # Load YAML reward rules
    rules_df = load_rules()

    # Compute
    df["points_earned"] = 0.0
    df["best_card"] = None
    df["best_rate"] = 0.0

    for i, row in df.iterrows():
        cat = normalize_category_name(str(row["category"]))
        amt = row["amount"]
        card_norm = normalize_card_name(row["card_used"])

        # Use fallback-aware rate
        used_rate = get_card_rate(card_norm, cat, rules_df)

        # Find best card for that category
        best = rules_df[rules_df["category"].str.lower() == cat.lower()]
        if not best.empty:
            best_row = best.loc[best["multiplier"].idxmax()]
            df.at[i, "best_card"] = best_row["card_name"]
            df.at[i, "best_rate"] = best_row["multiplier"]
        else:
            # If no category found, default to highest base rate card
            df.at[i, "best_card"] = "Chase Freedom Unlimited"
            df.at[i, "best_rate"] = 1.5

        df.at[i, "points_earned"] = amt * used_rate

    # Optimal card check
    df["optimal_used"] = df.apply(
        lambda x: normalize_card_name(x["card_used"]) == normalize_card_name(x["best_card"]),
        axis=1
    )

    # Optimal + missed
    df["optimal_points"] = (df["amount"] * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).round(2)
    df.loc[df["missed_points"] < 0, "missed_points"] = 0

    # Save enriched CSV
    df.to_csv(output_path, index=False)
    print(f"✅ Saved {len(df)} transactions with points → {output_path}")

    return df


# --------------------------------------------------
# Best Card per Category
# --------------------------------------------------
def best_card_per_category(reward_rules_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns the single best card for each category based purely on earn_rules.yaml.
    reward_rules_df columns: ['card_name', 'category', 'multiplier']
    """
    if reward_rules_df.empty:
        return pd.DataFrame(columns=["category", "card_name", "multiplier"])

    best_cards = (
        reward_rules_df.loc[reward_rules_df.groupby("category")["multiplier"].idxmax()]
        .reset_index(drop=True)
        .sort_values("category")
    )

    hide = {"All", "None"}
    best_cards = best_cards[~best_cards["category"].isin(hide)]
    return best_cards[["category", "card_name", "multiplier"]]


# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    compute_points()