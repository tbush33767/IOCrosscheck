"""Extract all available data from an RSLogix 5000 / Studio 5000 L5X project file."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import l5x
import l5x.tag


# Max array elements to capture in detail
_MAX_ARRAY_ELEMENTS = 10
# Max structure nesting depth
_MAX_DEPTH = 2


def extract_l5x(filepath: str | Path) -> dict[str, Any]:
    """Walk the entire L5X project tree and return a structured dict of all data.

    Returns a dict with keys:
        filename, controller, modules, controller_tags, programs, statistics
    """
    filepath = Path(filepath)
    project = l5x.Project(str(filepath))

    data: dict[str, Any] = {
        "filename": filepath.name,
        "controller": _extract_controller_info(project),
        "modules": _extract_modules(project),
        "controller_tags": _extract_scope_tags(project.controller.tags),
        "programs": _extract_programs(project),
        "statistics": {},
    }

    # Build statistics
    data["statistics"] = _build_statistics(data)
    return data


# ---------------------------------------------------------------------------
# Controller info
# ---------------------------------------------------------------------------

def _extract_controller_info(project: l5x.Project) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        info["comm_path"] = project.controller.comm_path
    except Exception:
        info["comm_path"] = None
    try:
        info["snn"] = project.controller.snn
    except Exception:
        info["snn"] = None
    return info


# ---------------------------------------------------------------------------
# I/O Modules
# ---------------------------------------------------------------------------

def _extract_modules(project: l5x.Project) -> list[dict[str, Any]]:
    """Extract ALL modules by walking the raw XML tree.

    The l5x library API (project.modules) only exposes top-level modules.
    For PLC5 upgrade projects with RIO scanned backplanes, the IO tree has
    deeply nested <Module> elements that the API misses. We parse the raw
    XML via project.doc to capture everything.
    """
    modules: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        root = project.doc
        for module_elem in root.iter("Module"):
            name = module_elem.get("Name", "")
            if name in seen:
                continue
            seen.add(name)
            mod_data = _extract_module_from_xml(module_elem)
            modules.append(mod_data)
    except Exception:
        pass

    return modules


def _extract_module_from_xml(elem) -> dict[str, Any]:
    """Extract module data directly from an XML <Module> element.

    This captures RIO adapters, scanned backplane modules, ENet bridges,
    and any other nested modules the l5x API doesn't expose.
    """
    mod_data: dict[str, Any] = {
        "name": elem.get("Name", ""),
        "source": "xml",
        "catalog_number": elem.get("CatalogNumber", ""),
        "parent_module": elem.get("ParentModule", ""),
        "parent_mod_port_id": elem.get("ParentModPortId", ""),
        "inhibited": elem.get("Inhibited", "").lower() == "true" if elem.get("Inhibited") else None,
        "major_rev": elem.get("Major", ""),
        "minor_rev": elem.get("Minor", ""),
        "vendor": elem.get("Vendor", ""),
        "product_type": elem.get("ProductType", ""),
        "product_code": elem.get("ProductCode", ""),
        "ports": [],
        "connections": [],
        "ext_properties": {},
    }

    # Extract ports from XML
    ports_elem = elem.find("Ports")
    if ports_elem is not None:
        for port_elem in ports_elem.findall("Port"):
            port_data: dict[str, Any] = {
                "id": port_elem.get("Id", ""),
                "type": port_elem.get("Type", ""),
                "address": port_elem.get("Address", ""),
                "upstream": port_elem.get("Upstream", "").lower() == "true",
            }
            # Check for bus info
            bus = port_elem.find("Bus")
            if bus is not None:
                port_data["bus_size"] = bus.get("Size", "")
            mod_data["ports"].append(port_data)

    # Extract connection info (RPI, input/output sizes, etc.)
    comms = elem.find("Communications")
    if comms is not None:
        for conn in comms.findall("Connections/Connection"):
            conn_data: dict[str, Any] = {
                "name": conn.get("Name", ""),
                "rpi": conn.get("RPI", ""),
                "type": conn.get("Type", ""),
            }
            # Input/Output tag info
            input_tag = conn.find("InputTag")
            if input_tag is not None:
                conn_data["input_tag"] = input_tag.get("ExternalAccess", "")
                conn_data["input_size"] = _get_data_size(input_tag)
            output_tag = conn.find("OutputTag")
            if output_tag is not None:
                conn_data["output_tag"] = output_tag.get("ExternalAccess", "")
                conn_data["output_size"] = _get_data_size(output_tag)
            mod_data["connections"].append(conn_data)

    # Extract extended properties (keying, electronic keying, etc.)
    ext_props = elem.find("ExtendedProperties")
    if ext_props is not None:
        for prop in ext_props:
            mod_data["ext_properties"][prop.tag] = prop.text or prop.get("Value", "")

    return mod_data


def _get_data_size(tag_elem) -> str:
    """Try to determine data size from a connection tag element."""
    # Look for Data child elements or DataType attributes
    for child in tag_elem:
        if child.tag == "Data":
            fmt = child.get("Format", "")
            if fmt:
                return fmt
    return ""


# ---------------------------------------------------------------------------
# Tags (controller-scoped or program-scoped)
# ---------------------------------------------------------------------------

def _extract_scope_tags(tags_container) -> dict[str, list[dict[str, Any]]]:
    """Extract all tags from a scope (controller or program).

    Returns dict with keys: alias_tags, regular_tags
    """
    alias_tags: list[dict[str, Any]] = []
    regular_tags: list[dict[str, Any]] = []

    try:
        names = tags_container.names
    except Exception:
        return {"alias_tags": alias_tags, "regular_tags": regular_tags}

    for name in names:
        try:
            tag = tags_container[name]
        except Exception:
            continue

        if isinstance(tag, l5x.tag.AliasTag):
            alias_data: dict[str, Any] = {
                "name": name,
                "alias_for": None,
                "description": None,
            }
            try:
                alias_data["alias_for"] = tag.alias_for
            except Exception:
                pass
            try:
                alias_data["description"] = tag.description
            except Exception:
                pass
            alias_tags.append(alias_data)
        else:
            tag_data = _extract_tag_detail(name, tag, depth=0)
            regular_tags.append(tag_data)

    return {"alias_tags": alias_tags, "regular_tags": regular_tags}


def _extract_tag_detail(name: str, tag, depth: int) -> dict[str, Any]:
    """Extract full detail from a single tag, including members, bits, arrays."""
    data: dict[str, Any] = {
        "name": name,
        "data_type": None,
        "description": None,
        "value_summary": None,
        "is_array": False,
        "array_shape": None,
        "members": [],
        "bit_descriptions": [],
        "consumed": None,
    }

    try:
        data["data_type"] = tag.data_type
    except Exception:
        pass

    try:
        data["description"] = tag.description
    except Exception:
        pass

    # Consumed tag info
    try:
        producer = tag.producer
        remote = tag.remote_tag
        if producer:
            data["consumed"] = {"producer": producer, "remote_tag": remote}
    except Exception:
        pass

    # Array detection
    try:
        shape = tag.shape
        if shape:
            data["is_array"] = True
            data["array_shape"] = shape
            # Capture first N element values
            elements = []
            total = shape[0] if shape else 0
            for i in range(min(total, _MAX_ARRAY_ELEMENTS)):
                elem: dict[str, Any] = {"index": i}
                try:
                    elem["value"] = _safe_value(tag[i])
                except Exception:
                    elem["value"] = None
                try:
                    elem["description"] = tag[i].description
                except Exception:
                    elem["description"] = None
                elements.append(elem)
            data["value_summary"] = {
                "total_elements": total,
                "sample": elements,
            }
            return data
    except (TypeError, AttributeError):
        pass

    # Structure detection (has .names)
    if depth < _MAX_DEPTH:
        try:
            member_names = tag.names
            if member_names:
                for mname in member_names:
                    try:
                        member_obj = tag[mname]
                        member_data = _extract_tag_detail(mname, member_obj, depth + 1)
                        data["members"].append(member_data)
                    except Exception:
                        data["members"].append({"name": mname, "error": "Could not read"})
                return data
        except (TypeError, AttributeError):
            pass

    # Integer bit-level descriptions
    try:
        bit_count = len(tag)
        if bit_count and data["data_type"] in ("SINT", "INT", "DINT"):
            for bit in range(bit_count):
                bit_info: dict[str, Any] = {"bit": bit}
                try:
                    bit_info["value"] = tag[bit].value
                except Exception:
                    bit_info["value"] = None
                try:
                    desc = tag[bit].description
                    if desc:
                        bit_info["description"] = desc
                except Exception:
                    pass
                # Only include bits that have descriptions or non-zero values
                if bit_info.get("description") or bit_info.get("value"):
                    data["bit_descriptions"].append(bit_info)
    except (TypeError, AttributeError):
        pass

    # Simple value
    try:
        val = tag.value
        data["value_summary"] = _summarize_value(val)
    except Exception:
        pass

    return data


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

def _extract_programs(project: l5x.Project) -> list[dict[str, Any]]:
    programs = []
    try:
        prog_names = project.programs.names
    except Exception:
        return programs

    for prog_name in prog_names:
        try:
            program = project.programs[prog_name]
            tags_data = _extract_scope_tags(program.tags)
            programs.append({
                "name": prog_name,
                "tags": tags_data,
            })
        except Exception:
            programs.append({"name": prog_name, "tags": {"alias_tags": [], "regular_tags": []}, "error": "Could not read"})

    return programs


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _build_statistics(data: dict[str, Any]) -> dict[str, Any]:
    ctrl_tags = data["controller_tags"]
    ctrl_alias = len(ctrl_tags["alias_tags"])
    ctrl_regular = len(ctrl_tags["regular_tags"])

    prog_alias = 0
    prog_regular = 0
    for prog in data["programs"]:
        tags = prog.get("tags", {})
        prog_alias += len(tags.get("alias_tags", []))
        prog_regular += len(tags.get("regular_tags", []))

    # Data type breakdown (controller scope)
    dtype_counts: dict[str, int] = {}
    with_desc = 0
    without_desc = 0
    for t in ctrl_tags["regular_tags"]:
        dt = t.get("data_type") or "Unknown"
        dtype_counts[dt] = dtype_counts.get(dt, 0) + 1
        if t.get("description"):
            with_desc += 1
        else:
            without_desc += 1

    # Count bit-level descriptions
    bit_desc_count = 0
    for t in ctrl_tags["regular_tags"]:
        bit_desc_count += len([b for b in t.get("bit_descriptions", []) if b.get("description")])

    return {
        "total_modules": len(data["modules"]),
        "total_controller_tags": ctrl_alias + ctrl_regular,
        "controller_alias_tags": ctrl_alias,
        "controller_regular_tags": ctrl_regular,
        "total_program_tags": prog_alias + prog_regular,
        "program_alias_tags": prog_alias,
        "program_regular_tags": prog_regular,
        "total_programs": len(data["programs"]),
        "data_type_breakdown": dict(sorted(dtype_counts.items(), key=lambda x: -x[1])),
        "tags_with_descriptions": with_desc,
        "tags_without_descriptions": without_desc,
        "bit_level_descriptions": bit_desc_count,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_get(obj, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None


def _safe_value(tag) -> Any:
    try:
        v = tag.value
        if isinstance(v, dict):
            return {k: str(val) for k, val in v.items()}
        return v
    except Exception:
        return None


def _summarize_value(val: Any) -> Any:
    """Return a display-friendly summary of a tag value."""
    if val is None:
        return None
    if isinstance(val, (int, float, str)):
        return val
    if isinstance(val, dict):
        return {k: str(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        if len(val) <= _MAX_ARRAY_ELEMENTS:
            return val
        return {"preview": list(val[:_MAX_ARRAY_ELEMENTS]), "total": len(val)}
    return str(val)
