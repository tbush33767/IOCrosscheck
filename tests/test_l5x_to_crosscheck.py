"""Tests for l5x_to_crosscheck enrichment module."""
from __future__ import annotations

import pytest

from io_crosscheck.l5x_to_crosscheck import (
    extract_l5x_enrichment,
    enrich_results,
    _is_io_catalog,
)
from io_crosscheck.models import (
    MatchResult,
    PLCTag,
    IODevice,
    RecordType,
    AddressFormat,
    Classification,
    Confidence,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal L5X data dicts
# ---------------------------------------------------------------------------

def _make_data(alias_tags=None, regular_tags=None, modules=None, rung_references=None):
    return {
        "controller_tags": {
            "alias_tags": alias_tags or [],
            "regular_tags": regular_tags or [],
        },
        "modules": modules or [],
        "rung_references": rung_references or [],
    }


def _alias(name, alias_for, description=""):
    return {"name": name, "alias_for": alias_for, "description": description}


def _module(name, catalog, parent="", ports=None):
    return {
        "name": name,
        "catalog_number": catalog,
        "parent_module": parent,
        "ports": ports or [],
    }


def _port(port_type, address=""):
    return {"type": port_type, "address": address}


def _match_result(plc_name="", specifier="", dev_tag="", plc_address="",
                  classification=Classification.BOTH):
    """Build a minimal MatchResult for enrichment testing."""
    plc_tag = PLCTag(
        record_type=RecordType.COMMENT,
        name=plc_name,
        specifier=specifier,
    ) if plc_name else None
    io_device = IODevice(
        device_tag=dev_tag,
        plc_address=plc_address,
    ) if dev_tag else None
    return MatchResult(
        plc_tag=plc_tag,
        io_device=io_device,
        classification=classification,
        sources=["CSV", "XLSX"],
    )


# ===========================================================================
# extract_l5x_enrichment — alias indexing
# ===========================================================================

class TestExtractEnrichmentAliasIndex:
    """Physical IO aliases are indexed by address and name."""

    def test_clx_alias_indexed_by_address(self):
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2", "Tank 601 Valve"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "rack14:o.data[3].2" in enrichment["alias_by_address"]
        assert "an601" in enrichment["alias_by_name"]  # normalized, suffix stripped

    def test_slot_specific_alias_indexed(self):
        data = _make_data(alias_tags=[
            _alias("FSH623DN", "Rack25:8:I.Data.4"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "rack25:8:i.data.4" in enrichment["alias_by_address"]

    def test_plc5_rio_alias_indexed(self):
        data = _make_data(alias_tags=[
            _alias("LT601", "Rack16_Group0_Slot0_IO.READ[4]"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "rack16_group0_slot0_io.read[4]" in enrichment["alias_by_address"]

    def test_enet_alias_indexed(self):
        data = _make_data(alias_tags=[
            _alias("FT633P", "IPDEV_FT633P:I1.Process_variables_Mass_flow"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "ipdev_ft633p:i1.process_variables_mass_flow" in enrichment["alias_by_address"]


# ===========================================================================
# extract_l5x_enrichment — MSG alias flagging
# ===========================================================================

class TestAliasMsgReadFlagged:
    def test_n_file_read(self):
        data = _make_data(alias_tags=[
            _alias("DV50_AO_Deod", "N166_R[10].0", "40K DEODORIZER OPEN DV50"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["alias_by_address"]) == 0  # not indexed as IO
        assert len(enrichment["msg_tags"]) == 1
        assert enrichment["msg_tags"][0]["direction"] == "READ"
        assert enrichment["msg_tags"][0]["name"] == "DV50_AO_Deod"

    def test_b_file_read(self):
        data = _make_data(alias_tags=[
            _alias("D1DMV5_ZSC", "B119_R[34].3"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["msg_tags"]) == 1
        assert enrichment["msg_tags"][0]["direction"] == "READ"


class TestAliasMsgWriteFlagged:
    def test_n_file_write(self):
        data = _make_data(alias_tags=[
            _alias("AN692_AO_Deod", "N168_W[41].10", "Tank 692 Nitrogen Agitation"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["alias_by_address"]) == 0
        assert len(enrichment["msg_tags"]) == 1
        assert enrichment["msg_tags"][0]["direction"] == "WRITE"


class TestAliasMsgRWFlagged:
    def test_f_file_rw(self):
        data = _make_data(alias_tags=[
            _alias("FT5_Setpoint", "F112_RW[40]", "FT5 Set Point"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["msg_tags"]) == 1
        assert enrichment["msg_tags"][0]["direction"] == "READ/WRITE"


# ===========================================================================
# extract_l5x_enrichment — consumed / UDT reference flagging
# ===========================================================================

class TestAliasConsumedFlagged:
    def test_consumed_clx_data(self):
        data = _make_data(alias_tags=[
            _alias("FT615_Remote_Flow", "DeodSys_CLXData.Integer[3]"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["alias_by_address"]) == 0
        assert len(enrichment["consumed_tags"]) == 1
        assert enrichment["consumed_tags"][0]["name"] == "FT615_Remote_Flow"

    def test_consumed_udt_member(self):
        data = _make_data(alias_tags=[
            _alias("CW_T951_Minimum_Heating_Level", "Tanks[119].Device.Heat_Permissive",
                   "Tank 951 Minimum Level"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["consumed_tags"]) == 1

    def test_rack_address_not_consumed(self):
        """Rack addresses should NOT be flagged as consumed."""
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2"),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert len(enrichment["consumed_tags"]) == 0
        assert len(enrichment["alias_by_address"]) == 1


# ===========================================================================
# extract_l5x_enrichment — module lookup sets
# ===========================================================================

class TestModuleLookupSets:
    def test_io_module_names_included(self):
        data = _make_data(modules=[
            _module("Rack24_Slot06", "1756-IB16", "Rack24", [_port("ICP", "6")]),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "rack24_slot06" in enrichment["module_names"]
        assert "6" in enrichment["module_addresses"]

    def test_infra_module_excluded(self):
        data = _make_data(modules=[
            _module("ENET", "1756-EN2T", "Local", [_port("Ethernet", "10.9.54.52")]),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "enet" not in enrichment["module_names"]

    def test_enet_device_module_included(self):
        data = _make_data(modules=[
            _module("E300_P621", "193-ECM-ETR/A", "Local",
                    [_port("Ethernet", "192.168.12.150")]),
        ])
        enrichment = extract_l5x_enrichment(data)
        assert "e300_p621" in enrichment["module_names"]
        assert "192.168.12.150" in enrichment["module_addresses"]


# ===========================================================================
# IO catalog filter
# ===========================================================================

class TestModuleFilterIncludesIO:
    def test_1756_ib16(self):
        assert _is_io_catalog("1756-IB16") is True

    def test_1756_ob16e(self):
        assert _is_io_catalog("1756-OB16E") is True

    def test_1756_if8h(self):
        assert _is_io_catalog("1756-IF8H/A") is True

    def test_1756_of8i(self):
        assert _is_io_catalog("1756-OF8I/A") is True

    def test_rio_module(self):
        assert _is_io_catalog("RIO-MODULE") is True

    def test_193_ecm(self):
        assert _is_io_catalog("193-ECM-ETR/A") is True

    def test_powerflex(self):
        assert _is_io_catalog("PowerFlex 755-EENET") is True

    def test_promass(self):
        assert _is_io_catalog("Promass_83/A") is True

    def test_ethernet_module(self):
        assert _is_io_catalog("ETHERNET-MODULE") is True


class TestModuleFilterExcludesInfra:
    def test_1756_en2t(self):
        assert _is_io_catalog("1756-EN2T") is False

    def test_1756_enbt(self):
        assert _is_io_catalog("1756-ENBT/A") is False

    def test_1756_dhrio(self):
        assert _is_io_catalog("1756-DHRIO/D") is False

    def test_1756_l84e(self):
        assert _is_io_catalog("1756-L84E") is False

    def test_1771_asb(self):
        assert _is_io_catalog("1771-ASB") is False

    def test_dpi_peripheral(self):
        assert _is_io_catalog("DPI-DRIVE-PERIPHERAL-MODULE") is False

    def test_empty(self):
        assert _is_io_catalog("") is False


# ===========================================================================
# enrich_results — source confirmation
# ===========================================================================

class TestEnrichResultsTagConfirmation:
    """L5X alias confirms a PLC tag by name match."""

    def test_tag_name_confirmed(self):
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2", "Tank 601 Valve"),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(plc_name="AN601_EV", specifier="Rack14:O.Data[3].2")
        enrich_results([result], enrichment)

        assert "L5X" in result.sources
        assert any("confirms tag" in s for s in result.audit_trail)

    def test_tag_not_in_l5x_no_confirmation(self):
        data = _make_data(alias_tags=[])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(plc_name="UNKNOWN_TAG", specifier="Rack99:I.Data[0].0")
        enrich_results([result], enrichment)

        assert "L5X" not in result.sources


class TestEnrichResultsAddressConfirmation:
    """L5X alias confirms a PLC address match."""

    def test_address_confirmed(self):
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2"),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(plc_name="SomeOtherTag", specifier="Rack14:O.Data[3].2")
        enrich_results([result], enrichment)

        assert "L5X" in result.sources
        assert any("confirm address" in s for s in result.audit_trail)


class TestEnrichResultsModuleConfirmation:
    """L5X module tree confirms IO hardware exists."""

    def test_module_name_confirmed(self):
        data = _make_data(modules=[
            _module("E300_P621", "193-ECM-ETR/A", "Local",
                    [_port("Ethernet", "192.168.12.150")]),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(dev_tag="E300_P621", plc_address="192.168.12.150")
        enrich_results([result], enrichment)

        assert "L5X" in result.sources
        assert any("confirms IO hardware" in s for s in result.audit_trail)

    def test_module_address_confirmed(self):
        data = _make_data(modules=[
            _module("Rack24_Slot06", "1756-IB16", "Rack24", [_port("ICP", "6")]),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(dev_tag="SomeDev", plc_address="6")
        enrich_results([result], enrichment)

        assert "L5X" in result.sources
        assert any("confirms hardware" in s for s in result.audit_trail)


class TestEnrichResultsDescriptionSupplemented:
    """L5X supplies description when CSV had none."""

    def test_description_filled(self):
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2", "Tank 601 Valve from L5X"),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(plc_name="AN601_EV", specifier="Rack14:O.Data[3].2")
        result.plc_tag.description = ""  # CSV had no description
        enrich_results([result], enrichment)

        assert result.plc_tag.description == "Tank 601 Valve from L5X"
        assert any("supplied description" in s for s in result.audit_trail)

    def test_description_not_overwritten(self):
        data = _make_data(alias_tags=[
            _alias("AN601_EV", "Rack14:O.Data[3].2", "L5X description"),
        ])
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(plc_name="AN601_EV", specifier="Rack14:O.Data[3].2")
        result.plc_tag.description = "CSV description"
        enrich_results([result], enrichment)

        assert result.plc_tag.description == "CSV description"


# ===========================================================================
# Full enrichment pipeline
# ===========================================================================

class TestFullEnrichmentPipeline:
    def test_mixed_results(self):
        data = _make_data(
            alias_tags=[
                _alias("AN601_EV", "Rack14:O.Data[3].2", "Tank 601 Valve"),
                _alias("DV50_AO_Deod", "N166_R[10].0", "MSG tag"),
                _alias("FT615_Remote", "DeodSys_CLXData.Integer[3]"),
            ],
            modules=[
                _module("Rack24_Slot06", "1756-IB16", "Rack24", [_port("ICP", "6")]),
                _module("ENET", "1756-EN2T", "Local",
                        [_port("ICP", "1"), _port("Ethernet", "10.9.54.52")]),
            ],
        )
        enrichment = extract_l5x_enrichment(data)

        # 1 physical alias, 1 MSG, 1 consumed
        assert len(enrichment["alias_by_address"]) == 1
        assert len(enrichment["msg_tags"]) == 1
        assert len(enrichment["consumed_tags"]) == 1
        # 1 IO module (IB16), ENET skipped
        assert "rack24_slot06" in enrichment["module_names"]
        assert "enet" not in enrichment["module_names"]

        # Enrich a matching result
        result = _match_result(plc_name="AN601_EV", specifier="Rack14:O.Data[3].2")
        enrich_results([result], enrichment)
        assert "L5X" in result.sources


# ===========================================================================
# Rung CDATA enrichment — rack-style address detection & unused flagging
# ===========================================================================

class TestRungCdataAddressFoundInCdata:
    """When no alias exists but the full address IS in rung CDATA, note it."""

    def test_plc5_address_found_in_cdata(self):
        data = _make_data(
            rung_references=["rack0_group0_slot0_io.read[4]", "some_other_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="Rack0_Group0_Slot0_IO",
            dev_tag="LT611",
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
        )
        enrich_results([result], enrichment)

        assert any("rung CDATA references" in s for s in result.audit_trail)
        assert result.classification == Classification.BOTH

    def test_clx_address_found_in_cdata(self):
        """CLX rack address like Rack26:12:O.Data.8 found in CDATA."""
        data = _make_data(
            rung_references=["rack26:12:o.data.8", "some_other_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="TSV246_EV",
            dev_tag="TSV246",
            plc_address="Rack26:12:O.Data.8",
        )
        enrich_results([result], enrichment)

        assert any("rung CDATA references" in s for s in result.audit_trail)
        assert result.classification == Classification.BOTH


class TestRungCdataAddressNotInCdata:
    """When no alias AND no rung CDATA reference, flag as RACK_ONLY."""

    def test_plc5_address_not_in_cdata(self):
        data = _make_data(
            rung_references=["some_other_tag", "unrelated_address"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="Rack0_Group0_Slot0_IO",
            dev_tag="LT611",
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.RACK_ONLY
        assert result.conflict_flag is True
        assert any("may be unused" in s for s in result.audit_trail)

    def test_clx_address_not_in_cdata(self):
        """CLX rack address not found in CDATA — real-world scenario."""
        data = _make_data(
            rung_references=["some_other_tag", "unrelated_address"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="TSV246_EV",
            dev_tag="TSV246",
            plc_address="Rack26:12:O.Data.8",
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.RACK_ONLY
        assert result.conflict_flag is True
        assert any("may be unused" in s for s in result.audit_trail)

    def test_no_rung_refs_available(self):
        """When rung_references is empty, CDATA pass is skipped (no false positives)."""
        data = _make_data()  # no rung_references
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="TSV246_EV",
            dev_tag="TSV246",
            plc_address="Rack26:12:O.Data.8",
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.BOTH
        assert result.conflict_flag is False


class TestRungCdataSkipsAliasedTags:
    """When an alias IS found for the address, the CDATA pass should not fire."""

    def test_aliased_tag_not_flagged(self):
        data = _make_data(
            alias_tags=[
                _alias("LT_611", "Rack0_Group0_Slot0_IO.READ[4]", "Level Transmitter"),
            ],
            rung_references=[],  # empty CDATA — but alias exists, so no flag
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            plc_name="Rack0_Group0_Slot0_IO",
            dev_tag="LT611",
            plc_address="Rack0_Group0_Slot0_IO.READ[4]",
        )
        enrich_results([result], enrichment)

        assert result.plc_tag.name == "LT_611"
        assert result.classification != Classification.RACK_ONLY
        assert result.conflict_flag is False


class TestRungCdataOnlyAffectsRackAddresses:
    """Non-rack-style addresses should not trigger the CDATA check."""

    def test_non_rack_address_unaffected(self):
        data = _make_data(
            rung_references=["some_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        # ENet-style address — not rack-style
        result = _match_result(
            plc_name="LT_611",
            dev_tag="LT611",
            plc_address="E300_P621:I.Ch0Data",
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.BOTH
        assert result.conflict_flag is False


# ===========================================================================
# Spare CDATA check — spare IO points used in logic become conflicts
# ===========================================================================

class TestSpareCdataConflict:
    """Spare IO points found in rung CDATA should be reclassified as conflicts."""

    def test_spare_address_in_cdata_becomes_conflict(self):
        """Direct address reference in CDATA -> spare becomes conflict."""
        data = _make_data(
            rung_references=["rack26:12:o.data.8", "some_other_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            dev_tag="SPARE",
            plc_address="Rack26:12:O.Data.8",
            classification=Classification.SPARE,
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.CONFLICT
        assert result.conflict_flag is True
        assert any("spare but address is referenced in rung CDATA" in s for s in result.audit_trail)

    def test_spare_alias_in_cdata_becomes_conflict(self):
        """Alias tag name for spare address found in CDATA -> conflict."""
        data = _make_data(
            alias_tags=[
                _alias("LT_611", "Rack26:14:I.Ch0Data", "Level Transmitter"),
            ],
            rung_references=["lt_611", "some_other_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            dev_tag="SPARE",
            plc_address="Rack26:14:I.Ch0Data",
            classification=Classification.SPARE,
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.CONFLICT
        assert result.conflict_flag is True

    def test_spare_not_in_cdata_stays_spare(self):
        """Spare address NOT in CDATA -> stays spare."""
        data = _make_data(
            rung_references=["some_other_tag", "unrelated_address"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            dev_tag="SPARE",
            plc_address="Rack26:12:O.Data.8",
            classification=Classification.SPARE,
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.SPARE
        assert result.conflict_flag is False

    def test_spare_no_rung_refs_stays_spare(self):
        """No rung references available -> spare stays spare."""
        data = _make_data()
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            dev_tag="SPARE",
            plc_address="Rack26:12:O.Data.8",
            classification=Classification.SPARE,
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.SPARE
        assert result.conflict_flag is False

    def test_spare_no_plc_address_stays_spare(self):
        """Spare with no PLC address -> stays spare (nothing to check)."""
        data = _make_data(
            rung_references=["some_tag"],
        )
        enrichment = extract_l5x_enrichment(data)

        result = _match_result(
            dev_tag="SPARE",
            plc_address="",
            classification=Classification.SPARE,
        )
        enrich_results([result], enrichment)

        assert result.classification == Classification.SPARE
        assert result.conflict_flag is False
