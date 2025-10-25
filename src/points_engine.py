"""
PointsPilot - Points Engine (Accurate Missed Points Version)
------------------------------------------------------------
Processes raw_transactions.csv, filters valid credit-card spend,
computes actual vs. optimal points based on earn_rules.yaml,
and applies an ML model for predictive insights.
"""

import os
import re
import pandas as pd
import yaml
from sklearn.preprocessing import LabelEncoder
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import matplotlib.pyplot as plt
import seaborn as sns


# --------------------------------------------------
# Load earning rules
# --------------------------------------------------
def load_rules(yaml_path=None):
    base_path = os.path.dirname(os.path.dirname(__file__))
    yaml_path = yaml_path or os.path.join(base_path, "src", "earn_rules.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"earn_rules.yaml not found at {yaml_path}")

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    records = []
    for card in data.get("cards", []):
        card_name = card.get("card_name")
        for category, details in card.get("rewards", {}).items():
            multiplier = details.get("multiplier", card.get("base_rate", 1))
            records.append({
                "card_name": card_name,
                "category": category,
                "multiplier": multiplier
            })
    return pd.DataFrame(records)


# --------------------------------------------------
# Infer category from transaction name
# --------------------------------------------------
def infer_category_from_name(name: str):
    if not isinstance(name, str):
        return "Other"
    name = name.lower()

    keywords = {
        "Dining": ["cafe", "coffee", "restaurant", "bar", "grill", "pizza", "bistro", "pub"],
        "Groceries": ["whole foods", "trader joe", "aldi", "wegmans", "safeway", "kroger", "grocery", "supermarket"],
        "Gas Stations": ["shell", "exxon", "chevron", "marathon", "bp", "sunoco", "mobil"],
        "Drugstores": ["cvs", "walgreens", "rite aid", "pharmacy"],
        "Entertainment": ["amc", "theater", "netflix", "spotify", "concert", "bowling", "museum"],
        "Travel": ["uber", "lyft", "delta", "american airlines", "united", "marriott", "hilton", "airbnb", "sixt", "hertz"],
        "Shopping": ["amazon", "target", "walmart", "costco", "ikea", "best buy", "store", "mall"],
        "Personal Care": ["hair", "salon", "spa", "massage", "barber", "nail"],
        "Misc": ["venmo", "zelle", "cash app", "atm", "fee", "transfer"]
    }

    for category, terms in keywords.items():
        if any(term in name for term in terms):
            return category

    return "Other"


# --------------------------------------------------
# Normalize + cross-check categories
# --------------------------------------------------
def normalize_category(cat: str, name: str = ""):
    cat = str(cat).strip().lower() if isinstance(cat, str) else "other"
    inferred = infer_category_from_name(name)

    base_map = {
        "restaurants": "Dining",
        "restaurants & bars": "Dining",
        "bars & nightlife": "Dining",
        "car/gas": "Gas Stations",
        "groceries": "Groceries",
        "subscriptions": "Entertainment",
        "travel & vacation": "Travel",
        "entertainment": "Entertainment",
        "drugstores": "Drugstores",
        "personal care": "Personal Care",
        "gifts": "Shopping",
        "misc": "Other",
    }

    normalized = base_map.get(cat, cat.title())
    if normalized in ["Misc", "Other", "Gifts"] and inferred != "Other":
        return inferred
    return normalized


# --------------------------------------------------
# Fuzzy card name matching
# --------------------------------------------------
def match_card_name(account_name: str, valid_cards: list):
    """Match transaction account name to one of your known cards."""
    if not isinstance(account_name, str):
        return None

    name = account_name.lower().strip()

    # Exclude non-credit accounts
    if any(excl in name for excl in ["checking", "savings", "venmo", "paypal", "transfer", "profile", "internal"]):
        return None

    for valid in valid_cards:
        valid_lower = valid.lower()
        if valid_lower in name:
            return valid

        valid_tokens = [v for v in valid_lower.split() if v not in ["chase", "citi", "card", "mastercard", "visa", "world", "elite"]]
        if all(v in name for v in valid_tokens):
            return valid

        if "sapphire" in name and "preferred" not in name and "sapphire preferred" in valid_lower:
            return valid

    return None


# --------------------------------------------------
# Multiplier helpers (Enhanced for fuzzy matching)
# --------------------------------------------------

def get_multiplier(card, category, rules_df):
    """Return earning multiplier for the given card/category pair.
    - Tries exact match first.
    - Then fuzzy match (e.g., 'restaurants' matches 'restaurants & bars').
    - Falls back to base rates if nothing matches.
    """
    card = str(card).lower().strip()
    category = str(category).lower().strip()

    # 🎯 1️⃣ Exact match
    match = rules_df[
        (rules_df["card_name"].str.lower() == card)
        & (rules_df["category"].str.lower() == category)
    ]

    # 🎯 2️⃣ Fuzzy match (for categories like "Restaurants & Bars" vs "Restaurants")
    if match.empty:
        match = rules_df[
            (rules_df["card_name"].str.lower() == card)
            & (rules_df["category"].str.lower().apply(
                lambda x: x in category or category in x
            ))
        ]

    # ✅ 3️⃣ Found a match
    if not match.empty:
        return float(match["multiplier"].iloc[0])

    # ⚙️ 4️⃣ Fallbacks for base earn rates
    if "freedom unlimited" in card:
        return 1.5
    if "freedom flex" in card:
        return 1.0
    if "sapphire preferred" in card:
        return 1.0
    if "aadvantage" in card:
        return 1.0
    return 1.0


def get_best_card(category, rules_df):
    """Return best card and rate for a given category.
    - Uses fuzzy category match logic.
    - Returns highest multiplier and its card.
    """
    category = str(category).lower().strip()

    # Exact category match first
    cat_matches = rules_df[rules_df["category"].str.lower() == category]

    # Fuzzy match fallback
    if cat_matches.empty:
        cat_matches = rules_df[
            rules_df["category"].str.lower().apply(
                lambda x: x in category or category in x
            )
        ]

    if not cat_matches.empty:
        top_row = cat_matches.loc[cat_matches["multiplier"].idxmax()]
        return top_row["card_name"], float(top_row["multiplier"])

    # Default fallback
    return "None", 1.0

# --------------------------------------------------
# Main compute function
# --------------------------------------------------
def compute_points():
    base_path = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base_path, "data")

    df = pd.read_csv(os.path.join(data_dir, "raw_transactions.csv"))
    rules_df = load_rules()
    valid_cards = rules_df["card_name"].unique().tolist()

    # Clean columns
    df.columns = df.columns.str.strip().str.lower()
    df.rename(columns={"account": "card_used", "account mask": "account_mask"}, inplace=True)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    # --------------------------------------------------
    # Filter valid credit-card transactions ONLY
    # --------------------------------------------------
    df["card_mapped"] = df["card_used"].apply(lambda x: match_card_name(x, valid_cards))
    df = df[df["card_mapped"].notna()]
    df = df[df["amount"].abs() > 0.01]

    exclude_keywords = [
        "transfer", "payment", "pay", "thank you", "refund",
        "credit", "balance", "adjustment", "reversal"
    ]
    df = df[
        ~df["type"].str.contains("transfer", case=False, na=False)
        & ~df["name"].str.contains("|".join(exclude_keywords), case=False, na=False)
        & ~df["category"].str.contains("|".join(exclude_keywords), case=False, na=False)
    ]

    print(f"✅ Loaded {len(df)} valid credit-card transactions after removing internal transfers and payments.")
    print(f"🪪 Recognized cards: {', '.join(df['card_mapped'].unique())}")

    # Normalize categories
    df["normalized_category"] = df.apply(lambda x: normalize_category(x["category"], x["name"]), axis=1)

    # --------------------------------------------------
    # Compute best and actual points
    # --------------------------------------------------
    df["best_card"], df["best_rate"] = zip(*df["normalized_category"].map(lambda c: get_best_card(c, rules_df)))
    df["used_rate"] = df.apply(lambda x: get_multiplier(x["card_mapped"], x["normalized_category"], rules_df), axis=1)

    df["points_earned"] = (df["amount"] * df["used_rate"]).round(2)
    df["optimal_points"] = (df["amount"] * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).clip(lower=0)

    # --------------------------------------------------
    # ML model: Decision Tree for insights
    # --------------------------------------------------
    df_ml = df[df["best_card"] != "None"].copy()
    le_cat = LabelEncoder()
    le_card = LabelEncoder()

    df_ml["cat_encoded"] = le_cat.fit_transform(df_ml["normalized_category"])
    df_ml["card_encoded"] = le_card.fit_transform(df_ml["best_card"])

    X = df_ml[["cat_encoded", "amount"]]
    y = df_ml["card_encoded"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = DecisionTreeClassifier(max_depth=4, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n🧠 ML Model Accuracy: {acc * 100:.2f}%")
    print(classification_report(y_test, y_pred, target_names=le_card.classes_))

    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Greens",
                xticklabels=le_card.classes_, yticklabels=le_card.classes_)
    plt.title("Confusion Matrix - PointsPilot ML Model")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.tight_layout()
    plt.savefig(os.path.join(data_dir, "decision_tree_confusion_matrix.png"))
    plt.close()

    # Handle unseen categories gracefully
    known_classes = set(le_cat.classes_)
    df["normalized_category"] = df["normalized_category"].apply(lambda c: c if c in known_classes else "Other")
    df["cat_encoded"] = le_cat.transform(df["normalized_category"])
    df["ml_pred_encoded"] = model.predict(df[["cat_encoded", "amount"]])
    df["ml_suggested_card"] = le_card.inverse_transform(df["ml_pred_encoded"])
    df["model_disagreement"] = df["ml_suggested_card"] != df["best_card"]

    # --------------------------------------------------
    # Save output and summary
    # --------------------------------------------------
    output_path = os.path.join(data_dir, "transactions_review.csv")
    df.to_csv(output_path, index=False)

    print(f"\n✅ Saved filtered + analyzed transactions → {output_path}")
    print(f"⚡ Model disagreements flagged: {df['model_disagreement'].sum()}\n")

    summary = (
        df.groupby("card_mapped")
        .agg(
            Transactions=("amount", "count"),
            Total_Spend=("amount", "sum"),
            Points_Earned=("points_earned", "sum"),
            Missed_Points=("missed_points", "sum")
        )
        .reset_index()
    )

    summary["Optimization_Rate"] = (
        (summary["Points_Earned"] / (summary["Points_Earned"] + summary["Missed_Points"])) * 100
    ).round(1)

    print("📊 Summary by Card:\n")
    print(summary.to_string(index=False))
    print("\n💾 You can find this breakdown inside transactions_review.csv as well.")

    # --------------------------------------------------
    # Save summary as card_summary.csv for dashboard use
    # --------------------------------------------------
    summary_path = os.path.join(data_dir, "card_summary.csv")
    summary.to_csv(summary_path, index=False)
    print(f"📁 Saved card summary → {summary_path}")

    return df

# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    compute_points()