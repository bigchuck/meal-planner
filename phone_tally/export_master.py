"""
Generate the phone tally web app's index.html from index.template.html.

index.template.html holds the app shell/CSS/JS with the food and alias data
left as empty placeholders (/*MASTER_DATA_START*/[]/*MASTER_DATA_END*/ and
/*ALIAS_DATA_START*/{}/*ALIAS_DATA_END*/ inside its inline <script>) — it's
the tracked source of truth for the app's logic. This script reads that
template, reads master/alias data through the app's normal config (config.py
/ config_local.py MODE selection), and writes the filled-in result to
index.html.

index.html itself is git-ignored and always fully regenerated from the
template — never hand-edit it, and never edit-in-place, since either would
be silently discarded (or worse, relied upon) next time this runs. This also
means index.html can always be rebuilt from scratch (e.g. after deleting it)
as long as index.template.html and the data files still exist.

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

TEMPLATE_PATH = Path(__file__).parent / "index.template.html"
OUTPUT_PATH = Path(__file__).parent / "index.html"

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

    if not TEMPLATE_PATH.exists():
        raise SystemExit(
            f"Template not found: {TEMPLATE_PATH}\n"
            "index.html is generated from this file and is never itself the source "
            "of truth — restore index.template.html (e.g. from git) before re-running."
        )

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for name, pattern in (("MASTER_DATA", MASTER_MARKER_RE), ("ALIAS_DATA", ALIAS_MARKER_RE)):
        if not pattern.search(html):
            raise SystemExit(
                f"Could not find {name}_START/END markers in {TEMPLATE_PATH}. "
                "Was the inline <script> restructured?"
            )

    master_payload = json.dumps(records, separators=(",", ":"))
    html = MASTER_MARKER_RE.sub(lambda m: m.group(1) + master_payload + m.group(3), html, count=1)

    alias_payload = json.dumps(aliases, separators=(",", ":"))
    html = ALIAS_MARKER_RE.sub(lambda m: m.group(1) + alias_payload + m.group(3), html, count=1)

    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(f"Embedded {len(records)} codes from {config.MASTER_FILE} into {OUTPUT_PATH}")
    print(f"Embedded {len(aliases)} aliases from {config.ALIASES_FILE} into {OUTPUT_PATH}")
    print(f"Mode: {config.MODE}")


if __name__ == "__main__":
    main()
