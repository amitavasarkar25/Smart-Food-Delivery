import unittest
from datetime import datetime
from analytics import summarize_sales


class AnalyticsTests(unittest.TestCase):
    def test_empty_data(self):
        summary = summarize_sales([])
        self.assertEqual(summary["total_orders"], 0)
        self.assertEqual(summary["daily_sales"], [])

    def test_sales_aggregations_exclude_cancelled_revenue(self):
        rows = [
            {"order_id": 1, "order_date": datetime(2026, 1, 2), "order_status": "DELIVERED", "total_amount": 100},
            {"order_id": 2, "order_date": datetime(2026, 1, 2), "order_status": "PLACED", "total_amount": 50},
            {"order_id": 3, "order_date": datetime(2026, 1, 3), "order_status": "CANCELLED", "total_amount": 80},
        ]
        summary = summarize_sales(rows)
        self.assertEqual(summary["total_orders"], 3)
        self.assertEqual(summary["total_revenue"], 150.0)
        self.assertEqual(summary["average_order_value"], 75.0)
        self.assertEqual(summary["daily_labels"], ["2026-01-02"])
        self.assertEqual(summary["daily_sales"], [150.0])
        self.assertEqual(summary["status_counts"], [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
