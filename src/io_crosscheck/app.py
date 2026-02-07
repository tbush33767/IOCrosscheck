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
from io_crosscheck.reports import generate_xlsx_report, generate_html_report, generate_xlsm_report
from io_crosscheck.models import Classification, MatchResult
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
    /* Top padding — enough room for tab headers */
    .block-container { padding-top: 2.5rem; }

    /* File uploader dropzone — rounded corners */
    [data-testid="stFileUploaderDropzone"] {
        border-radius: 12px !important;
    }

    /* Theme toggle — style the sidebar icon button */
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:first-of-type {
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        padding: 4px 8px !important;
        min-height: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:first-of-type:hover {
        background: rgba(128,128,128,0.15) !important;
        border-radius: 8px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:first-of-type span[data-testid="stIconMaterial"] {
        color: #1e293b !important;
        font-size: 26px !important;
    }

    /* Metric cards — base styling */
    div[data-testid="stMetric"] {
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
        transition: box-shadow 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.12);
    }
    div[data-testid="stMetric"] label { color: inherit !important; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: inherit !important; }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] { color: inherit !important; }

    /* Color-coded metric cards (applied via nth-child on the 6-column layout) */
    .metric-total div[data-testid="stMetric"] { background: linear-gradient(135deg, #f8fafc, #e2e8f0); border-left: 4px solid #475569; }
    .metric-both div[data-testid="stMetric"] { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 4px solid #22c55e; }
    .metric-io-only div[data-testid="stMetric"] { background: linear-gradient(135deg, #fef2f2, #fee2e2); border-left: 4px solid #ef4444; }
    .metric-plc-only div[data-testid="stMetric"] { background: linear-gradient(135deg, #eff6ff, #dbeafe); border-left: 4px solid #3b82f6; }
    .metric-conflict div[data-testid="stMetric"] { background: linear-gradient(135deg, #fffbeb, #fef3c7); border-left: 4px solid #f59e0b; }
    .metric-spare div[data-testid="stMetric"] { background: linear-gradient(135deg, #f9fafb, #f3f4f6); border-left: 4px solid #9ca3af; }

    /* Classification badge pills */
    .cls-both { background-color: #dcfce7; color: #166534; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-both-rack { background-color: #fef9c3; color: #854d0e; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-io-only { background-color: #fee2e2; color: #991b1b; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-plc-only { background-color: #dbeafe; color: #1e40af; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-conflict { background-color: #ffedd5; color: #9a3412; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-spare { background-color: #f3f4f6; color: #4b5563; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }
    .cls-rack-only { background-color: #fef3c7; color: #78350f; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }

    /* Alternating row stripes on dataframes */
    div[data-testid="stDataFrame"] table tbody tr:nth-child(even) {
        background-color: rgba(68, 114, 196, 0.04);
    }

    /* Custom HTML results table */
    .cx-table-wrap { border: 1px solid #cbd5e1; border-radius: 12px; overflow: auto; }
    .cx-table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; table-layout: fixed; }
    .cx-table th { position: sticky; top: 0; background: #f1f5f9; text-align: left; padding: 8px 10px; border-bottom: 2px solid #cbd5e1; white-space: nowrap; z-index: 1; overflow: hidden; text-overflow: ellipsis; font-size: 13px; }
    .cx-table td { padding: 6px 10px; border-bottom: 1px solid #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0; font-size: 13px; line-height: 1.5; }
    .cx-table td * { font-size: 13px !important; font-weight: normal !important; margin: 0 !important; padding: 0 !important; line-height: 1.5 !important; }
    .cx-table td h1, .cx-table td h2, .cx-table td h3, .cx-table td h4, .cx-table td h5, .cx-table td h6,
    .cx-table td p, .cx-table td span, .cx-table td div { font-size: 13px !important; font-weight: normal !important; display: inline !important; }
    .cx-table td:nth-child(2) { white-space: pre-wrap; word-break: break-all; }
    .cx-table td:nth-child(3) { white-space: pre-wrap; word-break: break-word; }
    .cx-table tr:nth-child(even) { background: rgba(68, 114, 196, 0.04); }
    .cx-table tr:hover { background: rgba(68, 114, 196, 0.08); }
    .cx-table mark { background-color: #fde68a; color: #1e293b; padding: 1px 2px; border-radius: 3px; font-size: inherit; }
    .cx-table code { font-size: 13px; font-family: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace; background: transparent; color: inherit; word-break: break-all; white-space: pre-wrap; }

    /* Getting-started card — matches file uploader dropzone */
    .getting-started {
        background: #FAFBFC;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 2rem 2.5rem;
        margin: 1rem 0 1.5rem 0;
    }
    .getting-started h4 { margin-top: 0; color: #1e40af; }
    .gs-subtitle { margin-bottom: 0.5rem; font-weight: 600; color: #334155; }
    .gs-table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
    .gs-table th { text-align: left; padding: 6px 8px; border-bottom: 2px solid #cbd5e1; }
    .gs-table td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; }
    .gs-table tr:nth-child(even) { background: rgba(68,114,196,0.04); }

    /* Classification legend in sidebar */
    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
        font-size: 0.88em;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        display: inline-block;
        flex-shrink: 0;
    }

    /* Consistent section spacing */
    .stDivider { margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }

    /* Expander styling */
    details[data-testid="stExpander"] summary {
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def results_to_dataframe(results: list[MatchResult], l5x_used: bool = False) -> pd.DataFrame:
    """Convert MatchResult list to a pandas DataFrame for display.

    Column headers include the data source in parentheses so a separate
    Sources column is unnecessary.
    """
    l5x_tag = ", L5X" if l5x_used else ""
    rows = []
    for r in results:
        io = r.io_device
        plc = r.plc_tag
        rows.append({
            "Device Tag (XLSX)": io.device_tag if io else "",
            "IO Tag (XLSX)": io.io_tag if io else "",
            "Panel (XLSX)": io.panel if io else "",
            "Rack (XLSX)": io.rack if io else "",
            "Slot (XLSX)": io.slot if io else "",
            "Channel (XLSX)": io.channel if io else "",
            "PLC Address (XLSX)": io.plc_address if io else "",
            "Module Type (XLSX)": io.module_type if io else "",
            "Classification": r.classification.value,
            "Strategy": r.strategy_id if r.strategy_id else "",
            "Confidence": r.confidence.value if r.strategy_id else "",
            f"PLC Tag (CSV{l5x_tag})": plc.name if plc else "",
            f"PLC Description (CSV{l5x_tag})": plc.description if plc else "",
            "Conflict": "YES" if r.conflict_flag else "",
            "Audit Trail": " | ".join(r.audit_trail),
        })
    return pd.DataFrame(rows)


def color_classification(val: str) -> str:
    """Return CSS styling for classification column."""
    is_dark = st.session_state.get("dark_mode", False)
    if is_dark:
        colors = {
            "Both": "background-color: #166534; color: #bbf7d0",
            "IO List Only": "background-color: #991b1b; color: #fecaca",
            "PLC Only": "background-color: #1e40af; color: #bfdbfe",
            "Conflict": "background-color: #92400e; color: #fed7aa",
            "Spare": "background-color: #374151; color: #d1d5db",
            "Rack Only": "background-color: #78350f; color: #fde68a",
        }
    else:
        colors = {
            "Both": "background-color: #dcfce7; color: #166534",
            "IO List Only": "background-color: #fee2e2; color: #991b1b",
            "PLC Only": "background-color: #dbeafe; color: #1e40af",
            "Conflict": "background-color: #ffedd5; color: #9a3412",
            "Spare": "background-color: #f3f4f6; color: #4b5563",
            "Rack Only": "background-color: #fef3c7; color: #78350f",
        }
    return colors.get(val, "")


def _cls_badge(val: str) -> str:
    """Wrap classification value in a styled badge span."""
    css_cls = {
        "Both": "cls-both", "IO List Only": "cls-io-only",
        "PLC Only": "cls-plc-only", "Conflict": "cls-conflict", "Spare": "cls-spare",
        "Rack Only": "cls-rack-only",
    }
    c = css_cls.get(val, "")
    return f'<span class="{c}">{val}</span>' if c else val


# Fixed column widths (px) keyed by column name — keeps layout stable across filters
_COL_WIDTHS: dict[str, int] = {
    "Device Tag (XLSX)": 120,
    "IO Tag (XLSX)": 120,
    "Panel (XLSX)": 60,
    "Rack (XLSX)": 52,
    "Slot (XLSX)": 48,
    "Channel (XLSX)": 68,
    "PLC Address (XLSX)": 150,
    "Module Type (XLSX)": 100,
    "Classification": 95,
    "Strategy": 60,
    "Confidence": 78,
    "PLC Tag (CSV)": 150,
    "PLC Tag (CSV, L5X)": 160,
    "PLC Description (CSV)": 200,
    "PLC Description (CSV, L5X)": 210,
    "Conflict": 58,
}


def df_to_html(dataframe: pd.DataFrame, max_height: int = 500) -> str:
    """Render a DataFrame as a scrollable HTML table with click-to-copy cells."""
    import html as _html
    cols = list(dataframe.columns)
    rows_html = []
    for _, row in dataframe.iterrows():
        cells = []
        for col in cols:
            raw = str(row[col]) if pd.notna(row[col]) else ""
            if col == "Classification":
                cells.append(f"<td>{_cls_badge(raw)}</td>")
            else:
                escaped = _html.escape(raw)
                cells.append(f'<td class="cx-copy" title="{escaped}">{escaped}</td>')
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    header = "<tr>" + "".join(f"<th>{_html.escape(c)}</th>" for c in cols) + "</tr>"
    colgroup = "<colgroup>" + "".join(
        f'<col style="width:{_COL_WIDTHS.get(c, 100)}px">'
        for c in cols
    ) + "</colgroup>"

    # Build a self-contained HTML page so JS executes inside the component iframe
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 0.85em; }}
  .cx-table-wrap {{ border: 1px solid #cbd5e1; border-radius: 12px; overflow: auto; max-height: {max_height}px; }}
  .cx-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  .cx-table th {{ position: sticky; top: 0; background: #f1f5f9; text-align: left; padding: 8px 10px;
                  border-bottom: 2px solid #cbd5e1; white-space: nowrap; z-index: 1;
                  overflow: hidden; text-overflow: ellipsis; }}
  .cx-table td {{ padding: 6px 10px; border-bottom: 1px solid #e2e8f0; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; cursor: pointer;
                  transition: background-color 0.2s; }}
  .cx-table tr:nth-child(even) {{ background: rgba(68, 114, 196, 0.04); }}
  .cx-table tr:hover {{ background: rgba(68, 114, 196, 0.08); }}
  .cx-table td:hover {{ background-color: rgba(59,130,246,0.15) !important; }}
  .cx-copied {{ background-color: rgba(34,197,94,0.25) !important; transition: background-color 0.1s; }}
  .cls-both {{ background-color: #dcfce7; color: #166534; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .cls-io-only {{ background-color: #fee2e2; color: #991b1b; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .cls-plc-only {{ background-color: #dbeafe; color: #1e40af; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .cls-conflict {{ background-color: #ffedd5; color: #9a3412; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .cls-spare {{ background-color: #f3f4f6; color: #4b5563; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .cls-rack-only {{ background-color: #fef3c7; color: #78350f; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  #toast {{ position: fixed; bottom: 12px; right: 12px; background: #166534; color: #fff;
            padding: 6px 16px; border-radius: 8px; font-size: 0.85em; opacity: 0;
            transition: opacity 0.3s; pointer-events: none; z-index: 999; }}
  #toast.show {{ opacity: 1; }}
</style>
</head>
<body>
<div class="cx-table-wrap">
  <table class="cx-table">{colgroup}{header}{chr(10).join(rows_html)}</table>
</div>
<div id="toast">Copied!</div>
<script>
document.addEventListener('click', function(e) {{
    var td = e.target.closest('td');
    if (!td) return;
    var text = td.innerText.trim();
    if (!text) return;
    navigator.clipboard.writeText(text).then(function() {{
        td.classList.add('cx-copied');
        var toast = document.getElementById('toast');
        toast.textContent = 'Copied: ' + text;
        toast.classList.add('show');
        setTimeout(function(){{ td.classList.remove('cx-copied'); toast.classList.remove('show'); }}, 1200);
    }}).catch(function(err) {{
        // Fallback for older browsers / permission issues
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        td.classList.add('cx-copied');
        var toast = document.getElementById('toast');
        toast.textContent = 'Copied: ' + text;
        toast.classList.add('show');
        setTimeout(function(){{ td.classList.remove('cx-copied'); toast.classList.remove('show'); }}, 1200);
    }});
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("IO Crosscheck")
    st.caption("PLC-to-IO List Device Verification Engine")

    # Dark mode toggle disabled for now — keeping code but forcing light mode
    if "dark_mode" not in st.session_state:
        st.session_state["dark_mode"] = False
    dark_mode = False

    st.divider()

    st.markdown("**Settings**")
    sheet_name = st.text_input("Sheet Name", value="ESCO List", key="sidebar_sheet")
    encoding = st.selectbox(
        "CSV Encoding",
        options=["latin-1", "utf-8", "cp1252"],
        index=0,
        key="sidebar_encoding",
    )

    st.divider()

    with st.expander("**RSLogix Integration**", expanded=False):
        rslogix_enabled = st.toggle(
            "Enable Search Automation",
            value=st.session_state.get("rslogix_enabled", False),
            key="rslogix_enabled",
            help="Send tag searches to Studio 5000 via keyboard automation",
        )
        rslogix_mode = st.selectbox(
            "Target Mode",
            options=["VMware", "Studio 5000 (Direct)"],
            index=0,
            key="rslogix_mode",
            help="Where is Studio 5000 running?",
        )
        default_title = "VMware Workstation" if rslogix_mode == "VMware" else "Logix Designer"
        rslogix_window = st.text_input(
            "Window Title Pattern",
            value=st.session_state.get("rslogix_window", default_title),
            key="rslogix_window",
            help="Substring to match the target window title",
        )
        rslogix_delay = st.slider(
            "Keystroke Delay (ms)",
            min_value=200,
            max_value=2000,
            value=st.session_state.get("rslogix_delay", 500),
            step=100,
            key="rslogix_delay",
            help="Wait time after focusing window before sending keystrokes",
        )

    st.divider()

    st.markdown("**Classification Legend**")
    st.markdown("""
    <div class="legend-item"><span class="legend-dot" style="background:#22c55e;"></span> Both — confirmed in PLC &amp; IO List</div>
    <div class="legend-item"><span class="legend-dot" style="background:#ef4444;"></span> IO List Only — missing from PLC</div>
    <div class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> PLC Only — missing from IO List</div>
    <div class="legend-item"><span class="legend-dot" style="background:#f59e0b;"></span> Conflict — address match, name differs</div>
    <div class="legend-item"><span class="legend-dot" style="background:#9ca3af;"></span> Spare — excluded from mismatch</div>
    """, unsafe_allow_html=True)

    st.divider()
    st.caption("v0.1.0")


# ---------------------------------------------------------------------------
# Dark mode CSS overrides
# ---------------------------------------------------------------------------

if dark_mode:
    st.markdown("""
    <style>
        /* ===== DARK MODE ===== */

        /* Global text color catch-all */
        .stApp, .stApp * { color: #e2e8f0; }

        /* Main area backgrounds */
        .stApp,
        [data-testid="stAppViewContainer"],
        .block-container,
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            background-color: #0f172a !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {
            background-color: #1e293b !important;
        }
        section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] { background-color: transparent !important; }
        .stTabs [data-baseweb="tab"] { color: #94a3b8 !important; }
        .stTabs [aria-selected="true"] { color: #e2e8f0 !important; }
        .stTabs [data-baseweb="tab-highlight"] { background-color: #4472C4 !important; }
        .stTabs [data-baseweb="tab-border"] { background-color: #334155 !important; }

        /* Metric cards */
        .metric-total div[data-testid="stMetric"] { background: linear-gradient(135deg, #1e293b, #334155) !important; border-left-color: #94a3b8 !important; }
        .metric-both div[data-testid="stMetric"] { background: linear-gradient(135deg, #14532d, #166534) !important; border-left-color: #22c55e !important; }
        .metric-io-only div[data-testid="stMetric"] { background: linear-gradient(135deg, #7f1d1d, #991b1b) !important; border-left-color: #ef4444 !important; }
        .metric-plc-only div[data-testid="stMetric"] { background: linear-gradient(135deg, #1e3a5f, #1e40af) !important; border-left-color: #3b82f6 !important; }
        .metric-conflict div[data-testid="stMetric"] { background: linear-gradient(135deg, #78350f, #92400e) !important; border-left-color: #f59e0b !important; }
        .metric-spare div[data-testid="stMetric"] { background: linear-gradient(135deg, #1e293b, #334155) !important; border-left-color: #6b7280 !important; }
        div[data-testid="stMetric"] * { color: #e2e8f0 !important; }
        div[data-testid="stMetric"] { border-color: #475569 !important; }

        /* Getting-started card */
        .getting-started { background: #1e293b !important; border-color: #475569 !important; }
        .getting-started * { color: #cbd5e1 !important; }
        .getting-started h4 { color: #93c5fd !important; }
        .gs-subtitle { color: #94a3b8 !important; }
        .gs-table th { border-bottom-color: #475569 !important; color: #e2e8f0 !important; }
        .gs-table td { border-bottom-color: #334155 !important; }
        .gs-table tr:nth-child(even) { background: rgba(148, 163, 184, 0.08) !important; }
        .getting-started .cls-both { background-color: #166534 !important; color: #bbf7d0 !important; }
        .getting-started .cls-plc-only { background-color: #1e40af !important; color: #bfdbfe !important; }

        /* Inputs, selects, text areas */
        div[data-baseweb="input"],
        div[data-baseweb="input"] input,
        div[data-baseweb="select"],
        div[data-baseweb="select"] div,
        div[data-baseweb="popover"] li,
        .stTextInput > div > div,
        .stSelectbox > div > div,
        .stTextArea textarea {
            background-color: #1e293b !important;
            color: #e2e8f0 !important;
        }

        /* File uploader — container and label area */
        [data-testid="stFileUploader"],
        [data-testid="stFileUploader"] > div,
        [data-testid="stFileUploader"] > section,
        [data-testid="stFileUploader"] > label,
        [data-testid="stFileUploadDropzone"] {
            background-color: transparent !important;
            color: #e2e8f0 !important;
        }
        [data-testid="stFileUploader"] label,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] p {
            color: #e2e8f0 !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background-color: #1e293b !important;
            border: 1px solid #475569 !important;
            border-radius: 12px !important;
        }
        /* Browse files button — visible border and text */
        [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
            border: 1px solid #94a3b8 !important;
            color: #e2e8f0 !important;
            background-color: #334155 !important;
            border-radius: 6px !important;
        }
        [data-testid="stFileUploaderDropzone"] button span,
        [data-testid="stFileUploaderDropzone"] button p {
            color: #e2e8f0 !important;
        }
        [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stFileUploaderDropzone"] small { color: #94a3b8 !important; }

        /* Theme toggle icon — yellow sun in dark mode */
        section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:first-of-type span[data-testid="stIconMaterial"] {
            color: #facc15 !important;
        }

        /* Buttons */
        .stButton > button { border-color: #475569 !important; color: #e2e8f0 !important; background-color: #1e293b !important; }
        .stButton > button:hover { background-color: #334155 !important; }
        .stButton > button[kind="primary"],
        .stButton > button[data-testid="stBaseButton-primary"] {
            background-color: #4472C4 !important; border-color: #4472C4 !important; color: #ffffff !important;
        }
        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-testid="stBaseButton-primary"]:hover {
            background-color: #3561a8 !important;
        }
        .stDownloadButton > button {
            border: 1px solid #475569 !important;
            color: #e2e8f0 !important;
            background-color: #1e293b !important;
        }
        .stDownloadButton > button:hover { background-color: #334155 !important; }
        .stDownloadButton > button span,
        .stDownloadButton > button p { color: #e2e8f0 !important; }

        /* Segmented control / radio pills */
        [data-testid="stSegmentedControl"] { background-color: #1e293b !important; border: 1px solid #475569 !important; border-radius: 8px !important; }
        [data-testid="stSegmentedControl"] label,
        [data-testid="stSegmentedControl"] span,
        [data-testid="stSegmentedControl"] p,
        [data-testid="stSegmentedControl"] div,
        [data-testid="stSegmentedControl"] button {
            color: #94a3b8 !important;
            background-color: transparent !important;
        }
        [data-testid="stSegmentedControl"] button[aria-checked="true"],
        [data-testid="stSegmentedControl"] button[aria-checked="true"] span,
        [data-testid="stSegmentedControl"] button[aria-checked="true"] p,
        [data-testid="stSegmentedControl"] button[aria-checked="true"] div {
            background-color: #4472C4 !important;
            color: #ffffff !important;
        }

        /* Input placeholders */
        ::placeholder { color: #64748b !important; opacity: 1 !important; }
        input::placeholder, textarea::placeholder { color: #64748b !important; }

        /* Dataframe (st.dataframe — Glide Data Grid, used in L5X tab) */
        div[data-testid="stDataFrame"] { background-color: #1e293b !important; }
        div[data-testid="stDataFrame"] * { color: #e2e8f0 !important; }

        /* Custom HTML results table — dark mode */
        .cx-table-wrap { border-color: #475569 !important; }
        .cx-table th { background: #0f172a !important; color: #e2e8f0 !important; border-bottom-color: #475569 !important; }
        .cx-table td { color: #e2e8f0 !important; border-bottom-color: #334155 !important; }
        .cx-table tr:nth-child(even) { background: rgba(148, 163, 184, 0.08) !important; }
        .cx-table tr:hover { background: rgba(148, 163, 184, 0.15) !important; }

        /* Classification badge pills — dark mode */
        .cls-both { background-color: #166534 !important; color: #bbf7d0 !important; }
        .cls-both-rack { background-color: #713f12 !important; color: #fef08a !important; }
        .cls-io-only { background-color: #991b1b !important; color: #fecaca !important; }
        .cls-plc-only { background-color: #1e40af !important; color: #bfdbfe !important; }
        .cls-conflict { background-color: #92400e !important; color: #fed7aa !important; }
        .cls-spare { background-color: #374151 !important; color: #d1d5db !important; }
        .cls-rack-only { background-color: #78350f !important; color: #fde68a !important; }

        /* Alerts: keep their colored backgrounds, ensure text is readable */
        .stAlert { border-radius: 8px !important; }
        [data-testid="stNotification"] { background-color: #1e293b !important; border: 1px solid #475569 !important; }
        [data-testid="stNotification"] p,
        [data-testid="stNotification"] span,
        [data-testid="stNotification"] div { color: #e2e8f0 !important; }
        /* Warning alert — amber tint */
        div[data-baseweb="notification"][kind="warning"],
        .stAlert[data-baseweb] { background-color: rgba(245, 158, 11, 0.15) !important; border-left: 4px solid #f59e0b !important; }
        /* Info alert — blue tint */
        div[data-baseweb="notification"][kind="info"] { background-color: rgba(59, 130, 246, 0.15) !important; border-left: 4px solid #3b82f6 !important; }
        /* Success alert — green tint */
        div[data-baseweb="notification"][kind="positive"],
        [data-testid="stAlert"] div[role="alert"] { background-color: rgba(34, 197, 94, 0.15) !important; border-left: 4px solid #22c55e !important; }

        /* Captions */
        [data-testid="stCaptionContainer"] * { color: #94a3b8 !important; }

        /* Dividers */
        hr { border-color: #334155 !important; }

        /* Expanders */
        details[data-testid="stExpander"] { background-color: #1e293b !important; border: 1px solid #475569 !important; border-radius: 12px !important; }
        details[data-testid="stExpander"] * { color: #e2e8f0 !important; }
        details[data-testid="stExpander"] summary { background-color: #1e293b !important; border-radius: 12px !important; }

        /* Code blocks */
        .stCodeBlock, .stCodeBlock code, pre { background-color: #0f172a !important; color: #e2e8f0 !important; border: 1px solid #334155 !important; border-radius: 8px !important; }

        /* Spinner */
        .stSpinner > div { color: #e2e8f0 !important; }

        /* Popover / dropdown menus */
        [data-baseweb="popover"], [data-baseweb="menu"] { background-color: #1e293b !important; border: 1px solid #475569 !important; }
        [data-baseweb="popover"] *, [data-baseweb="menu"] * { color: #e2e8f0 !important; }
        [data-baseweb="menu"] li:hover { background-color: #334155 !important; }

        /* Help tooltips */
        [data-testid="stTooltipIcon"] svg { color: #94a3b8 !important; fill: #94a3b8 !important; }

        /* Markdown bold text */
        .stMarkdown strong { color: #e2e8f0 !important; }

        /* Column containers — prevent white gaps */
        [data-testid="stHorizontalBlock"],
        [data-testid="stVerticalBlock"],
        [data-testid="stColumn"] {
            background-color: transparent !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_crosscheck, tab_l5x = st.tabs(["IO Crosscheck", "L5X Explorer"])


# ===================================================================
# TAB 1: IO Crosscheck
# ===================================================================

with tab_crosscheck:
    st.markdown("### Upload Files")
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

    run_btn = st.button(
        "Run Analysis",
        type="primary",
        disabled=(csv_file is None or xlsx_file is None),
    )

    if not run_btn and "results" not in st.session_state:
        st.markdown("""
        <div class="getting-started">
            <h4>Getting Started</h4>
            <p style="margin-bottom: 0.8rem;">
                Upload your <strong>PLC Tag Export CSV</strong> and <strong>IO List XLSX</strong> above,
                then click <strong>Run Analysis</strong> to verify every device.
                Optionally add an <strong>L5X project file</strong> to enrich results with
                source confirmation from alias mappings and module validation.
            </p>
            <p class="gs-subtitle">Matching Strategies (Priority Order)</p>
            <table class="gs-table">
                <tr>
                    <th>#</th>
                    <th>Strategy</th>
                    <th>Confidence</th>
                    <th>Description</th>
                </tr>
                <tr>
                    <td>1</td>
                    <td>Direct CLX Address Match</td>
                    <td><span class="cls-both">Exact</span></td>
                    <td>IO List PLC address vs PLC COMMENT specifiers</td>
                </tr>
                <tr>
                    <td>2</td>
                    <td>PLC5 Rack Address Match</td>
                    <td><span class="cls-both">Exact</span></td>
                    <td>PLC5-format addresses vs PLC TAG names</td>
                </tr>
                <tr>
                    <td>4</td>
                    <td>ENet Module Tag Extraction</td>
                    <td><span class="cls-both">Exact</span></td>
                    <td>Extract device IDs from E300_/VFD_/IPDev_ prefixed tags</td>
                </tr>
                <tr>
                    <td>5</td>
                    <td>Tag Name Normalization</td>
                    <td><span class="cls-plc-only">High</span></td>
                    <td>Suffix-stripped, case-folded exact name matching</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)


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
                xlsm_report_path = output_dir / "io_crosscheck_report.xlsm"
                generate_xlsx_report(results, xlsx_report_path)
                generate_html_report(results, html_report_path)
                generate_xlsm_report(results, xlsm_report_path)

                st.session_state["results"] = results
                st.session_state["plc_tag_count"] = len(plc_tags)
                st.session_state["io_device_count"] = len(io_devices)
                st.session_state["spare_count"] = sum(1 for d in io_devices if is_spare(d.io_tag))
                st.session_state["xlsx_bytes"] = xlsx_report_path.read_bytes()
                st.session_state["html_bytes"] = html_report_path.read_bytes()
                st.session_state["xlsm_bytes"] = xlsm_report_path.read_bytes()
                st.session_state["df"] = results_to_dataframe(results, l5x_used=l5x_cx_file is not None)
                st.session_state["l5x_msg_tags"] = (
                    l5x_enrichment_data["msg_tags"] if l5x_enrichment_data else []
                )
                st.session_state["l5x_consumed_tags"] = (
                    l5x_enrichment_data["consumed_tags"] if l5x_enrichment_data else []
                )
                st.session_state["l5x_used"] = l5x_cx_file is not None

                # Populate L5X Explorer tab data when L5X was used
                if l5x_cx_file is not None and l5x_data is not None:
                    md_content = generate_l5x_markdown(l5x_data)
                    st.session_state["l5x_data"] = l5x_data
                    st.session_state["l5x_md"] = md_content
                    st.session_state["l5x_filename"] = l5x_cx_file.name

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
        metric_css_classes = [
            "metric-total", "metric-both", "metric-io-only",
            "metric-plc-only", "metric-conflict", "metric-spare",
        ]
        metrics = [
            ("Total", len(results)),
            ("Both", cls_counts.get("Both", 0)),
            ("IO List Only", cls_counts.get("IO List Only", 0)),
            ("PLC Only", cls_counts.get("PLC Only", 0)),
            ("Conflicts", conflict_count),
            ("Spares", cls_counts.get("Spare", 0)),
        ]
        cols = st.columns(6)
        for col, css_cls, (label, value) in zip(cols, metric_css_classes, metrics):
            with col:
                pct = f"{value / len(results) * 100:.1f}%" if results else "0%"
                st.markdown(f'<div class="{css_cls}">', unsafe_allow_html=True)
                st.metric(label, value, pct)
                st.markdown('</div>', unsafe_allow_html=True)

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
        dl_col1, dl_col2, dl_col3, _ = st.columns([1, 1, 1, 2])
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
        with dl_col3:
            st.download_button(
                label="Download XLSM (Macros)",
                data=st.session_state["xlsm_bytes"],
                file_name="io_crosscheck_report.xlsm",
                mime="application/vnd.ms-excel.sheet.macroEnabled.12",
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
            use_container_width=True,
            height=500,
            hide_index=True,
        )

        # RSLogix search
        if st.session_state.get("rslogix_enabled", False):
            st.divider()
            st.markdown("### Search in RSLogix")
            # Build tag list from visible results for autocomplete
            # Column names include source annotations; find by prefix
            def _col(prefix: str) -> str:
                return next((c for c in filtered_df.columns if c.startswith(prefix)), "")
            tag_options = sorted(set(
                t for t in filtered_df.get(_col("PLC Tag"), pd.Series()).tolist()
                + filtered_df.get(_col("Device Tag"), pd.Series()).tolist()
                + filtered_df.get(_col("IO Tag"), pd.Series()).tolist()
                if t and str(t).strip() and str(t) != "nan"
            ))

            # Show result from previous search attempt
            if "rslogix_result" in st.session_state:
                r = st.session_state.pop("rslogix_result")
                if r["success"]:
                    st.success(r["message"])
                else:
                    st.error(r["message"])

            with st.form("rslogix_form", clear_on_submit=False):
                rs_col1, rs_col2 = st.columns([3, 1])
                with rs_col1:
                    search_tag = st.selectbox(
                        "Tag to search",
                        options=[""] + tag_options,
                        index=0,
                        key="rslogix_search_tag",
                        placeholder="Select or type a tag name...",
                        label_visibility="collapsed",
                    )
                with rs_col2:
                    submitted = st.form_submit_button(
                        "🔍 Search in RSLogix",
                        use_container_width=True,
                        type="primary",
                    )
                if submitted:
                    if search_tag:
                        from io_crosscheck.rslogix_bridge import search_in_rslogix
                        result = search_in_rslogix(
                            tag_name=search_tag,
                            window_title=st.session_state.get("rslogix_window", "VMware Workstation"),
                            delay_ms=st.session_state.get("rslogix_delay", 500),
                        )
                        st.session_state["rslogix_result"] = result
                    else:
                        st.session_state["rslogix_result"] = {
                            "success": False, "message": "Select a tag name first.",
                        }

        # Conflicts detail
        if conflict_count > 0:
            st.divider()
            st.markdown("### Conflicts Requiring Review")
            st.warning(f"{conflict_count} device(s) have address matches but different names. These require human review.")
            # Column names include source annotations; find by prefix
            def _dcol(prefix: str) -> str:
                return next((c for c in df.columns if c.startswith(prefix)), "")
            conflict_mask = df["Conflict"] == "YES"
            conflict_src = df[conflict_mask].copy()
            # Build a concise reason from the audit trail
            audit_col = "Audit Trail"
            if audit_col in conflict_src.columns:
                def _extract_reason(trail: str) -> str:
                    for part in reversed(trail.split(" | ")):
                        p = part.strip()
                        if any(kw in p.lower() for kw in ["spare but", "may be unused", "conflict", "no alias found", "rung cdata"]):
                            return p
                    return ""
                conflict_src["Reason"] = conflict_src[audit_col].apply(_extract_reason)
            else:
                conflict_src["Reason"] = ""
            conflict_df = conflict_src[
                [_dcol("Device Tag"), _dcol("IO Tag"), _dcol("PLC Address"), _dcol("PLC Tag"), _dcol("PLC Description"), "Reason"]
            ]
            st.dataframe(conflict_df, use_container_width=True, height=400, hide_index=True)

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

    if not l5x_extract_btn and "l5x_data" not in st.session_state:
        st.markdown("""
        <div class="getting-started">
            <h4>L5X Project Explorer</h4>
            <p>
                Upload an RSLogix 5000 / Studio 5000 <strong>L5X project file</strong> to extract
                every tag, module, alias, bit-level description, and structure member
                into a downloadable Markdown report.
            </p>
            <p style="font-size: 0.9em; color: #64748b;">
                <strong>Tip:</strong> If you include an L5X file in the IO Crosscheck analysis,
                the extracted data will automatically appear here.
            </p>
        </div>
        """, unsafe_allow_html=True)

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
        l5x_metrics = [
            ("Modules", stats.get("total_modules", 0)),
            ("Controller Tags", stats.get("total_controller_tags", 0)),
            ("Alias Tags", stats.get("controller_alias_tags", 0)),
            ("Programs", stats.get("total_programs", 0)),
            ("Program Tags", stats.get("total_program_tags", 0)),
            ("Bit Descriptions", stats.get("bit_level_descriptions", 0)),
        ]
        m_cols = st.columns(6)
        for col, (label, value) in zip(m_cols, l5x_metrics):
            with col:
                st.markdown('<div class="metric-total">', unsafe_allow_html=True)
                st.metric(label, value)
                st.markdown('</div>', unsafe_allow_html=True)

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

        # --- Programs & Routines (Rung Data) ---
        total_routines = sum(len(p.get("routines", [])) for p in programs)
        total_rungs = sum(
            len(r.get("rungs", []))
            for p in programs for r in p.get("routines", [])
        )
        with st.expander(f"Programs & Routines — Rung Data ({total_routines} routines, {total_rungs} rungs)"):
            if not programs:
                st.info("No programs found.")
            else:
                for prog in programs:
                    prog_name = prog.get("name", "Unknown")
                    routines = prog.get("routines", [])
                    if not routines:
                        continue
                    st.markdown(f"#### Program: `{prog_name}`")
                    rung_search = st.text_input(
                        "Search rungs",
                        placeholder="Filter by rung #, text, or comment...",
                        key=f"rung_search_{prog_name}",
                        label_visibility="collapsed",
                    )
                    for routine in routines:
                        routine_name = routine.get("name", "Unknown")
                        routine_type = routine.get("type", "")
                        rungs = routine.get("rungs", [])
                        type_label = f" ({routine_type})" if routine_type else ""

                        # Apply search filter
                        if rung_search:
                            q = rung_search.lower()
                            rungs = [
                                r for r in rungs
                                if q in str(r.get("number", "")).lower()
                                or q in r.get("text", "").lower()
                                or q in r.get("comment", "").lower()
                            ]

                        rung_count_label = f"{len(rungs)} rungs" if not rung_search else f"{len(rungs)} matches"
                        with st.expander(f"Routine: {routine_name}{type_label} — {rung_count_label}"):
                            if not rungs:
                                st.info("No rungs match your search." if rung_search else "No rungs in this routine (may be a non-ladder routine).")
                            else:
                                def _highlight(text: str, query: str) -> str:
                                    """Wrap all case-insensitive occurrences of query in <mark> tags."""
                                    import html as _html
                                    escaped = _html.escape(text).replace("\n", "<br>")
                                    if not query:
                                        return escaped
                                    import re as _re
                                    pattern = _re.compile(_re.escape(_html.escape(query)), _re.IGNORECASE)
                                    return pattern.sub(lambda m: f"<mark>{m.group()}</mark>", escaped)

                                q_hl = rung_search.strip() if rung_search else ""
                                rows_html = []
                                for rung in rungs:
                                    num = str(rung.get("number", ""))
                                    txt = rung.get("text", "")
                                    cmt = rung.get("comment", "")
                                    rows_html.append(
                                        f"<tr><td>{_highlight(num, q_hl)}</td>"
                                        f"<td><code>{_highlight(txt, q_hl)}</code></td>"
                                        f"<td>{_highlight(cmt, q_hl)}</td></tr>"
                                    )
                                table_html = (
                                    f'<div class="cx-table-wrap" style="max-height:600px;overflow:auto;">'
                                    f'<table class="cx-table">'
                                    f'<tr><th style="width:70px;">Rung #</th><th>Neutral Text</th><th>Comment</th></tr>'
                                    f'{"".join(rows_html)}'
                                    f'</table></div>'
                                )
                                st.markdown(table_html, unsafe_allow_html=True)
