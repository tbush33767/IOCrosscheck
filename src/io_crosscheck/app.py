"""Streamlit GUI for IO Crosscheck."""
from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path
from io import BytesIO

import streamlit as st
import pandas as pd

from io_crosscheck.parsers import parse_plc_csv, parse_io_list_xlsx
from io_crosscheck.classifiers import classify_tag, is_spare
from io_crosscheck.strategies import MatchingEngine
from io_crosscheck.reports import generate_xlsx_report, generate_html_report
from io_crosscheck.models import Classification, MatchResult
from io_crosscheck.normalizers import extract_rack_base
from io_crosscheck.l5x_extractor import extract_l5x
from io_crosscheck.l5x_report import generate_l5x_markdown
from io_crosscheck.l5x_to_crosscheck import extract_l5x_enrichment, enrich_results


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="IO Crosscheck",
    page_icon="\u2699\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .block-container { padding-top: 2.5rem; }
    div[data-testid="stMetric"] {
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid rgba(128, 128, 128, 0.3);
    }
    div[data-testid="stMetric"] label {
        color: inherit !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: inherit !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        color: inherit !important;
    }
    .cls-both { background-color: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
    .cls-both-rack { background-color: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
    .cls-io-only { background-color: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
    .cls-plc-only { background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
    .cls-conflict { background-color: #ffedd5; color: #9a3412; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
    .cls-spare { background-color: #f3f4f6; color: #4b5563; padding: 2px 8px; border-radius: 10px; font-weight: 600; font-size: 0.85em; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rack_address(r: MatchResult) -> str:
    """Extract rack base address for Rack Only results (e.g. 'Rack0:I')."""
    if r.classification != Classification.RACK_ONLY:
        return ""
    if r.io_device and r.io_device.plc_address:
        base = extract_rack_base(r.io_device.plc_address)
        return base if base else ""
    return ""


def results_to_dataframe(results: list[MatchResult]) -> pd.DataFrame:
    """Convert MatchResult list to a pandas DataFrame for display."""
    rows = []
    for r in results:
        io = r.io_device
        plc = r.plc_tag
        rows.append({
            "Device Tag": io.device_tag if io else "",
            "IO Tag": io.io_tag if io else "",
            "Panel": io.panel if io else "",
            "Rack": io.rack if io else "",
            "Slot": io.slot if io else "",
            "Channel": io.channel if io else "",
            "PLC Address": io.plc_address if io else "",
            "Module Type": io.module_type if io else "",
            "Classification": r.classification.value,
            "Strategy": r.strategy_id if r.strategy_id else "",
            "Confidence": r.confidence.value if r.strategy_id else "",
            "Rack Address": _rack_address(r),
            "PLC Tag": plc.name if plc else "",
            "PLC Description": plc.description if plc else "",
            "Conflict": "YES" if r.conflict_flag else "",
            "Sources": ", ".join(r.sources) if r.sources else "",
            "Audit Trail": " | ".join(r.audit_trail),
        })
    return pd.DataFrame(rows)


def color_classification(val: str) -> str:
    """Return CSS styling for classification column."""
    colors = {
        "Both": "background-color: #dcfce7; color: #166534",
        "Rack Only": "background-color: #fef9c3; color: #854d0e",
        "IO List Only": "background-color: #fee2e2; color: #991b1b",
        "PLC Only": "background-color: #dbeafe; color: #1e40af",
        "Conflict": "background-color: #ffedd5; color: #9a3412",
        "Spare": "background-color: #f3f4f6; color: #4b5563",
    }
    return colors.get(val, "")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("IO Crosscheck")
    st.caption("PLC-to-IO List Device Verification Engine")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_crosscheck, tab_l5x = st.tabs(["IO Crosscheck", "L5X Explorer"])


# ===================================================================
# TAB 1: IO Crosscheck
# ===================================================================

with tab_crosscheck:
    st.subheader("Upload Files")
    up_col1, up_col2, up_col3 = st.columns(3)
    with up_col1:
        csv_file = st.file_uploader(
            "PLC Tag Export (.csv)",
            type=["csv"],
            help="RSLogix 5000 CSV tag export file",
            key="csv_upload",
        )
    with up_col2:
        xlsx_file = st.file_uploader(
            "IO List (.xlsx)",
            type=["xlsx", "xls"],
            help="IO List spreadsheet (ESCO List sheet)",
            key="xlsx_upload",
        )
    with up_col3:
        l5x_cx_file = st.file_uploader(
            "L5X Project File (optional)",
            type=["L5X", "l5x"],
            help="Optional — enriches results with alias confirmations, module validation, and MSG/consumed tag flagging",
            key="l5x_enrich_upload",
        )

    set_col1, set_col2, set_col3 = st.columns([2, 2, 1])
    with set_col1:
        sheet_name = st.text_input("Sheet Name", value="ESCO List")
    with set_col2:
        encoding = st.selectbox(
            "CSV Encoding",
            options=["latin-1", "utf-8", "cp1252"],
            index=0,
        )
    with set_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button(
            "Run Analysis",
            type="primary",
            use_container_width=True,
            disabled=(csv_file is None or xlsx_file is None),
        )

    if not run_btn and "results" not in st.session_state:
        st.divider()
        st.markdown(
            "Upload your **PLC Tag Export CSV** and **IO List XLSX** above, "
            "then click **Run Analysis** to verify every device. "
            "Optionally add an **L5X project file** to enrich results with "
            "source confirmation from alias mappings and module validation."
        )

        st.markdown("##### Matching Strategies (Priority Order)")
        strategies_data = {
            "#": [1, 2, 3, 4, 5],
            "Strategy": [
                "Direct CLX Address Match",
                "PLC5 Rack Address Match",
                "Rack-Level TAG Existence",
                "ENet Module Tag Extraction",
                "Tag Name Normalization",
            ],
            "Confidence": ["Exact", "Exact", "Partial", "Exact", "High"],
            "Description": [
                "IO List PLC address vs PLC COMMENT specifiers (case-insensitive)",
                "PLC5-format addresses vs PLC TAG names",
                "Verify parent rack TAG exists when no per-point COMMENT",
                "Extract device IDs from E300_/VFD_/IPDev_ prefixed tags",
                "Suffix-stripped, case-folded exact name matching",
            ],
        }
        st.dataframe(pd.DataFrame(strategies_data), width="stretch", hide_index=True)


    # ---------------------------------------------------------------------------
    # Run analysis
    # ---------------------------------------------------------------------------

    if run_btn:
        with st.spinner("Analyzing..."):
            tmp_dir = Path(tempfile.mkdtemp(prefix="iocx_"))
            csv_path = tmp_dir / "tags.csv"
            xlsx_path = tmp_dir / "io_list.xlsx"

            csv_path.write_bytes(csv_file.getvalue())
            xlsx_path.write_bytes(xlsx_file.getvalue())

            try:
                # Parse CSV + XLSX (baseline crosscheck)
                plc_tags = parse_plc_csv(csv_path, encoding=encoding)
                for tag in plc_tags:
                    tag.category = classify_tag(tag)

                io_devices = parse_io_list_xlsx(xlsx_path, sheet_name=sheet_name)

                engine = MatchingEngine()
                results = engine.run(io_devices, plc_tags)

                # Mark baseline sources on results
                for r in results:
                    r.sources = ["CSV", "XLSX"]

                # L5X enrichment (optional)
                l5x_enrichment_data = None
                if l5x_cx_file is not None:
                    l5x_path = tmp_dir / l5x_cx_file.name
                    l5x_path.write_bytes(l5x_cx_file.getvalue())
                    l5x_data = extract_l5x(l5x_path)
                    l5x_enrichment_data = extract_l5x_enrichment(l5x_data)
                    results = enrich_results(results, l5x_enrichment_data)

                # Generate reports
                output_dir = tmp_dir / "output"
                output_dir.mkdir()
                xlsx_report_path = output_dir / "io_crosscheck_report.xlsx"
                html_report_path = output_dir / "io_crosscheck_report.html"
                generate_xlsx_report(results, xlsx_report_path)
                generate_html_report(results, html_report_path)

                st.session_state["results"] = results
                st.session_state["plc_tag_count"] = len(plc_tags)
                st.session_state["io_device_count"] = len(io_devices)
                st.session_state["spare_count"] = sum(1 for d in io_devices if is_spare(d.io_tag))
                st.session_state["xlsx_bytes"] = xlsx_report_path.read_bytes()
                st.session_state["html_bytes"] = html_report_path.read_bytes()
                st.session_state["df"] = results_to_dataframe(results)
                st.session_state["l5x_msg_tags"] = (
                    l5x_enrichment_data["msg_tags"] if l5x_enrichment_data else []
                )
                st.session_state["l5x_consumed_tags"] = (
                    l5x_enrichment_data["consumed_tags"] if l5x_enrichment_data else []
                )
                st.session_state["l5x_used"] = l5x_cx_file is not None

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                import traceback
                st.code(traceback.format_exc())
                st.stop()

        st.rerun()

    # -----------------------------------------------------------------------
    # Display results
    # -----------------------------------------------------------------------

    if "results" in st.session_state:
        results = st.session_state["results"]
        df = st.session_state["df"]

        cls_counts = Counter(r.classification.value for r in results)
        conflict_count = sum(1 for r in results if r.conflict_flag)

        # Summary metrics
        st.markdown("### Summary")
        cols = st.columns(7)
        metrics = [
            ("Total", len(results), None),
            ("Both", cls_counts.get("Both", 0), "normal"),
            ("Rack Only", cls_counts.get("Rack Only", 0), None),
            ("IO List Only", cls_counts.get("IO List Only", 0), "inverse"),
            ("PLC Only", cls_counts.get("PLC Only", 0), None),
            ("Conflicts", conflict_count, "inverse" if conflict_count > 0 else None),
            ("Spares", cls_counts.get("Spare", 0), None),
        ]
        for col, (label, value, delta_color) in zip(cols, metrics):
            with col:
                pct = f"{value / len(results) * 100:.1f}%" if results else "0%"
                st.metric(label, value, pct)

        # Parse info
        l5x_used = st.session_state.get("l5x_used", False)
        l5x_confirmed = sum(1 for r in results if "L5X" in r.sources) if l5x_used else 0
        parse_caption = (
            f"Parsed **{st.session_state['plc_tag_count']}** PLC records and "
            f"**{st.session_state['io_device_count']}** IO devices "
            f"({st.session_state['spare_count']} spares)"
        )
        if l5x_used:
            parse_caption += f" — **L5X enrichment active:** {l5x_confirmed}/{len(results)} results confirmed by L5X"
        st.caption(parse_caption)

        # Downloads
        st.markdown("### Download Reports")
        dl_col1, dl_col2, _ = st.columns([1, 1, 3])
        with dl_col1:
            st.download_button(
                label="Download XLSX Report",
                data=st.session_state["xlsx_bytes"],
                file_name="io_crosscheck_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with dl_col2:
            st.download_button(
                label="Download HTML Report",
                data=st.session_state["html_bytes"],
                file_name="io_crosscheck_report.html",
                mime="text/html",
                use_container_width=True,
            )

        st.divider()

        # Filters
        st.markdown("### Results")

        filter_col1, filter_col2 = st.columns([2, 3])
        with filter_col1:
            search = st.text_input(
                "Search",
                placeholder="Filter by device tag, IO tag, address...",
                label_visibility="collapsed",
            )
        with filter_col2:
            cls_options = ["All"] + [c.value for c in Classification]
            selected_cls = st.segmented_control(
                "Filter by classification",
                options=cls_options,
                default="All",
                label_visibility="collapsed",
            )

        # Apply filters
        filtered_df = df.copy()
        if search:
            mask = filtered_df.apply(
                lambda row: search.lower() in " ".join(row.astype(str)).lower(), axis=1
            )
            filtered_df = filtered_df[mask]
        if selected_cls and selected_cls != "All":
            filtered_df = filtered_df[filtered_df["Classification"] == selected_cls]

        st.caption(f"Showing {len(filtered_df)} of {len(df)} results")

        # Display table with colored classification
        display_df = filtered_df.drop(columns=["Audit Trail"])

        st.dataframe(
            display_df.style.map(
                color_classification,
                subset=["Classification"],
            ),
            width="stretch",
            height=500,
            hide_index=True,
        )

        # Conflicts detail
        if conflict_count > 0:
            st.divider()
            st.markdown("### Conflicts Requiring Review")
            st.warning(f"{conflict_count} device(s) have address matches but different names. These require human review.")
            conflict_df = df[df["Conflict"] == "YES"][
                ["Device Tag", "IO Tag", "PLC Address", "PLC Description", "Audit Trail"]
            ]
            st.dataframe(conflict_df, width="stretch", hide_index=True)

        # Audit trail expander
        st.divider()
        st.markdown("### Audit Trail")
        st.caption("Expand any device to see the full matching decision trail.")

        audit_df = filtered_df[["Device Tag", "IO Tag", "Classification", "Audit Trail"]]
        for _, row in audit_df.head(100).iterrows():
            tag_label = row["Device Tag"] or row["IO Tag"] or "(PLC Only)"
            with st.expander(f"{tag_label} — {row['Classification']}"):
                for step in row["Audit Trail"].split(" | "):
                    st.markdown(f"- {step}")

        # -------------------------------------------------------------------
        # L5X-specific: Inter-Controller MSG Tags
        # -------------------------------------------------------------------
        msg_tags = st.session_state.get("l5x_msg_tags", [])
        if msg_tags:
            st.divider()
            st.markdown("### Inter-Controller MSG Tags")
            st.info(
                f"{len(msg_tags)} alias tag(s) target inter-controller message "
                "file addresses (N-file, B-file, F-file). These are **not physical IO** "
                "and are excluded from the crosscheck."
            )
            msg_rows = [{
                "Tag Name": m["name"],
                "Target Address": m["alias_for"],
                "Direction": m["direction"],
                "Description": m.get("description", ""),
            } for m in msg_tags]
            st.dataframe(pd.DataFrame(msg_rows), hide_index=True, height=300)

        # -------------------------------------------------------------------
        # L5X-specific: Consumed / Program Data Tags
        # -------------------------------------------------------------------
        consumed_tags = st.session_state.get("l5x_consumed_tags", [])
        if consumed_tags:
            st.divider()
            st.markdown("### Consumed / Program Data Tags")
            st.info(
                f"{len(consumed_tags)} alias tag(s) reference consumed data or UDT "
                "members from other controllers. These are **not physical IO** "
                "and are excluded from the crosscheck."
            )
            cons_rows = [{
                "Tag Name": c["name"],
                "Target Reference": c["alias_for"],
                "Description": c.get("description", ""),
            } for c in consumed_tags]
            st.dataframe(pd.DataFrame(cons_rows), hide_index=True, height=300)


# ===================================================================
# TAB 2: L5X Explorer
# ===================================================================

with tab_l5x:
    st.markdown("### L5X Project Explorer")
    st.markdown(
        "Upload an RSLogix 5000 / Studio 5000 **L5X project file** to extract "
        "every tag, module, alias, bit-level description, and structure member "
        "into a downloadable Markdown report."
    )

    l5x_file = st.file_uploader(
        "L5X Project File",
        type=["L5X", "l5x"],
        help="RSLogix 5000 / Studio 5000 exported L5X file",
        key="l5x_upload",
    )

    l5x_extract_btn = st.button(
        "Extract Data",
        type="primary",
        disabled=(l5x_file is None),
        key="l5x_extract",
    )

    if l5x_extract_btn and l5x_file is not None:
        with st.spinner("Extracting L5X data... This may take a moment for large projects."):
            tmp_dir = Path(tempfile.mkdtemp(prefix="l5x_"))
            l5x_path = tmp_dir / l5x_file.name
            l5x_path.write_bytes(l5x_file.getvalue())

            try:
                data = extract_l5x(l5x_path)
                md_content = generate_l5x_markdown(data)

                st.session_state["l5x_data"] = data
                st.session_state["l5x_md"] = md_content
                st.session_state["l5x_filename"] = l5x_file.name
            except Exception as e:
                st.error(f"L5X extraction failed: {e}")
                import traceback
                st.code(traceback.format_exc())

    if "l5x_data" in st.session_state:
        data = st.session_state["l5x_data"]
        stats = data.get("statistics", {})
        filename = st.session_state.get("l5x_filename", "")

        st.success(f"Extracted data from **{filename}**")

        # Summary metrics
        m_cols = st.columns(6)
        with m_cols[0]:
            st.metric("Modules", stats.get("total_modules", 0))
        with m_cols[1]:
            st.metric("Controller Tags", stats.get("total_controller_tags", 0))
        with m_cols[2]:
            st.metric("Alias Tags", stats.get("controller_alias_tags", 0))
        with m_cols[3]:
            st.metric("Programs", stats.get("total_programs", 0))
        with m_cols[4]:
            st.metric("Program Tags", stats.get("total_program_tags", 0))
        with m_cols[5]:
            st.metric("Bit Descriptions", stats.get("bit_level_descriptions", 0))

        # Download button
        md_bytes = st.session_state["l5x_md"].encode("utf-8")
        md_filename = filename.rsplit(".", 1)[0] + "_report.md" if filename else "l5x_report.md"
        st.download_button(
            label=f"Download Full Markdown Report ({len(md_bytes) / 1024:.0f} KB)",
            data=md_bytes,
            file_name=md_filename,
            mime="text/markdown",
            use_container_width=False,
        )

        st.divider()

        # --- Controller Info ---
        ctrl = data.get("controller", {})
        with st.expander("Controller Info"):
            comm = ctrl.get("comm_path")
            snn = ctrl.get("snn")
            st.markdown(f"**Communication Path:** `{comm}`" if comm else "**Communication Path:** *(not set)*")
            st.markdown(f"**Safety Network Number:** `{snn}`" if snn else "**Safety Network Number:** *(N/A)*")

        # --- Data Type Breakdown ---
        dtype_breakdown = stats.get("data_type_breakdown", {})
        if dtype_breakdown:
            with st.expander(f"Data Type Breakdown ({len(dtype_breakdown)} types)"):
                dt_df = pd.DataFrame(
                    [(dt, count) for dt, count in dtype_breakdown.items()],
                    columns=["Data Type", "Count"],
                )
                st.dataframe(dt_df, hide_index=True)

        # --- I/O Modules ---
        modules = data.get("modules", [])
        with st.expander(f"I/O Modules ({len(modules)})"):
            if not modules:
                st.info("No modules found.")
            else:
                mod_rows = []
                for m in modules:
                    ports_str = ", ".join(
                        f"{p.get('type', '')}:{p.get('address', '')}"
                        for p in m.get("ports", [])
                    )
                    mod_rows.append({
                        "Name": m.get("name", ""),
                        "Catalog #": m.get("catalog_number", ""),
                        "Parent": m.get("parent_module", ""),
                        "Inhibited": "Yes" if m.get("inhibited") else ("No" if m.get("inhibited") is False else ""),
                        "Vendor": m.get("vendor", ""),
                        "Revision": f"{m.get('major_rev', '')}.{m.get('minor_rev', '')}".strip("."),
                        "Ports": ports_str,
                    })
                st.dataframe(pd.DataFrame(mod_rows), hide_index=True, height=400)

                # Per-module details
                for m in modules:
                    cat = m.get("catalog_number", "")
                    label = f"{m['name']} ({cat})" if cat else m.get("name", "")
                    with st.expander(f"Module: {label}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Catalog:** {m.get('catalog_number', '')}")
                            st.markdown(f"**Parent:** {m.get('parent_module', '')}")
                            st.markdown(f"**Inhibited:** {m.get('inhibited')}")
                        with col2:
                            st.markdown(f"**Vendor:** {m.get('vendor', '')}")
                            st.markdown(f"**Product Type:** {m.get('product_type', '')}")
                            st.markdown(f"**Revision:** {m.get('major_rev', '')}.{m.get('minor_rev', '')}")

                        ports = m.get("ports", [])
                        if ports:
                            st.markdown("**Ports:**")
                            port_rows = []
                            for p in ports:
                                port_rows.append({
                                    "ID": p.get("id", ""),
                                    "Type": p.get("type", ""),
                                    "Address": p.get("address", ""),
                                    "Upstream": "Yes" if p.get("upstream") else "",
                                    "Bus Size": p.get("bus_size", ""),
                                })
                            st.dataframe(pd.DataFrame(port_rows), hide_index=True)

                        conns = m.get("connections", [])
                        if conns:
                            st.markdown("**Connections:**")
                            conn_rows = []
                            for c in conns:
                                conn_rows.append({
                                    "Name": c.get("name", ""),
                                    "Type": c.get("type", ""),
                                    "RPI": c.get("rpi", ""),
                                    "Input": c.get("input_size", ""),
                                    "Output": c.get("output_size", ""),
                                })
                            st.dataframe(pd.DataFrame(conn_rows), hide_index=True)

        # --- Controller Alias Tags ---
        ctrl_tags = data.get("controller_tags", {})
        alias_tags = ctrl_tags.get("alias_tags", [])
        with st.expander(f"Controller Alias Tags ({len(alias_tags)})"):
            if not alias_tags:
                st.info("No alias tags.")
            else:
                alias_rows = [{
                    "Name": a.get("name", ""),
                    "Alias For": a.get("alias_for", ""),
                    "Description": a.get("description") or "",
                } for a in alias_tags]
                st.dataframe(pd.DataFrame(alias_rows), hide_index=True, height=400)

        # --- Controller Regular Tags ---
        regular_tags = ctrl_tags.get("regular_tags", [])
        with st.expander(f"Controller Regular Tags ({len(regular_tags)})"):
            if not regular_tags:
                st.info("No regular tags.")
            else:
                tag_rows = [{
                    "Name": t.get("name", ""),
                    "Data Type": t.get("data_type") or "",
                    "Description": t.get("description") or "",
                    "Array": f"shape={t['array_shape']}" if t.get("is_array") else "",
                    "Members": len(t.get("members", [])),
                    "Bit Descs": len(t.get("bit_descriptions", [])),
                    "Consumed": "Yes" if t.get("consumed") else "",
                } for t in regular_tags]
                st.dataframe(pd.DataFrame(tag_rows), hide_index=True, height=400)

                # Per-tag detail expanders for tags with interesting data
                detail_tags = [t for t in regular_tags if t.get("members") or t.get("bit_descriptions") or t.get("consumed")]
                if detail_tags:
                    st.caption(f"{len(detail_tags)} tags with structure members, bit descriptions, or consumed info:")
                    for t in detail_tags:
                        dt = t.get("data_type") or ""
                        with st.expander(f"Tag: {t['name']} ({dt})"):
                            if t.get("description"):
                                st.markdown(f"**Description:** {t['description']}")
                            if t.get("consumed"):
                                c = t["consumed"]
                                st.markdown(f"**Consumed from:** {c.get('producer', '')} / {c.get('remote_tag', '')}")

                            members = t.get("members", [])
                            if members:
                                st.markdown("**Members:**")
                                mem_rows = [{
                                    "Member": m.get("name", ""),
                                    "Data Type": m.get("data_type") or "",
                                    "Description": m.get("description") or "",
                                } for m in members]
                                st.dataframe(pd.DataFrame(mem_rows), hide_index=True)

                            bits = t.get("bit_descriptions", [])
                            if bits:
                                st.markdown("**Bit-Level Descriptions:**")
                                bit_rows = [{
                                    "Bit": b.get("bit", ""),
                                    "Value": b.get("value", ""),
                                    "Description": b.get("description", ""),
                                } for b in bits]
                                st.dataframe(pd.DataFrame(bit_rows), hide_index=True)

        # --- Bit-Level Descriptions (dedicated section) ---
        bit_tags = [t for t in regular_tags if t.get("bit_descriptions")]
        if bit_tags:
            total_bits = sum(len(t.get("bit_descriptions", [])) for t in bit_tags)
            with st.expander(f"All Bit-Level Descriptions ({total_bits} across {len(bit_tags)} tags)"):
                st.caption("These correspond to PLC COMMENT records in CSV exports.")
                all_bit_rows = []
                for t in bit_tags:
                    for b in t.get("bit_descriptions", []):
                        all_bit_rows.append({
                            "Tag": t.get("name", ""),
                            "Data Type": t.get("data_type") or "",
                            "Bit": b.get("bit", ""),
                            "Value": b.get("value", ""),
                            "Description": b.get("description", ""),
                        })
                st.dataframe(pd.DataFrame(all_bit_rows), hide_index=True, height=400)

        # --- Array Tags ---
        array_tags = [t for t in regular_tags if t.get("is_array")]
        if array_tags:
            with st.expander(f"Array Tags ({len(array_tags)})"):
                for t in array_tags:
                    shape = t.get("array_shape", ())
                    vs = t.get("value_summary", {})
                    with st.expander(f"{t['name']} ({t.get('data_type', '')}) \u2014 shape {shape}"):
                        if t.get("description"):
                            st.markdown(f"**Description:** {t['description']}")
                        if isinstance(vs, dict) and "sample" in vs:
                            sample = vs.get("sample", [])
                            total = vs.get("total_elements", 0)
                            st.caption(f"Showing first {len(sample)} of {total} elements")
                            elem_rows = [{
                                "Index": e.get("index", ""),
                                "Value": str(e.get("value", "")),
                                "Description": e.get("description") or "",
                            } for e in sample]
                            st.dataframe(pd.DataFrame(elem_rows), hide_index=True)

        # --- Consumed Tags ---
        consumed_tags = [t for t in regular_tags if t.get("consumed")]
        if consumed_tags:
            with st.expander(f"Consumed Tags ({len(consumed_tags)})"):
                cons_rows = [{
                    "Name": t.get("name", ""),
                    "Data Type": t.get("data_type") or "",
                    "Producer": t["consumed"].get("producer", ""),
                    "Remote Tag": t["consumed"].get("remote_tag", ""),
                } for t in consumed_tags]
                st.dataframe(pd.DataFrame(cons_rows), hide_index=True)

        # --- Programs ---
        programs = data.get("programs", [])
        with st.expander(f"Programs ({len(programs)})"):
            if not programs:
                st.info("No programs found.")
            else:
                for prog in programs:
                    prog_name = prog.get("name", "Unknown")
                    tags = prog.get("tags", {})
                    a_count = len(tags.get("alias_tags", []))
                    r_count = len(tags.get("regular_tags", []))
                    with st.expander(f"Program: {prog_name} ({a_count} aliases, {r_count} tags)"):
                        if tags.get("alias_tags"):
                            st.markdown("**Alias Tags:**")
                            pa_rows = [{
                                "Name": a.get("name", ""),
                                "Alias For": a.get("alias_for", ""),
                                "Description": a.get("description") or "",
                            } for a in tags["alias_tags"]]
                            st.dataframe(pd.DataFrame(pa_rows), hide_index=True)

                        if tags.get("regular_tags"):
                            st.markdown("**Regular Tags:**")
                            pr_rows = [{
                                "Name": t.get("name", ""),
                                "Data Type": t.get("data_type") or "",
                                "Description": t.get("description") or "",
                            } for t in tags["regular_tags"]]
                            st.dataframe(pd.DataFrame(pr_rows), hide_index=True)

                        if not tags.get("alias_tags") and not tags.get("regular_tags"):
                            st.info("No tags in this program.")
