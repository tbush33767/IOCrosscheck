"""PLC tag classification logic for IO Crosscheck."""
from __future__ import annotations

import re

from io_crosscheck.models import PLCTag, TagCategory, RecordType

_RACK_IO_PATTERN = re.compile(r"^Rack\d+:[IO]$", re.IGNORECASE)
_ENET_PREFIX_PATTERN = re.compile(r"^(?:E300|VFD|IPDev|IPDEV)_", re.IGNORECASE)
_PROGRAM_DATATYPES = frozenset({
    "dint", "real", "int", "bool", "timer", "counter", "string",
})


def classify_tag(tag: PLCTag) -> TagCategory:
    """Classify a PLC tag into its category based on detection rules.

    Priority order matters: check record-type-based categories first,
    then name-based, then datatype-based.
    """
    if is_alias_tag(tag):
        return TagCategory.ALIAS
    if tag.record_type == RecordType.COMMENT and tag.specifier:
        return TagCategory.BIT_LEVEL_COMMENT
    if is_enet_device_tag(tag):
        return TagCategory.ENET_DEVICE
    if is_io_module_tag(tag):
        return TagCategory.IO_MODULE
    if is_rack_io_tag(tag):
        return TagCategory.RACK_IO
    if is_program_tag(tag):
        return TagCategory.PROGRAM
    return TagCategory.UNKNOWN


def is_io_module_tag(tag: PLCTag) -> bool:
    """True if datatype starts with AB: or EH: (Rockwell/EtherNet module definitions)."""
    dt = tag.datatype.strip().upper()
    return dt.startswith("AB:") or dt.startswith("EH:")


def is_rack_io_tag(tag: PLCTag) -> bool:
    """True if name matches Rack<N>:I or Rack<N>:O pattern."""
    return bool(_RACK_IO_PATTERN.match(tag.name.strip()))


def is_enet_device_tag(tag: PLCTag) -> bool:
    """True if name matches E300_*, VFD_*, IPDev_*, IPDEV_* prefix patterns."""
    return bool(_ENET_PREFIX_PATTERN.match(tag.name.strip()))


def is_alias_tag(tag: PLCTag) -> bool:
    """True if record type is ALIAS."""
    return tag.record_type == RecordType.ALIAS


def is_program_tag(tag: PLCTag) -> bool:
    """True if datatype is DINT, REAL, INT, BOOL, TIMER, COUNTER, STRING, or known UDT."""
    dt = tag.datatype.strip().lower()
    return dt in _PROGRAM_DATATYPES


def is_spare(io_tag: str) -> bool:
    """True if the IO tag indicates a spare point."""
    tag = io_tag.strip()
    return tag.lower() == "spare"


# ---------------------------------------------------------------------------
# Inter-controller MSG / consumed-tag detection (for L5X alias targets)
# ---------------------------------------------------------------------------

_MSG_READ_PATTERN = re.compile(r"^[NBF]\d+_R\[", re.IGNORECASE)
_MSG_WRITE_PATTERN = re.compile(r"^N\d+_W\[", re.IGNORECASE)
_MSG_RW_PATTERN = re.compile(r"^F\d+_RW\[", re.IGNORECASE)
_CONSUMED_PATTERN = re.compile(
    r"^(?!Rack\d)[\w]+(?:\[\d+\])?\.[\w]", re.IGNORECASE
)


def detect_msg_direction(alias_for: str) -> tuple[bool, str]:
    """Check if an alias target is an inter-controller MSG address.

    Returns ``(is_msg, direction)`` where *direction* is one of
    ``'READ'``, ``'WRITE'``, or ``'READ/WRITE'``.  When *is_msg* is
    ``False``, *direction* is the empty string.
    """
    if not alias_for:
        return False, ""
    target = alias_for.strip()
    if _MSG_WRITE_PATTERN.match(target):
        return True, "WRITE"
    if _MSG_RW_PATTERN.match(target):
        return True, "READ/WRITE"
    if _MSG_READ_PATTERN.match(target):
        return True, "READ"
    return False, ""


def is_consumed_reference(alias_for: str) -> bool:
    """True if the alias target looks like a consumed / UDT member reference.

    Examples that match:
        ``DeodSys_CLXData.Integer[3]``
        ``Tanks[119].Device.Heat_Permissive``
        ``Flow[40].Device.FlowTotal_Remote``

    Examples that do NOT match (these are physical IO):
        ``Rack6:I.Data[0].4``
        ``Rack16_Group0_Slot0_IO.READ[18]``
    """
    if not alias_for:
        return False
    target = alias_for.strip()
    # Exclude anything that looks like a Rack address or MSG address
    if target.upper().startswith("RACK"):
        return False
    if _MSG_READ_PATTERN.match(target) or _MSG_WRITE_PATTERN.match(target) or _MSG_RW_PATTERN.match(target):
        return False
    # Exclude ENet device references (IPDEV_*, E300_*, VFD_*)
    if _ENET_PREFIX_PATTERN.match(target):
        return False
    return bool(_CONSUMED_PATTERN.match(target))
