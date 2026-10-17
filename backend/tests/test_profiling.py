import pandas as pd
import pytest

from core.profiling import build_report, detect_type, profile_table
from core.upload import read_tables


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("gross_revenue", ["$1,200.50", "$30.00", "$9.99"], "currency"),
        ("amount_inr", ["₹500", "₹1,250", "₹99"], "currency"),
        ("discount", ["5%", "10%", "0%"], "percentage"),
        ("quantity", ["1", "2", "3"], "integer"),
        ("price", ["1.5", "2.25", "3"], "decimal"),
        ("order_date", ["2026-01-01", "2026-02-15", "2026-03-31"], "date"),
        ("created_at", ["2026-01-01 10:30", "2026-01-02 11:00", "2026-01-03 09:15"], "datetime"),
        ("active", ["Yes", "No", "Yes"], "boolean"),
        ("email", ["a@b.com", "c@d.in", "e@f.org"], "email"),
        ("city", ["Delhi", "Pune", "Delhi"], "location"),
        ("zip_code", ["110001", "400001", "560001"], "location"),
        ("store_id", ["101", "102", "103"], "id"),
        ("customer_guid", ["c81e728d-9dac-4b2c-9a6b-0e4d1f2a3b4c", "f47ac10b-58cc-4372-a567-0e02b2c3d479", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"], "uuid"),
        ("status", ["Open", "Closed", "Open", "Open"], "category"),
    ],
)
def test_detect_type(name, values, expected):
    assert detect_type(name, pd.Series(values, dtype="string"))[0] == expected


def _sample_tables(sample_bytes):
    tables = []
    for filename, content in sample_bytes.items():
        for name, (sheet, df) in read_tables(filename, content).items():
            tables.append((name, "f1", sheet, df))
    return tables


def _col(report, table, column):
    t = next(t for t in report.tables if t.name == table)
    return next(c for c in t.column_profiles if c.name == column)


def test_sample_report_finds_keys_measures_and_issues(sample_bytes):
    report = build_report(_sample_tables(sample_bytes))

    assert _col(report, "orders", "order_id").role == "primary_key"
    assert _col(report, "products", "product_id").role == "primary_key"
    # customer_id is unique once the 3 duplicate CRM rows are removed.
    assert _col(report, "customers_Customers", "customer_id").role == "primary_key"

    fk = _col(report, "orders", "customer_id")
    assert (fk.role, fk.role_target) == ("foreign_key", "customers_Customers")
    assert _col(report, "orders", "product_id").role_target == "products"

    revenue = _col(report, "orders", "gross_revenue")
    assert revenue.detected_type == "currency" and revenue.currency_symbol == "$"
    assert revenue.role == "measure" and revenue.needs_casting
    assert revenue.numeric.outliers > 0

    ts = _col(report, "orders", "order_timestamp")
    assert ts.role == "time_dimension" and ts.null_count == 12 and ts.dates.span_days > 100

    assert _col(report, "orders", "destination_city").inconsistent_values > 0
    assert _col(report, "orders", "fulfillment_status").role == "categorical_slicer"
    assert _col(report, "products", "product_name").role == "attribute"

    customers = next(t for t in report.tables if t.name == "customers_Customers")
    assert customers.duplicate_rows == 3

    assert 0 < report.score <= 100
    assert "2 foreign key relationship candidates" in report.signal
    assert "2 columns require numeric casting" in report.signal
    assert report.total_rows == 600 + 123 + 3 + 40


def test_empty_report():
    report = build_report([])
    assert report.score == 0 and report.tables == []


def test_quality_score_penalises_nulls_and_duplicates():
    clean = pd.DataFrame({"id": ["1", "2", "3", "4"], "v": ["a", "b", "c", "d"]}, dtype="string")
    messy = pd.DataFrame({"id": ["1", "1", None, "4"], "v": ["a", "a", None, None]}, dtype="string")
    assert profile_table("clean", "f", None, clean).quality_score > profile_table("messy", "f", None, messy).quality_score
