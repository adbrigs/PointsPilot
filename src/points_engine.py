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
        "freedom flex": "chase freedom flex",
        "sapphire preferred": "chase sapphire preferred",
        "aadvantage": "citi american airlines aadvantage platinum select",
        "citi aadvantage": "citi american airlines aadvantage platinum select",
        "citi aa": "citi american airlines aadvantage platinum select",
        "citi aadvantage platinum": "citi american airlines aadvantage platinum select",
    }
    for key, canonical in aliases.items():
        if key in name:
            return canonical
    return name

# --------------------------------------------------
# Normalize category names (Plaid → YAML)
# --------------------------------------------------
def normalize_category_name(cat: str) -> str:
    if not isinstance(cat, str):
        return "Other"
    cat = cat.strip().lower()

    mapping = {
        # Core Plaid categories
        "food_and_drink": "Restaurants",
        "food_and_drink_fast_food": "Restaurants",
        "food_and_drink_restaurant": "Restaurants",
        "general_merchandise": "Shopping",
        "general_merchandise_sporting_goods": "Shopping",
        "general_merchandise_clothing": "Shopping",
        "travel": "Travel",
        "travel_air": "Travel",
        "travel_car_rental": "Travel",
        "travel_lodging": "Travel",
        "entertainment": "Entertainment",
        "recreation": "Entertainment",
        "gas": "Gas",
        "automotive_fuel": "Gas",
        "drugstores": "Drugstores",
        "pharmacy": "Drugstores",
        "healthcare": "Drugstores",
        "other": "Other",
        "none": "Other",
        "service": "Other",
    }

    # Fallback: capitalize first letter for YAML readability
    return mapping.get(cat, cat.replace("_", " ").title())

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

    # Load earning rules (flattened YAML → DataFrame)
    rules_df = load_rules()

    # Compute points + best card logic
    df["points_earned"] = 0.0
    df["best_card"] = None
    df["best_rate"] = 0.0

    for i, row in df.iterrows():
        cat = normalize_category_name(str(row["category"]))
        amt = row["amount"]

        # Find rate for card used
        used_rate = rules_df[
            (rules_df["card_name"].apply(normalize_card_name)
             == normalize_card_name(row["card_used"]))
            & (rules_df["category"].str.lower() == cat.lower())
        ]["multiplier"].max() if not rules_df.empty else 0

        # Best available card for category
        best = rules_df[rules_df["category"].str.lower() == cat.lower()]
        if not best.empty:
            best_row = best.loc[best["multiplier"].idxmax()]
            df.at[i, "best_card"] = best_row["card_name"]
            df.at[i, "best_rate"] = best_row["multiplier"]

        df.at[i, "points_earned"] = amt * (used_rate if pd.notna(used_rate) else 0)

    # Normalize and flag if optimal card used
    df["optimal_used"] = df.apply(
        lambda x: normalize_card_name(x["card_used"]) == normalize_card_name(x["best_card"]),
        axis=1
    )

    # Compute optimal and missed points
    df["optimal_points"] = (df["amount"] * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).round(2)
    df.loc[df["missed_points"] < 0, "missed_points"] = 0

    # Save enriched CSV
    df.to_csv(output_path, index=False)
    print(f"✅ Saved {len(df)} transactions with points → {output_path}")

    return df

# --------------------------------------------------
# Helper: Best Card per Category
# --------------------------------------------------

def best_card_per_category(reward_rules_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns the single best card for each category based purely on earn_rules.yaml.
    reward_rules_df columns: ['card_name', 'category', 'multiplier']
    """
    if reward_rules_df.empty:
        return pd.DataFrame(columns=["category", "card_name", "multiplier"])

    # pick the highest multiplier per category
    best_cards = (
        reward_rules_df.loc[reward_rules_df.groupby("category")["multiplier"].idxmax()]
        .reset_index(drop=True)
        .sort_values("category")
    )

    # optional: hide meta buckets from the snapshot
    hide = {"All", "None"}
    best_cards = best_cards[~best_cards["category"].isin(hide)]

    return best_cards[["category", "card_name", "multiplier"]]

# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    compute_points()