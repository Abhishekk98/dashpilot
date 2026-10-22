def _upload(api, project_id, files):
    return api.post(f"/api/projects/{project_id}/files", files=[("files", f) for f in files])


def test_full_upload_and_profile_flow(api, sample_bytes):
    project = api.post("/api/projects", json={"name": "Orders & Revenue Q1"}).json()
    pid = project["id"]
    assert project["name"] == "Orders & Revenue Q1" and project["files"] == []

    res = _upload(
        api,
        pid,
        [
            ("orders.csv", sample_bytes["orders.csv"], "text/csv"),
            ("customers.xlsx", sample_bytes["customers.xlsx"], "application/octet-stream"),
            ("products.csv", sample_bytes["products.csv"], "text/csv"),
            ("notes.txt", b"hello", "text/plain"),
        ],
    )
    body = res.json()
    assert res.status_code == 200
    assert len(body["project"]["files"]) == 3
    assert body["errors"] == ["notes.txt: only .csv, .xlsx and .xls files are supported"]
    excel = next(f for f in body["project"]["files"] if f["filename"] == "customers.xlsx")
    assert [t["name"] for t in excel["tables"]] == ["customers_Customers", "customers_Segments"]

    report = api.get(f"/api/projects/{pid}/profile").json()
    assert {t["name"] for t in report["tables"]} == {"orders", "customers_Customers", "customers_Segments", "products"}
    assert report["ai_refined"] is False
    assert report["label"] in ("Good Quality", "Fair Quality", "Needs Attention")

    csv_res = api.get(f"/api/projects/{pid}/profile/columns.csv")
    assert csv_res.status_code == 200
    assert csv_res.text.splitlines()[0].startswith("table,column,detected_type")

    # Removing a file invalidates the cached profile.
    products = next(f for f in body["project"]["files"] if f["filename"] == "products.csv")
    after = api.delete(f"/api/projects/{pid}/files/{products['id']}").json()
    assert len(after["files"]) == 2
    report = api.get(f"/api/projects/{pid}/profile").json()
    assert "products" not in {t["name"] for t in report["tables"]}


def test_upload_limits_and_missing_project(api):
    pid = api.post("/api/projects", json={}).json()["id"]
    too_big = b"a,b\n" + b"1,2\n" * 300_000  # > 1 MB test limit
    body = _upload(api, pid, [("big.csv", too_big, "text/csv")]).json()
    assert body["errors"] == ["big.csv: file is larger than 1 MB"]

    assert api.get("/api/projects/doesnotexist").status_code == 404
    assert api.get("/api/projects/../etc").status_code == 404
    assert api.delete(f"/api/projects/{pid}/files/nope").status_code == 404


def test_list_and_delete_projects(api):
    p1 = api.post("/api/projects", json={"name": "Alpha Project"}).json()
    p2 = api.post("/api/projects", json={"name": "Beta Project"}).json()
    
    projects = api.get("/api/projects").json()
    ids = [p["id"] for p in projects]
    assert p1["id"] in ids and p2["id"] in ids
    
    # Check ProjectSummary fields
    summary = next(p for p in projects if p["id"] == p1["id"])
    assert summary["name"] == "Alpha Project"
    assert summary["stage"] == 1
    assert "stage_label" in summary
    assert "files_count" in summary
    
    # Delete
    del_res = api.delete(f"/api/projects/{p1['id']}")
    assert del_res.status_code == 200
    assert api.get(f"/api/projects/{p1['id']}").status_code == 404
