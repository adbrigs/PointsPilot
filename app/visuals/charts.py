import plotly.express as px
import pandas as pd

## Points Per Card

def points_per_card_chart(df: pd.DataFrame):
    """
    Visualize total and potential points earned per card.
    Expects df with columns: ['card_used', 'points_earned', 'optimal_points']
    """
    if df.empty:
        return None

    # Aggregate by card
    card_summary = (
        df.groupby("card_used")
        .agg({"points_earned": "sum", "optimal_points": "sum"})
        .reset_index()
    )

    # Estimate cash value at 1.5¢ per point
    card_summary["points_value"] = card_summary["points_earned"] * 0.015
    card_summary["optimization_rate"] = (
        card_summary["points_earned"] / card_summary["optimal_points"]
    ).fillna(0) * 100

    fig = px.bar(
        card_summary,
        y="card_used",
        x="points_earned",
        color="optimization_rate",
        orientation="h",
        title="💳 Points Earned per Card",
        labels={
            "card_used": "Card",
            "points_earned": "Points Earned",
            "optimization_rate": "% Optimized",
        },
        hover_data=["optimal_points", "points_value"],
        color_continuous_scale="Blues",
    )

    fig.update_layout(
        yaxis_title="",
        xaxis_title="Points",
        height=400,
        coloraxis_colorbar=dict(title="% Optimized"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig