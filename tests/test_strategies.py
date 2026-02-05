"""Tests for all matching strategies in the rule cascade."""
from __future__ import annotations

import pytest

from io_crosscheck.models import (
    PLCTag, IODevice, MatchResult, RecordType, TagCategory,
    AddressFormat, Classification, Confidence,
)
from io_crosscheck.strategies import (
    DirectCLXAddressMatch,
    PLC5RackAddressMatch,
    RackLevelTagExistence,
    ENetModuleTagExtraction,
    TagNameNormalizationMatch,
    MatchingEngine,
)


# ===================================================================
# Strategy 1: Direct CLX Address Match
# ===================================================================

class TestDirectCLXAddressMatch:
    """Strategy 1 — match IO List PLC address against PLC COMMENT specifiers."""

    @pytest.fixture
    def strategy(self):
        return DirectCLXAddressMatch()

    def test_exact_match_case_insensitive(self, strategy):
        """PRD test vector: Rack0:I.Data[5].7 vs Rack0:I.DATA[5].7 → Both."""
        io_dev = IODevice(
            plc_address="Rack0:I.Data[5].7",
            io_tag="HLSTL5A",
            device_tag="HLSTL5A",
            address_format=AddressFormat.CLX,
            source_row=1,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5A",
                specifier="Rack0:I.DATA[5].7",
                category=TagCategory.BIT_LEVEL_COMMENT,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.BOTH
        assert result.strategy_id == 1
        assert result.confidence == Confidence.EXACT

    def test_no_match_different_address(self, strategy):
        io_dev = IODevice(
            plc_address="Rack11:I.Data[3].13",
            io_tag="LT611",
            device_tag="LT611",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5A",
                specifier="Rack0:I.DATA[5].7",
                category=TagCategory.BIT_LEVEL_COMMENT,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_conflict_address_matches_name_differs(self, strategy):
        """PRD test vector: FT656B_Pulse @ Rack0:I.Data[5].6 vs HLSTL5C → Conflict."""
        io_dev = IODevice(
            plc_address="Rack0:I.Data[5].6",
            io_tag="FT656B_Pulse",
            device_tag="FT656B",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5C",
                specifier="Rack0:I.DATA[5].6",
                category=TagCategory.BIT_LEVEL_COMMENT,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.CONFLICT
        assert result.conflict_flag is True

    def test_skips_plc5_format(self, strategy):
        """Strategy 1 only applies to CLX-format addresses."""
        io_dev = IODevice(
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
            io_tag="TSV22_EV",
            device_tag="TSV22",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="TSV22",
                specifier="Rack0:I.DATA[0].0",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_skips_non_comment_tags(self, strategy):
        """Strategy 1 only matches against COMMENT records."""
        io_dev = IODevice(
            plc_address="Rack0:I.Data[5].7",
            io_tag="HLSTL5A",
            device_tag="HLSTL5A",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0:I",
                datatype="AB:1756_IF8:I:0",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_empty_plc_tags(self, strategy):
        io_dev = IODevice(
            plc_address="Rack0:I.Data[5].7",
            address_format=AddressFormat.CLX,
        )
        result = strategy.match(io_dev, [])
        assert result is None


# ===================================================================
# Strategy 2: PLC5 Rack Address Match
# ===================================================================

class TestPLC5RackAddressMatch:
    """Strategy 2 — match PLC5-format IO addresses against PLC TAG names."""

    @pytest.fixture
    def strategy(self):
        return PLC5RackAddressMatch()

    def test_exact_plc5_match(self, strategy):
        io_dev = IODevice(
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
            io_tag="TSV22_EV",
            device_tag="TSV22",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0_Group0_Slot0_IO",
                base_name="Rack0_Group0_Slot0_IO",
                datatype="AB:1771_IFE:I:0",
                category=TagCategory.IO_MODULE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.BOTH
        assert result.strategy_id == 2
        assert result.confidence == Confidence.EXACT

    def test_case_insensitive_plc5(self, strategy):
        io_dev = IODevice(
            plc_address="rack0_group0_slot0_io.read[4]",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0_Group0_Slot0_IO",
                base_name="Rack0_Group0_Slot0_IO",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_no_match_wrong_rack(self, strategy):
        io_dev = IODevice(
            plc_address="Rack1_Group1_Slot2_IO.WRITE[0]",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0_Group0_Slot0_IO",
                base_name="Rack0_Group0_Slot0_IO",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_skips_clx_format(self, strategy):
        io_dev = IODevice(
            plc_address="Rack11:I.Data[3].13",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="Rack11:I"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_write_format(self, strategy):
        io_dev = IODevice(
            plc_address="Rack1_Group1_Slot2_IO.WRITE[0]",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack1_Group1_Slot2_IO",
                base_name="Rack1_Group1_Slot2_IO",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None


# ===================================================================
# Strategy 3: Rack-Level TAG Existence
# ===================================================================

class TestRackLevelTagExistence:
    """Strategy 3 — verify parent rack TAG exists when no per-point COMMENT."""

    @pytest.fixture
    def strategy(self):
        return RackLevelTagExistence()

    def test_rack_exists_point_unconfirmed(self, strategy):
        """PRD test vector: AS611_AUX @ Rack0:I.Data[6].0, no COMMENT, Rack0:I exists."""
        io_dev = IODevice(
            plc_address="Rack0:I.Data[6].0",
            io_tag="AS611_AUX",
            device_tag="AS611",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0:I",
                base_name="Rack0",
                datatype="AB:1756_IF8:I:0",
                category=TagCategory.RACK_IO,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.RACK_ONLY
        assert result.strategy_id == 3
        assert result.confidence == Confidence.PARTIAL

    def test_rack_does_not_exist(self, strategy):
        io_dev = IODevice(
            plc_address="Rack99:I.Data[0].0",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="Rack0:I"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_skips_plc5_format(self, strategy):
        io_dev = IODevice(
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
            address_format=AddressFormat.PLC5,
        )
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="Rack0:I"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_output_rack(self, strategy):
        io_dev = IODevice(
            plc_address="Rack11:O.Data[2].5",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="Rack11:O"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.RACK_ONLY

    def test_case_insensitive_rack_lookup(self, strategy):
        io_dev = IODevice(
            plc_address="rack11:i.data[3].13",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(record_type=RecordType.TAG, name="Rack11:I"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None


# ===================================================================
# Strategy 4: EtherNet/IP Module Tag Extraction
# ===================================================================

class TestENetModuleTagExtraction:
    """Strategy 4 — extract device from E300_/VFD_/IPDev_/IPDEV_ tags."""

    @pytest.fixture
    def strategy(self):
        return ENetModuleTagExtraction()

    def test_e300_match(self, strategy):
        """PRD test vector: E300_P621:I vs IO Device Tag P621 → Both."""
        io_dev = IODevice(
            io_tag="P621",
            device_tag="P621",
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="E300_P621:I",
                base_name="E300_P621",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.BOTH
        assert result.strategy_id == 4
        assert result.confidence == Confidence.EXACT

    def test_vfd_match(self, strategy):
        io_dev = IODevice(device_tag="M101")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="VFD_M101:O",
                base_name="VFD_M101",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.BOTH

    def test_ipdev_match(self, strategy):
        io_dev = IODevice(device_tag="FT601")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="IPDev_FT601:I",
                base_name="IPDev_FT601",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_no_match_different_device(self, strategy):
        io_dev = IODevice(device_tag="P622")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="E300_P621:I",
                base_name="E300_P621",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_case_insensitive_device_match(self, strategy):
        io_dev = IODevice(device_tag="p621")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="E300_P621:I",
                base_name="E300_P621",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_plc_only_enet_no_io_device(self, strategy):
        """PRD test vector: E300_P9203:I with no IO List entry → PLC Only."""
        io_dev = IODevice(device_tag="SOMETHING_ELSE")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="E300_P9203:I",
                base_name="E300_P9203",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_skips_non_enet_tags(self, strategy):
        io_dev = IODevice(device_tag="P621")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0:I",
                category=TagCategory.RACK_IO,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None


# ===================================================================
# Strategy 5: Tag Name Normalization Match
# ===================================================================

class TestTagNameNormalizationMatch:
    """Strategy 5 — normalized IO tag/device tag vs PLC tag base names."""

    @pytest.fixture
    def strategy(self):
        return TagNameNormalizationMatch()

    def test_suffix_stripping_match(self, strategy):
        """PRD test vector: TSV22_EV vs PLC comment TSV22 → Both after stripping _EV."""
        io_dev = IODevice(
            io_tag="TSV22_EV",
            device_tag="TSV22",
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="TSV22",
                category=TagCategory.BIT_LEVEL_COMMENT,
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None
        assert result.classification == Classification.BOTH
        assert result.strategy_id == 5
        assert result.confidence == Confidence.HIGH

    def test_device_tag_match(self, strategy):
        """Match on device_tag when io_tag has suffix."""
        io_dev = IODevice(
            io_tag="P611_MC",
            device_tag="P611",
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="P611",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_case_insensitive_match(self, strategy):
        io_dev = IODevice(io_tag="tsv22_ev", device_tag="tsv22")
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="TSV22",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_no_match_different_base(self, strategy):
        io_dev = IODevice(io_tag="LT611", device_tag="LT611")
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="LT612",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_matches_plc_tag_base_name(self, strategy):
        """Match against PLC TAG base_name, not just COMMENT descriptions."""
        io_dev = IODevice(io_tag="TSV22_EV", device_tag="TSV22")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="TSV22:O",
                base_name="TSV22",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is not None

    def test_empty_io_tag(self, strategy):
        io_dev = IODevice(io_tag="", device_tag="")
        plc_tags = [
            PLCTag(record_type=RecordType.COMMENT, name="Rack0:I", description="TSV22"),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None


# ===================================================================
# Adversarial / Edge Case Tests
# ===================================================================

class TestAdversarialCases:
    """Deliberately crafted edge cases from PRD Section 9.2."""

    def test_substring_safety_lt611_vs_lt6110(self):
        """PRD test vector: LT611 should NOT match LT6110_Monitor."""
        strategy = TagNameNormalizationMatch()
        io_dev = IODevice(io_tag="LT611", device_tag="LT611")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="LT6110_Monitor",
                base_name="LT6110_Monitor",
                description="",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None, "LT611 must NOT match LT6110 — exact base name required"

    def test_substring_safety_reverse(self):
        """LT6110 should NOT match PLC tag LT611."""
        strategy = TagNameNormalizationMatch()
        io_dev = IODevice(io_tag="LT6110", device_tag="LT6110")
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="LT611",
                base_name="LT611",
            ),
        ]
        result = strategy.match(io_dev, plc_tags)
        assert result is None

    def test_identical_device_names_different_racks(self):
        """Two devices with the same name in different racks should each match their own rack."""
        strategy = DirectCLXAddressMatch()
        io_dev_rack0 = IODevice(
            plc_address="Rack0:I.Data[1].0",
            io_tag="LS100",
            device_tag="LS100",
            address_format=AddressFormat.CLX,
        )
        io_dev_rack11 = IODevice(
            plc_address="Rack11:I.Data[1].0",
            io_tag="LS100",
            device_tag="LS100",
            address_format=AddressFormat.CLX,
        )
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                specifier="Rack0:I.DATA[1].0",
                description="LS100",
            ),
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack11:I",
                specifier="Rack11:I.DATA[1].0",
                description="LS100",
            ),
        ]
        result0 = strategy.match(io_dev_rack0, plc_tags)
        result11 = strategy.match(io_dev_rack11, plc_tags)
        assert result0 is not None
        assert result11 is not None
        # Each should match its own rack's comment
        assert result0.plc_tag.specifier.lower() == "rack0:i.data[1].0"
        assert result11.plc_tag.specifier.lower() == "rack11:i.data[1].0"

    def test_spare_with_device_like_name(self):
        """A spare point should be excluded even if it has a device-like name pattern."""
        from io_crosscheck.classifiers import is_spare
        assert is_spare("Spare") is True
        # But a real device that happens to contain "spare" is not spare
        assert is_spare("SpareValve1") is False


# ===================================================================
# Matching Engine (Integration-level)
# ===================================================================

class TestMatchingEngine:
    """Integration tests for the full matching cascade."""

    @pytest.fixture
    def engine(self):
        return MatchingEngine()

    def test_spare_excluded(self, engine):
        """PRD test vector: IO Tag = 'Spare' → excluded from mismatch reporting."""
        io_devices = [
            IODevice(
                plc_address="Rack0_Group0_Slot0_IO.READ[14]",
                io_tag="Spare",
                device_tag="",
                address_format=AddressFormat.PLC5,
            ),
        ]
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0_Group0_Slot0_IO",
                base_name="Rack0_Group0_Slot0_IO",
            ),
        ]
        results = engine.run(io_devices, plc_tags)
        assert len(results) == 1
        assert results[0].classification == Classification.SPARE

    def test_strategy_priority_order(self, engine):
        """Strategy 1 should take precedence over Strategy 5 when both could match."""
        io_devices = [
            IODevice(
                plc_address="Rack0:I.Data[5].7",
                io_tag="HLSTL5A",
                device_tag="HLSTL5A",
                address_format=AddressFormat.CLX,
            ),
        ]
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5A",
                specifier="Rack0:I.DATA[5].7",
                category=TagCategory.BIT_LEVEL_COMMENT,
            ),
            PLCTag(
                record_type=RecordType.TAG,
                name="HLSTL5A",
                base_name="HLSTL5A",
            ),
        ]
        results = engine.run(io_devices, plc_tags)
        assert len(results) == 1
        assert results[0].strategy_id == 1, "Strategy 1 should match first"

    def test_io_list_only_classification(self, engine):
        """Device with no PLC match → IO List Only."""
        io_devices = [
            IODevice(
                plc_address="Rack99:I.Data[0].0",
                io_tag="PHANTOM_DEVICE",
                device_tag="PHANTOM_DEVICE",
                address_format=AddressFormat.CLX,
            ),
        ]
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="Rack0:I",
                base_name="Rack0",
            ),
        ]
        results = engine.run(io_devices, plc_tags)
        assert len(results) == 1
        assert results[0].classification == Classification.IO_LIST_ONLY

    def test_plc_only_enet_devices(self, engine):
        """PLC ENet tags with no IO List match → PLC Only."""
        io_devices = []  # empty IO list
        plc_tags = [
            PLCTag(
                record_type=RecordType.TAG,
                name="E300_P9203:I",
                base_name="E300_P9203",
                datatype="AB:E300_OL:I:0",
                category=TagCategory.ENET_DEVICE,
            ),
        ]
        results = engine.run(io_devices, plc_tags)
        # Should produce a PLC Only result for the unmatched ENet tag
        plc_only = [r for r in results if r.classification == Classification.PLC_ONLY]
        assert len(plc_only) >= 1

    def test_deterministic_results(self, engine):
        """Same inputs must produce identical results (FR-ACC-05)."""
        io_devices = [
            IODevice(
                plc_address="Rack0:I.Data[5].7",
                io_tag="HLSTL5A",
                device_tag="HLSTL5A",
                address_format=AddressFormat.CLX,
            ),
        ]
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5A",
                specifier="Rack0:I.DATA[5].7",
            ),
        ]
        results1 = engine.run(io_devices, plc_tags)
        results2 = engine.run(io_devices, plc_tags)
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.classification == r2.classification
            assert r1.strategy_id == r2.strategy_id
            assert r1.confidence == r2.confidence

    def test_audit_trail_populated(self, engine):
        """Every result must have a non-empty audit trail (FR-ACC-04)."""
        io_devices = [
            IODevice(
                plc_address="Rack0:I.Data[5].7",
                io_tag="HLSTL5A",
                device_tag="HLSTL5A",
                address_format=AddressFormat.CLX,
            ),
        ]
        plc_tags = [
            PLCTag(
                record_type=RecordType.COMMENT,
                name="Rack0:I",
                description="HLSTL5A",
                specifier="Rack0:I.DATA[5].7",
            ),
        ]
        results = engine.run(io_devices, plc_tags)
        for result in results:
            assert len(result.audit_trail) > 0, "Audit trail must not be empty"
