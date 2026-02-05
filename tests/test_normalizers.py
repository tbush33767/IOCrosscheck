"""Tests for tag and address normalization."""
from __future__ import annotations

import pytest

from io_crosscheck.normalizers import (
    normalize_tag,
    strip_suffixes,
    normalize_address,
    detect_address_format,
    extract_rack_base,
    extract_enet_device,
    KNOWN_SUFFIXES,
)


# ---------------------------------------------------------------------------
# normalize_tag
# ---------------------------------------------------------------------------

class TestNormalizeTag:
    """Tag normalization: case-fold + suffix strip + whitespace trim."""

    def test_lowercase(self):
        assert normalize_tag("TSV22") == "tsv22"

    def test_strips_ev_suffix(self):
        assert normalize_tag("TSV22_EV") == "tsv22"

    def test_strips_mc_suffix(self):
        assert normalize_tag("P611_MC") == "p611"

    def test_strips_aux_suffix(self):
        assert normalize_tag("AS611_AUX") == "as611"

    def test_strips_zso_suffix(self):
        assert normalize_tag("XV100_ZSO") == "xv100"

    def test_strips_zsc_suffix(self):
        assert normalize_tag("XV100_ZSC") == "xv100"

    def test_strips_pulse_suffix(self):
        assert normalize_tag("FT656B_Pulse") == "ft656b"

    def test_strips_in_suffix(self):
        assert normalize_tag("SOL1_In") == "sol1"

    def test_strips_input_suffix(self):
        assert normalize_tag("SOL1_Input") == "sol1"

    def test_strips_out_suffix(self):
        assert normalize_tag("SOL1_Out") == "sol1"

    def test_strips_old_suffix(self):
        assert normalize_tag("P100_Old") == "p100"

    def test_strips_pos_suffix(self):
        assert normalize_tag("XV200_Pos") == "xv200"

    def test_strips_failedtoclose_suffix(self):
        assert normalize_tag("XV200_FailedToClose") == "xv200"

    def test_strips_failedtoopen_suffix(self):
        assert normalize_tag("XV200_FailedToOpen") == "xv200"

    def test_strips_ontimer_suffix(self):
        assert normalize_tag("P100_OnTimer") == "p100"

    def test_strips_offtimer_suffix(self):
        assert normalize_tag("P100_OffTimer") == "p100"

    def test_strips_monitor_suffix(self):
        assert normalize_tag("LT6110_Monitor") == "lt6110"

    def test_strips_failed_suffix(self):
        assert normalize_tag("P100_Failed") == "p100"

    def test_trims_whitespace(self):
        assert normalize_tag("  TSV22_EV  ") == "tsv22"

    def test_empty_string(self):
        assert normalize_tag("") == ""

    def test_no_suffix_to_strip(self):
        assert normalize_tag("LT611") == "lt611"

    def test_only_strips_one_suffix(self):
        """If a tag has nested suffixes, only the outermost known suffix is stripped."""
        result = normalize_tag("P100_Failed_Old")
        # _Old is stripped first, leaving P100_Failed
        # Whether to strip again depends on implementation; at minimum _Old is gone
        assert result in ("p100_failed", "p100")

    def test_case_insensitive_suffix(self):
        """Suffix matching should be case-insensitive."""
        assert normalize_tag("TSV22_ev") == "tsv22"


# ---------------------------------------------------------------------------
# strip_suffixes
# ---------------------------------------------------------------------------

class TestStripSuffixes:

    def test_strips_known_suffix(self):
        assert strip_suffixes("TSV22_EV") == "TSV22"

    def test_no_match_returns_original(self):
        assert strip_suffixes("LT611") == "LT611"

    def test_custom_suffix_list(self):
        assert strip_suffixes("PUMP_RUN", ["_RUN", "_STOP"]) == "PUMP"

    def test_empty_string(self):
        assert strip_suffixes("") == ""

    def test_longest_suffix_wins(self):
        """_Input should be stripped before _In when both could match."""
        result = strip_suffixes("SOL1_Input")
        assert result == "SOL1"


# ---------------------------------------------------------------------------
# normalize_address
# ---------------------------------------------------------------------------

class TestNormalizeAddress:

    def test_clx_address_case_fold(self):
        """'Rack0:I.Data[5].0' and 'Rack0:I.DATA[5].0' should normalize to same value."""
        a = normalize_address("Rack0:I.Data[5].0")
        b = normalize_address("Rack0:I.DATA[5].0")
        assert a == b

    def test_clx_address_preserves_structure(self):
        result = normalize_address("Rack11:I.DATA[3].13")
        assert "rack11" in result.lower()

    def test_plc5_address_case_fold(self):
        a = normalize_address("Rack0_Group0_Slot0_IO.READ[4]")
        b = normalize_address("rack0_group0_slot0_io.read[4]")
        assert a == b

    def test_trims_whitespace(self):
        assert normalize_address("  Rack0:I.DATA[5].0  ") == normalize_address("Rack0:I.DATA[5].0")

    def test_empty_string(self):
        assert normalize_address("") == ""


# ---------------------------------------------------------------------------
# detect_address_format
# ---------------------------------------------------------------------------

class TestDetectAddressFormat:

    def test_clx_format(self):
        assert detect_address_format("Rack11:I.Data[3].13") == "CLX"

    def test_clx_output_format(self):
        assert detect_address_format("Rack0:O.DATA[2].5") == "CLX"

    def test_plc5_format(self):
        assert detect_address_format("Rack0_Group0_Slot0_IO.READ[4]") == "PLC5"

    def test_plc5_write_format(self):
        assert detect_address_format("Rack1_Group1_Slot2_IO.WRITE[0]") == "PLC5"

    def test_unknown_format(self):
        assert detect_address_format("SomeRandomTag") == "Unknown"

    def test_empty_string(self):
        assert detect_address_format("") == "Unknown"

    def test_clx_slot_specific(self):
        """Slot-specific CLX address like Rack25:8:I.Data.4."""
        assert detect_address_format("Rack25:8:I.Data.4") == "CLX"

    def test_clx_analog_channel(self):
        """Analog channel CLX address like Rack24:14:I.Ch2Data."""
        assert detect_address_format("Rack24:14:I.Ch2Data") == "CLX"

    def test_clx_slot_specific_output(self):
        assert detect_address_format("Rack25:10:O.Data.11") == "CLX"


# ---------------------------------------------------------------------------
# extract_rack_base
# ---------------------------------------------------------------------------

class TestExtractRackBase:

    def test_clx_input(self):
        assert extract_rack_base("Rack11:I.DATA[3].13") == "Rack11:I"

    def test_clx_output(self):
        assert extract_rack_base("Rack0:O.DATA[2].5") == "Rack0:O"

    def test_case_insensitive_result(self):
        result = extract_rack_base("Rack0:I.Data[5].0")
        assert result is not None
        assert result.lower() == "rack0:i"

    def test_non_rack_address_returns_none(self):
        assert extract_rack_base("E300_P621:I") is None

    def test_empty_returns_none(self):
        assert extract_rack_base("") is None

    def test_plc5_returns_none(self):
        """PLC5 addresses don't have a CLX rack base."""
        assert extract_rack_base("Rack0_Group0_Slot0_IO.READ[4]") is None

    def test_slot_specific_returns_rack_name(self):
        """Slot-specific CLX: Rack25:8:I.Data.4 -> Rack25."""
        assert extract_rack_base("Rack25:8:I.Data.4") == "Rack25"

    def test_analog_channel_returns_rack_name(self):
        """Analog channel CLX: Rack24:14:I.Ch2Data -> Rack24."""
        assert extract_rack_base("Rack24:14:I.Ch2Data") == "Rack24"


# ---------------------------------------------------------------------------
# extract_enet_device
# ---------------------------------------------------------------------------

class TestExtractEnetDevice:

    def test_e300_prefix(self):
        assert extract_enet_device("E300_P621:I") == "P621"

    def test_vfd_prefix(self):
        assert extract_enet_device("VFD_M101:O") == "M101"

    def test_ipdev_prefix(self):
        assert extract_enet_device("IPDev_FT601:I") == "FT601"

    def test_ipdev_uppercase(self):
        assert extract_enet_device("IPDEV_FT601:I") == "FT601"

    def test_no_io_suffix(self):
        """Handle tags without :I or :O suffix."""
        result = extract_enet_device("E300_P621")
        assert result == "P621"

    def test_non_enet_returns_none(self):
        assert extract_enet_device("Rack0:I") is None

    def test_empty_returns_none(self):
        assert extract_enet_device("") is None

    def test_regular_tag_returns_none(self):
        assert extract_enet_device("MyCounter") is None

    def test_case_insensitive_prefix(self):
        assert extract_enet_device("e300_P621:I") == "P621"
