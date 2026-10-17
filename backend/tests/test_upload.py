import pytest

from core.upload import UploadError, read_tables, table_name, validate_upload


def test_validate_rejects_bad_extension_and_size():
    with pytest.raises(UploadError):
        validate_upload("data.parquet", 10, 100)
    with pytest.raises(UploadError):
        validate_upload("data.csv", 0, 100)
    with pytest.raises(UploadError):
        validate_upload("data.csv", 101 * 1024 * 1024, 100)
    assert validate_upload("Data.XLSX", 10, 100) == ".xlsx"


def test_table_name_is_power_bi_friendly():
    assert table_name("Orders 2026 (US).csv") == "Orders_2026_US"
    assert table_name("book.xlsx", "Sheet 1", multi_sheet=True) == "book_Sheet_1"


def test_csv_semicolon_and_values_kept_as_text():
    tables = read_tables("t.csv", b"id;amount;note\n007;1,5;  hi \n008;2;\n")
    sheet, df = tables["t"]
    assert sheet is None
    assert df["id"].tolist() == ["007", "008"]  # leading zeros preserved
    assert df["note"].iloc[0] == "hi"
    assert df["note"].isna().iloc[1]


def test_excel_multi_sheet_becomes_multiple_tables(sample_bytes):
    tables = read_tables("customers.xlsx", sample_bytes["customers.xlsx"])
    assert set(tables) == {"customers_Customers", "customers_Segments"}
    assert tables["customers_Customers"][1].shape == (123, 6)


def test_unreadable_file_raises_upload_error():
    with pytest.raises(UploadError):
        read_tables("broken.xlsx", b"not really excel")
