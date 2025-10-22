import streamlit as st
import pandas as pd

def render_best_card_snapshot(best_cards_df: pd.DataFrame):
    """
    Render a clean, smaller best-card grid with clear labels and consistent sizing.
    """
    st.subheader("🏆 Best Card by Category")

    if best_cards_df.empty:
        st.warning("No category data available.")
        return

    # Display 3–4 cards per row
    num_cols = min(len(best_cards_df), 4)
    cols = st.columns(num_cols)

    for i, (_, row) in enumerate(best_cards_df.iterrows()):
        col = cols[i % num_cols]
        with col:
            st.markdown(
                f"""
                <div style="
                    background-color: #f8f9fa;
                    border-radius: 12px;
                    padding: 10px 14px;
                    margin-bottom: 10px;
                    text-align: center;
                    box-shadow: 0px 1px 2px rgba(0,0,0,0.1);
                ">
                    <div style="font-size: 0.85rem; font-weight: 600; color: #666;">
                        {row['category']}
                    </div>
                    <div style="font-size: 1rem; font-weight: 700; color: #000;">
                        {row['card_name']}
                    </div>
                    <div style="
                        font-size: 0.85rem;
                        background-color: #e6f4ea;
                        color: #1b7e3b;
                        font-weight: 600;
                        display: inline-block;
                        padding: 2px 8px;
                        border-radius: 8px;
                        margin-top: 4px;
                    ">
                        {row['multiplier']}×
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )