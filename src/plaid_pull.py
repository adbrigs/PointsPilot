"""
PointsPilot - Plaid Sandbox Pull (Multi-card)
---------------------------------------------
Connects to multiple Plaid sandbox institutions, retrieves transactions,
filters out internal/irrelevant activity, and saves a combined CSV
for the Streamlit dashboard.
"""

import os
import json
import time
import pandas as pd
import yaml
from datetime import datetime, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.products import Products


# -----------------------------------------------------
# Load Plaid credentials (supports Streamlit Cloud + local)
# -----------------------------------------------------
def load_plaid_credentials():
    try:
        import streamlit as st
        if "plaid" in st.secrets:
            return {
                "PLAID_CLIENT_ID": st.secrets["plaid"]["PLAID_CLIENT_ID"],
                "PLAID_SECRET": st.secrets["plaid"]["PLAID_SECRET"],
                "PLAID_ENV": st.secrets["plaid"]["PLAID_ENV"],
            }
    except Exception:
        pass

    cred_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "credentials",
        "plaid_credentials.json",
    )
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Plaid credentials not found at {cred_path}")

    with open(cred_path, "r") as f:
        return json.load(f)


# -----------------------------------------------------
# Create Plaid client
# -----------------------------------------------------
def create_plaid_client():
    creds = load_plaid_credentials()
    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={
            "client_id": creds["PLAID_CLIENT_ID"],
            "secret": creds["PLAID_SECRET"],
        },
    )
    api_client = plaid.ApiClient(configuration)
    api_client.default_headers["PLAID-CLIENT-ID"] = creds["PLAID_CLIENT_ID"]
    api_client.default_headers["PLAID-SECRET"] = creds["PLAID_SECRET"]
    return plaid_api.PlaidApi(api_client)


# -----------------------------------------------------
# Load institution → card mapping
# -----------------------------------------------------
def load_card_mapping():
    """Load Plaid institution_id → card name mapping safely."""
    base_path = os.path.dirname(os.path.dirname(__file__))
    yaml_path = os.path.join(base_path, "src", "card_mapping.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"❌ Missing card_mapping.yaml at {yaml_path}")

    with open(yaml_path, "r") as f:
        mapping = yaml.safe_load(f)

    if not mapping or not isinstance(mapping, dict):
        raise ValueError(f"⚠️ Invalid or empty card_mapping.yaml at {yaml_path}")

    print(f"✅ Loaded card mapping for {len(mapping)} institutions.")
    return mapping


# -----------------------------------------------------
# Helper: Infer category (fallback)
# -----------------------------------------------------
def infer_category(name: str) -> str:
    name = (name or "").lower()
    if any(x in name for x in ["mcdonald", "burger", "taco", "chipotle", "restaurant", "pizza", "grill"]):
        return "Restaurants"
    elif any(x in name for x in ["shell", "exxon", "bp", "gas", "chevron"]):
        return "Gas"
    elif any(x in name for x in ["walgreens", "cvs", "rite aid", "pharmacy"]):
        return "Drugstores"
    elif any(x in name for x in ["hotel", "airbnb", "airlines", "uber", "lyft", "delta", "southwest"]):
        return "Travel"
    elif any(x in name for x in ["amazon", "target", "walmart", "best buy", "store", "market"]):
        return "Shopping"
    elif any(x in name for x in ["spotify", "netflix", "concert", "movie", "theater", "music"]):
        return "Entertainment"
    else:
        return "Other"


# -----------------------------------------------------
# Main: Get transactions from multiple institutions
# -----------------------------------------------------
def get_sandbox_transactions():
    client = create_plaid_client()
    mapping = load_card_mapping()
    all_txns = []

    # Plaid categories to ignore
    EXCLUDED_TYPES = {"TRANSFER_OUT", "TRANSFER_IN", "LOAN_PAYMENTS", "BANK_FEES", "INCOME"}

    for inst_id, card_name in mapping.items():
        print(f"\n🏦 Creating sandbox item for {inst_id} ({card_name}) ...")

        # Create sandbox item
        public_req = SandboxPublicTokenCreateRequest(
            institution_id=inst_id,
            initial_products=[Products("transactions")],
        )
        public_resp = client.sandbox_public_token_create(public_req)
        public_token = public_resp.public_token

        # Exchange for access token
        exchange_req = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_resp = client.item_public_token_exchange(exchange_req)
        access_token = exchange_resp.access_token

        print("⏳ Waiting 5 seconds for transactions to populate ...")
        time.sleep(5)

        start_date = (datetime.now() - timedelta(days=30)).date()
        end_date = datetime.now().date()
        tx_req = TransactionsGetRequest(access_token=access_token, start_date=start_date, end_date=end_date)
        tx_resp = client.transactions_get(tx_req)

        txns = tx_resp["transactions"]
        print(f"✅ Retrieved {len(txns)} transactions from {inst_id}")

        for t in txns:
            pfc = t.get("personal_finance_category", {})
            primary_cat = pfc.get("primary", "Other")
            detailed_cat = pfc.get("detailed", "")

            # Filter out excluded transaction types
            if any(x in (primary_cat or "").upper() for x in EXCLUDED_TYPES):
                continue
            if any(x in (detailed_cat or "").upper() for x in EXCLUDED_TYPES):
                continue

            all_txns.append({
                "date": t.get("date"),
                "merchant": t.get("merchant_name") or t.get("name"),
                "amount": abs(t.get("amount", 0)),
                "category": primary_cat if primary_cat and primary_cat != "Other" else infer_category(t.get("name")),
                "card_used": card_name,
            })

    if not all_txns:
        print("❌ No valid transactions found after filtering.")
        return pd.DataFrame()

    df = pd.DataFrame(all_txns)

    # Save output CSV
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, "transactions.csv")
    df.to_csv(csv_path, index=False)

    print(f"✅ Saved {len(df)} valid transactions → {csv_path}")
    return df


# -----------------------------------------------------
# Entry Point
# -----------------------------------------------------
if __name__ == "__main__":
    print("Plaid pull disabled. Using local CSV instead.") # replaced... get_sandbox_transactions() with temporary hold

