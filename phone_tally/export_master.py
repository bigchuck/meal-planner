"""
Regenerate the embedded master-data and alias arrays inside the phone tally
web app.

Reads master/alias data through the app's normal config (config.py /
config_local.py MODE selection) and writes them directly into index.html, as
JSON between the /*MASTER_DATA_START*/.../*MASTER_DATA_END*/ and
/*ALIAS_DATA_START*/.../*ALIAS_DATA_END*/ markers in its inline <script>.
index.html is a single self-contained file — nothing is fetched at runtime —
so re-run this and re-copy index.html to the phone whenever the master food
data or aliases change.

Usage: python phone_tally/export_master.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from meal_planner.data.master_loader import MasterLoader
from meal_planner.data.alias_manager import AliasManager

INDEX_PATH = Path(__file__).parent / "index.html"

EXPORT_COLUMNS = [
    "code", "section", "option",
    "cal", "prot_g", "carbs_g", "fat_g", "GI", "GL", "sugar_g",
    "fiber_g", "sodium_mg", "potassium_mg", "vitA_mcg", "vitC_mg", "iron_mg",
]

MASTER_MARKER_RE = re.compile(
    r"(/\*MASTER_DATA_START\*/)(.*?)(/\*MASTER_DATA_END\*/)", re.DOTALL
)
ALIAS_MARKER_RE = re.compile(
    r"(/\*ALIAS_DATA_START\*/)(.*?)(/\*ALIAS_DATA_END\*/)", re.DOTALL
)


def main() -> None:
    loader = MasterLoader(config.MASTER_FILE)
    df = loader.load()

    records = []
    for _, row in df.iterrows():
        record = {col: row.get(col) for col in EXPORT_COLUMNS}
        record["code"] = str(record["code"]).upper()
        records.append(record)

    alias_manager = AliasManager(config.ALIASES_FILE)
    aliases = alias_manager.load()

    html = INDEX_PATH.read_text(encoding="utf-8")
    for name, pattern in (("MASTER_DATA", MASTER_MARKER_RE), ("ALIAS_DATA", ALIAS_MARKER_RE)):
        if not pattern.search(html):
            raise SystemExit(
                f"Could not find {name}_START/END markers in {INDEX_PATH}. "
                "Was the inline <script> restructured?"
            )

    master_payload = json.dumps(records, separators=(",", ":"))
    html = MASTER_MARKER_RE.sub(lambda m: m.group(1) + master_payload + m.group(3), html, count=1)

    alias_payload = json.dumps(aliases, separators=(",", ":"))
    html = ALIAS_MARKER_RE.sub(lambda m: m.group(1) + alias_payload + m.group(3), html, count=1)

    INDEX_PATH.write_text(html, encoding="utf-8")

    print(f"Embedded {len(records)} codes from {config.MASTER_FILE} into {INDEX_PATH}")
    print(f"Embedded {len(aliases)} aliases from {config.ALIASES_FILE} into {INDEX_PATH}")
    print(f"Mode: {config.MODE}")


if __name__ == "__main__":
    main()
