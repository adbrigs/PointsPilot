import pandas as pd

def generate_insights(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates two layers of insights:
      1. Transaction-level feedback (existing)
      2. Aggregated smart insights about optimization and usage patterns
    """
    insights = []

    # -----------------------------
    # 1️⃣ Transaction-level insights (your existing logic)
    # -----------------------------
    for _, row in results_df.iterrows():
        if "best?" in results_df.columns and row.get("best?") == "✅":
            insights.append({
                "merchant": row["merchant"],
                "insight": f"You used the best card ({row['card_used']}) for {row['merchant']} 👍",
                "type": "optimal"
            })
        elif "best?" in results_df.columns:
            regret_points = row.get("regret_points", row.get("missed_points", 0))
            best_points = row.get("best_points", row.get("optimal_points", 0))
            earned = row.get("points_earned", 0)
            insights.append({
                "merchant": row["merchant"],
                "insight": (
                    f"You used {row['card_used']} at {row['merchant']}, "
                    f"but {row['best_card']} would have earned "
                    f"{regret_points:.1f} more points "
                    f"({best_points:.1f} vs {earned:.1f})."
                ),
                "type": "missed"
            })

    # -----------------------------
    # 2️⃣ Category-level optimization insights
    # -----------------------------
    if all(col in results_df.columns for col in ["category", "points_earned", "optimal_points"]):
        cat_summary = (
            results_df.groupby("category")[["points_earned", "optimal_points"]]
            .sum()
            .reset_index()
        )
        cat_summary["optimization_rate"] = (
            cat_summary["points_earned"] / cat_summary["optimal_points"]
        ).fillna(0)

        # Find least-optimized categories
        low_opt = cat_summary.sort_values("optimization_rate").head(2)
        for _, r in low_opt.iterrows():
            missed = r["optimal_points"] - r["points_earned"]
            if missed > 0:
                insights.append({
                    "merchant": None,
                    "insight": (
                        f"You're missing points in **{r['category']}** — "
                        f"about {missed:,.0f} points left on the table."
                    ),
                    "type": "category"
                })

    # -----------------------------
    # 3️⃣ Card performance summary insights
    # -----------------------------
    if "card_used" in results_df.columns:
        card_perf = (
            results_df.groupby("card_used")[["points_earned", "optimal_points"]]
            .sum()
            .reset_index()
        )
        card_perf["optimization_rate"] = (
            card_perf["points_earned"] / card_perf["optimal_points"]
        ).fillna(0)

        # Highlight weakest and strongest cards
        if not card_perf.empty:
            best_card = card_perf.loc[card_perf["optimization_rate"].idxmax()]
            worst_card = card_perf.loc[card_perf["optimization_rate"].idxmin()]
            insights.append({
                "merchant": None,
                "insight": f"Your **{best_card['card_used']}** card is performing best overall "
                           f"({best_card['optimization_rate']*100:.1f}% optimized).",
                "type": "card"
            })
            insights.append({
                "merchant": None,
                "insight": f"Consider reviewing your **{worst_card['card_used']}** usage "
                           f"({worst_card['optimization_rate']*100:.1f}% optimized).",
                "type": "card"
            })

    # -----------------------------
    # 4️⃣ Optional redemption suggestions (placeholder)
    # -----------------------------
    if "optimal_points" in results_df.columns:
        total_opt = results_df["optimal_points"].sum()
        if total_opt > 10000:
            insights.append({
                "merchant": None,
                "insight": (
                    f"You’ve earned over **{total_opt:,.0f} potential points** — "
                    f"that’s worth about **${total_opt*0.015:,.2f}** in travel value. "
                    f"Consider redeeming via Chase Travel or AAdvantage deals."
                ),
                "type": "redemption"
            })

    return pd.DataFrame(insights)