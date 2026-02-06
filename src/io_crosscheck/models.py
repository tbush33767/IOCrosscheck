"""Data models for IO Crosscheck."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecordType(Enum):
    TAG = "TAG"
    COMMENT = "COMMENT"
    ALIAS = "ALIAS"
    RCOMMENT = "RCOMMENT"


class TagCategory(Enum):
    IO_MODULE = "IO_Module"
    RACK_IO = "Rack_IO"
    ENET_DEVICE = "ENet_Device"
    ALIAS = "Alias"
    PROGRAM = "Program"
    BIT_LEVEL_COMMENT = "Bit_Level_Comment"
    UNKNOWN = "Unknown"


class AddressFormat(Enum):
    PLC5 = "PLC5"
    CLX = "CLX"
    UNKNOWN = "Unknown"


class Classification(Enum):
    BOTH = "Both"
    IO_LIST_ONLY = "IO List Only"
    PLC_ONLY = "PLC Only"
    CONFLICT = "Conflict"
    SPARE = "Spare"


class Confidence(Enum):
    EXACT = "Exact"
    HIGH = "High"
    PARTIAL = "Partial"
    SUPPORTING = "Supporting"


@dataclass
class PLCTag:
    record_type: RecordType
    name: str
    base_name: str = ""
    description: str = ""
    datatype: str = ""
    scope: str = ""
    specifier: str = ""
    suffixes: list[str] = field(default_factory=list)
    category: TagCategory = TagCategory.UNKNOWN
    source_line: int = 0


@dataclass
class IODevice:
    panel: str = ""
    rack: str = ""
    group: str = ""
    slot: str = ""
    channel: str = ""
    plc_address: str = ""
    io_tag: str = ""
    device_tag: str = ""
    module_type: str = ""
    module: str = ""
    range_low: str = ""
    range_high: str = ""
    units: str = ""
    address_format: AddressFormat = AddressFormat.UNKNOWN
    source_row: int = 0


@dataclass
class MatchResult:
    io_device: Optional[IODevice] = None
    plc_tag: Optional[PLCTag] = None
    strategy_id: int = 0
    confidence: Confidence = Confidence.EXACT
    classification: Classification = Classification.IO_LIST_ONLY
    conflict_flag: bool = False
    audit_trail: list[str] = field(default_factory=list)
    reviewer: str = ""
    review_timestamp: str = ""
    sources: list[str] = field(default_factory=list)
