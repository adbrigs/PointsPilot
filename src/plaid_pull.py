"""
PointsPilot - Plaid Sandbox Pull (v3: AI Categorization)
--------------------------------------------------------
Connects to multiple Plaid sandbox institutions, retrieves up to 100
transactions per bank, and saves a combined CSV for the Streamlit dashboard.

This version leverages Plaid's AI-based 'personal_finance_category'
to provide high-confidence merchant categorization, with fallbacks
for merchants missing that data.
"""

import os
import json
import time
import pandas as pd
from datetime import datetime, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.exceptions import ApiException


# -----------------------------------------------------
# Load Plaid credentials
# -----------------------------------------------------
def load_plaid_credentials():
    cred_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "credentials",
        "plaid_credentials.json"
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
            "clientId": creds["PLAID_CLIENT_ID"],
            "secret": creds["PLAID_SECRET"]
        },
    )

    api_client = plaid.ApiClient(configuration)
    # Some SDK versions require explicit headers
    api_client.default_headers["PLAID-CLIENT-ID"] = creds["PLAID_CLIENT_ID"]
    api_client.default_headers["PLAID-SECRET"] = creds["PLAID_SECRET"]

    return plaid_api.PlaidApi(api_client)


# -----------------------------------------------------
# Fetch transactions from multiple sandbox institutions
# -----------------------------------------------------
def get_sandbox_transactions():
    client = create_plaid_client()

    # Each sandbox "bank" creates its own fake dataset (~15–20 txns)
    institution_ids = [
        "ins_109508",  # Chase
        "ins_128031",  # US Bank
    ]

    all_txns = []

    for inst in institution_ids:
        print(f"\n🏦 Creating sandbox item for {inst} ...")

        public_req = SandboxPublicTokenCreateRequest(
            institution_id=inst,
            initial_products=[Products("transactions")],
        )
        public_resp = client.sandbox_public_token_create(public_req)
        public_token = public_resp.public_token

        exchange_req = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_resp = client.item_public_token_exchange(exchange_req)
        access_token = exchange_resp.access_token

        # Wait for Plaid to generate fake transactions
        print("⏳ Waiting 5 seconds for transactions to populate ...")
        time.sleep(5)

        # Request transactions for the last 30 days
        start_date = (datetime.now() - timedelta(days=30)).date()
        end_date = datetime.now().date()

        tx_req = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options={"count": 100},
        )

        # Retry logic for PRODUCT_NOT_READY
        for attempt in range(5):
            try:
                tx_resp = client.transactions_get(tx_req)
                txns = tx_resp.to_dict().get("transactions", [])
                print(f"✅ Retrieved {len(txns)} transactions from {inst}")
                all_txns.extend(txns)
                break
            except ApiException as e:
                error_body = json.loads(e.body)
                if error_body.get("error_code") == "PRODUCT_NOT_READY":
                    print("⏳ Transactions not ready yet — retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    print(f"⚠️  Failed for {inst}: {e}")
                    break

    # -------------------------------------------------
    # Format & Save Combined Transactions
    # -------------------------------------------------
    if not all_txns:
        print("❌ No transactions retrieved.")
        return

    # 🔹 Plaid → PointsPilot category mapping
    category_map = {
        "FOOD_AND_DRINK": "Restaurants",
        "TRAVEL": "Travel",
        "GENERAL_MERCHANDISE": "Shopping",
        "TRANSPORTATION": "Travel",
        "BANK_FEES": "Other",
        "INCOME": "Other",
        "RENT_AND_UTILITIES": "Other",
        "ENTERTAINMENT": "Entertainment",
        "TRANSFER_OUT": "Other",
        "TRANSFER_IN": "Other",
        "LOAN_PAYMENTS": "Other",
        "OTHER_EXPENSE": "Other"
    }

    def infer_category_fallback(name: str) -> str:
        """Simple backup if Plaid category missing."""
        name = (name or "").lower()
        if any(x in name for x in ["mcdonald", "burger", "taco", "chipotle", "pizza", "restaurant", "grill"]):
            return "Restaurants"
        elif any(x in name for x in ["uber", "lyft", "airbnb", "hotel", "delta", "american airlines", "southwest"]):
            return "Travel"
        elif any(x in name for x in ["target", "walmart", "best buy", "store", "market", "amazon"]):
            return "Shopping"
        else:
            return "Other"

    records = []
    for t in all_txns:
        pfc = t.get("personal_finance_category") or {}
        primary = pfc.get("primary")
        mapped_cat = category_map.get(primary)

        if not mapped_cat:
            if t.get("category") and isinstance(t["category"], list) and t["category"]:
                mapped_cat = t["category"][0]
            else:
                mapped_cat = infer_category_fallback(t.get("name"))

        records.append({
            "date": t.get("date"),
            "merchant": t.get("merchant_name") or t.get("name"),
            "amount": abs(t.get("amount", 0)),
            "card_used": "Freedom Unlimited",  # placeholder for now
            "category": mapped_cat,
            "plaid_primary": primary,
            "plaid_detailed": pfc.get("detailed"),
            "confidence": pfc.get("confidence_level"),
            "logo_url": t.get("logo_url"),
            "website": t.get("website"),
        })

    # Save results
    df = pd.DataFrame(records)
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, "transactions.csv")
    df.to_csv(csv_path, index=False)

    print(f"\n✅  Saved {len(df)} total transactions → {csv_path}")
    print(df.head())


# -----------------------------------------------------
# Entry Point
# -----------------------------------------------------
if __name__ == "__main__":
    get_sandbox_transactions()