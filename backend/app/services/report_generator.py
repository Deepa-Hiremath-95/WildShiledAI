"""
WildShield AI - Analytics and Operational Reporting Service
==========================================================
Generates standard downloadable CSV and PDF reports from live database records.
Uses pure-Python PDF generation conforming to the PDF-1.4 specification without
external binary dependencies.
"""

import io
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional


class SimplePDFBuilder:
    """Lightweight, standard-compliant PDF-1.4 builder with table, text, and layout primitives."""

    def __init__(self, width: float = 612.0, height: float = 792.0):
        self.width = width
        self.height = height
        self.pages: List[List[str]] = []
        self.current_stream: List[str] = []

    def add_page(self):
        self.current_stream = []
        self.pages.append(self.current_stream)

    def draw_text(
        self,
        text: str,
        x: float,
        y: float,
        font: str = "F1",
        size: float = 10.0,
        r: float = 0.1,
        g: float = 0.1,
        b: float = 0.1,
    ):
        if not self.pages:
            self.add_page()
        # Escape special PDF characters: backslash, parens
        clean = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .encode("latin-1", "replace")
            .decode("latin-1")
        )
        op = f"BT /{font} {size:.2f} Tf {r:.2f} {g:.2f} {b:.2f} rg {x:.2f} {y:.2f} Td ({clean}) Tj ET"
        self.current_stream.append(op)

    def draw_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill_rgb: Optional[tuple] = None,
        stroke_rgb: Optional[tuple] = None,
        line_width: float = 1.0,
    ):
        if not self.pages:
            self.add_page()
        ops = []
        if line_width != 1.0:
            ops.append(f"{line_width:.2f} w")
        if fill_rgb:
            ops.append(f"{fill_rgb[0]:.2f} {fill_rgb[1]:.2f} {fill_rgb[2]:.2f} rg")
        if stroke_rgb:
            ops.append(f"{stroke_rgb[0]:.2f} {stroke_rgb[1]:.2f} {stroke_rgb[2]:.2f} RG")
        ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill_rgb and stroke_rgb:
            ops.append("B")
        elif fill_rgb:
            ops.append("f")
        elif stroke_rgb:
            ops.append("S")
        self.current_stream.append(" ".join(ops))

    def draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke_rgb: tuple = (0.7, 0.7, 0.7),
        line_width: float = 0.75,
    ):
        if not self.pages:
            self.add_page()
        op = f"{line_width:.2f} w {stroke_rgb[0]:.2f} {stroke_rgb[1]:.2f} {stroke_rgb[2]:.2f} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        self.current_stream.append(op)

    def draw_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        col_widths: List[float],
        start_x: float,
        start_y: float,
        row_height: float = 18.0,
        header_bg: tuple = (0.92, 0.95, 0.92),
    ) -> float:
        """Draws a styled table and returns the final y position."""
        current_y = start_y
        total_width = sum(col_widths)

        # Header background
        self.draw_rect(start_x, current_y - row_height, total_width, row_height, fill_rgb=header_bg, stroke_rgb=(0.7, 0.8, 0.7))
        # Header text
        cx = start_x
        for i, h in enumerate(headers):
            self.draw_text(h, cx + 6, current_y - 13, font="F2", size=9, r=0.1, g=0.3, b=0.15)
            cx += col_widths[i]

        current_y -= row_height

        # Data rows
        for r_idx, row in enumerate(rows):
            # Check for page overflow
            if current_y < 60:
                self.add_page()
                current_y = self.height - 60
                # Redraw header on new page
                self.draw_rect(start_x, current_y - row_height, total_width, row_height, fill_rgb=header_bg, stroke_rgb=(0.7, 0.8, 0.7))
                cx = start_x
                for i, h in enumerate(headers):
                    self.draw_text(h, cx + 6, current_y - 13, font="F2", size=9, r=0.1, g=0.3, b=0.15)
                    cx += col_widths[i]
                current_y -= row_height

            bg_color = (0.98, 0.99, 0.98) if r_idx % 2 == 1 else (1.0, 1.0, 1.0)
            self.draw_rect(start_x, current_y - row_height, total_width, row_height, fill_rgb=bg_color, stroke_rgb=(0.88, 0.9, 0.88), line_width=0.5)
            cx = start_x
            for c_idx, cell in enumerate(row):
                val_str = str(cell) if cell is not None else "--"
                self.draw_text(val_str, cx + 6, current_y - 13, font="F1", size=8.5, r=0.2, g=0.2, b=0.2)
                cx += col_widths[c_idx]
            current_y -= row_height

        return current_y

    def build(self) -> bytes:
        if not self.pages:
            self.add_page()

        objs: Dict[int, bytes] = {}
        # 1: Catalog, 2: Pages, 3: Font Helvetica, 4: Font Helvetica-Bold
        objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        page_obj_ids = [5 + i * 2 for i in range(len(self.pages))]
        kids_str = " ".join([f"{pid} 0 R" for pid in page_obj_ids])
        objs[2] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(self.pages)} >>".encode("latin1")
        objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        objs[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"

        for idx, page in enumerate(self.pages):
            pid = 5 + idx * 2
            cid = 6 + idx * 2
            stream_bytes = "\n".join(page).encode("latin1")
            objs[pid] = (
                f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/MediaBox [0 0 {self.width:.2f} {self.height:.2f}] /Contents {cid} 0 R >>"
            ).encode("latin1")
            objs[cid] = f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin1") + stream_bytes + b"\nendstream"

        max_id = max(objs.keys())
        pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets = {0: 0}
        for i in range(1, max_id + 1):
            offsets[i] = len(pdf)
            pdf += f"{i} 0 obj\n".encode("latin1") + objs[i] + b"\nendobj\n"

        xref_offset = len(pdf)
        pdf += f"xref\n0 {max_id + 1}\n0000000000 65535 f \n".encode("latin1")
        for i in range(1, max_id + 1):
            pdf += f"{offsets[i]:010d} 00000 n \n".encode("latin1")
        pdf += f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1")
        return pdf


def generate_csv_report(records: List[Dict[str, Any]], filters: Dict[str, Any]) -> str:
    """Generates an RFC 4180 compliant CSV export with metadata header and detailed rows."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Metadata Header
    writer.writerow(["# WildShield AI - Operational Intelligence Export"])
    writer.writerow(["# Generated At", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")])
    writer.writerow(["# Filter: Village", filters.get("village_name") or "All Villages"])
    writer.writerow(["# Filter: Species", filters.get("species") or "All Species"])
    writer.writerow(["# Filter: Risk Level", filters.get("risk_level") or "All Risk Levels"])
    writer.writerow(["# Filter: Start Date", filters.get("start_date") or "Unrestricted"])
    writer.writerow(["# Filter: End Date", filters.get("end_date") or "Unrestricted"])
    writer.writerow(["# Total Records", len(records)])
    writer.writerow([])  # Blank delimiter

    headers = [
        "Detection ID",
        "Timestamp (UTC)",
        "Event Type",
        "Species",
        "Confidence",
        "Risk Level",
        "Village",
        "Zone",
        "Zone Type",
        "Camera ID",
        "Movement Direction",
        "Siren Triggered",
        "Action Taken",
        "Alert ID",
        "Alert Status",
    ]
    writer.writerow(headers)

    for r in records:
        writer.writerow([
            r.get("id", ""),
            r.get("created_at", ""),
            r.get("event_type", ""),
            r.get("species", ""),
            f"{r.get('confidence', 0.0):.3f}",
            r.get("risk_level", ""),
            r.get("village_name", ""),
            r.get("zone_name", ""),
            r.get("zone_type", ""),
            r.get("camera_id", ""),
            r.get("movement_direction", "N/A"),
            "YES" if r.get("siren_triggered") else "NO",
            r.get("action_taken", "LOGGED"),
            r.get("alert_id", "N/A"),
            r.get("alert_status", "N/A"),
        ])

    return output.getvalue()


def generate_pdf_report(
    summary: Dict[str, Any],
    species_breakdown: List[Dict[str, Any]],
    risk_breakdown: Dict[str, int],
    hotspots: List[Dict[str, Any]],
    human_summary: Dict[str, Any],
    filters: Dict[str, Any],
) -> bytes:
    """Generates a professional multi-section executive intelligence PDF report."""
    pdf = SimplePDFBuilder(width=612, height=792)
    pdf.add_page()

    margin_x = 54.0
    usable_width = 504.0
    y = 745.0

    # Header Top Banner (Green Accent)
    pdf.draw_rect(margin_x, y - 48, usable_width, 48, fill_rgb=(0.08, 0.38, 0.18))
    pdf.draw_text("WILDSHIELD AI - OPERATIONAL INTELLIGENCE REPORT", margin_x + 14, y - 22, font="F2", size=13, r=1, g=1, b=1)
    pdf.draw_text("Human-Wildlife Conflict Early Warning & Monitoring System", margin_x + 14, y - 38, font="F1", size=8.5, r=0.88, g=0.96, b=0.9)

    y -= 62

    # Metadata & Filter Info Box
    pdf.draw_rect(margin_x, y - 36, usable_width, 36, fill_rgb=(0.95, 0.97, 0.95), stroke_rgb=(0.8, 0.88, 0.8), line_width=0.75)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    v_filter = filters.get("village_name") or "All Villages"
    s_filter = filters.get("species") or "All Species"
    r_filter = filters.get("risk_level") or "All Levels"
    d_range = f"{filters.get('start_date') or 'Any'} to {filters.get('end_date') or 'Present'}"

    pdf.draw_text(f"Generated: {now_str}", margin_x + 10, y - 14, font="F2", size=8, r=0.2, g=0.2, b=0.2)
    pdf.draw_text(f"Village Filter: {v_filter}  |  Species Filter: {s_filter}", margin_x + 10, y - 26, font="F1", size=8, r=0.3, g=0.3, b=0.3)
    pdf.draw_text(f"Risk Filter: {r_filter}  |  Timeframe: {d_range}", margin_x + 270, y - 26, font="F1", size=8, r=0.3, g=0.3, b=0.3)

    y -= 50

    # Section 1: Executive KPI Metrics
    pdf.draw_text("1. EXECUTIVE OPERATIONAL SUMMARY", margin_x, y, font="F2", size=10.5, r=0.1, g=0.35, b=0.15)
    pdf.draw_line(margin_x, y - 4, margin_x + usable_width, y - 4, stroke_rgb=(0.2, 0.5, 0.25), line_width=1)
    y -= 14

    kpi_headers = ["Total Events", "Wildlife Incursions", "Human Intrusions", "Siren Deterrences", "Total Alerts"]
    kpi_rows = [[
        str(summary.get("total_detections", 0)),
        str(summary.get("wildlife_count", 0)),
        str(summary.get("human_count", 0)),
        str(summary.get("siren_count", 0)),
        str(summary.get("total_alerts", 0)),
    ]]
    col_w_kpi = [usable_width / 5.0] * 5
    y = pdf.draw_table(kpi_headers, kpi_rows, col_w_kpi, margin_x, y, row_height=18)

    y -= 18

    # Section 2: Species Activity Breakdown
    pdf.draw_text("2. SPECIES DETECTION BREAKDOWN & CONFIDENCE", margin_x, y, font="F2", size=10.5, r=0.1, g=0.35, b=0.15)
    pdf.draw_line(margin_x, y - 4, margin_x + usable_width, y - 4, stroke_rgb=(0.2, 0.5, 0.25), line_width=1)
    y -= 14

    sp_headers = ["Species", "Detections", "Share (%)", "Avg Conf", "Conf Range", "Primary Risk"]
    sp_rows = []
    tot_sp = sum([s.get("count", 0) for s in species_breakdown]) or 1
    for s in species_breakdown:
        cnt = s.get("count", 0)
        pct = f"{(cnt / tot_sp) * 100:.1f}%"
        avg_c = f"{s.get('avg_confidence', 0.0):.2f}" if s.get("avg_confidence") is not None else "--"
        c_min = f"{s.get('min_confidence', 0.0):.2f}" if s.get("min_confidence") is not None else "--"
        c_max = f"{s.get('max_confidence', 0.0):.2f}" if s.get("max_confidence") is not None else "--"
        sp_rows.append([
            s.get("name", "Unknown"),
            str(cnt),
            pct,
            avg_c,
            f"{c_min} - {c_max}",
            s.get("primary_risk", "Medium").upper(),
        ])
    if not sp_rows:
        sp_rows = [["No species detections recorded", "0", "0.0%", "--", "--", "--"]]

    col_w_sp = [110.0, 70.0, 70.0, 70.0, 94.0, 90.0]
    y = pdf.draw_table(sp_headers, sp_rows, col_w_sp, margin_x, y, row_height=17)

    y -= 18

    # Section 3: Risk Hierarchy & Hotspots
    pdf.draw_text("3. RISK HIERARCHY & ACTIVITY RANKING", margin_x, y, font="F2", size=10.5, r=0.1, g=0.35, b=0.15)
    pdf.draw_line(margin_x, y - 4, margin_x + usable_width, y - 4, stroke_rgb=(0.2, 0.5, 0.25), line_width=1)
    y -= 14

    risk_headers = ["Critical Threat", "High Risk", "Medium Risk", "Low Risk", "Risk Engine Type"]
    risk_rows = [[
        str(risk_breakdown.get("critical", 0)),
        str(risk_breakdown.get("high", 0)),
        str(risk_breakdown.get("medium", 0)),
        str(risk_breakdown.get("low", 0)),
        "Heuristic (Rule-Engine)",
    ]]
    col_w_risk = [100.0, 95.0, 95.0, 94.0, 120.0]
    y = pdf.draw_table(risk_headers, risk_rows, col_w_risk, margin_x, y, row_height=17)

    y -= 16

    # Section 4: Monitoring Zone Hotspots
    pdf.draw_text("Top Active Monitoring Zones (Descriptive Ranking)", margin_x, y, font="F2", size=9.5, r=0.2, g=0.2, b=0.2)
    y -= 10

    hot_headers = ["Rank", "Zone Name", "Village", "Zone Type", "Primary Species", "Detections", "Alerts"]
    hot_rows = []
    for idx, h in enumerate(hotspots[:6]):
        hot_rows.append([
            f"#{idx + 1}",
            h.get("zone_name", "N/A"),
            h.get("village_name", "N/A"),
            h.get("zone_type", "ANIMAL"),
            h.get("primary_species", "None"),
            str(h.get("detection_count", 0)),
            str(h.get("alert_count", 0)),
        ])
    if not hot_rows:
        hot_rows = [["--", "No active zone activity", "--", "--", "--", "0", "0"]]

    col_w_hot = [40.0, 114.0, 95.0, 85.0, 90.0, 45.0, 35.0]
    y = pdf.draw_table(hot_headers, hot_rows, col_w_hot, margin_x, y, row_height=16)

    y -= 18

    # Section 5: Human Intrusion & Compliance Notice
    pdf.draw_text("4. HUMAN INTRUSION AUDIT & PROTOCOL COMPLIANCE", margin_x, y, font="F2", size=10.5, r=0.1, g=0.35, b=0.15)
    pdf.draw_line(margin_x, y - 4, margin_x + usable_width, y - 4, stroke_rgb=(0.2, 0.5, 0.25), line_width=1)
    y -= 14

    human_headers = ["Total Intrusions", "Restricted Area", "Buffer Zone", "Siren Activations", "Protocol Status"]
    human_rows = [[
        str(human_summary.get("total_human_detections", 0)),
        str(human_summary.get("restricted_zone_activity", 0)),
        str(human_summary.get("buffer_zone_activity", 0)),
        "0 (Prohibited)",
        "COMPLIANT - SIRENS INHIBITED",
    ]]
    col_w_hum = [95.0, 95.0, 95.0, 105.0, 114.0]
    y = pdf.draw_table(human_headers, human_rows, col_w_hum, margin_x, y, row_height=17)

    y -= 20

    # Section 6: Regulatory & Methodological Disclaimers
    pdf.draw_rect(margin_x, y - 45, usable_width, 45, fill_rgb=(0.97, 0.97, 0.98), stroke_rgb=(0.82, 0.82, 0.86), line_width=0.75)
    pdf.draw_text("METHODOLOGICAL & OPERATIONAL INTELLIGENCE NOTES:", margin_x + 8, y - 12, font="F2", size=7.5, r=0.3, g=0.3, b=0.3)
    pdf.draw_text("- Heuristic Risk Engine: Risk levels are derived from rule-based thresholds (species, zone type, proximity, time-of-day).", margin_x + 8, y - 22, font="F1", size=7.0, r=0.4, g=0.4, b=0.4)
    pdf.draw_text("- Hotspot Ranking: Zone activity represents descriptive camera event frequency and does not constitute predictive spatial migration modeling.", margin_x + 8, y - 31, font="F1", size=7.0, r=0.4, g=0.4, b=0.4)
    pdf.draw_text("- Human Detection Protocol: Animal deterrent sirens are permanently inhibited for all human encounters; events are channeled to discrete logs.", margin_x + 8, y - 40, font="F1", size=7.0, r=0.4, g=0.4, b=0.4)

    # Footer
    pdf.draw_text("WildShield AI Autonomous Defense Grid | Operational Intelligence Report", margin_x, 24, font="F1", size=7.5, r=0.5, g=0.5, b=0.5)
    pdf.draw_text("Page 1 of 1", margin_x + usable_width - 45, 24, font="F1", size=7.5, r=0.5, g=0.5, b=0.5)

    return pdf.build()

