"""
Generate the trimmed master-data file for the phone tally web app.

Reads master data through the app's normal config (config.py / config_local.py
MODE selection) and writes a flat JSON array to phone_tally/master.json —
the file you upload alongside index.html to your web host. Re-run this and
re-upload master.json whenever the master food data changes; index.html
itself doesn't need to change.

Usage: python phone_tally/export_master.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from meal_planner.data.master_loader import MasterLoader

OUTPUT_PATH = Path(__file__).parent / "master.json"

EXPORT_COLUMNS = [
    "code", "section", "option",
    "cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "GL",
    "fiber_g", "sodium_mg", "potassium_mg", "vitA_mcg", "vitC_mg", "iron_mg",
]


def main() -> None:
    loader = MasterLoader(config.MASTER_FILE)
    df = loader.load()

    records = []
    for _, row in df.iterrows():
        record = {col: row.get(col) for col in EXPORT_COLUMNS}
        record["code"] = str(record["code"]).upper()
        records.append(record)

    OUTPUT_PATH.write_text(json.dumps(records, separators=(",", ":")))
    print(f"Wrote {len(records)} codes from {config.MASTER_FILE} to {OUTPUT_PATH}")
    print(f"Mode: {config.MODE}")


if __name__ == "__main__":
    main()
