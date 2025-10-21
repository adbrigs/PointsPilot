import pandas as pd

def generate_insights(results_df: pd.DataFrame) -> pd.DataFrame:
    insights = []
    for _, row in results_df.iterrows():
        if row["best?"] == "✅":
            insights.append({
                "merchant": row["merchant"],
                "insight": f"You used the best card ({row['card_used']}) for {row['merchant']} 👍",
                "type": "optimal"
            })
        else:
            insights.append({
                "merchant": row["merchant"],
                "insight": (
                    f"You used {row['card_used']} at {row['merchant']}, "
                    f"but {row['best_card']} would have earned "
                    f"{row['regret_points']:.1f} more points "
                    f"({row['best_points']:.1f} vs {row['points_earned']:.1f})."
                ),
                "type": "missed"
            })
    return pd.DataFrame(insights)