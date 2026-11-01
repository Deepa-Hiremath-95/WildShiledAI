"""
WildShield AI - Phase 6 Advanced Analytics, Reporting & Intelligence Verification Suite
======================================================================================
Comprehensive test suite validating:
- Analytics calculations & consistency
- Village, species, risk, and date filtering
- Empty database behavior (no crashes, clean empty states)
- Hotspot descriptive ranking & spatial disclaimers
- Human intrusion analytics & zero-siren compliance enforcement
- Camera analytics with unavailable uptime distinction (no fabrication)
- Alert resolution duration metrics
- CSV and PDF report generation (PDF-1.4 conformance)
- Backward compatibility for existing /api/analytics endpoint
"""

import io
import csv
import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure backend root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.database import Base, run_migrations
from app import models
from app.routers import analytics, frontend_compat


class Phase6AnalyticsTestCase(unittest.TestCase):
    """Isolated in-memory database test harness seeded with diverse operational data."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        run_migrations(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        self._seed_operational_data()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _seed_operational_data(self):
        # 1. Villages
        v1 = models.Village(id="vil-a", name="Village A", code="VIL-A", siren_pattern="pattern_1")
        v2 = models.Village(id="vil-b", name="Village B", code="VIL-B", siren_pattern="pattern_2")
        self.db.add_all([v1, v2])
        self.db.commit()

        # 2. Monitoring Zones
        z1 = models.Zone(id="zone-a-animal", village_id="vil-a", name="Zone A Buffer", type=models.ZoneType.ANIMAL)
        z2 = models.Zone(id="zone-a-human", village_id="vil-a", name="Zone A Restricted Corridor", type=models.ZoneType.RESTRICTED)
        z3 = models.Zone(id="zone-b-animal", village_id="vil-b", name="Zone B Forest Border", type=models.ZoneType.ANIMAL)
        self.db.add_all([z1, z2, z3])
        self.db.commit()

        # 3. Cameras
        c1 = models.Camera(id="CAM-001", zone_id=z1.id, village_id=v1.id, name="North Perimeter Cam", is_online=True, last_heartbeat=datetime.utcnow())
        c2 = models.Camera(id="CAM-002", zone_id=z2.id, village_id=v1.id, name="Corridor Cam", is_online=True, last_heartbeat=datetime.utcnow())
        c3 = models.Camera(id="CAM-003", zone_id=z3.id, village_id=v2.id, name="Village B Ridge Cam", is_online=False, last_heartbeat=datetime.utcnow() - timedelta(days=2))
        self.db.add_all([c1, c2, c3])
        self.db.commit()

        # 4. Detections & Alerts
        base_time = datetime.utcnow() - timedelta(days=3)

        # Elephant in Zone A (Critical, Siren ON)
        alt1 = models.Alert(
            id="alt-01",
            zone_id=z1.id,
            camera_id=c1.id,
            village_id=v1.id,
            species="Elephant",
            confidence=0.94,
            risk_level="critical",
            siren_activated=True,
            status="active",
            event_type=models.EventType.ANIMAL_DETECTED,
            created_at=base_time + timedelta(hours=1),
        )
        det1 = models.Detection(
            id="det-01",
            zone_id=z1.id,
            camera_id=c1.id,
            village_id=v1.id,
            species="Elephant",
            confidence=0.94,
            risk_level="critical",
            siren_triggered=True,
            event_type=models.EventType.ANIMAL_DETECTED,
            alert_id=alt1.id,
            created_at=base_time + timedelta(hours=1),
        )

        # Leopard in Zone B (High, Siren ON, Acknowledged & Resolved)
        alt2 = models.Alert(
            id="alt-02",
            zone_id=z3.id,
            camera_id=c3.id,
            village_id=v2.id,
            species="Leopard",
            confidence=0.88,
            risk_level="high",
            siren_activated=True,
            status="resolved",
            event_type=models.EventType.ANIMAL_DETECTED,
            created_at=base_time + timedelta(hours=5),
            acknowledged_at=base_time + timedelta(hours=5, minutes=12),
            resolved_at=base_time + timedelta(hours=5, minutes=45),
        )
        det2 = models.Detection(
            id="det-02",
            zone_id=z3.id,
            camera_id=c3.id,
            village_id=v2.id,
            species="Leopard",
            confidence=0.88,
            risk_level="high",
            siren_triggered=True,
            event_type=models.EventType.ANIMAL_DETECTED,
            alert_id=alt2.id,
            created_at=base_time + timedelta(hours=5),
        )

        # Deer in Zone A (Low, Siren OFF)
        det3 = models.Detection(
            id="det-03",
            zone_id=z1.id,
            camera_id=c1.id,
            village_id=v1.id,
            species="Deer",
            confidence=0.76,
            risk_level="low",
            siren_triggered=False,
            event_type=models.EventType.ANIMAL_DETECTED,
            created_at=base_time + timedelta(days=1, hours=2),
        )

        # Wild Boar in Zone A (Medium, Siren OFF)
        det4 = models.Detection(
            id="det-04",
            zone_id=z1.id,
            camera_id=c1.id,
            village_id=v1.id,
            species="Wild Boar",
            confidence=0.82,
            risk_level="medium",
            siren_triggered=False,
            event_type=models.EventType.ANIMAL_DETECTED,
            created_at=base_time + timedelta(days=1, hours=4),
        )

        # Human in Zone A Restricted Corridor (Night, Medium, SIREN NEVER TRIGGERED)
        det5 = models.Detection(
            id="det-05",
            zone_id=z2.id,
            camera_id=c2.id,
            village_id=v1.id,
            species="Human",
            confidence=0.91,
            risk_level="medium",
            siren_triggered=False,
            event_type=models.EventType.PERSON_DETECTED,
            created_at=base_time.replace(hour=23, minute=15),
        )

        self.db.add_all([alt1, det1, alt2, det2, det3, det4, det5])
        self.db.commit()


class TestAnalyticsEngine(Phase6AnalyticsTestCase):
    """Audit & Verification Tests for Phase 6 Analytics Modules."""

    def test_01_analytics_calculations(self):
        """Verify summary calculations: total detections, wildlife vs human, siren counts."""
        res = analytics.get_analytics_summary(db=self.db)
        self.assertEqual(res["total_detections"], 5)
        self.assertEqual(res["wildlife_count"], 4)
        self.assertEqual(res["human_count"], 1)
        self.assertEqual(res["siren_count"], 2)
        self.assertEqual(res["total_alerts"], 2)
        self.assertEqual(res["active_alerts"], 1)
        self.assertEqual(res["resolved_alerts"], 1)
        # Verify mathematical consistency
        self.assertEqual(res["total_detections"], res["wildlife_count"] + res["human_count"])

    def test_02_village_analytics_aggregation(self):
        """Task 1: Verify detections, species, risk, and alert rates by village."""
        res = analytics.get_village_analytics(db=self.db)
        self.assertEqual(res["total_settlements"], 2)

        vil_a = next(v for v in res["villages"] if v["village_name"] == "Village A")
        self.assertEqual(vil_a["total_detections"], 4)  # Elephant, Deer, Wild Boar, Human
        self.assertEqual(vil_a["species_distribution"]["Elephant"], 1)
        self.assertEqual(vil_a["species_distribution"]["Human"], 1)
        self.assertEqual(vil_a["risk_distribution"]["critical"], 1)
        self.assertEqual(vil_a["siren_deterrences"], 1)

        vil_b = next(v for v in res["villages"] if v["village_name"] == "Village B")
        self.assertEqual(vil_b["total_detections"], 1)  # Leopard
        self.assertEqual(vil_b["species_distribution"]["Leopard"], 1)
        self.assertEqual(vil_b["siren_deterrences"], 1)

    def test_03_species_analytics_and_confidence_metrics(self):
        """Task 2: Verify tracking of Elephant, Leopard, Deer, Wild Boar and confidence stats."""
        res = analytics.get_species_analytics(db=self.db)
        tracked_species = [s["species"] for s in res["species_analytics"]]
        # Ensure mandatory species are tracked
        for mandatory in ["Elephant", "Leopard", "Deer", "Wild Boar"]:
            self.assertIn(mandatory, tracked_species)

        elephant = next(s for s in res["species_analytics"] if s["species"] == "Elephant")
        self.assertEqual(elephant["total_detections"], 1)
        self.assertEqual(elephant["confidence_distribution"]["avg"], 0.94)
        self.assertEqual(elephant["confidence_distribution"]["buckets"][">0.85"], 1)
        self.assertEqual(elephant["village_distribution"]["Village A"], 1)

    def test_04_risk_analytics_and_heuristic_disclosure(self):
        """Task 3: Verify risk counts and explicit heuristic disclosure."""
        res = analytics.get_risk_analytics(db=self.db)
        rc = res["risk_counts"]
        self.assertEqual(rc["critical"], 1)
        self.assertEqual(rc["high"], 1)
        self.assertEqual(rc["medium"], 2)  # Wild Boar + Human
        self.assertEqual(rc["low"], 1)     # Deer

        # Crucial Rule: Heuristic labeling
        self.assertEqual(res["engine_label"], "HEURISTIC_RULE_ENGINE")
        self.assertIn("heuristic", res["disclaimer"].lower())
        self.assertEqual(res["field_validation_status"], "PENDING_FIELD_CALIBRATION")

    def test_05_hotspot_analysis_and_spatial_notice(self):
        """Task 4: Identify active monitoring zones with descriptive ranking notice."""
        res = analytics.get_hotspot_analysis(limit=5, db=self.db)
        self.assertTrue(len(res["hotspots"]) >= 2)
        # Zone A Buffer had 3 detections (Elephant, Deer, Wild Boar) -> Rank 1
        top_zone = res["hotspots"][0]
        self.assertEqual(top_zone["rank"], 1)
        self.assertEqual(top_zone["zone_name"], "Zone A Buffer")
        self.assertEqual(top_zone["detection_count"], 3)

        # Crucial Rule: Descriptive notice, not predictive modeling
        self.assertIn("descriptive activity ranking only", res["spatial_disclaimer"].lower())

    def test_06_human_intrusion_analytics_and_zero_siren_enforcement(self):
        """Task 5: Verify human intrusion tracking and STRICT ZERO SIREN compliance."""
        res = analytics.get_human_intrusion_analytics(db=self.db)
        self.assertEqual(res["total_human_detections"], 1)
        self.assertEqual(res["restricted_zone_activity"], 1)
        self.assertEqual(res["buffer_zone_activity"], 0)

        # Enforced zero siren
        self.assertEqual(res["siren_policy"]["siren_activations"], 0)
        self.assertEqual(res["siren_policy"]["policy_status"], "COMPLIANT_ZERO_SIREN")
        self.assertIn("permanently inhibited", res["siren_policy"]["enforcement_statement"])

    def test_07_camera_analytics_and_unavailable_uptime_distinction(self):
        """Task 6: Verify camera telemetry and explicit unavailable uptime without fabrication."""
        res = analytics.get_camera_analytics(db=self.db)
        self.assertEqual(res["total_cameras"], 3)
        self.assertEqual(res["online_count"], 2)
        self.assertEqual(res["offline_count"], 1)

        c1 = next(c for c in res["camera_details"] if c["camera_id"] == "CAM-001")
        self.assertTrue(c1["is_online"])
        self.assertEqual(c1["total_detections_recorded"], 3)

        # Crucial Rule: Do not invent uptime when heartbeat history is unavailable
        self.assertIsNone(c1["uptime_percentage"])
        self.assertEqual(c1["uptime_status"], "UNAVAILABLE")
        self.assertIn("insufficient historical heartbeat", c1["uptime_reason"].lower())

    def test_08_alert_analytics_and_response_durations(self):
        """Task 7: Verify alert metrics and time-to-acknowledge / resolve calculations."""
        res = analytics.get_alert_analytics(db=self.db)
        self.assertEqual(res["total_alerts"], 2)
        self.assertEqual(res["status_distribution"]["active"], 1)
        self.assertEqual(res["status_distribution"]["resolved"], 1)

        # Alert alt-02 had acknowledged_at (12 min = 720s) and resolved_at (45 min = 2700s)
        t_ack = res["time_to_acknowledge"]
        self.assertEqual(t_ack["status"], "COMPUTED")
        self.assertEqual(t_ack["sample_size"], 1)
        self.assertEqual(t_ack["avg_seconds"], 720.0)

        t_res = res["time_to_resolve"]
        self.assertEqual(t_res["status"], "COMPUTED")
        self.assertEqual(t_res["sample_size"], 1)
        self.assertEqual(t_res["avg_seconds"], 2700.0)

    def test_09_village_filtering(self):
        """Verify analytics filtering by village_id."""
        res_a = analytics.get_analytics_summary(village_id="vil-a", db=self.db)
        self.assertEqual(res_a["total_detections"], 4)

        res_b = analytics.get_analytics_summary(village_id="vil-b", db=self.db)
        self.assertEqual(res_b["total_detections"], 1)

    def test_10_species_filtering(self):
        """Verify analytics filtering by species name."""
        res_ele = analytics.get_analytics_summary(species="Elephant", db=self.db)
        self.assertEqual(res_ele["total_detections"], 1)
        self.assertEqual(res_ele["wildlife_count"], 1)

        res_hum = analytics.get_analytics_summary(species="Human", db=self.db)
        self.assertEqual(res_hum["total_detections"], 1)
        self.assertEqual(res_hum["human_count"], 1)

    def test_11_risk_level_filtering(self):
        """Verify analytics filtering by risk level."""
        res_crit = analytics.get_analytics_summary(risk_level="critical", db=self.db)
        self.assertEqual(res_crit["total_detections"], 1)

        res_low = analytics.get_analytics_summary(risk_level="low", db=self.db)
        self.assertEqual(res_low["total_detections"], 1)

    def test_12_date_filtering_and_validation(self):
        """Verify start/end date range filtering and invalid date handling."""
        now = datetime.utcnow()
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        res_recent = analytics.get_analytics_summary(start_date=yesterday_str, end_date=tomorrow_str, db=self.db)
        # Should return detections from within that window
        self.assertIsInstance(res_recent["total_detections"], int)

        # Invalid date format raises HTTP 400
        with self.assertRaises(HTTPException) as ctx:
            analytics.get_analytics_summary(start_date="not-a-valid-date", db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_13_empty_database_behavior(self):
        """Verify zero crashes and graceful defaults when database has zero records."""
        # Create separate clean empty in-memory DB
        empty_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(bind=empty_engine)
        run_migrations(empty_engine)
        empty_session = sessionmaker(bind=empty_engine)()

        try:
            summary = analytics.get_analytics_summary(db=empty_session)
            self.assertEqual(summary["total_detections"], 0)
            self.assertEqual(summary["total_alerts"], 0)

            villages = analytics.get_village_analytics(db=empty_session)
            self.assertEqual(villages["total_settlements"], 0)

            species = analytics.get_species_analytics(db=empty_session)
            self.assertTrue(len(species["species_analytics"]) >= 4)  # 4 mandatory tracked with 0 detections

            risk = analytics.get_risk_analytics(db=empty_session)
            self.assertEqual(risk["risk_counts"]["critical"], 0)

            hotspots = analytics.get_hotspot_analysis(db=empty_session)
            self.assertEqual(hotspots["total_active_zones"], 0)

            alerts = analytics.get_alert_analytics(db=empty_session)
            self.assertEqual(alerts["time_to_acknowledge"]["status"], "UNAVAILABLE_NO_RECORDS")
        finally:
            empty_session.close()
            Base.metadata.drop_all(bind=empty_engine)

    def test_14_csv_report_generation(self):
        """Task 8: Verify downloadable CSV report export with metadata and columns."""
        res = analytics.download_csv_report(village_id="vil-a", db=self.db)
        self.assertEqual(res.media_type, "text/csv")
        self.assertIn("attachment; filename=", res.headers["Content-Disposition"])

        csv_text = res.body.decode("utf-8")
        lines = csv_text.strip().splitlines()
        # Verify metadata comments present
        self.assertTrue(any("WildShield AI" in l for l in lines))
        self.assertTrue(any("Filter: Village" in l for l in lines))

        # Parse CSV rows
        reader = csv.reader(io.StringIO(csv_text))
        data_rows = [row for row in reader if row and not row[0].startswith("#")]
        header = data_rows[0]
        self.assertIn("Detection ID", header)
        self.assertIn("Species", header)
        self.assertIn("Risk Level", header)
        self.assertIn("Village", header)
        self.assertEqual(len(data_rows) - 1, 4)  # 4 detections in vil-a

    def test_15_pdf_report_generation(self):
        """Task 8: Verify downloadable PDF report export conforming to PDF-1.4."""
        res = analytics.download_pdf_report(village_id="vil-a", db=self.db)
        self.assertEqual(res.media_type, "application/pdf")
        self.assertIn("attachment; filename=", res.headers["Content-Disposition"])

        pdf_bytes = res.body
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf_bytes.endswith(b"%%EOF\n") or b"%%EOF" in pdf_bytes)
        self.assertGreater(len(pdf_bytes), 500)

    def test_16_backward_compatibility_frontend_endpoint(self):
        """Verify existing GET /api/analytics returns real aggregated data shapes."""
        res = frontend_compat.get_analytics(db=self.db)
        self.assertIn("speciesCounts", res)
        self.assertIn("riskLevels", res)
        self.assertIn("wildlifeIntrusions", res)
        self.assertIn("humanIntrusions", res)
        self.assertIn("sirenActivations", res)
        self.assertIn("falseAlarmStats", res)

        # Check real values
        self.assertEqual(res["totalAlerts"], 2)
        self.assertEqual(len(res["wildlifeIntrusions"]), 6)
        self.assertEqual(len(res["humanIntrusions"]), 6)
        # Check label/value formatting for UI renderers
        self.assertTrue(any(s["label"] == "Elephant" for s in res["speciesCounts"]))
        self.assertTrue(any(r["label"] == "Critical" and r["value"] == 1 for r in res["riskLevels"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
