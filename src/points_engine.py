"""
PointsPilot - Points Engine
---------------------------
Loads Plaid transaction data, applies earning rules,
and saves an enriched CSV (transactions_with_points.csv)
for the Streamlit dashboard.
"""

import os
import pandas as pd
import yaml


# --------------------------------------------------
# Load earning rules
# --------------------------------------------------
def load_rules():
    base_path = os.path.dirname(os.path.dirname(__file__))
    yaml_path = os.path.join(base_path, "src", "earn_rules.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"earn_rules.yaml not found at {yaml_path}")

    with open(yaml_path, "r") as f:
        rules = yaml.safe_load(f)
    return rules


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
        "aadvantage": "citi american airlines aadvantage",
        "citi aadvantage": "citi american airlines aadvantage",
    }
    for key, canonical in aliases.items():
        if key in name:
            return canonical
    return name


# --------------------------------------------------
# Compute points from transactions and save CSV
# --------------------------------------------------
def compute_points(transactions_path: str = None):
    base_path = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base_path, "data")
    os.makedirs(data_dir, exist_ok=True)

    transactions_path = transactions_path or os.path.join(data_dir, "transactions.csv")
    output_path = os.path.join(data_dir, "transactions_with_points.csv")

    # Load transaction data
    if not os.path.exists(transactions_path):
        raise FileNotFoundError(f"Transactions file not found: {transactions_path}")

    df = pd.read_csv(transactions_path)

    # Ensure column consistency
    required_cols = ["date", "merchant", "amount", "category", "card_used"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing column '{col}' in transactions.csv")

    # Load earning rules
    rules = load_rules()

    # Flatten rules into lookup DataFrame
    rows = []
    for card, categories in rules.items():
        for cat, rate in categories.items():
            rows.append({"card": card, "category": cat, "rate": rate})
    rules_df = pd.DataFrame(rows)

    # Compute points and best card logic
    df["points_earned"] = 0.0
    df["best_card"] = None
    df["best_rate"] = 0.0

    for i, row in df.iterrows():
        cat = str(row["category"]).strip()
        amt = row["amount"]

        # Rate for card used
        used_rate = rules_df[
            (rules_df["card"].apply(normalize_card_name)
             == normalize_card_name(row["card_used"]))
            & (rules_df["category"].str.lower() == cat.lower())
        ]["rate"].max() if not rules_df.empty else 0

        # Best card overall
        best = rules_df[rules_df["category"].str.lower() == cat.lower()]
        if not best.empty:
            best_row = best.loc[best["rate"].idxmax()]
            df.at[i, "best_card"] = best_row["card"]
            df.at[i, "best_rate"] = best_row["rate"]

        df.at[i, "points_earned"] = amt * (used_rate if pd.notna(used_rate) else 0)

    # Normalize cards for comparison
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
# Entry Point (manual run)
# --------------------------------------------------
if __name__ == "__main__":
    compute_points()