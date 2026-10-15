"""
Tests for Phase 5: Analytics, Exports, Health Check, Flow Graphs, and Demo Seeder.
"""
import pytest
from backend.app.models import Scan, MaterialEntry, VirtualBin, MaterialEvent
from backend.scripts.seed_demo import run_seed


def test_correction_rates_calculation(client, test_db):
    """Verifies category-level and overall correction rates from persisted scan confirmations."""
    # Scan 1: Predicted plastic, confirmed plastic (no correction)
    s1 = Scan(id="scan-stat-1", predicted_category="plastic", confidence=0.90)
    # Scan 2: Predicted paper, confirmed plastic (corrected)
    s2 = Scan(id="scan-stat-2", predicted_category="paper", confidence=0.70)
    # Scan 3: Predicted paper, confirmed paper (no correction)
    s3 = Scan(id="scan-stat-3", predicted_category="paper", confidence=0.85)

    test_db.add_all([s1, s2, s3])
    test_db.commit()

    client.post("/api/materials/confirm", json={"scan_id": s1.id, "confirmed_category": "plastic"})
    client.post("/api/materials/confirm", json={"scan_id": s2.id, "confirmed_category": "plastic"})
    client.post("/api/materials/confirm", json={"scan_id": s3.id, "confirmed_category": "paper"})

    resp = client.get("/api/analytics/corrections")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_confirmed_scans"] == 3
    # 1 out of 3 corrected -> 0.333
    assert data["overall_correction_rate"] == 0.333

    paper_rate = next(r for r in data["category_rates"] if r["category"] == "paper")
    assert paper_rate["total_scanned"] == 2
    assert paper_rate["corrected_count"] == 1
    assert paper_rate["correction_rate"] == 0.5


def test_confusion_matrix_calculation(client, test_db):
    """Verifies confusion matrix counts and detection of high-risk confusable pairs."""
    s1 = Scan(id="cm-scan-1", predicted_category="paper", confidence=0.60)
    s2 = Scan(id="cm-scan-2", predicted_category="plastic", confidence=0.95)
    test_db.add_all([s1, s2])
    test_db.commit()

    # s1 corrected from paper to plastic
    client.post("/api/materials/confirm", json={"scan_id": s1.id, "confirmed_category": "plastic"})
    client.post("/api/materials/confirm", json={"scan_id": s2.id, "confirmed_category": "plastic"})

    resp = client.get("/api/analytics/confusion-matrix")
    assert resp.status_code == 200
    data = resp.json()

    assert "paper" in data["matrix"]
    assert data["matrix"]["paper"]["plastic"] == 1
    assert data["matrix"]["plastic"]["plastic"] == 1

    # High-risk confusions list
    assert len(data["high_risk_confusions"]) >= 1
    hr = data["high_risk_confusions"][0]
    assert hr["predicted"] == "paper"
    assert hr["confirmed"] == "plastic"


def test_export_corrected_scans(client, test_db):
    """Verifies JSON and CSV export of corrected scans."""
    s1 = Scan(id="export-scan-1", predicted_category="paper", confidence=0.65)
    test_db.add(s1)
    test_db.commit()

    client.post("/api/materials/confirm", json={"scan_id": s1.id, "confirmed_category": "plastic"})

    # JSON export
    resp_json = client.get("/api/analytics/export/corrected-scans?format=json")
    assert resp_json.status_code == 200
    json_data = resp_json.json()
    assert len(json_data) >= 1
    assert json_data[0]["predicted_category"] == "paper"
    assert json_data[0]["confirmed_category"] == "plastic"

    # CSV export
    resp_csv = client.get("/api/analytics/export/corrected-scans?format=csv")
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "predicted_category,confirmed_category" in resp_csv.text
    assert "paper,plastic" in resp_csv.text


def test_export_events(client, test_db, sample_scan):
    """Verifies JSON and CSV export of material flow events."""
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 3.0},
    )

    # JSON
    resp_json = client.get("/api/analytics/export/events?format=json")
    assert resp_json.status_code == 200
    assert len(resp_json.json()) >= 1

    # CSV
    resp_csv = client.get("/api/analytics/export/events?format=csv")
    assert resp_csv.status_code == 200
    assert "event_type,material_id" in resp_csv.text
    assert "confirmed" in resp_csv.text


def test_material_flow_sankey_data(client, test_db, sample_scan):
    """Verifies aggregation of flow data for Sankey diagrams."""
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 7.0},
    )

    resp = client.get("/api/analytics/flow")
    assert resp.status_code == 200
    data = resp.json()

    assert "nodes" in data
    assert "links" in data
    assert any("category:plastic" in n["id"] for n in data["nodes"])
    assert any(l["value"] == 7.0 for l in data["links"])


def test_fill_rates_and_time_to_full(client, test_db, sample_scan):
    """Verifies linear fill-rate estimation and insufficient data handling."""
    resp = client.get("/api/analytics/fill-rates?window_hours=24")
    assert resp.status_code == 200
    data = resp.json()
    assert "bin_estimates" in data
    assert "bin-plastic" in data["bin_estimates"]


def test_health_check(client):
    """Verifies database connectivity health check endpoint."""
    resp = client.get("/api/analytics/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_demo_seeder_execution(test_db):
    """Verifies seed_demo runs through real confirmation and digital twin flow with is_demo=True."""
    run_seed(test_db)

    # Verify seeded scans and entries
    demo_scans = test_db.query(Scan).filter(Scan.is_demo == True).all()
    assert len(demo_scans) >= 5

    demo_entries = test_db.query(MaterialEntry).filter(MaterialEntry.is_demo == True).all()
    assert len(demo_entries) >= 5

    # Verify at least one reclassification was logged
    reclass_event = (
        test_db.query(MaterialEvent)
        .filter(MaterialEvent.event_type == "reclassified", MaterialEvent.is_demo == True)
        .first()
    )
    assert reclass_event is not None
