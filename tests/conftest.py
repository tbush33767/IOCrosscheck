"""Shared fixtures for IO Crosscheck tests."""
from __future__ import annotations

import pytest

from io_crosscheck.models import (
    PLCTag, IODevice, RecordType, TagCategory, AddressFormat,
)


# ---------------------------------------------------------------------------
# PLCTag fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clx_rack_tag() -> PLCTag:
    """A ControlLogix rack IO TAG entry."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="Rack11:I",
        base_name="Rack11",
        datatype="AB:1756_IF8:I:0",
        scope="",
        category=TagCategory.RACK_IO,
        source_line=100,
    )


@pytest.fixture
def clx_comment_tag() -> PLCTag:
    """A COMMENT record pointing to a specific bit on a CLX rack."""
    return PLCTag(
        record_type=RecordType.COMMENT,
        name="Rack0:I",
        base_name="Rack0",
        description="HLSTL5A",
        specifier="Rack0:I.DATA[5].7",
        category=TagCategory.BIT_LEVEL_COMMENT,
        source_line=200,
    )


@pytest.fixture
def plc5_rack_tag() -> PLCTag:
    """A PLC5-format rack IO TAG entry."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="Rack0_Group0_Slot0_IO",
        base_name="Rack0_Group0_Slot0_IO",
        datatype="AB:1771_IFE:I:0",
        scope="",
        category=TagCategory.IO_MODULE,
        source_line=300,
    )


@pytest.fixture
def enet_e300_tag() -> PLCTag:
    """An E300 EtherNet/IP module TAG."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="E300_P621:I",
        base_name="E300_P621",
        datatype="AB:E300_OL:I:0",
        scope="",
        category=TagCategory.ENET_DEVICE,
        source_line=400,
    )


@pytest.fixture
def enet_vfd_tag() -> PLCTag:
    """A VFD EtherNet/IP module TAG."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="VFD_M101:O",
        base_name="VFD_M101",
        datatype="AB:PF525:O:0",
        scope="",
        category=TagCategory.ENET_DEVICE,
        source_line=410,
    )


@pytest.fixture
def enet_ipdev_tag() -> PLCTag:
    """An IPDev EtherNet/IP module TAG."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="IPDev_FT601:I",
        base_name="IPDev_FT601",
        datatype="EH:Promass:I:0",
        scope="",
        category=TagCategory.ENET_DEVICE,
        source_line=420,
    )


@pytest.fixture
def program_dint_tag() -> PLCTag:
    """A program-level DINT tag (working memory, not IO)."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="MyCounter",
        base_name="MyCounter",
        datatype="DINT",
        scope="MainProgram",
        category=TagCategory.PROGRAM,
        source_line=500,
    )


@pytest.fixture
def program_timer_tag() -> PLCTag:
    """A program-level TIMER tag."""
    return PLCTag(
        record_type=RecordType.TAG,
        name="Delay_Timer",
        base_name="Delay_Timer",
        datatype="TIMER",
        scope="MainProgram",
        category=TagCategory.PROGRAM,
        source_line=510,
    )


@pytest.fixture
def alias_tag() -> PLCTag:
    """An ALIAS record."""
    return PLCTag(
        record_type=RecordType.ALIAS,
        name="Local:1:I.Data.0",
        base_name="Local:1:I",
        description="",
        scope="",
        category=TagCategory.ALIAS,
        source_line=600,
    )


@pytest.fixture
def comment_with_conflict() -> PLCTag:
    """A COMMENT where the description differs from the IO List device tag."""
    return PLCTag(
        record_type=RecordType.COMMENT,
        name="Rack0:I",
        base_name="Rack0",
        description="HLSTL5C",
        specifier="Rack0:I.DATA[5].6",
        category=TagCategory.BIT_LEVEL_COMMENT,
        source_line=210,
    )


# ---------------------------------------------------------------------------
# IODevice fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clx_io_device() -> IODevice:
    """A CLX-format IO device from the IO List."""
    return IODevice(
        panel="X3",
        rack="11",
        slot="3",
        channel="13",
        plc_address="Rack11:I.Data[3].13",
        io_tag="LT611",
        device_tag="LT611",
        module_type="AI",
        address_format=AddressFormat.CLX,
        source_row=50,
    )


@pytest.fixture
def clx_io_device_case_mismatch() -> IODevice:
    """A CLX device whose address has different case than PLC."""
    return IODevice(
        panel="X1",
        rack="0",
        slot="5",
        channel="7",
        plc_address="Rack0:I.Data[5].7",
        io_tag="HLSTL5A",
        device_tag="HLSTL5A",
        module_type="DI",
        address_format=AddressFormat.CLX,
        source_row=60,
    )


@pytest.fixture
def plc5_io_device() -> IODevice:
    """A PLC5-format IO device from the IO List."""
    return IODevice(
        panel="X1",
        rack="0",
        group="0",
        slot="0",
        channel="4",
        plc_address="Rack0_Group0_Slot0_IO.READ[4]",
        io_tag="TSV22_EV",
        device_tag="TSV22",
        module_type="DO",
        address_format=AddressFormat.PLC5,
        source_row=70,
    )


@pytest.fixture
def spare_io_device() -> IODevice:
    """A spare point in the IO List."""
    return IODevice(
        panel="X1",
        rack="0",
        group="0",
        slot="0",
        channel="14",
        plc_address="Rack0_Group0_Slot0_IO.READ[14]",
        io_tag="Spare",
        device_tag="",
        module_type="DI",
        address_format=AddressFormat.PLC5,
        source_row=80,
    )


@pytest.fixture
def conflict_io_device() -> IODevice:
    """An IO device that will conflict with PLC comment at same address."""
    return IODevice(
        panel="X1",
        rack="0",
        slot="5",
        channel="6",
        plc_address="Rack0:I.Data[5].6",
        io_tag="FT656B_Pulse",
        device_tag="FT656B",
        module_type="DI",
        address_format=AddressFormat.CLX,
        source_row=90,
    )


@pytest.fixture
def enet_io_device() -> IODevice:
    """An IO device that should match an ENet PLC tag."""
    return IODevice(
        panel="X2",
        rack="",
        slot="",
        channel="",
        plc_address="",
        io_tag="P621",
        device_tag="P621",
        module_type="",
        address_format=AddressFormat.UNKNOWN,
        source_row=110,
    )


@pytest.fixture
def suffix_io_device() -> IODevice:
    """An IO device with a suffix that needs stripping for matching."""
    return IODevice(
        panel="X1",
        rack="0",
        slot="6",
        channel="0",
        plc_address="Rack0:I.Data[6].0",
        io_tag="AS611_AUX",
        device_tag="AS611",
        module_type="DI",
        address_format=AddressFormat.CLX,
        source_row=120,
    )
