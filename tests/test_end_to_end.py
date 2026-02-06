"""End-to-end smoke test: create synthetic CSV + XLSX, run CLI, verify outputs."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from io_crosscheck.main import main


def _create_plc_csv(path: Path) -> None:
    """Create a minimal RSLogix 5000-style CSV tag export."""
    with open(path, "w", newline="", encoding="latin-1") as f:
        w = csv.writer(f)
        w.writerow(["TYPE", "SCOPE", "NAME", "DESCRIPTION", "DATATYPE", "SPECIFIER", "ATTRIBUTES"])
        # Rack IO tags
        w.writerow(["TAG", "", "Rack0:I", "", "AB:1756_IF8:I:0", "", ""])
        w.writerow(["TAG", "", "Rack0:O", "", "AB:1756_OB16E:O:0", "", ""])
        w.writerow(["TAG", "", "Rack11:I", "", "AB:1756_IF8:I:0", "", ""])
        # PLC5-format rack tag
        w.writerow(["TAG", "", "Rack0_Group0_Slot0_IO", "", "AB:1771_IFE:I:0", "", ""])
        # COMMENT records
        w.writerow(["COMMENT", "", "Rack0:I", "HLSTL5A", "", "Rack0:I.DATA[5].7", ""])
        w.writerow(["COMMENT", "", "Rack0:I", "HLSTL5C", "", "Rack0:I.DATA[5].6", ""])
        w.writerow(["COMMENT", "", "Rack0:I", "TSV22", "", "Rack0:I.DATA[0].0", ""])
        # ENet tags
        w.writerow(["TAG", "", "E300_P621:I", "", "AB:E300_OL:I:0", "", ""])
        w.writerow(["TAG", "", "E300_P9203:I", "", "AB:E300_OL:I:0", "", ""])
        w.writerow(["TAG", "", "VFD_M101:O", "", "AB:PF525:O:0", "", ""])
        # Program tags
        w.writerow(["TAG", "MainProgram", "MyCounter", "", "DINT", "", ""])
        w.writerow(["TAG", "MainProgram", "LT6110_Monitor", "", "DINT", "", ""])


def _create_io_xlsx(path: Path) -> None:
    """Create a minimal IO List XLSX."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ESCO List"
    headers = [
        "Panel", "Rack", "Group", "Slot", "Channel",
        "PLC IO Address", "IO Tag", "Device Tag",
        "Module Type", "Module", "Range Low", "Range High", "Units",
    ]
    ws.append(headers)
    # CLX device — Strategy 1 match (case-insensitive address)
    ws.append(["X1", "0", "", "5", "7", "Rack0:I.Data[5].7", "HLSTL5A", "HLSTL5A", "DI", "", "", "", ""])
    # CLX device — Strategy 1 conflict (address matches, name differs)
    ws.append(["X1", "0", "", "5", "6", "Rack0:I.Data[5].6", "FT656B_Pulse", "FT656B", "DI", "", "", "", ""])
    # PLC5 device — Strategy 2 match
    ws.append(["X1", "0", "0", "0", "4", "Rack0_Group0_Slot0_IO.READ[4]", "TSV22_EV", "TSV22", "DO", "", "", "", ""])
    # CLX device — Strategy 3 rack-only match (no COMMENT at this address)
    ws.append(["X1", "0", "", "6", "0", "Rack0:I.Data[6].0", "AS611_AUX", "AS611", "DI", "", "", "", ""])
    # ENet device — Strategy 4 match
    ws.append(["X2", "", "", "", "", "", "P621", "P621", "", "", "", "", ""])
    # Spare point
    ws.append(["X1", "0", "0", "0", "14", "Rack0_Group0_Slot0_IO.READ[14]", "Spare", "", "DI", "", "", "", ""])
    # Suffix stripping — Strategy 5 match (TSV22_EV → TSV22 matches COMMENT)
    ws.append(["X1", "0", "", "", "", "", "P611_MC", "P611", "", "", "", "", ""])
    # Substring safety — LT611 should NOT match LT6110_Monitor
    ws.append(["X1", "", "", "", "", "Rack99:I.Data[0].0", "LT611", "LT611", "AI", "", "", "", ""])
    # IO List Only — no match anywhere
    ws.append(["X3", "", "", "", "", "Rack99:I.Data[9].9", "PHANTOM", "PHANTOM", "DI", "", "", "", ""])

    wb.save(str(path))


class TestEndToEnd:

    def test_cli_runs_and_generates_reports(self, tmp_path):
        csv_path = tmp_path / "tags.csv"
        xlsx_path = tmp_path / "io_list.xlsx"
        output_dir = tmp_path / "output"

        _create_plc_csv(csv_path)
        _create_io_xlsx(xlsx_path)

        rc = main([
            str(csv_path),
            str(xlsx_path),
            "-o", str(output_dir),
            "--sheet", "ESCO List",
            "--encoding", "latin-1",
        ])

        assert rc == 0
        assert (output_dir / "io_crosscheck_report.xlsx").exists()
        assert (output_dir / "io_crosscheck_report.html").exists()

    def test_cli_xlsx_only(self, tmp_path):
        csv_path = tmp_path / "tags.csv"
        xlsx_path = tmp_path / "io_list.xlsx"
        output_dir = tmp_path / "output"

        _create_plc_csv(csv_path)
        _create_io_xlsx(xlsx_path)

        rc = main([
            str(csv_path), str(xlsx_path),
            "-o", str(output_dir), "--xlsx-only",
        ])
        assert rc == 0
        assert (output_dir / "io_crosscheck_report.xlsx").exists()
        assert not (output_dir / "io_crosscheck_report.html").exists()

    def test_cli_missing_file(self, tmp_path):
        rc = main([
            str(tmp_path / "nonexistent.csv"),
            str(tmp_path / "nonexistent.xlsx"),
        ])
        assert rc == 1

    def test_classifications_correct(self, tmp_path):
        """Verify the synthetic data produces expected classifications."""
        csv_path = tmp_path / "tags.csv"
        xlsx_path = tmp_path / "io_list.xlsx"

        _create_plc_csv(csv_path)
        _create_io_xlsx(xlsx_path)

        from io_crosscheck.parsers import parse_plc_csv, parse_io_list_xlsx
        from io_crosscheck.classifiers import classify_tag
        from io_crosscheck.strategies import MatchingEngine
        from io_crosscheck.models import Classification

        plc_tags = parse_plc_csv(csv_path, encoding="latin-1")
        for t in plc_tags:
            t.category = classify_tag(t)
        io_devices = parse_io_list_xlsx(xlsx_path)

        engine = MatchingEngine()
        results = engine.run(io_devices, plc_tags)

        # Build a lookup by io_tag
        by_tag = {}
        for r in results:
            if r.io_device and r.io_device.io_tag:
                by_tag[r.io_device.io_tag] = r

        # Strategy 1: case-insensitive address match
        assert by_tag["HLSTL5A"].classification == Classification.BOTH
        assert by_tag["HLSTL5A"].strategy_id == 1

        # Strategy 1: conflict
        assert by_tag["FT656B_Pulse"].classification == Classification.CONFLICT

        # Strategy 2: PLC5 match
        assert by_tag["TSV22_EV"].classification == Classification.BOTH
        assert by_tag["TSV22_EV"].strategy_id == 2

        # No comment match — falls through to IO List Only
        assert by_tag["AS611_AUX"].classification == Classification.IO_LIST_ONLY

        # Strategy 4: ENet
        assert by_tag["P621"].classification == Classification.BOTH
        assert by_tag["P621"].strategy_id == 4

        # Spare
        assert by_tag["Spare"].classification == Classification.SPARE

        # Substring safety: LT611 must NOT match LT6110_Monitor
        assert by_tag["LT611"].classification == Classification.IO_LIST_ONLY

        # IO List Only
        assert by_tag["PHANTOM"].classification == Classification.IO_LIST_ONLY

        # PLC Only: E300_P9203 and VFD_M101 should be PLC Only
        plc_only = [r for r in results if r.classification == Classification.PLC_ONLY]
        plc_only_names = {r.plc_tag.name for r in plc_only if r.plc_tag}
        assert "E300_P9203:I" in plc_only_names
        assert "VFD_M101:O" in plc_only_names
