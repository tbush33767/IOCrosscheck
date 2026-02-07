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
    Classification,
    MatchResult,
    PLCTag,
    RecordType,
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
        rung_references:  set   — lowercased operands found in rung CDATA
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

    # Build rung reference set from CDATA operands
    rung_refs_list = data.get("rung_references", [])
    rung_references: set[str] = set(rung_refs_list)

    return {
        "alias_by_address": alias_by_address,
        "alias_by_name": alias_by_name,
        "module_names": module_names,
        "module_addresses": module_addresses,
        "rung_references": rung_references,
        "msg_tags": msg_tags,
        "consumed_tags": consumed_tags,
    }


def enrich_results(
    results: list[MatchResult],
    l5x_enrichment: dict[str, Any],
) -> list[MatchResult]:
    """Enrich crosscheck results with L5X source confirmation.

    Key behaviours:
      - **Source confirmation:** Adds ``'L5X'`` to ``result.sources`` when
        the L5X independently confirms the match.
      - **Description fill:** Supplies a description from L5X when the CSV
        had none.
    """
    alias_by_address = l5x_enrichment["alias_by_address"]
    alias_by_name = l5x_enrichment["alias_by_name"]
    module_names = l5x_enrichment["module_names"]
    module_addresses = l5x_enrichment["module_addresses"]
    rung_references = l5x_enrichment.get("rung_references", set())

    for result in results:
        l5x_confirmations: list[str] = []
        alias_found_for_device = False

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
                addr_key = normalize_address(dev.plc_address)
                if addr_key in alias_by_address:
                    aliases = alias_by_address[addr_key]
                    alias_names = [a["name"] for a in aliases]
                    alias_found_for_device = True
                    l5x_confirmations.append(
                        f"L5X alias(es) {alias_names} reference device address '{dev.plc_address}'"
                    )

                    # If the current PLC tag is just a rack-level base name
                    # (e.g. "Rack0_Group0_Slot0_IO"), upgrade it to the real
                    # alias tag name from the L5X so the user sees the actual
                    # PLC tag instead of the rack structure.
                    if result.plc_tag and len(aliases) == 1:
                        alias = aliases[0]
                        rack_base = result.plc_tag.name.strip().lower()
                        addr_base = dev.plc_address.split(".")[0].strip().lower()
                        if rack_base == addr_base:
                            old_name = result.plc_tag.name
                            result.plc_tag = PLCTag(
                                name=alias["name"],
                                description=alias.get("description", "") or result.plc_tag.description,
                                record_type=RecordType.TAG,
                                specifier=alias["alias_for"],
                            )
                            l5x_confirmations.append(
                                f"L5X upgraded PLC tag from rack-level '{old_name}' to alias '{alias['name']}'"
                            )

                # --- Rung CDATA pass for rack-style addresses with no alias ---
                # If the device has a rack-style address (CLX or PLC5) but
                # the L5X has no alias for it, check whether the full
                # address is referenced directly in rung logic.
                addr_fmt = detect_address_format(dev.plc_address)
                is_rack_addr = addr_fmt in ("CLX", "PLC5")

                if (
                    not alias_found_for_device
                    and is_rack_addr
                    and rung_references
                    and result.classification != Classification.SPARE
                ):
                    full_addr_lower = dev.plc_address.lower()
                    if full_addr_lower in rung_references:
                        l5x_confirmations.append(
                            f"L5X rung CDATA references address '{dev.plc_address}' directly (no alias, used in logic)"
                        )
                    else:
                        # IO point has a rack-style address but no L5X alias
                        # AND is not referenced in any rung logic — flag it
                        result.classification = Classification.RACK_ONLY
                        result.conflict_flag = True
                        l5x_confirmations.append(
                            f"L5X: No alias found for '{dev.plc_address}' and address not referenced in rung CDATA — IO point may be unused"
                        )

            # Check if device tag name matches a module name
            if dev.device_tag and dev.device_tag.lower() in module_names:
                l5x_confirmations.append(
                    f"L5X module '{dev.device_tag}' confirms IO hardware exists"
                )

        # --- Spare CDATA check ---
        # If the IO list labels this point as spare but the address (or an
        # alias for it) appears in rung CDATA, the point is actually used
        # in logic and should be flagged as a conflict.
        if (
            result.classification == Classification.SPARE
            and result.io_device
            and result.io_device.plc_address
            and rung_references
        ):
            addr_lower = result.io_device.plc_address.lower()
            addr_key = normalize_address(result.io_device.plc_address)
            # Check if the full address is directly in rung CDATA
            found_in_cdata = addr_lower in rung_references
            # Also check if any alias for this address is in rung CDATA
            if not found_in_cdata and addr_key in alias_by_address:
                for alias in alias_by_address[addr_key]:
                    if alias["name"].lower() in rung_references:
                        found_in_cdata = True
                        break
            if found_in_cdata:
                result.classification = Classification.CONFLICT
                result.conflict_flag = True
                l5x_confirmations.append(
                    f"L5X: IO list marks '{result.io_device.plc_address}' as spare but address is referenced in rung CDATA — point is used in logic"
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
