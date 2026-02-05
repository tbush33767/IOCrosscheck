"""Integration tests using PRD Section 9.2 test vectors.

These tests exercise the full matching engine end-to-end with the specific
test cases defined in the PRD to ensure correctness against known-good data.
"""
from __future__ import annotations

import pytest

from io_crosscheck.models import (
    PLCTag, IODevice, RecordType, TagCategory,
    AddressFormat, Classification, Confidence,
)
from io_crosscheck.strategies import MatchingEngine


@pytest.fixture
def engine():
    return MatchingEngine()


@pytest.fixture
def chrl_plc_tags() -> list[PLCTag]:
    """A representative set of PLC tags mimicking the CHRL Xfer System."""
    return [
        # Rack IO TAGs
        PLCTag(record_type=RecordType.TAG, name="Rack0:I", base_name="Rack0",
               datatype="AB:1756_IF8:I:0", category=TagCategory.IO_MODULE, source_line=10),
        PLCTag(record_type=RecordType.TAG, name="Rack0:O", base_name="Rack0",
               datatype="AB:1756_OB16E:O:0", category=TagCategory.IO_MODULE, source_line=11),
        PLCTag(record_type=RecordType.TAG, name="Rack11:I", base_name="Rack11",
               datatype="AB:1756_IF8:I:0", category=TagCategory.RACK_IO, source_line=12),
        # PLC5-format rack TAG
        PLCTag(record_type=RecordType.TAG, name="Rack0_Group0_Slot0_IO",
               base_name="Rack0_Group0_Slot0_IO", datatype="AB:1771_IFE:I:0",
               category=TagCategory.IO_MODULE, source_line=20),
        # COMMENT records (bit-level)
        PLCTag(record_type=RecordType.COMMENT, name="Rack0:I", description="HLSTL5A",
               specifier="Rack0:I.DATA[5].7", category=TagCategory.BIT_LEVEL_COMMENT, source_line=100),
        PLCTag(record_type=RecordType.COMMENT, name="Rack0:I", description="HLSTL5C",
               specifier="Rack0:I.DATA[5].6", category=TagCategory.BIT_LEVEL_COMMENT, source_line=101),
        PLCTag(record_type=RecordType.COMMENT, name="Rack0:I", description="TSV22",
               specifier="Rack0:I.DATA[0].0", category=TagCategory.BIT_LEVEL_COMMENT, source_line=102),
        # ENet module tags
        PLCTag(record_type=RecordType.TAG, name="E300_P621:I", base_name="E300_P621",
               datatype="AB:E300_OL:I:0", category=TagCategory.ENET_DEVICE, source_line=200),
        PLCTag(record_type=RecordType.TAG, name="E300_P9203:I", base_name="E300_P9203",
               datatype="AB:E300_OL:I:0", category=TagCategory.ENET_DEVICE, source_line=201),
        # Program tags (should be excluded from IO matching)
        PLCTag(record_type=RecordType.TAG, name="MyCounter", base_name="MyCounter",
               datatype="DINT", scope="MainProgram", category=TagCategory.PROGRAM, source_line=300),
        PLCTag(record_type=RecordType.TAG, name="LT6110_Monitor", base_name="LT6110_Monitor",
               datatype="DINT", scope="MainProgram", category=TagCategory.PROGRAM, source_line=301),
    ]


class TestPRDTestVectors:
    """Each test corresponds to a row in PRD Section 9.2 'Specific Test Vectors'."""

    def test_case_sensitivity(self, engine, chrl_plc_tags):
        """IO: Rack0:I.Data[5].7 vs PLC: Rack0:I.DATA[5].7 (HLSTL5A) → Both, Strategy 1."""
        io_devices = [
            IODevice(
                panel="X1", rack="0", slot="5", channel="7",
                plc_address="Rack0:I.Data[5].7",
                io_tag="HLSTL5A", device_tag="HLSTL5A",
                module_type="DI", address_format=AddressFormat.CLX, source_row=1,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "HLSTL5A"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.BOTH
        assert matched[0].strategy_id == 1

    def test_suffix_stripping(self, engine, chrl_plc_tags):
        """IO: TSV22_EV vs PLC comment: TSV22 → Both, Strategy 5 after stripping _EV."""
        io_devices = [
            IODevice(
                panel="X1", rack="0",
                plc_address="",
                io_tag="TSV22_EV", device_tag="TSV22",
                address_format=AddressFormat.UNKNOWN, source_row=2,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "TSV22_EV"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.BOTH
        assert matched[0].strategy_id == 5

    def test_name_conflict(self, engine, chrl_plc_tags):
        """IO: FT656B_Pulse @ Rack0:I.Data[5].6 vs PLC: HLSTL5C → Conflict."""
        io_devices = [
            IODevice(
                panel="X1", rack="0", slot="5", channel="6",
                plc_address="Rack0:I.Data[5].6",
                io_tag="FT656B_Pulse", device_tag="FT656B",
                module_type="DI", address_format=AddressFormat.CLX, source_row=3,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "FT656B_Pulse"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.CONFLICT
        assert matched[0].conflict_flag is True

    def test_enet_extraction(self, engine, chrl_plc_tags):
        """PLC: E300_P621:I vs IO Device Tag: P621 → Both, Strategy 4."""
        io_devices = [
            IODevice(
                io_tag="P621", device_tag="P621",
                address_format=AddressFormat.UNKNOWN, source_row=4,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.device_tag == "P621"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.BOTH
        assert matched[0].strategy_id == 4

    def test_spare_exclusion(self, engine, chrl_plc_tags):
        """IO Tag = 'Spare' at Rack0_Group0_Slot0_IO.READ[14] → Excluded."""
        io_devices = [
            IODevice(
                plc_address="Rack0_Group0_Slot0_IO.READ[14]",
                io_tag="Spare", device_tag="",
                address_format=AddressFormat.PLC5, source_row=5,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "Spare"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.SPARE

    def test_rack_only_match(self, engine, chrl_plc_tags):
        """IO: AS611_AUX @ Rack0:I.Data[6].0, no COMMENT, Rack0:I exists → Both (Rack Only)."""
        io_devices = [
            IODevice(
                panel="X1", rack="0", slot="6", channel="0",
                plc_address="Rack0:I.Data[6].0",
                io_tag="AS611_AUX", device_tag="AS611",
                module_type="DI", address_format=AddressFormat.CLX, source_row=6,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "AS611_AUX"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.RACK_ONLY
        assert matched[0].strategy_id == 3

    def test_substring_safety(self, engine, chrl_plc_tags):
        """IO: LT611 should NOT match PLC program tag LT6110_Monitor → No match."""
        io_devices = [
            IODevice(
                plc_address="Rack99:I.Data[0].0",
                io_tag="LT611", device_tag="LT611",
                address_format=AddressFormat.CLX, source_row=7,
            ),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        matched = [r for r in results if r.io_device and r.io_device.io_tag == "LT611"]
        assert len(matched) == 1
        assert matched[0].classification == Classification.IO_LIST_ONLY

    def test_plc_only_enet(self, engine, chrl_plc_tags):
        """PLC: E300_P9203:I with no IO List entry → PLC Only."""
        io_devices = []  # No IO devices at all
        results = engine.run(io_devices, chrl_plc_tags)
        plc_only_enet = [
            r for r in results
            if r.classification == Classification.PLC_ONLY
            and r.plc_tag is not None
            and "P9203" in r.plc_tag.name
        ]
        assert len(plc_only_enet) >= 1


class TestEndToEndProperties:
    """Property-based tests for the full engine."""

    def test_every_io_device_gets_classified(self, engine, chrl_plc_tags):
        """Every IO device must receive exactly one classification."""
        io_devices = [
            IODevice(plc_address="Rack0:I.Data[5].7", io_tag="HLSTL5A",
                     device_tag="HLSTL5A", address_format=AddressFormat.CLX, source_row=1),
            IODevice(plc_address="Rack0:I.Data[6].0", io_tag="AS611_AUX",
                     device_tag="AS611", address_format=AddressFormat.CLX, source_row=2),
            IODevice(plc_address="Rack0_Group0_Slot0_IO.READ[14]", io_tag="Spare",
                     device_tag="", address_format=AddressFormat.PLC5, source_row=3),
            IODevice(plc_address="Rack99:I.Data[0].0", io_tag="PHANTOM",
                     device_tag="PHANTOM", address_format=AddressFormat.CLX, source_row=4),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        io_results = [r for r in results if r.io_device is not None]
        assert len(io_results) == len(io_devices)

    def test_no_duplicate_classifications(self, engine, chrl_plc_tags):
        """Each IO device should appear in results exactly once."""
        io_devices = [
            IODevice(plc_address="Rack0:I.Data[5].7", io_tag="HLSTL5A",
                     device_tag="HLSTL5A", address_format=AddressFormat.CLX, source_row=1),
        ]
        results = engine.run(io_devices, chrl_plc_tags)
        io_results = [r for r in results if r.io_device is not None]
        source_rows = [r.io_device.source_row for r in io_results]
        assert len(source_rows) == len(set(source_rows)), "Duplicate IO device in results"

    def test_program_tags_excluded_from_io_matching(self, engine):
        """Program-only tags (DINT, TIMER, etc.) should never produce a 'Both' match
        unless the IO device name genuinely matches."""
        io_devices = [
            IODevice(io_tag="RandomDevice", device_tag="RandomDevice",
                     address_format=AddressFormat.UNKNOWN, source_row=1),
        ]
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="MyCounter", base_name="MyCounter",
                   datatype="DINT", category=TagCategory.PROGRAM),
            PLCTag(record_type=RecordType.TAG, name="Delay_Timer", base_name="Delay_Timer",
                   datatype="TIMER", category=TagCategory.PROGRAM),
        ]
        results = engine.run(io_devices, plc_tags)
        io_results = [r for r in results if r.io_device is not None]
        assert all(r.classification != Classification.BOTH for r in io_results)
