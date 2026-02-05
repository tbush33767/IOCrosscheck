"""CLI entry point for IO Crosscheck."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from io_crosscheck.parsers import parse_plc_csv, parse_io_list_xlsx
from io_crosscheck.classifiers import classify_tag, is_spare
from io_crosscheck.strategies import MatchingEngine
from io_crosscheck.reports import generate_xlsx_report, generate_html_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="io-crosscheck",
        description="IO Crosscheck — PLC-to-IO List Device Verification Engine",
    )
    parser.add_argument(
        "plc_csv",
        type=Path,
        help="Path to RSLogix 5000 CSV tag export file",
    )
    parser.add_argument(
        "io_list_xlsx",
        type=Path,
        help="Path to IO List XLSX file",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for reports (default: ./output)",
    )
    parser.add_argument(
        "--sheet",
        default="ESCO List",
        help="IO List sheet name (default: 'ESCO List')",
    )
    parser.add_argument(
        "--encoding",
        default="latin-1",
        help="PLC CSV encoding (default: latin-1)",
    )
    parser.add_argument(
        "--xlsx-only",
        action="store_true",
        help="Only generate XLSX report (skip HTML)",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML report (skip XLSX)",
    )

    args = parser.parse_args(argv)

    # Validate inputs
    if not args.plc_csv.exists():
        print(f"Error: PLC CSV file not found: {args.plc_csv}", file=sys.stderr)
        return 1
    if not args.io_list_xlsx.exists():
        print(f"Error: IO List XLSX file not found: {args.io_list_xlsx}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("IO Crosscheck — PLC-to-IO List Device Verification Engine")
    print("=" * 60)

    # Phase 1: Parse inputs
    print(f"\n[1/4] Parsing PLC CSV: {args.plc_csv}")
    t0 = time.perf_counter()
    plc_tags = parse_plc_csv(args.plc_csv, encoding=args.encoding)
    t1 = time.perf_counter()
    print(f"       Parsed {len(plc_tags)} PLC records in {t1 - t0:.2f}s")

    # Classify tags
    for tag in plc_tags:
        tag.category = classify_tag(tag)

    from collections import Counter
    cat_counts = Counter(t.category.value for t in plc_tags)
    for cat, count in sorted(cat_counts.items()):
        print(f"         {cat}: {count}")

    print(f"\n[2/4] Parsing IO List: {args.io_list_xlsx} (sheet: {args.sheet})")
    t0 = time.perf_counter()
    io_devices = parse_io_list_xlsx(args.io_list_xlsx, sheet_name=args.sheet)
    t1 = time.perf_counter()
    print(f"       Parsed {len(io_devices)} IO devices in {t1 - t0:.2f}s")

    spare_count = sum(1 for d in io_devices if is_spare(d.io_tag))
    active_count = len(io_devices) - spare_count
    print(f"         Active: {active_count}, Spare: {spare_count}")

    # Phase 2: Run matching engine
    print(f"\n[3/4] Running matching engine...")
    t0 = time.perf_counter()
    engine = MatchingEngine()
    results = engine.run(io_devices, plc_tags)
    t1 = time.perf_counter()
    print(f"       Completed {len(results)} classifications in {t1 - t0:.2f}s")

    # Print summary
    from io_crosscheck.models import Classification
    cls_counts = Counter(r.classification.value for r in results)
    print(f"\n       --- Classification Summary ---")
    for cls in Classification:
        count = cls_counts.get(cls.value, 0)
        if count > 0:
            pct = count / len(results) * 100 if results else 0
            print(f"         {cls.value}: {count} ({pct:.1f}%)")

    conflict_count = sum(1 for r in results if r.conflict_flag)
    if conflict_count:
        print(f"\n       ⚠ {conflict_count} CONFLICTS requiring human review")

    # Phase 3: Generate reports
    print(f"\n[4/4] Generating reports...")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    if not args.html_only:
        xlsx_path = args.output_dir / "io_crosscheck_report.xlsx"
        generate_xlsx_report(results, xlsx_path)
        generated.append(f"XLSX: {xlsx_path}")

    if not args.xlsx_only:
        html_path = args.output_dir / "io_crosscheck_report.html"
        generate_html_report(results, html_path)
        generated.append(f"HTML: {html_path}")

    for g in generated:
        print(f"       {g}")

    print(f"\n{'=' * 60}")
    print(f"Done. {len(results)} devices classified.")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
