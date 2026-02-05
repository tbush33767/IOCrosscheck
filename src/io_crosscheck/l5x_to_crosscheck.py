"""L5X enrichment layer for the IO Crosscheck engine.

The L5X file is an *optional third input* that enriches the baseline
CSV + XLSX crosscheck.  It does **not** replace either side.

What the L5X adds:
  - Alias-to-address mappings confirm CSV COMMENT records (source confirmation)
  - Module tree validates that referenced hardware exists
  - Descriptions from L5X can fill gaps in CSV data
  - Inter-controller MSG aliases and consumed tags are flagged separately
"""
from __future__ import annotations

import re
from typing import Any

from io_crosscheck.models import (
    MatchResult,
    PLCTag,
    RecordType,
    Classification,
    Confidence,
)
from io_crosscheck.normalizers import (
    normalize_address,
    normalize_tag,
    strip_suffixes,
    detect_address_format,
)
from io_crosscheck.classifiers import detect_msg_direction, is_consumed_reference


# ---------------------------------------------------------------------------
# IO catalog patterns (include list)
# ---------------------------------------------------------------------------

_IO_CATALOG_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^1756-IB", re.IGNORECASE),       # CLX discrete input
    re.compile(r"^1756-OB", re.IGNORECASE),       # CLX discrete output
    re.compile(r"^1756-IF", re.IGNORECASE),       # CLX analog input
    re.compile(r"^1756-OF", re.IGNORECASE),       # CLX analog output
    re.compile(r"^RIO-MODULE$", re.IGNORECASE),   # PLC5 scanned IO
    re.compile(r"^193-ECM", re.IGNORECASE),       # E300 overload relay
    re.compile(r"^PowerFlex", re.IGNORECASE),     # VFD
    re.compile(r"^Promass", re.IGNORECASE),       # Flow meter
    re.compile(r"^ETHERNET-MODULE$", re.IGNORECASE),  # Generic ENet device
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_l5x_enrichment(data: dict[str, Any]) -> dict[str, Any]:
    """Pre-process L5X data into lookup structures for enrichment.

    Returns a dict with:
        alias_by_address: dict  — normalized address → list of alias dicts
        alias_by_name:    dict  — normalized tag name → alias dict
        module_names:     set   — names of all IO-catalog modules
        module_addresses: set   — normalized addresses of all IO modules
        msg_tags:         list  — inter-controller MSG aliases (flagged)
        consumed_tags:    list  — consumed/UDT-reference aliases (flagged)
    """
    alias_by_address: dict[str, list[dict[str, str]]] = {}
    alias_by_name: dict[str, dict[str, str]] = {}
    msg_tags: list[dict[str, str]] = []
    consumed_tags: list[dict[str, str]] = []

    ctrl_tags = data.get("controller_tags", {})
    alias_list = ctrl_tags.get("alias_tags", [])

    for alias in alias_list:
        name = alias.get("name", "")
        alias_for = alias.get("alias_for", "")
        description = alias.get("description", "") or ""

        if not name or not alias_for:
            continue

        # Check for inter-controller MSG
        is_msg, direction = detect_msg_direction(alias_for)
        if is_msg:
            msg_tags.append({
                "name": name,
                "alias_for": alias_for,
                "description": description,
                "direction": direction,
            })
            continue

        # Check for consumed / UDT member reference
        if is_consumed_reference(alias_for):
            consumed_tags.append({
                "name": name,
                "alias_for": alias_for,
                "description": description,
            })
            continue

        # Physical IO alias — index by address and name
        addr_key = normalize_address(alias_for)
        entry = {"name": name, "alias_for": alias_for, "description": description}
        alias_by_address.setdefault(addr_key, []).append(entry)
        alias_by_name[normalize_tag(name)] = entry

    # Build module lookup sets
    module_names: set[str] = set()
    module_addresses: set[str] = set()
    modules = data.get("modules", [])

    for mod in modules:
        catalog = mod.get("catalog_number", "")
        if not _is_io_catalog(catalog):
            continue
        name = mod.get("name", "")
        if name:
            module_names.add(name.lower())
        for port in mod.get("ports", []):
            addr = port.get("address", "")
            if addr:
                module_addresses.add(addr.lower())

    return {
        "alias_by_address": alias_by_address,
        "alias_by_name": alias_by_name,
        "module_names": module_names,
        "module_addresses": module_addresses,
        "msg_tags": msg_tags,
        "consumed_tags": consumed_tags,
    }


def enrich_results(
    results: list[MatchResult],
    l5x_enrichment: dict[str, Any],
) -> list[MatchResult]:
    """Enrich crosscheck results with L5X source confirmation.

    Key behaviours:
      - **Rack-Only upgrade:** When a result is ``Both (Rack Only)`` and the
        L5X contains an alias whose address matches the IO device's PLC
        address, the result is upgraded to ``Both`` with ``Exact`` confidence
        and the PLCTag is replaced with the actual alias tag name.
      - **Source confirmation:** Adds ``'L5X'`` to ``result.sources`` when
        the L5X independently confirms the match.
      - **Description fill:** Supplies a description from L5X when the CSV
        had none.
    """
    alias_by_address = l5x_enrichment["alias_by_address"]
    alias_by_name = l5x_enrichment["alias_by_name"]
    module_names = l5x_enrichment["module_names"]
    module_addresses = l5x_enrichment["module_addresses"]

    for result in results:
        l5x_confirmations: list[str] = []

        # --- Rack-Only upgrade via IO device address → L5X alias ----------
        if (
            result.io_device
            and result.io_device.plc_address
            and result.classification == Classification.RACK_ONLY
        ):
            addr_key = normalize_address(result.io_device.plc_address)
            if addr_key in alias_by_address:
                aliases = alias_by_address[addr_key]
                best = aliases[0]  # first match
                desc = best.get("description", "")

                # Replace the rack-level PLCTag with the actual alias tag
                result.plc_tag = PLCTag(
                    record_type=RecordType.COMMENT,
                    name=best["name"],
                    base_name=strip_suffixes(best["name"]),
                    description=desc,
                    specifier=best["alias_for"],
                    scope="controller",
                )
                result.classification = Classification.BOTH
                result.confidence = Confidence.EXACT
                result.strategy_id = 1  # effectively a direct address match
                l5x_confirmations.append(
                    f"L5X alias '{best['name']}' → '{best['alias_for']}' "
                    f"upgraded Rack Only → Both (Exact)"
                )

        # --- Check PLC tag side ---
        if result.plc_tag:
            tag = result.plc_tag
            tag_name_norm = normalize_tag(tag.name)

            # Does the L5X have an alias with this name?
            if tag_name_norm in alias_by_name:
                l5x_alias = alias_by_name[tag_name_norm]
                l5x_confirmations.append(
                    f"L5X alias '{l5x_alias['name']}' → '{l5x_alias['alias_for']}' confirms tag"
                )

                # If the CSV had no description but L5X does, supplement it
                if not tag.description and l5x_alias.get("description"):
                    tag.description = l5x_alias["description"]
                    l5x_confirmations.append(
                        f"L5X supplied description: '{l5x_alias['description']}'"
                    )

            # Does the L5X have an alias matching this address?
            if tag.specifier:
                addr_norm = normalize_address(tag.specifier)
                if addr_norm in alias_by_address:
                    aliases = alias_by_address[addr_norm]
                    alias_names = [a["name"] for a in aliases]
                    l5x_confirmations.append(
                        f"L5X alias(es) {alias_names} confirm address '{tag.specifier}'"
                    )

        # --- Check IO device side ---
        if result.io_device:
            dev = result.io_device

            # Does the L5X module tree contain this device's address?
            if dev.plc_address:
                addr_norm = dev.plc_address.lower()
                if addr_norm in module_addresses:
                    l5x_confirmations.append(
                        f"L5X module tree confirms hardware at '{dev.plc_address}'"
                    )

                # Also check alias_by_address for the device's PLC address
                # (skip if we already did the rack-only upgrade above)
                if result.classification != Classification.BOTH or not any(
                    "upgraded Rack Only" in c for c in l5x_confirmations
                ):
                    addr_key = normalize_address(dev.plc_address)
                    if addr_key in alias_by_address:
                        aliases = alias_by_address[addr_key]
                        alias_names = [a["name"] for a in aliases]
                        l5x_confirmations.append(
                            f"L5X alias(es) {alias_names} reference device address '{dev.plc_address}'"
                        )

            # Check if device tag name matches a module name
            if dev.device_tag and dev.device_tag.lower() in module_names:
                l5x_confirmations.append(
                    f"L5X module '{dev.device_tag}' confirms IO hardware exists"
                )

        # Apply confirmations
        if l5x_confirmations:
            if "L5X" not in result.sources:
                result.sources.append("L5X")
            for note in l5x_confirmations:
                result.audit_trail.append(note)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_io_catalog(catalog: str) -> bool:
    """True if the catalog number matches one of the IO include patterns."""
    if not catalog:
        return False
    return any(pat.match(catalog) for pat in _IO_CATALOG_PATTERNS)


def _is_enet_catalog(catalog: str) -> bool:
    """True if the catalog number is an ENet device type."""
    if not catalog:
        return False
    cat = catalog.upper()
    return (
        cat.startswith("193-ECM")
        or cat.startswith("POWERFLEX")
        or cat.startswith("PROMASS")
        or cat == "ETHERNET-MODULE"
    )
