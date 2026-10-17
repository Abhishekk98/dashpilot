"""Generate the small, deterministic sales sample used in tests and demos.

Run from backend/:  python samples/generate_samples.py
Writes orders.csv, customers.xlsx (two sheets) and products.csv into samples/sales/.
The data deliberately contains real-world mess: currency stored as text, a few
missing dates, inconsistent city casing and duplicate customer rows.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "sales"
CITIES = ["Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Kolkata", "Jaipur"]
STATUSES = ["Delivered", "In Transit", "Returned", "Cancelled"]
SEGMENTS = ["Consumer", "Corporate", "Small Business"]
CATEGORIES = ["Electronics", "Home", "Fashion", "Grocery"]


def build(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)

    products = pd.DataFrame(
        {
            "product_id": [f"P{i:03d}" for i in range(1, 41)],
            "product_name": [f"Product {i}" for i in range(1, 41)],
            "category": [CATEGORIES[i % 4] for i in range(40)],
            "unit_price": [round(rng.uniform(5, 900), 2) for _ in range(40)],
        }
    )

    customers = pd.DataFrame(
        {
            "customer_id": [f"C{i:04d}" for i in range(1, 121)],
            "customer_name": [f"Customer {i}" for i in range(1, 121)],
            "email": [f"customer{i}@example.com" for i in range(1, 121)],
            "city": [rng.choice(CITIES) for _ in range(120)],
            "segment": [rng.choice(SEGMENTS) for _ in range(120)],
            "signup_date": [
                (datetime(2024, 1, 1) + timedelta(days=rng.randint(0, 700))).date().isoformat() for _ in range(120)
            ],
        }
    )
    # Three exact duplicate rows, as often seen in CRM exports.
    customers = pd.concat([customers, customers.iloc[[3, 10, 42]]], ignore_index=True)

    rows = []
    start = datetime(2026, 1, 1)
    for i in range(1, 601):
        product = products.iloc[rng.randrange(len(products))]
        qty = rng.randint(1, 5)
        revenue = float(product["unit_price"]) * qty
        if i % 97 == 0:
            revenue *= 25  # a few bulk orders -> outliers
        city = rng.choice(CITIES)
        if i % 11 == 0:
            city = city.lower()  # inconsistent casing
        ts = start + timedelta(hours=rng.randint(0, 24 * 120), minutes=rng.randint(0, 59))
        rows.append(
            {
                "order_id": f"ORD-{10000 + i}",
                "order_timestamp": "" if i % 50 == 0 else ts.strftime("%Y-%m-%d %H:%M"),
                "customer_id": f"C{rng.randint(1, 120):04d}",
                "product_id": product["product_id"],
                "destination_city": city,
                "quantity": qty,
                "gross_revenue": f"${revenue:,.2f}",
                "discount_pct": f"{rng.choice([0, 5, 10, 15])}%",
                "fulfillment_status": rng.choice(STATUSES),
                "is_prime": rng.choice(["Yes", "No"]),
            }
        )
    orders = pd.DataFrame(rows)
    return {"orders": orders, "customers": customers, "products": products}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = build()
    data["orders"].to_csv(OUT / "orders.csv", index=False)
    data["products"].to_csv(OUT / "products.csv", index=False)
    segments = data["customers"].groupby("segment").size().reset_index(name="customers")
    with pd.ExcelWriter(OUT / "customers.xlsx") as writer:
        data["customers"].to_excel(writer, sheet_name="Customers", index=False)
        segments.to_excel(writer, sheet_name="Segments", index=False)
    print(f"Wrote sample files to {OUT}")


if __name__ == "__main__":
    main()
