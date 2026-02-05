"""Tests for PLC tag classification logic."""
from __future__ import annotations

import pytest

from io_crosscheck.models import PLCTag, RecordType, TagCategory
from io_crosscheck.classifiers import (
    classify_tag,
    is_io_module_tag,
    is_rack_io_tag,
    is_enet_device_tag,
    is_alias_tag,
    is_program_tag,
    is_spare,
)


# ---------------------------------------------------------------------------
# is_io_module_tag — datatype starts with AB: or EH:
# ---------------------------------------------------------------------------

class TestIsIOModuleTag:

    def test_ab_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack11:I", datatype="AB:1756_IF8:I:0")
        assert is_io_module_tag(tag) is True

    def test_eh_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="IPDev_FT601:I", datatype="EH:Promass:I:0")
        assert is_io_module_tag(tag) is True

    def test_dint_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="MyVar", datatype="DINT")
        assert is_io_module_tag(tag) is False

    def test_empty_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="X", datatype="")
        assert is_io_module_tag(tag) is False

    def test_case_insensitive(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0:I", datatype="ab:1771_IFE:I:0")
        assert is_io_module_tag(tag) is True


# ---------------------------------------------------------------------------
# is_rack_io_tag — name matches Rack<N>:I or Rack<N>:O
# ---------------------------------------------------------------------------

class TestIsRackIOTag:

    def test_rack_input(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack11:I")
        assert is_rack_io_tag(tag) is True

    def test_rack_output(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0:O")
        assert is_rack_io_tag(tag) is True

    def test_rack_with_suffix(self):
        """Rack11:I is a rack tag, but Rack11:I.DATA[3].13 is a specifier, not a tag name."""
        tag = PLCTag(record_type=RecordType.TAG, name="Rack11:I")
        assert is_rack_io_tag(tag) is True

    def test_non_rack(self):
        tag = PLCTag(record_type=RecordType.TAG, name="E300_P621:I")
        assert is_rack_io_tag(tag) is False

    def test_plc5_style_not_rack_io(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0_Group0_Slot0_IO")
        assert is_rack_io_tag(tag) is False

    def test_multi_digit_rack(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack26:I")
        assert is_rack_io_tag(tag) is True


# ---------------------------------------------------------------------------
# is_enet_device_tag — E300_*, VFD_*, IPDev_*, IPDEV_*
# ---------------------------------------------------------------------------

class TestIsEnetDeviceTag:

    def test_e300(self):
        tag = PLCTag(record_type=RecordType.TAG, name="E300_P621:I")
        assert is_enet_device_tag(tag) is True

    def test_vfd(self):
        tag = PLCTag(record_type=RecordType.TAG, name="VFD_M101:O")
        assert is_enet_device_tag(tag) is True

    def test_ipdev_lower(self):
        tag = PLCTag(record_type=RecordType.TAG, name="IPDev_FT601:I")
        assert is_enet_device_tag(tag) is True

    def test_ipdev_upper(self):
        tag = PLCTag(record_type=RecordType.TAG, name="IPDEV_FT601:I")
        assert is_enet_device_tag(tag) is True

    def test_regular_tag(self):
        tag = PLCTag(record_type=RecordType.TAG, name="MyCounter")
        assert is_enet_device_tag(tag) is False

    def test_rack_tag(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0:I")
        assert is_enet_device_tag(tag) is False


# ---------------------------------------------------------------------------
# is_alias_tag — record type is ALIAS
# ---------------------------------------------------------------------------

class TestIsAliasTag:

    def test_alias_record(self):
        tag = PLCTag(record_type=RecordType.ALIAS, name="Local:1:I.Data.0")
        assert is_alias_tag(tag) is True

    def test_tag_record(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0:I")
        assert is_alias_tag(tag) is False

    def test_comment_record(self):
        tag = PLCTag(record_type=RecordType.COMMENT, name="Rack0:I")
        assert is_alias_tag(tag) is False


# ---------------------------------------------------------------------------
# is_program_tag — DINT, REAL, INT, BOOL, TIMER, COUNTER, STRING
# ---------------------------------------------------------------------------

class TestIsProgramTag:

    @pytest.mark.parametrize("datatype", [
        "DINT", "REAL", "INT", "BOOL", "TIMER", "COUNTER", "STRING",
    ])
    def test_program_datatypes(self, datatype):
        tag = PLCTag(record_type=RecordType.TAG, name="X", datatype=datatype)
        assert is_program_tag(tag) is True

    def test_io_module_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack0:I", datatype="AB:1756_IF8:I:0")
        assert is_program_tag(tag) is False

    def test_empty_datatype(self):
        tag = PLCTag(record_type=RecordType.TAG, name="X", datatype="")
        assert is_program_tag(tag) is False

    def test_case_insensitive(self):
        tag = PLCTag(record_type=RecordType.TAG, name="X", datatype="dint")
        assert is_program_tag(tag) is True


# ---------------------------------------------------------------------------
# is_spare
# ---------------------------------------------------------------------------

class TestIsSpare:

    def test_spare_exact(self):
        assert is_spare("Spare") is True

    def test_spare_case_insensitive(self):
        assert is_spare("spare") is True
        assert is_spare("SPARE") is True

    def test_spare_with_whitespace(self):
        assert is_spare("  Spare  ") is True

    def test_not_spare(self):
        assert is_spare("LT611") is False

    def test_empty(self):
        assert is_spare("") is False

    def test_spare_in_name(self):
        """A tag containing 'spare' as substring should NOT be classified as spare."""
        assert is_spare("Spare_Point") is False


# ---------------------------------------------------------------------------
# classify_tag — full classification
# ---------------------------------------------------------------------------

class TestClassifyTag:

    def test_io_module(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack11:I", datatype="AB:1756_IF8:I:0")
        assert classify_tag(tag) == TagCategory.IO_MODULE

    def test_rack_io(self):
        tag = PLCTag(record_type=RecordType.TAG, name="Rack11:I", datatype="DINT")
        # Name matches rack pattern — should be RACK_IO even if datatype is DINT
        assert classify_tag(tag) == TagCategory.RACK_IO

    def test_enet_device(self):
        tag = PLCTag(record_type=RecordType.TAG, name="E300_P621:I", datatype="AB:E300_OL:I:0")
        assert classify_tag(tag) == TagCategory.ENET_DEVICE

    def test_alias(self):
        tag = PLCTag(record_type=RecordType.ALIAS, name="Local:1:I.Data.0", datatype="")
        assert classify_tag(tag) == TagCategory.ALIAS

    def test_program(self):
        tag = PLCTag(record_type=RecordType.TAG, name="MyVar", datatype="DINT")
        assert classify_tag(tag) == TagCategory.PROGRAM

    def test_bit_level_comment(self):
        tag = PLCTag(
            record_type=RecordType.COMMENT,
            name="Rack0:I",
            specifier="Rack0:I.DATA[5].7",
        )
        assert classify_tag(tag) == TagCategory.BIT_LEVEL_COMMENT
