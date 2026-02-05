# IO Crosscheck

**PLC-to-IO List Device Verification Engine**

A deterministic, rule-based matching engine that cross-references RSLogix 5000 PLC tag exports against IO List spreadsheets to verify every device exists in the PLC program, the IO List, or both.

## Quick Start

```bash
# Install
pip install -e .

# Run
python -m io_crosscheck path/to/tags.csv path/to/io_list.xlsx

# Or use the CLI entry point
io-crosscheck path/to/tags.csv path/to/io_list.xlsx
```

## Usage

```
io-crosscheck [-h] [-o OUTPUT_DIR] [--sheet SHEET] [--encoding ENCODING]
               [--xlsx-only] [--html-only]
               plc_csv io_list_xlsx

positional arguments:
  plc_csv               Path to RSLogix 5000 CSV tag export file
  io_list_xlsx          Path to IO List XLSX file

options:
  -o, --output-dir      Output directory for reports (default: ./output)
  --sheet               IO List sheet name (default: 'ESCO List')
  --encoding            PLC CSV encoding (default: latin-1)
  --xlsx-only           Only generate XLSX report (skip HTML)
  --html-only           Only generate HTML report (skip XLSX)
```

## Output Reports

- **XLSX** — `io_crosscheck_report.xlsx` with three sheets:
  - **Verification Detail** — one row per device with color-coded classification
  - **Summary** — counts and percentages per classification
  - **Conflicts** — devices where address matches but names differ

- **HTML** — `io_crosscheck_report.html` with interactive DataTables filtering/sorting

### Classification Color Coding

| Color  | Classification     | Meaning |
|--------|--------------------|---------|
| Green  | Both               | Device confirmed in both PLC and IO List |
| Yellow | Both (Rack Only)   | Rack TAG exists but individual point not confirmed |
| Red    | IO List Only       | Device in IO List but not found in PLC |
| Blue   | PLC Only           | Device in PLC but not in IO List |
| Orange | Conflict           | Address matches but device names differ |
| Grey   | Spare              | Spare point — excluded from mismatch reporting |

## Matching Strategies (Priority Order)

1. **Direct CLX Address Match** — IO List PLC address vs PLC COMMENT specifiers (case-insensitive)
2. **PLC5 Rack Address Match** — PLC5-format addresses vs PLC TAG names
3. **Rack-Level TAG Existence** — Verify parent rack TAG exists when no per-point COMMENT
4. **ENet Module Tag Extraction** — Extract device IDs from E300_/VFD_/IPDev_/IPDEV_ prefixed tags
5. **Tag Name Normalization** — Suffix-stripped, case-folded exact name matching

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=io_crosscheck --cov-report=term-missing
```

## Project Structure

```
src/io_crosscheck/
├── models.py        # Data models (PLCTag, IODevice, MatchResult)
├── normalizers.py   # Tag/address normalization, ENet device extraction
├── classifiers.py   # PLC tag classification, spare detection
├── parsers.py       # CSV tag export + XLSX IO List parsers
├── strategies.py    # 5 matching strategies + MatchingEngine
├── reports.py       # XLSX and HTML report generation
├── main.py          # CLI entry point
└── __main__.py      # python -m support
```
