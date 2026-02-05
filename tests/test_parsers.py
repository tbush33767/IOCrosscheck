"""Tests for PLC CSV and IO List XLSX parsers."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from io_crosscheck.models import PLCTag, IODevice, RecordType, AddressFormat
from io_crosscheck.parsers import parse_plc_csv, parse_io_list_xlsx


# ---------------------------------------------------------------------------
# CSV Parser Tests
# ---------------------------------------------------------------------------

class TestParsePLCCSV:
    """Tests for RSLogix 5000 CSV tag export parsing."""

    def _write_csv(self, lines: list[str], encoding: str = "utf-8") -> Path:
        """Helper to write CSV lines to a temp file."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding=encoding, newline=""
        )
        for line in lines:
            tmp.write(line + "\n")
        tmp.close()
        return Path(tmp.name)

    def test_parse_tag_record(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,,Rack0:I,,AB:1756_IF8:I:0,,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        assert len(tags) >= 1
        tag = [t for t in tags if t.name == "Rack0:I"][0]
        assert tag.record_type == RecordType.TAG
        assert tag.datatype == "AB:1756_IF8:I:0"

    def test_parse_comment_record(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'COMMENT,,Rack0:I,HLSTL5A,,Rack0:I.DATA[5].7,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        comments = [t for t in tags if t.record_type == RecordType.COMMENT]
        assert len(comments) >= 1
        assert comments[0].description == "HLSTL5A"
        assert comments[0].specifier == "Rack0:I.DATA[5].7"

    def test_parse_alias_record(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'ALIAS,,Local:1:I.Data.0,,,Rack25:1:I.Data.0,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        aliases = [t for t in tags if t.record_type == RecordType.ALIAS]
        assert len(aliases) >= 1

    def test_base_name_extraction(self):
        """Base name should strip :I, :O, :C, :S suffixes."""
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,,E300_P621:I,,AB:E300_OL:I:0,,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        tag = [t for t in tags if t.name == "E300_P621:I"][0]
        assert tag.base_name == "E300_P621"

    def test_base_name_no_suffix(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,,MyCounter,,DINT,,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        tag = [t for t in tags if t.name == "MyCounter"][0]
        assert tag.base_name == "MyCounter"

    def test_scoped_tag(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,MainProgram,LocalVar,,DINT,,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        tag = [t for t in tags if t.name == "LocalVar"][0]
        assert tag.scope == "MainProgram"

    def test_source_line_tracking(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,,Rack0:I,,AB:1756_IF8:I:0,,',
            'TAG,,Rack11:I,,AB:1756_IF8:I:0,,',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        # Source lines should be tracked (1-indexed, skipping header)
        assert all(t.source_line > 0 for t in tags)

    def test_empty_file(self):
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
        ]
        path = self._write_csv(lines)
        tags = parse_plc_csv(path, encoding="utf-8")
        assert tags == []

    def test_latin1_encoding(self):
        """CHRL tag export uses Latin-1 with degree symbols."""
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'TAG,,TempSensor,Temperature \xb0F,REAL,,',
        ]
        path = self._write_csv(lines, encoding="latin-1")
        tags = parse_plc_csv(path, encoding="latin-1")
        assert len(tags) >= 1
        assert "°" in tags[0].description or "\xb0" in tags[0].description

    def test_rcomment_record_skipped_or_parsed(self):
        """RCOMMENT records should be handled (parsed or skipped gracefully)."""
        lines = [
            'TYPE,SCOPE,NAME,DESCRIPTION,DATATYPE,SPECIFIER,ATTRIBUTES',
            'RCOMMENT,MainProgram,0,"This is a rung comment",,,',
        ]
        path = self._write_csv(lines)
        # Should not raise
        tags = parse_plc_csv(path, encoding="utf-8")
        # RCOMMENT may or may not be in results, but should not crash


# ---------------------------------------------------------------------------
# IO List XLSX Parser Tests (using synthetic data)
# ---------------------------------------------------------------------------

class TestParseIOListXLSX:
    """Tests for IO List XLSX parsing.

    These tests create minimal XLSX files with openpyxl to test parsing logic.
    """

    def _create_xlsx(self, rows: list[list], sheet_name: str = "ESCO List") -> Path:
        """Create a minimal XLSX file with given rows."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name
        for row in rows:
            ws.append(row)
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        wb.save(tmp.name)
        return Path(tmp.name)

    def test_parse_basic_row(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        data = ["X3", "11", "", "3", "13",
                "Rack11:I.Data[3].13", "LT611", "LT611",
                "AI", "1756-IF8", "4", "20", "mA"]
        path = self._create_xlsx([header, data])
        devices = parse_io_list_xlsx(path)
        assert len(devices) == 1
        d = devices[0]
        assert d.panel == "X3"
        assert d.rack == "11"
        assert d.slot == "3"
        assert d.channel == "13"
        assert d.plc_address == "Rack11:I.Data[3].13"
        assert d.io_tag == "LT611"
        assert d.device_tag == "LT611"
        assert d.module_type == "AI"

    def test_address_format_detection_clx(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        data = ["X3", "11", "", "3", "13",
                "Rack11:I.Data[3].13", "LT611", "LT611",
                "AI", "", "", "", ""]
        path = self._create_xlsx([header, data])
        devices = parse_io_list_xlsx(path)
        assert devices[0].address_format == AddressFormat.CLX

    def test_address_format_detection_plc5(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        data = ["X1", "0", "0", "0", "4",
                "Rack0_Group0_Slot0_IO.READ[4]", "TSV22_EV", "TSV22",
                "DO", "", "", "", ""]
        path = self._create_xlsx([header, data])
        devices = parse_io_list_xlsx(path)
        assert devices[0].address_format == AddressFormat.PLC5

    def test_spare_point_parsed(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        data = ["X1", "0", "0", "0", "14",
                "Rack0_Group0_Slot0_IO.READ[14]", "Spare", "",
                "DI", "", "", "", ""]
        path = self._create_xlsx([header, data])
        devices = parse_io_list_xlsx(path)
        assert len(devices) == 1
        assert devices[0].io_tag == "Spare"

    def test_source_row_tracking(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        data1 = ["X1", "0", "", "0", "0", "Rack0:I.Data[0].0", "D1", "D1", "DI", "", "", "", ""]
        data2 = ["X1", "0", "", "0", "1", "Rack0:I.Data[0].1", "D2", "D2", "DI", "", "", "", ""]
        path = self._create_xlsx([header, data1, data2])
        devices = parse_io_list_xlsx(path)
        assert len(devices) == 2
        assert devices[0].source_row != devices[1].source_row

    def test_empty_sheet(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        path = self._create_xlsx([header])
        devices = parse_io_list_xlsx(path)
        assert devices == []

    def test_multiple_panels(self):
        header = ["Panel", "Rack", "Group", "Slot", "Channel",
                  "PLC IO Address", "IO Tag", "Device Tag",
                  "Module Type", "Module", "Range Low", "Range High", "Units"]
        rows = [header]
        for panel in ["X1", "X2", "X3"]:
            rows.append([panel, "0", "", "0", "0", "Rack0:I.Data[0].0",
                        f"D_{panel}", f"D_{panel}", "DI", "", "", "", ""])
        path = self._create_xlsx(rows)
        devices = parse_io_list_xlsx(path)
        panels = {d.panel for d in devices}
        assert panels == {"X1", "X2", "X3"}
