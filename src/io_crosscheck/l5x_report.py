"""Generate a well-organized Markdown report from extracted L5X data."""
from __future__ import annotations

from typing import Any


def generate_l5x_markdown(data: dict[str, Any]) -> str:
    """Format extracted L5X data dict into a comprehensive Markdown report."""
    lines: list[str] = []
    _w = lines.append

    filename = data.get("filename", "Unknown")
    _w(f"# L5X Project Report: {filename}\n")

    # ---- Statistics overview ----
    stats = data.get("statistics", {})
    _w("## Summary\n")
    _w(f"| Metric | Count |")
    _w(f"|--------|-------|")
    _w(f"| I/O Modules | {stats.get('total_modules', 0)} |")
    _w(f"| Controller Tags (total) | {stats.get('total_controller_tags', 0)} |")
    _w(f"| Controller Regular Tags | {stats.get('controller_regular_tags', 0)} |")
    _w(f"| Controller Alias Tags | {stats.get('controller_alias_tags', 0)} |")
    _w(f"| Programs | {stats.get('total_programs', 0)} |")
    _w(f"| Program Tags (total) | {stats.get('total_program_tags', 0)} |")
    _w(f"| Tags with Descriptions | {stats.get('tags_with_descriptions', 0)} |")
    _w(f"| Tags without Descriptions | {stats.get('tags_without_descriptions', 0)} |")
    _w(f"| Bit-Level Descriptions | {stats.get('bit_level_descriptions', 0)} |")
    _w("")

    # Data type breakdown
    dtype_breakdown = stats.get("data_type_breakdown", {})
    if dtype_breakdown:
        _w("### Data Type Breakdown (Controller Scope)\n")
        _w("| Data Type | Count |")
        _w("|-----------|-------|")
        for dt, count in dtype_breakdown.items():
            _w(f"| `{dt}` | {count} |")
        _w("")

    # ---- Controller Info ----
    ctrl = data.get("controller", {})
    _w("## 1. Controller Info\n")
    comm = ctrl.get("comm_path")
    snn = ctrl.get("snn")
    _w(f"- **Communication Path:** `{comm}`" if comm else "- **Communication Path:** *(not set)*")
    _w(f"- **Safety Network Number:** `{snn}`" if snn else "- **Safety Network Number:** *(N/A)*")
    _w("")

    # ---- I/O Modules ----
    modules = data.get("modules", [])
    _w(f"## 2. I/O Modules ({len(modules)} total)\n")
    if not modules:
        _w("*No modules found.*\n")
    else:
        _w("| Module Name | Catalog # | Parent Module | Inhibited | Ports |")
        _w("|-------------|-----------|---------------|-----------|-------|")
        for mod in modules:
            ports_str = _format_ports(mod.get("ports", []))
            inh = mod.get("inhibited")
            inh_str = "Yes" if inh else ("No" if inh is False else "?")
            cat = mod.get("catalog_number") or ""
            parent = mod.get("parent_module") or ""
            _w(f"| `{mod['name']}` | {cat} | {parent} | {inh_str} | {ports_str} |")
        _w("")

        # Detailed port info
        _w("### Module Port Details\n")
        for mod in modules:
            ports = mod.get("ports", [])
            if not ports:
                continue
            cat = mod.get("catalog_number") or ""
            cat_str = f" ({cat})" if cat else ""
            _w(f"#### {mod['name']}{cat_str}\n")
            _w("| Port | Type | Address | Upstream | Bus Size |")
            _w("|------|------|---------|----------|----------|")
            for p in ports:
                addr = p.get("address", "")
                upstream = "Yes" if p.get("upstream") else ""
                bus = p.get("bus_size", "")
                nat = p.get("nat_address")
                if nat:
                    addr = f"{addr} (NAT: {nat})"
                _w(f"| {p.get('id', '')} | {p.get('type', '')} | `{addr}` | {upstream} | {bus} |")
            _w("")

        # Connection details for modules that have them
        conn_modules = [m for m in modules if m.get("connections")]
        if conn_modules:
            _w("### Module Connections\n")
            for mod in conn_modules:
                _w(f"#### {mod['name']}\n")
                _w("| Connection | Type | RPI | Input | Output |")
                _w("|------------|------|-----|-------|--------|")
                for c in mod["connections"]:
                    inp = c.get("input_size", "")
                    out = c.get("output_size", "")
                    _w(f"| {c.get('name', '')} | {c.get('type', '')} | {c.get('rpi', '')} | {inp} | {out} |")
                _w("")

    # ---- Controller Tags ----
    ctrl_tags = data.get("controller_tags", {})
    _w("## 3. Controller-Scoped Tags\n")

    # Alias tags
    alias_tags = ctrl_tags.get("alias_tags", [])
    _w(f"### 3.1 Alias Tags ({len(alias_tags)})\n")
    if alias_tags:
        _w("| Name | Alias For | Description |")
        _w("|------|-----------|-------------|")
        for a in alias_tags:
            desc = _esc(a.get("description") or "")
            _w(f"| `{a['name']}` | `{a.get('alias_for', '')}` | {desc} |")
        _w("")
    else:
        _w("*No alias tags.*\n")

    # Regular tags
    regular_tags = ctrl_tags.get("regular_tags", [])
    _w(f"### 3.2 Regular Tags ({len(regular_tags)})\n")
    if regular_tags:
        _w("| Name | Data Type | Description | Value |")
        _w("|------|-----------|-------------|-------|")
        for t in regular_tags:
            desc = _esc(t.get("description") or "")
            val = _format_value_summary(t)
            dt = t.get("data_type") or ""
            _w(f"| `{t['name']}` | `{dt}` | {desc} | {val} |")
        _w("")

        # Tags with structure members
        struct_tags = [t for t in regular_tags if t.get("members")]
        if struct_tags:
            _w("### 3.3 Structure Details\n")
            for t in struct_tags:
                _w(f"#### `{t['name']}` (`{t.get('data_type', '')}`)\n")
                _write_members(lines, t.get("members", []), indent=0)
                _w("")

        # Tags with bit-level descriptions
        bit_tags = [t for t in regular_tags if t.get("bit_descriptions")]
        if bit_tags:
            _w("### 3.4 Bit-Level Descriptions\n")
            _w("These correspond to PLC COMMENT records in CSV exports.\n")
            for t in bit_tags:
                _w(f"#### `{t['name']}` (`{t.get('data_type', '')}`)\n")
                _w("| Bit | Value | Description |")
                _w("|-----|-------|-------------|")
                for b in t["bit_descriptions"]:
                    bdesc = _esc(b.get("description") or "")
                    _w(f"| {b['bit']} | {b.get('value', '')} | {bdesc} |")
                _w("")

        # Array tags
        array_tags = [t for t in regular_tags if t.get("is_array")]
        if array_tags:
            _w("### 3.5 Array Tags\n")
            for t in array_tags:
                shape = t.get("array_shape", ())
                _w(f"#### `{t['name']}` (`{t.get('data_type', '')}`) — shape {shape}\n")
                vs = t.get("value_summary", {})
                if isinstance(vs, dict) and "sample" in vs:
                    total = vs.get("total_elements", 0)
                    sample = vs.get("sample", [])
                    _w(f"Showing first {len(sample)} of {total} elements:\n")
                    _w("| Index | Value | Description |")
                    _w("|-------|-------|-------------|")
                    for elem in sample:
                        edesc = _esc(elem.get("description") or "")
                        _w(f"| {elem['index']} | {elem.get('value', '')} | {edesc} |")
                _w("")

        # Consumed tags
        consumed_tags = [t for t in regular_tags if t.get("consumed")]
        if consumed_tags:
            _w("### 3.6 Consumed Tags\n")
            _w("| Name | Data Type | Producer | Remote Tag |")
            _w("|------|-----------|----------|------------|")
            for t in consumed_tags:
                c = t["consumed"]
                _w(f"| `{t['name']}` | `{t.get('data_type', '')}` | {c.get('producer', '')} | {c.get('remote_tag', '')} |")
            _w("")

    else:
        _w("*No regular tags.*\n")

    # ---- Programs ----
    programs = data.get("programs", [])
    _w(f"## 4. Program-Scoped Tags ({len(programs)} programs)\n")
    if not programs:
        _w("*No programs found.*\n")
    else:
        for prog in programs:
            prog_name = prog.get("name", "Unknown")
            tags = prog.get("tags", {})
            alias_count = len(tags.get("alias_tags", []))
            reg_count = len(tags.get("regular_tags", []))
            _w(f"### Program: `{prog_name}` ({alias_count} aliases, {reg_count} tags)\n")

            if tags.get("alias_tags"):
                _w("**Alias Tags:**\n")
                _w("| Name | Alias For | Description |")
                _w("|------|-----------|-------------|")
                for a in tags["alias_tags"]:
                    desc = _esc(a.get("description") or "")
                    _w(f"| `{a['name']}` | `{a.get('alias_for', '')}` | {desc} |")
                _w("")

            if tags.get("regular_tags"):
                _w("**Regular Tags:**\n")
                _w("| Name | Data Type | Description |")
                _w("|------|-----------|-------------|")
                for t in tags["regular_tags"]:
                    desc = _esc(t.get("description") or "")
                    dt = t.get("data_type") or ""
                    _w(f"| `{t['name']}` | `{dt}` | {desc} |")
                _w("")

            if not tags.get("alias_tags") and not tags.get("regular_tags"):
                _w("*No tags in this program.*\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_ports(ports: list[dict]) -> str:
    if not ports:
        return ""
    parts = []
    for p in ports:
        addr = p.get("address", "")
        ptype = p.get("type", "")
        parts.append(f"{ptype}:{addr}" if ptype else str(addr))
    return ", ".join(parts)


def _format_value_summary(tag_data: dict) -> str:
    vs = tag_data.get("value_summary")
    if vs is None:
        return ""
    if isinstance(vs, (int, float)):
        return str(vs)
    if isinstance(vs, str):
        return _esc(vs[:80])
    if isinstance(vs, dict):
        if "preview" in vs:
            return f"[{vs.get('total', '?')} elements]"
        # Structure value dict
        items = list(vs.items())[:5]
        s = ", ".join(f"{k}={v}" for k, v in items)
        if len(vs) > 5:
            s += ", ..."
        return _esc(s[:80])
    return ""


def _write_members(lines: list[str], members: list[dict], indent: int) -> None:
    prefix = "  " * indent
    for m in members:
        name = m.get("name", "?")
        dt = m.get("data_type") or ""
        desc = _esc(m.get("description") or "")
        val = _format_value_summary(m)
        lines.append(f"{prefix}- **`.{name}`** (`{dt}`) — {desc} {'= ' + val if val else ''}")
        sub_members = m.get("members", [])
        if sub_members:
            _write_members(lines, sub_members, indent + 1)


def _esc(text: str) -> str:
    """Escape pipe characters for Markdown tables."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")
