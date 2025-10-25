"""
PointsPilot - Points Engine (Enhanced with Travel & Transit Logic)
-----------------------------------------------------------------
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
    """Guess category based on merchant name keywords."""
    if not isinstance(name, str):
        return "Other"
    name = name.lower()

    keywords = {
        "Dining": ["cafe", "coffee", "restaurant", "bar", "grill", "pizza", "bistro", "pub"],
        "Groceries": ["whole foods", "trader joe", "aldi", "wegmans", "safeway", "kroger", "grocery", "supermarket"],
        "Gas Stations": ["shell", "exxon", "chevron", "marathon", "bp", "sunoco", "mobil"],
        "Drugstores": ["cvs", "walgreens", "rite aid", "pharmacy"],
        "Entertainment": ["amc", "theater", "netflix", "spotify", "concert", "bowling", "museum"],
        "Travel": ["uber", "lyft", "delta", "united", "marriott", "hilton", "airbnb", "sixt", "hertz"],
        "Transit/Tolls": ["ez pass", "e-zpass", "turnpike", "toll", "parking", "septa", "mta", "transit", "metro", "train", "bus"],
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
        "travel": "Travel",
        "tolls": "Transit/Tolls",
        "parking": "Transit/Tolls",
        "entertainment": "Entertainment",
        "drugstores": "Drugstores",
        "personal care": "Personal Care",
        "gifts": "Shopping",
        "misc": "Other",
    }

    normalized = base_map.get(cat, cat.title())
    if normalized in ["Misc", "Other", "Gifts", "Car/Gas"] and inferred != "Other":
        return inferred
    return normalized


# --------------------------------------------------
# Canonical category helper
# --------------------------------------------------
def canonical_category(cat):
    """Normalize minor variations for category matching."""
    cat = str(cat).lower()
    if "restaurant" in cat or "dining" in cat or "bar" in cat:
        return "dining"
    if "gas" in cat:
        return "gas stations"
    if "toll" in cat or "transit" in cat or "parking" in cat:
        return "transit/tolls"
    if "travel" in cat:
        return "travel"
    return cat.strip()


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

    aliases = {
        "sapphire": "Sapphire Preferred",
        "freedom unlimited": "Freedom Unlimited",
        "freedom flex": "Freedom Flex",
        "aadvantage": "AAdvantage Platinum Select"
    }

    for key, value in aliases.items():
        if key in name:
            return value

    return None


# --------------------------------------------------
# Multiplier helpers (Enhanced with Travel + Transit logic)
# --------------------------------------------------
def get_multiplier(card, category, rules_df, name=""):
    """
    Return earning multiplier for the given card/category pair.
    Includes special-case handling for travel portals, airline-specific rules,
    and transit/tolls.
    """
    card = str(card).lower().strip()
    category = canonical_category(category)
    name = str(name).lower().strip()

    # Base rule lookup
    match = rules_df[
        (rules_df["card_name"].str.lower() == card)
        & (rules_df["category"].str.lower().apply(lambda c: canonical_category(c) == category))
    ]
    if not match.empty:
        multiplier = float(match["multiplier"].iloc[0])
    else:
        multiplier = 1.0

    # ✈️ Travel portal logic (Chase)
    if "travel" in category:
        if any(word in name for word in ["chase travel", "chase portal", "expedia", "ultimate rewards"]):
            pass  # keep assigned multiplier (5× via portal)
        elif "freedom unlimited" in card or "freedom flex" in card:
            multiplier = 1.5  # Base rate
        elif "sapphire preferred" in card:
            multiplier = 2.0  # Standard travel rate (non-portal)
        else:
            multiplier = 1.0

    # 🛫 AAdvantage logic (AA-only)
    if "aadvantage" in card and "travel" in category:
        if "american airlines" in name or "aa.com" in name:
            multiplier = 2.0
        else:
            multiplier = 1.0

    # 🚗 Transit / Tolls → no travel portal or airline logic applies
    if "transit" in category or "toll" in category:
        if "freedom unlimited" in card:
            multiplier = 1.5
        elif "freedom flex" in card:
            multiplier = 1.0
        elif "sapphire preferred" in card:
            multiplier = 1.0
        elif "aadvantage" in card:
            multiplier = 1.0

    return multiplier


def get_best_cards(category, rules_df, name=""):
    """
    Return list of best cards and top multiplier for given category,
    respecting travel and airline-specific conditions.
    """
    category = canonical_category(category)
    name = str(name).lower().strip()

    cat_matches = rules_df[
        rules_df["category"].str.lower().apply(lambda c: canonical_category(c) == category)
    ].copy()

    # Travel-specific adjustments
    if "travel" in category:
        # AAdvantage only 2× for AA
        if not ("american airlines" in name or "aa.com" in name):
            cat_matches.loc[
                cat_matches["card_name"].str.contains("aadvantage", case=False),
                "multiplier"
            ] = 1.0

        # Chase cards: 5× only through portal
        cat_matches.loc[
            cat_matches["card_name"].str.contains("freedom|sapphire", case=False),
            "multiplier"
        ] = cat_matches["multiplier"].apply(lambda x: 2.0 if x > 2 else x)

    # Transit/Tolls — always 1.5× for Freedom Unlimited
    if "transit" in category or "toll" in category:
        cat_matches.loc[
            cat_matches["card_name"].str.contains("freedom unlimited", case=False),
            "multiplier"
        ] = 1.5

    if not cat_matches.empty:
        max_mult = cat_matches["multiplier"].max()
        best_cards = cat_matches.loc[cat_matches["multiplier"] == max_mult, "card_name"].tolist()
        return best_cards, float(max_mult)

    return ["None"], 1.0


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

    # Filter valid credit-card transactions
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

    # Compute best and actual points
    df["best_cards_list"], df["best_rate"] = zip(*df.apply(lambda x: get_best_cards(x["normalized_category"], rules_df, x["name"]), axis=1))
    df["best_card"] = df["best_cards_list"].apply(lambda lst: ", ".join(lst))
    df["used_rate"] = df.apply(lambda x: get_multiplier(x["card_mapped"], x["normalized_category"], rules_df, x["name"]), axis=1)

    df["points_earned"] = (df["amount"] * df["used_rate"]).round(2)
    df["optimal_points"] = (df["amount"] * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).clip(lower=0)
    df["optimal_used"] = df.apply(lambda x: str(x["card_mapped"]).lower() in str(x["best_card"]).lower(), axis=1)

    # ML model (Decision Tree)
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
    print(f"\n🧠 ML Model Accuracy: {acc * 100:.2f}%")

    # Handle mismatch between y_test labels and encoded classes
    unique_labels = sorted(set(y_test) | set(y_pred))
    class_labels = [le_card.inverse_transform([i])[0] for i in unique_labels]

    # Compute confusion matrix and report safely
    cm = confusion_matrix(y_test, y_pred, labels=unique_labels)
    print(classification_report(y_test, y_pred, labels=unique_labels, target_names=class_labels))

    # Save confusion matrix
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Greens",
                xticklabels=le_card.classes_, yticklabels=le_card.classes_)
    plt.title("Confusion Matrix - PointsPilot ML Model")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.tight_layout()
    plt.savefig(os.path.join(data_dir, "decision_tree_confusion_matrix.png"))
    plt.close()

    # Save output
    output_path = os.path.join(data_dir, "transactions_review.csv")
    df.to_csv(output_path, index=False)

    print(f"\n✅ Saved filtered + analyzed transactions → {output_path}")
    print(f"⚡ Model disagreements flagged: {df['optimal_used'].sum()}\n")

    # Card summary
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

    summary_path = os.path.join(data_dir, "card_summary.csv")
    summary.to_csv(summary_path, index=False)

    print("📊 Summary by Card:\n")
    print(summary.to_string(index=False))
    print(f"\n💾 Saved card summary → {summary_path}")

    return df


# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    compute_points()