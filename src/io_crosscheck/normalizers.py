"""Tag and address normalization for IO Crosscheck."""
from __future__ import annotations

import re

# Ordered longest-first so that _Input is checked before _In, etc.
KNOWN_SUFFIXES = [
    "_FailedToClose", "_FailedToOpen", "_OnTimer", "_OffTimer",
    "_Monitor", "_Failed", "_Pulse", "_Input", "_Out", "_Old",
    "_Pos", "_EV", "_MC", "_AUX", "_ZSO", "_ZSC", "_In",
]

_ENET_PREFIXES = ("E300_", "VFD_", "IPDev_", "IPDEV_")

_CLX_PATTERN = re.compile(
    r"^Rack\d+:(?:[IO]|\d+:[IO])", re.IGNORECASE
)
_CLX_RACK_BASE_PATTERN = re.compile(
    r"^(Rack\d+:[IO])", re.IGNORECASE
)
_CLX_SLOT_RACK_BASE_PATTERN = re.compile(
    r"^(Rack\d+):\d+:[IO]", re.IGNORECASE
)
_PLC5_PATTERN = re.compile(
    r"^Rack\d+_Group\d+_Slot\d+_IO\.", re.IGNORECASE
)
_ENET_PATTERN = re.compile(
    r"^(?:E300|VFD|IPDev|IPDEV)_(.+?)(?::[IOCS].*)?$", re.IGNORECASE
)


def normalize_tag(tag: str) -> str:
    """Strip known suffixes and case-fold a tag name."""
    tag = tag.strip()
    if not tag:
        return ""
    tag = strip_suffixes(tag)
    return tag.lower()


def strip_suffixes(tag: str, suffixes: list[str] | None = None) -> str:
    """Strip the first matching known suffix from a tag name."""
    if not tag:
        return ""
    suffix_list = suffixes if suffixes is not None else KNOWN_SUFFIXES
    tag_lower = tag.lower()
    for suffix in suffix_list:
        if tag_lower.endswith(suffix.lower()):
            return tag[: len(tag) - len(suffix)]
    return tag


def normalize_address(address: str) -> str:
    """Case-fold and normalize a PLC address for comparison."""
    address = address.strip()
    if not address:
        return ""
    return address.lower()


def detect_address_format(address: str) -> str:
    """Return 'CLX', 'PLC5', or 'Unknown' for a given address string."""
    address = address.strip()
    if not address:
        return "Unknown"
    if _CLX_PATTERN.match(address):
        return "CLX"
    if _PLC5_PATTERN.match(address):
        return "PLC5"
    return "Unknown"


def extract_rack_base(address: str) -> str | None:
    """Extract the rack base from a CLX address.

    Standard:      'Rack11:I.DATA[3].13' -> 'Rack11:I'
    Slot-specific: 'Rack25:8:I.Data.4'   -> 'Rack25'
    """
    if not address:
        return None
    addr = address.strip()
    m = _CLX_RACK_BASE_PATTERN.match(addr)
    if m:
        return m.group(1)
    m = _CLX_SLOT_RACK_BASE_PATTERN.match(addr)
    if m:
        return m.group(1)
    return None


def extract_enet_device(tag_name: str) -> str | None:
    """Extract embedded device identifier from ENet module tags.

    E.g. 'E300_P621:I' -> 'P621', 'VFD_M101:O' -> 'M101'.
    Returns None if the tag doesn't match an ENet prefix pattern.
    """
    if not tag_name:
        return None
    m = _ENET_PATTERN.match(tag_name.strip())
    if m:
        return m.group(1)
    return None
