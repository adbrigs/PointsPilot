"""
PointsPilot - Points Engine (Override-Integrated)
-------------------------------------------------
✅ Normalizes card names from Plaid/CSV to match earn_rules.yaml
✅ Applies merchant-based overrides correctly (American, Chase Travel, etc.)
✅ Skips internal transfers and non-regular transactions
✅ Ensures override multiplier also updates best_rate
✅ Filters strictly to user's active credit cards
"""

import os
import yaml
import pandas as pd

# ==========================================================
# LOAD RULES
# ==========================================================
def load_rules():
    base_path = os.path.dirname(os.path.dirname(__file__))
    yaml_path = os.path.join(base_path, "src", "earn_rules.yaml")
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    rules = {c["card_name"]: c.get("rewards", {}) for c in data["cards"]}
    overrides = data.get("name_overrides", [])
    return rules, data["credit_card_categories"], overrides


# ==========================================================
# CARD NAME NORMALIZATION
# ==========================================================
def normalize_card_name(name: str):
    """Normalize messy Plaid account names to clean, consistent card names."""
    if not isinstance(name, str) or not name.strip():
        return None

    name_lower = name.lower().strip()

    mapping = {
        # Chase Sapphire variants
        "chase sapphire preferred": "Chase Sapphire Preferred",
        "chase sapphire": "Chase Sapphire Preferred",

        # Freedom Unlimited variants
        "freedom unlimited": "Chase Freedom Unlimited",
        "chase freedom unlimited": "Chase Freedom Unlimited",
        "freedom unlimited card": "Chase Freedom Unlimited",

        # Freedom Flex variants
        "freedom flex": "Chase Freedom Flex",
        "chase freedom flex": "Chase Freedom Flex",
        "freedom": "Chase Freedom Flex",  # catches “Chase Freedom” (legacy)

        # Citi AAdvantage variants
        "citi®/aadvantage® platinum select® world elite mastercard®": "Citi AAdvantage Platinum Select",
        "citi aadvantage platinum select": "Citi AAdvantage Platinum Select",
        "aadvantage": "Citi AAdvantage Platinum Select",
        "citi / aadvantage": "Citi AAdvantage Platinum Select",
        "citi advantage": "Citi AAdvantage Platinum Select",
    }

    for key, normalized in mapping.items():
        if key in name_lower:
            return normalized

    # Fallback
    return name.title()


# ==========================================================
# CATEGORY MAPPING
# ==========================================================
def map_to_cc_category(cat):
    mapping = {
        "Bars & Nightlife": "Dining",
        "Restaurants & Bars": "Dining",
        "Car/Gas": "Gas",
        "Groceries": "Groceries",
        "Travel & Vacation": "Travel",
        "Ubers/Septa": "Transit",
        "Subscriptions": "Streaming",
        "Entertainment": "Other",
        "Gifts": "Other",
        "Clothing": "Other",
        "Gym": "Other",
        "Health Care": "Other",
        "Home Improvement": "Other",
        "Insurance": "Other",
        "Loans": "Other",
        "Misc": "Other",
        "Personal Care": "Other",
        "Recreation": "Other",
        "Rent/Utilities": "Other",
        "Shops": "Other",
        "Sports Data Now": "Other",
    }
    return mapping.get(cat, "Other")


# ==========================================================
# APPLY MERCHANT OVERRIDES
# ==========================================================
def apply_overrides(row, overrides):
    name = str(row.get("name", "")).lower()
    for rule in overrides:
        if any(term in name for term in rule.get("match", [])):
            if rule.get("category_override"):
                row["CC_Category"] = rule["category_override"]
            elif rule.get("category"):
                row["CC_Category"] = rule["category"]
            if rule.get("preferred_card"):
                row["override_card"] = rule["preferred_card"]
            if rule.get("multiplier_override"):
                row["override_rate"] = rule["multiplier_override"]
            row["override_applied"] = True
            row["override_reason"] = f"Matched override: {', '.join(rule['match'])}"
            return row
    row["override_applied"] = False
    row["override_reason"] = ""
    return row


# ==========================================================
# BEST CARD LOGIC
# ==========================================================
def get_best_cards(cat, rules):
    best_rate = 0
    best_cards = []
    for card, r in rules.items():
        rate = r.get(cat, r.get("Other", 1))
        if rate > best_rate:
            best_rate = rate
            best_cards = [card]
        elif rate == best_rate:
            best_cards.append(card)
    return best_cards, best_rate


# ==========================================================
# MAIN COMPUTE FUNCTION
# ==========================================================
def compute_points():
    base_path = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base_path, "data")
    input_path = os.path.join(data_dir, "raw_transactions.csv")
    output_path = os.path.join(data_dir, "transactions_review.csv")

    df = pd.read_csv(input_path)
    rules, valid_cats, overrides = load_rules()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # --- 1. Include only "regular" transactions
    if "type" in df.columns:
        df = df[df["type"].str.lower() == "regular"]

    # --- 2. Exclude internal transfers, payments, refunds, etc.
    exclude_keywords = [
        "transfer", "payment", "thank you", "refund", "credit", "balance",
        "internal", "adjustment", "reversal", "deposit", "offer"
    ]
    for col in ["name", "category", "account"]:
        if col in df.columns:
            mask = ~df[col].astype(str).str.lower().str.contains("|".join(exclude_keywords), na=False)
            df = df[mask]

    # --- 3. Normalize card names
    df["card_mapped"] = df["account"].apply(normalize_card_name)

    # --- 4. Filter only user’s active credit cards
    user_cards = [
        "Chase Sapphire Preferred",
        "Chase Freedom Unlimited",
        "Chase Freedom Flex",
        "Citi AAdvantage Platinum Select",
    ]
    df = df[df["card_mapped"].isin(user_cards)]

    # --- 5. Map category → CC Category
    df["CC_Category"] = df["category"].apply(map_to_cc_category)

    # --- 6. Apply merchant-based overrides
    df = df.apply(lambda x: apply_overrides(x, overrides), axis=1)

    # --- 7. Helper: get card multiplier
    def get_multiplier(card, cat):
        card_rules = rules.get(card, {})
        return card_rules.get(cat, card_rules.get("Other", 1))

    # --- 8. Determine used rate
    def determine_used_rate(row):
        # If there's a manual override multiplier, that replaces only the *recommended* rate
        if pd.notna(row.get("override_rate")):
            return get_multiplier(row["card_mapped"], row["CC_Category"])
        if pd.notna(row.get("override_card")):
            return get_multiplier(row["override_card"], row["CC_Category"])
        return get_multiplier(row["card_mapped"], row["CC_Category"])

    df["used_rate"] = df.apply(determine_used_rate, axis=1)

    # --- 9. Determine effective card (what was actually used)
    df["effective_card"] = df["card_mapped"]

    # --- 10. Points earned
    df["points_earned"] = (df["amount"].astype(float) * df["used_rate"]).round(2)

    # --- 11. Compute best cards + best rate (respect overrides properly)
    def compute_best_info(row):
        """Best cards are determined by category & overrides, not what was used."""
        best_cards, best_rate = get_best_cards(row["CC_Category"], rules)

        # If an override applies (e.g. Adobe), check if it improves the best rate
        if row.get("override_applied") and pd.notna(row.get("override_rate")):
            override_rate = float(row.get("override_rate", 0))
            override_card = row.get("override_card")

            # Override rate wins → new best card
            if override_rate > best_rate:
                best_cards = [override_card]
                best_rate = override_rate
            # Equal rate → add override card as valid option
            elif abs(override_rate - best_rate) < 1e-6 and override_card not in best_cards:
                best_cards.append(override_card)

        return best_cards, best_rate

    best_info = df.apply(compute_best_info, axis=1)
    df["best_cards"] = best_info.apply(lambda x: ", ".join(x[0]) if isinstance(x[0], list) else x[0])
    df["best_rate"] = best_info.apply(lambda x: x[1])

    # --- 12. Calculate points and flags
    df["optimal_points"] = (df["amount"].astype(float) * df["best_rate"]).round(2)
    df["missed_points"] = (df["optimal_points"] - df["points_earned"]).clip(lower=0)

    # ✅ Used best card only if effective_card is actually among best_cards
    df["used_best_card"] = df.apply(
        lambda x: any(card.strip() == x["effective_card"] for card in str(x["best_cards"]).split(",")),
        axis=1
    )

    # --- 13. Save and summarize
    df.to_csv(output_path, index=False)
    print(f"✅ Processed {len(df)} transactions after filtering & normalization.")
    print(f"💳 Cards included: {', '.join(user_cards)}")
    print(f"💾 Saved → {output_path}")
    print("Columns include: effective_card, override_card, override_rate, best_cards, best_rate, points_earned, missed_points, override_applied")

    return df
# ==========================================================
# RUN DIRECTLY
# ==========================================================
if __name__ == "__main__":
    compute_points()