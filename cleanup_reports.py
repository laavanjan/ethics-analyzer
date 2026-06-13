"""Delete saved ethics reports older than the configured TTL.

Addresses CER control **PRIV-04** (retention / deletion).

Default TTL: 30 days. Run from cron or Task Scheduler to keep the
``./reports/`` directory bounded.

Examples
--------
    python cleanup_reports.py              # delete reports older than 30 days
    python cleanup_reports.py --days 7     # custom TTL
    python cleanup_reports.py --dry-run    # show what would be deleted
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

DEFAULT_TTL_DAYS = 30
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def _expired_files(reports_dir: Path, cutoff: datetime) -> list[Path]:
    if not reports_dir.exists():
        return []
    out: list[Path] = []
    for path in reports_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime < cutoff:
            out.append(path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_TTL_DAYS,
        help=f"Delete reports older than this many days (default: {DEFAULT_TTL_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without deleting anything.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help=f"Directory holding the reports (default: {REPORTS_DIR}).",
    )
    args = parser.parse_args()

    if args.days <= 0:
        parser.error("--days must be a positive integer.")

    cutoff = datetime.now() - timedelta(days=args.days)
    expired = _expired_files(args.reports_dir, cutoff)

    if not expired:
        print(f"No reports older than {args.days} day(s) found in {args.reports_dir}.")
        return 0

    action = "Would delete" if args.dry_run else "Deleting"
    print(f"{action} {len(expired)} report(s) older than {args.days} day(s):")
    for path in expired:
        age_days = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days
        print(f"  - {path.name}  ({age_days} day(s) old)")
        if not args.dry_run:
            try:
                path.unlink()
            except OSError as exc:
                print(f"    FAILED: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
