"""Pandas/NumPy summaries for the SmartBite admin sales dashboard."""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def summarize_sales(records: list[dict]) -> dict:
    """Convert Oracle order dictionaries to safe, JSON-friendly chart summaries."""
    columns = ["order_id", "order_date", "order_status", "total_amount"]
    frame = pd.DataFrame(records or [], columns=columns)
    if frame.empty:
        return {
            "total_orders": 0, "total_revenue": 0.0, "average_order_value": 0.0,
            "daily_labels": [], "daily_sales": [], "status_labels": [], "status_counts": [],
            "monthly_labels": [], "monthly_sales": [], "sales_stddev": 0.0,
            "message": "No orders are available for analytics yet.",
        }
    frame["total_amount"] = pd.to_numeric(frame["total_amount"], errors="coerce").fillna(0.0)
    frame["order_status"] = frame["order_status"].fillna("UNKNOWN").astype(str)
    frame["order_date"] = pd.to_datetime(frame["order_date"], errors="coerce")
    valid_sales = frame.loc[frame["order_status"] != "CANCELLED", "total_amount"]
    total_revenue = float(valid_sales.sum())
    avg = float(valid_sales.mean()) if len(valid_sales) else 0.0
    values = valid_sales.to_numpy(dtype=float)
    stddev = float(np.std(values)) if values.size else 0.0
    dated = frame.dropna(subset=["order_date"]).copy()
    if not dated.empty:
        dated["day"] = dated["order_date"].dt.strftime("%Y-%m-%d")
        daily = dated.loc[dated["order_status"] != "CANCELLED"].groupby("day", sort=True)["total_amount"].sum()
        dated["month"] = dated["order_date"].dt.strftime("%Y-%m")
        monthly = dated.loc[dated["order_status"] != "CANCELLED"].groupby("month", sort=True)["total_amount"].sum()
    else:
        daily = pd.Series(dtype=float)
        monthly = pd.Series(dtype=float)
    status_counts = frame.groupby("order_status").size().sort_index()
    return {
        "total_orders": int(len(frame)),
        "total_revenue": round(total_revenue, 2),
        "average_order_value": round(avg, 2),
        "daily_labels": daily.index.astype(str).tolist(),
        "daily_sales": [round(float(v), 2) for v in daily.to_numpy(dtype=float)],
        "status_labels": status_counts.index.astype(str).tolist(),
        "status_counts": [int(v) for v in status_counts.to_numpy()],
        "monthly_labels": monthly.index.astype(str).tolist(),
        "monthly_sales": [round(float(v), 2) for v in monthly.to_numpy(dtype=float)],
        "sales_stddev": round(stddev, 2),
        "message": "Cancelled orders are excluded from revenue and sales charts.",
    }
class SalesAnalytics:
    """Generate sales charts using Matplotlib."""

    def __init__(self, output_dir="static/charts"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    
    def _save_chart(self, filename):
        """Save the current Matplotlib chart as a tightly cropped PNG."""
        path = os.path.join(self.output_dir, filename)
        plt.tight_layout(pad=1)
        plt.savefig(
            path,
            dpi=110,
            bbox_inches="tight",
            pad_inches=0.12,
            facecolor="white",
        )
        plt.close()
        return filename


    def generate_charts(self, summary):
        """Generate daily, order-status and monthly sales charts."""
        charts = {}

        # 1. Daily sales bar chart
        plt.figure(figsize=(7, 3))
        plt.bar(
            summary["daily_labels"],
            summary["daily_sales"],
        )
        plt.title("Daily Sales")
        plt.xlabel("Date")
        plt.ylabel("Sales Amount")
        plt.xticks(rotation=45, ha="right")

        charts["daily"] = self._save_chart("daily_sales.png")

        # 2. Order-status pie chart
        
        
    
        
        
        # 2. Order-status pie chart
        fig, ax = plt.subplots(figsize=(5, 3.5))

        labels = summary["status_labels"]
        counts = summary["status_counts"]

        if labels and sum(counts) > 0:
            wedges, _, autotexts = ax.pie(
                counts,
                labels=None,
                autopct="%1.1f%%",
                startangle=90,
                pctdistance=0.65,
                radius=0.78,
                textprops={"fontsize": 9},
            )

            for text in autotexts:
                text.set_fontweight("bold")

            ax.set_title("Orders by Status", fontsize=12, pad=8)
            ax.axis("equal")

            # Reserve space below the pie for the legend.
            ax.legend(
                wedges,
                labels,
                loc="lower center",
                bbox_to_anchor=(0.5, -0.12),
                ncol=2,
                frameon=False,
                fontsize=8,
            )

            fig.subplots_adjust(
                left=0.06,
                right=0.94,
                top=0.85,
                bottom=0.25,
            )
        else:
            ax.text(
                0.5, 0.5,
                "No order data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.axis("off")

        # Save this chart without tight cropping so the legend remains visible.
        output_path = os.path.join(
            self.output_dir, "order_status.png"
        )
        fig.savefig(
            output_path,
            dpi=120,
            facecolor="white",
            bbox_inches=None,
            pad_inches=0.1,
        )
        plt.close(fig)

        charts["status"] = "order_status.png"


        # 3. Monthly sales line chart
        plt.figure(figsize=(7, 3))
        plt.plot(
            summary["monthly_labels"],
            summary["monthly_sales"],
            marker="o",
        )
        plt.title("Monthly Sales")
        plt.xlabel("Month")
        plt.ylabel("Sales Amount")
        plt.xticks(rotation=45, ha="right")

        charts["monthly"] = self._save_chart("monthly_sales.png")

        return charts
