"""
migrate_add_verified.py

One-off migration: adds 'verified' and 'verified_date' fields to every
entry in master.json that does not already have them.

Usage:
    python migrate_add_verified.py                        # defaults to production path
    python migrate_add_verified.py --dev                  # uses development path
    python migrate_add_verified.py --path "C:\path\to\meal_plan_master.json"
    python migrate_add_verified.py --dry-run              # preview only, no write
"""

import json
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime

PRODUCTION_PATH = Path(r"C:\data\mealplan\meal_plan_master.json")
DEVELOPMENT_PATH = Path(__file__).parent / "data" / "meal_plan_master.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Add verified fields to master.json")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dev", action="store_true", help="Use development data path")
    group.add_argument("--path", type=str, help="Explicit path to master.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    return parser.parse_args()


def resolve_path(args) -> Path:
    if args.path:
        return Path(args.path)
    if args.dev:
        return DEVELOPMENT_PATH
    return PRODUCTION_PATH


def create_backup(master_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = master_path.parent / f"{master_path.stem}_backup_{timestamp}.json"
    shutil.copy2(master_path, backup_path)
    return backup_path


def main():
    args = parse_args()
    master_path = resolve_path(args)

    if not master_path.exists():
        print(f"ERROR: File not found: {master_path}")
        sys.exit(1)

    print(f"Target file : {master_path}")
    print(f"Dry run     : {args.dry_run}")
    print()

    # Load
    with open(master_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not isinstance(entries, list):
        print("ERROR: master.json does not contain a list at the top level.")
        sys.exit(1)

    total = len(entries)
    already_had = 0
    added = 0

    for entry in entries:
        has_verified = "verified" in entry
        has_date = "verified_date" in entry

        if has_verified and has_date:
            already_had += 1
            continue

        # Add only the fields that are missing
        if not has_verified:
            entry["verified"] = False
        if not has_date:
            entry["verified_date"] = ""
        added += 1

    # Report
    print(f"Total entries     : {total}")
    print(f"Already had fields: {already_had}")
    print(f"Fields added to   : {added}")
    print()

    if added == 0:
        print("Nothing to do - all entries already have verified fields.")
        return

    if args.dry_run:
        print("Dry run complete. No changes written.")
        return

    # Backup before writing
    backup_path = create_backup(master_path)
    print(f"Backup created    : {backup_path.name}")

    # Write back
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    print(f"Migration complete. {added} entries updated.")


if __name__ == "__main__":
    main()