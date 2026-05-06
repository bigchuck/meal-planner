"""
fetch_canonical.py

Standalone tool for building and maintaining meal_plan_canonical_ingredients.json.
Fetches ingredient data from USDA FoodData Central (FDC) or accepts manual entry
for restaurant/diner items without an API source.

No external dependencies — uses only Python standard library.

Setup:
    1. Get a free FDC API key at https://fdc.nal.usda.gov/api-key-signup
    2. Save the key in C:\\data\\mealplan\\fdc_api_key.txt  (one line, no quotes)
       OR set environment variable FDC_API_KEY=yourkey

Usage:
    python fetch_canonical.py --list
    python fetch_canonical.py --fetch "chicken breast"
    python fetch_canonical.py --fetch "oats rolled"  --data-type Foundation
    python fetch_canonical.py --fdc-id 171705
    python fetch_canonical.py --manual
    python fetch_canonical.py --fetch "chicken breast" --dry-run
"""

import json
import sys
import os
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PRODUCTION_DATA_PATH = Path(r"C:\data\mealplan")
DEVELOPMENT_DATA_PATH = Path(__file__).parent / "data"

CANONICAL_FILENAME = "meal_plan_canonical_ingredients.json"
API_KEY_FILENAME   = "fdc_api_key.txt"

FDC_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# ---------------------------------------------------------------------------
# USDA FDC nutrient ID -> internal key mapping
# Priority: first matching ID wins (some foods report the same nutrient
# under multiple IDs; we take the most authoritative one).
# ---------------------------------------------------------------------------

NUTRIENT_MAP = {
    # Internal key       : [FDC nutrient IDs in priority order]
    "cal"        : [1008],            # Energy, kcal
    "prot_g"     : [1003],            # Protein
    "carbs_g"    : [1005],            # Carbohydrate, by difference
    "fat_g"      : [1004],            # Total lipid (fat)
    "sugar_g"    : [2000, 1063],      # Sugars, total (NLEA preferred)
    "fiber_g"    : [1079],            # Fiber, total dietary
    "sodium_mg"  : [1093],            # Sodium
    "potassium_mg": [1092],           # Potassium
    "vitA_mcg"   : [1106],            # Vitamin A, RAE
    "vitC_mg"    : [1162],            # Vitamin C, total ascorbic acid
    "iron_mg"    : [1089],            # Iron
}

# Valid data types the FDC search accepts
VALID_DATA_TYPES = ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"]
DEFAULT_DATA_TYPES = ["Foundation", "SR Legacy"]

# Valid source types for canonical entries
SOURCE_TYPES = ["usda_fdc", "nccdb", "restaurant", "manual"]


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_paths(args) -> tuple[Path, Path]:
    """Return (data_path, canonical_path)."""
    if args.path:
        canonical_path = Path(args.path)
        return canonical_path.parent, canonical_path
    data_path = DEVELOPMENT_DATA_PATH if args.dev else PRODUCTION_DATA_PATH
    return data_path, data_path / CANONICAL_FILENAME


def load_api_key(data_path: Path) -> str:
    """Load FDC API key from file or environment variable."""
    # Environment variable takes priority
    key = os.environ.get("FDC_API_KEY", "").strip()
    if key:
        return key

    key_file = data_path / API_KEY_FILENAME
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key

    print(f"ERROR: FDC API key not found.")
    print(f"  Set environment variable FDC_API_KEY=yourkey")
    print(f"  OR save your key (one line) to: {key_file}")
    print(f"  Get a free key at: https://fdc.nal.usda.gov/api-key-signup")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Canonical file I/O
# ---------------------------------------------------------------------------

def load_canonical(canonical_path: Path) -> list:
    """Load canonical ingredients file, returning list of entries."""
    if not canonical_path.exists():
        return []
    try:
        raw = canonical_path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            print(f"ERROR: {canonical_path} does not contain a list.")
            sys.exit(1)
        return data

    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse {canonical_path}: {e}")
        sys.exit(1)


def save_canonical(canonical_path: Path, entries: list) -> None:
    """Save canonical ingredients list to file."""
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def find_duplicate(entries: list, name: str) -> dict | None:
    """Return existing entry with matching name (case-insensitive), or None."""
    name_lower = name.strip().lower()
    for entry in entries:
        if entry.get("name", "").lower() == name_lower:
            return entry
    return None


# ---------------------------------------------------------------------------
# FDC API calls
# ---------------------------------------------------------------------------

def fdc_get(url: str) -> dict:
    """Perform a GET request to the FDC API and return parsed JSON."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: FDC API returned HTTP {e.code}: {body[:200]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Could not reach FDC API: {e.reason}")
        sys.exit(1)


def search_fdc(query: str, api_key: str, data_types: list, max_results: int = 10) -> list:
    """Search FDC by food name; return list of result dicts."""
    base_params = urllib.parse.urlencode({
        "query": query,
        "api_key": api_key,
        "pageSize": max_results,
    })
    type_params = "&".join(f"dataType={urllib.parse.quote(dt)}" for dt in data_types)
    url = f"{FDC_BASE_URL}/foods/search?{base_params}&{type_params}"
    data = fdc_get(url)
    return data.get("foods", [])


def fetch_fdc_by_id(fdc_id: int, api_key: str) -> dict:
    """Fetch a single food by FDC ID; return the food dict."""
    params = urllib.parse.urlencode({"api_key": api_key})
    url = f"{FDC_BASE_URL}/food/{fdc_id}?{params}"
    return fdc_get(url)


def extract_nutrients(food: dict) -> dict:
    """
    Extract our internal nutrients from an FDC food dict.
    Works for both search results (foodNutrients list) and
    single-food responses.
    """
    # FDC uses two slightly different structures depending on endpoint
    raw_nutrients = food.get("foodNutrients", [])

    # Build lookup: nutrient_id -> amount
    id_to_amount: dict[int, float] = {}
    for n in raw_nutrients:
        # Search results: {"nutrientId": 1003, "value": 25.0, ...}
        # Single food:    {"nutrient": {"id": 1003}, "amount": 25.0, ...}
        nid = n.get("nutrientId") or (n.get("nutrient") or {}).get("id")
        amount = n.get("value") or n.get("amount") or 0.0
        if nid is not None:
            id_to_amount[int(nid)] = float(amount)

    result = {}
    for key, ids in NUTRIENT_MAP.items():
        for nid in ids:
            if nid in id_to_amount:
                result[key] = round(id_to_amount[nid], 3)
                break
        if key not in result:
            result[key] = 0.0

    return result


def build_entry_from_fdc(food: dict, notes: str = "") -> dict:
    """Build a canonical entry dict from an FDC food dict."""
    fdc_id   = food.get("fdcId", "")
    name     = food.get("description", "").strip()
    category = food.get("foodCategory") or food.get("foodCategoryLabel", "")

    return {
        "name"              : name,
        "source_type"       : "usda_fdc",
        "source_id"         : str(fdc_id),
        "source_url"        : f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
        "date_fetched"      : datetime.now().strftime("%Y-%m-%d"),
        "fdc_data_type"     : food.get("dataType", ""),
        "food_category"     : str(category) if category else "",
        "nutrients_per_100g": extract_nutrients(food),
        "notes"             : notes,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_entry(entry: dict, index: int | None = None) -> None:
    """Print a single canonical entry in readable form."""
    prefix = f"[{index}] " if index is not None else ""
    print(f"\n{prefix}{entry.get('name', '(no name)')}")
    print(f"  Source      : {entry.get('source_type', '')} / {entry.get('source_id', '')}")
    print(f"  Date fetched: {entry.get('date_fetched', '')}")
    print(f"  Category    : {entry.get('food_category', '')}")
    n = entry.get("nutrients_per_100g", {})
    print(f"  Nutrients/100g:")
    print(f"    cal={n.get('cal',0):.1f}  prot={n.get('prot_g',0):.1f}g  "
          f"carbs={n.get('carbs_g',0):.1f}g  fat={n.get('fat_g',0):.1f}g  "
          f"sugar={n.get('sugar_g',0):.1f}g")
    print(f"    fiber={n.get('fiber_g',0):.1f}g  sodium={n.get('sodium_mg',0):.0f}mg  "
          f"potassium={n.get('potassium_mg',0):.0f}mg")
    print(f"    vitA={n.get('vitA_mcg',0):.1f}mcg  vitC={n.get('vitC_mg',0):.1f}mg  "
          f"iron={n.get('iron_mg',0):.2f}mg")
    if entry.get("notes"):
        print(f"  Notes       : {entry['notes']}")


def print_search_results(foods: list) -> None:
    """Print FDC search results for user selection."""
    print(f"\nFound {len(foods)} result(s):\n")
    for i, food in enumerate(foods, 1):
        fdc_id    = food.get("fdcId", "?")
        name      = food.get("description", "(no name)")
        data_type = food.get("dataType", "")
        category  = food.get("foodCategory") or food.get("foodCategoryLabel", "")
        print(f"  {i:2}. [{fdc_id}] {name}")
        print(f"        {data_type}  |  {category}")


def prompt_select(foods: list) -> dict | None:
    """Prompt user to select one result from a list; return selected food or None."""
    while True:
        raw = input("\nSelect number to fetch (or 'q' to quit): ").strip()
        if raw.lower() == "q":
            return None
        try:
            idx = int(raw)
            if 1 <= idx <= len(foods):
                return foods[idx - 1]
            print(f"  Enter a number between 1 and {len(foods)}.")
        except ValueError:
            print("  Enter a number or 'q'.")


# ---------------------------------------------------------------------------
# Subcommand: --list
# ---------------------------------------------------------------------------

def cmd_list(canonical_path: Path) -> None:
    entries = load_canonical(canonical_path)
    if not entries:
        print(f"Canonical file is empty or does not exist: {canonical_path}")
        return
    print(f"\nCanonical ingredients ({len(entries)} entries)  [{canonical_path}]\n")
    print(f"  {'#':<4} {'Name':<45} {'Source':<12} {'Date':<12} {'Cal':>6} {'Prot':>6}")
    print("  " + "-" * 90)
    for i, entry in enumerate(entries, 1):
        n    = entry.get("nutrients_per_100g", {})
        name = entry.get("name", "")[:44]
        src  = entry.get("source_type", "")[:11]
        date = entry.get("date_fetched", "")[:10]
        cal  = n.get("cal", 0)
        prot = n.get("prot_g", 0)
        print(f"  {i:<4} {name:<45} {src:<12} {date:<12} {cal:>6.0f} {prot:>5.1f}g")
    print()


# ---------------------------------------------------------------------------
# Subcommand: --fetch (search by name)
# ---------------------------------------------------------------------------

def cmd_fetch(query: str, api_key: str, data_types: list,
              canonical_path: Path, dry_run: bool, notes: str) -> None:
    entries = load_canonical(canonical_path)

    print(f"\nSearching FDC for: '{query}'  (data types: {', '.join(data_types)})")
    foods = search_fdc(query, api_key, data_types)

    if not foods:
        print("No results found. Try different search terms or --data-type Branded.")
        return

    print_search_results(foods)
    selected = prompt_select(foods)
    if selected is None:
        print("Cancelled.")
        return

    # Search results include nutrient data inline -- no secondary fetch needed
    entry = build_entry_from_fdc(selected, notes=notes)
    _finish_and_save(entry, entries, canonical_path, dry_run)


# ---------------------------------------------------------------------------
# Subcommand: --fdc-id (fetch by FDC ID directly)
# ---------------------------------------------------------------------------

def cmd_fdc_id(fdc_id: int, api_key: str,
               canonical_path: Path, dry_run: bool, notes: str) -> None:
    entries = load_canonical(canonical_path)

    print(f"\nFetching FDC ID {fdc_id}...")
    food = fetch_fdc_by_id(fdc_id, api_key)

    entry = build_entry_from_fdc(food, notes=notes)
    _finish_and_save(entry, entries, canonical_path, dry_run)


# ---------------------------------------------------------------------------
# Subcommand: --manual
# ---------------------------------------------------------------------------

def cmd_manual(canonical_path: Path, dry_run: bool) -> None:
    entries = load_canonical(canonical_path)

    print("\n--- Manual entry ---")
    print("Press Ctrl-C to cancel at any time.\n")

    try:
        name = input("Ingredient name: ").strip()
        if not name:
            print("Name is required.")
            return

        print(f"Source type options: {', '.join(SOURCE_TYPES)}")
        source_type = input("Source type [restaurant]: ").strip() or "restaurant"
        if source_type not in SOURCE_TYPES:
            print(f"WARNING: '{source_type}' is not a standard source type.")

        source_id  = input("Source ID or chain name (optional): ").strip()
        source_url = input("Source URL (optional): ").strip()
        notes      = input("Notes (optional): ").strip()

        print("\nNutrients per 100g (press Enter to leave as 0):")
        nutrients: dict[str, float] = {}
        for key in NUTRIENT_MAP:
            raw = input(f"  {key}: ").strip()
            try:
                nutrients[key] = round(float(raw), 3) if raw else 0.0
            except ValueError:
                print(f"  Invalid value for {key}, using 0.")
                nutrients[key] = 0.0

        entry = {
            "name"              : name,
            "source_type"       : source_type,
            "source_id"         : source_id,
            "source_url"        : source_url,
            "date_fetched"      : datetime.now().strftime("%Y-%m-%d"),
            "fdc_data_type"     : "",
            "food_category"     : "",
            "nutrients_per_100g": nutrients,
            "notes"             : notes,
        }

    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    _finish_and_save(entry, entries, canonical_path, dry_run)


# ---------------------------------------------------------------------------
# Shared save logic
# ---------------------------------------------------------------------------

def _finish_and_save(entry: dict, entries: list,
                     canonical_path: Path, dry_run: bool) -> None:
    """Duplicate check, preview, confirm, and save."""
    print_entry(entry)

    # Duplicate check
    existing = find_duplicate(entries, entry["name"])
    if existing:
        print(f"\nWARNING: An entry named '{existing['name']}' already exists "
              f"(fetched {existing.get('date_fetched', 'unknown')}).")
        raw = input("Overwrite? (y/N): ").strip().lower()
        if raw != "y":
            print("Skipped.")
            return
        entries = [e for e in entries if e.get("name", "").lower() != entry["name"].lower()]

    if dry_run:
        print("\nDry run — no changes written.")
        return

    confirm = input("\nAdd to canonical file? (Y/n): ").strip().lower()
    if confirm == "n":
        print("Skipped.")
        return

    entries.append(entry)
    save_canonical(canonical_path, entries)
    print(f"Saved. Canonical file now has {len(entries)} entries.")
    print(f"  {canonical_path}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage meal_plan_canonical_ingredients.json"
    )

    # Path selection
    path_group = parser.add_mutually_exclusive_group()
    path_group.add_argument("--dev",  action="store_true",
                            help="Use development data path")
    path_group.add_argument("--path", type=str,
                            help="Explicit path to canonical JSON file")

    # Subcommands
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--list",   action="store_true",
                              help="List all existing canonical entries")
    action_group.add_argument("--fetch",  type=str, metavar="QUERY",
                              help="Search FDC by food name")
    action_group.add_argument("--fdc-id", type=int, metavar="ID",
                              help="Fetch a specific food by FDC ID")
    action_group.add_argument("--manual", action="store_true",
                              help="Enter a food manually (restaurant/diner items)")

    # Options
    parser.add_argument("--data-type", type=str, default=None,
                        metavar="TYPE",
                        help=f"FDC data type filter for --fetch. "
                             f"Options: {', '.join(VALID_DATA_TYPES)}. "
                             f"Default: Foundation + SR Legacy")
    parser.add_argument("--notes", type=str, default="",
                        help="Optional notes to attach to the entry")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview entry without writing to file")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    data_path, canonical_path = resolve_paths(args)

    if args.list:
        cmd_list(canonical_path)
        return

    # Resolve data types
    if args.data_type:
        data_types = [dt.strip() for dt in args.data_type.split(",")]
        invalid = [dt for dt in data_types if dt not in VALID_DATA_TYPES]
        if invalid:
            print(f"ERROR: Invalid data type(s): {', '.join(invalid)}")
            print(f"Valid options: {', '.join(VALID_DATA_TYPES)}")
            sys.exit(1)
    else:
        data_types = DEFAULT_DATA_TYPES

    if args.fetch:
        api_key = load_api_key(data_path)
        cmd_fetch(args.fetch, api_key, data_types, canonical_path,
                  args.dry_run, args.notes)

    elif args.fdc_id:
        api_key = load_api_key(data_path)
        cmd_fdc_id(args.fdc_id, api_key, canonical_path,
                   args.dry_run, args.notes)

    elif args.manual:
        cmd_manual(canonical_path, args.dry_run)


if __name__ == "__main__":
    main()