#!/usr/bin/env python3
import pandas as pd
import re
import json
import os
from datetime import date
import numpy as np
import shlex
import string

import matplotlib
matplotlib.use("Agg")  # headless backend to save JPEG without a GUI
import matplotlib.pyplot as plt
import webbrowser
from datetime import datetime

MASTER_FILE = "meal_plan_master.csv"
LOG_FILE = "meal_plan_daily_log.csv"
PENDING_FILE = "meal_plan_pending.json"

# session-only stash (for in-memory use)
pending_stack = []
_editing_date = None

# Codes like B.1, S2.4, FR.12, D.11a (legacy X.* still parse, but must exist in MASTER)
# Existing (keep if you still use it elsewhere)
# CODE_RE = re.compile(r"([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)+)", re.IGNORECASE)

# New: codes must start with a letter, then letters/digits, then ".segment" parts
CODE_RE_CODEONLY = re.compile(
    r"([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)",
    re.IGNORECASE
)

# Multipliers: allow '*', 'x', or unicode '×' followed by an arithmetic expression
# Supports numbers with optional leading dot, chained by * or / (e.g., 5.7/4, .5*2/3)
MULT_RE = re.compile(
    r"[*x×]\s*([0-9]*\.?[0-9]+(?:\s*[*/]\s*[0-9]*\.?[0-9]+)*)",
    re.IGNORECASE
)
# Accept @HH or @HH:MM (24h)
TIME_RE = re.compile(r"^@(\d{1,2})(?::(\d{2}))?$")

# ---------- IO ----------

def load_master():
    return pd.read_csv(MASTER_FILE)

def ensure_log():
    try:
        log = pd.read_csv(LOG_FILE)
        # Ensure sugar_g exists for back-compat logs
        if "sugar_g" not in [str(c).lower() for c in log.columns]:
            log["sugar_g"] = 0
        # Ensure gl exists too
        if "gl" not in [str(c).lower() for c in log.columns]:
            log["gl"] = 0
    except Exception:
        log = pd.DataFrame(columns=["date","codes","cal","prot_g","carbs_g","fat_g","sugar_g","gl"])
    return log

def save_log(log):
    log.to_csv(LOG_FILE, index=False)

# ---------- Pending JSON (robust loader) ----------

def split_top_level(s: str):
    """Split by commas not inside parentheses."""
    parts, buf, depth = [], [], 0
    for ch in s:
        if ch == '(':
            depth += 1; buf.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1); buf.append(ch)
        elif ch == ',' and depth == 0:
            part = ''.join(buf).strip()
            if part: parts.append(part)
            buf = []
        else:
            buf.append(ch)
    tail = ''.join(buf).strip()
    if tail: parts.append(tail)
    return parts

def parse_selection_to_items(selection):
    """
    Accepts:
      - 'B.1 *1.5, S2.4, L.3x2'
      - '(FR.1, FR.2) *.5, B.1'
      - 'D.10-VE.T1', 'D.10 - VE.T1*.5'
      - '@11', '@11:30'
      - list like ['B.1','S2.4','@11']
    Returns list of dicts:
      - code rows: {"code": "B.1", "mult": 1.5}
      - time rows: {"time": "HH:MM"}
    """
    items = []
    if isinstance(selection, list):
        chunks = [str(c) for c in selection]
    else:
        s = str(selection).strip()
        chunks = split_top_level(s)

    for chunk in chunks:
        c = chunk.strip()
        if not c:
            continue

        # time token alone (e.g., @11 or @11:30)
        m_time = TIME_RE.match(c)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2)) if m_time.group(2) else 0
            items.append({"time": _norm_time(h, m)})
            continue

        # GROUP form: ( ... ) *<mult?>  (also accepts x / ×)
        if c.startswith("(") and ")" in c:
            close = c.rfind(")")
            inside = c[1:close]
            after = c[close+1:]  # where multiplier may live

            # find all codes inside the parentheses (avoid numbers like 0.5 being treated as a code)
            codes = [m.upper().strip() for m in CODE_RE_CODEONLY.findall(inside)]


            # multiplier on the group (default 1.0)
            m_mult = MULT_RE.search(after)
            if m_mult:
                mult_str = m_mult.group(1)
                if mult_str.startswith("."):
                    mult_str = "0" + mult_str
                gmult = _eval_mult_expr(mult_str)
            else:
                gmult = 1.0

            for code in codes:
                items.append({"code": code, "mult": gmult})
            continue

        # hyphen-separated subtractions within this chunk (ignore time on right)
        if "-" in c:
            parts_minus = [p.strip() for p in c.split("-")]
            # first part is positive (can be code or time, but treat time as separate)
            first_time = TIME_RE.match(parts_minus[0])
            if first_time:
                h = int(first_time.group(1))
                m = int(first_time.group(2)) if first_time.group(2) else 0
                items.append({"time": _norm_time(h, m)})
            else:
                first = _parse_one_code_mult(parts_minus[0])
                if first:
                    items.append(first)

            # subsequent parts are negative (codes only)
            for sub in parts_minus[1:]:
                if TIME_RE.match(sub):
                    # a time token after '-' doesn't make semantic sense; ignore cleanly
                    continue
                one = _parse_one_code_mult(sub)
                if one:
                    one["mult"] = -abs(float(one.get("mult", 1.0)))
                    items.append(one)
            continue

        # SINGLE item (code or time)
        m_time = TIME_RE.match(c)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2)) if m_time.group(2) else 0
            items.append({"time": _norm_time(h, m)})
            continue

        one = _parse_one_code_mult(c)
        if one:
            items.append(one)

    return items

def _fmt_x(val) -> str:
    """
    Format the quantity for the report's 'x' column to width 4:
    - Right-justify
    - Trim trailing zeros and trailing decimal
    - Try 0–3 decimals, rounding as needed to fit
    """
    try:
        import numpy as np
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "    "
        for dp in (0, 1, 2, 3):
            s = f"{float(val):.{dp}f}".rstrip("0").rstrip(".")
            if len(s) <= 4:
                return s.rjust(4)
        s = f"{int(round(float(val)))}"
        return (s[-4:]).rjust(4)
    except Exception:
        return "    "

def _continuous_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a daily date index from min..max dates.
    Keeps numeric cols; missing days become NaN (so prints/plots break at gaps).
    Returns a DataFrame indexed by daily DatetimeIndex.
    """
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    full_idx = pd.date_range(df["date"].iloc[0], df["date"].iloc[-1], freq="D")
    df = df.set_index("date").reindex(full_idx)

    for c in ["cal","prot_g","carbs_g","fat_g","sugar_g","gl"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

def _norm_time(h: int, m: int = 0) -> str:
    """Clamp/validate and return zero-padded HH:MM."""
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Invalid time")
    return f"{h:02d}:{m:02d}"

def _parse_one_code_mult(snippet: str):
    """
    Parse a single code + optional multiplier from snippet like:
      'D.10', 'VE.T1*.5', 'B.1 x2', 'S2.4 × .5'
    Returns None for pure time tokens.
    """
    if TIME_RE.match(snippet.strip()):
        return None
    m_code = CODE_RE_CODEONLY.search(snippet)  # was CODE_RE.search(...)
    if not m_code:
        return None
    code = m_code.group(1).upper()
    m_mult = MULT_RE.search(snippet)
    if m_mult:
        mult_str = m_mult.group(1)
        if mult_str.startswith("."):
            mult_str = "0" + mult_str
        mult = _eval_mult_expr(mult_str)
    else:
        mult = 1.0
    return {"code": code, "mult": mult}

def ensure_pending_shape(p):
    """
    Normalize to:
      {"date":"YYYY-MM-DD","items":[{"code":..,"mult":..} | {"time":"HH:MM"}, ...]}
    - Preserves and validates time-only items.
    - Keeps order.
    """
    if p is None:
        return None

    # unwrap {"pending": {...}} legacy shape
    if isinstance(p, dict) and "pending" in p and isinstance(p["pending"], dict):
        p = p["pending"]

    def _norm_item(it):
        """Return a normalized item dict or a list of items if 'it' is a string to parse."""
        # time-only dict: {"time": "HH:MM" | "H" | "H:MM"}
        if isinstance(it, dict) and "time" in it:
            t = str(it.get("time", "")).strip()
            m = TIME_RE.match(t if t.startswith("@") else "@"+t)
            if m:
                h = int(m.group(1))
                mm = int(m.group(2)) if m.group(2) else 0
                try:
                    return {"time": _norm_time(h, mm)}
                except ValueError:
                    return None  # invalid time, drop
            return None  # not a valid time
        # code dict: {"code": "...", "mult": float?}

        if isinstance(it, dict) and "code" in it:
            raw_mult = it.get("mult", 1.0)
            mult = float(raw_mult) if isinstance(raw_mult, (int, float)) else _eval_mult_expr(str(raw_mult))
            return {"code": str(it["code"]).upper(), "mult": mult}
        # string: could be codes and/or @time; let the parser handle it (returns list)
        if isinstance(it, str):
            return parse_selection_to_items(it)
        # unknown → drop
        return None

    # List top-level: treat as list of items/strings
    if isinstance(p, list):
        norm_items = []
        for it in p:
            ni = _norm_item(it)
            if ni is None:
                continue
            if isinstance(ni, list):
                norm_items.extend(ni)
            else:
                norm_items.append(ni)
        return {"date": str(date.today()), "items": norm_items}

    # Non-dict → not salvageable
    if not isinstance(p, dict):
        return None

    # Dict shape
    out = {}
    out["date"] = str(p.get("date") or p.get("day") or p.get("when") or date.today())

    if "items" in p and isinstance(p["items"], list):
        norm_items = []
        for it in p["items"]:
            # 1) Keep code dicts
            if isinstance(it, dict) and "code" in it:
                mult = float(it.get("mult", 1.0))
                norm_items.append({"code": str(it["code"]).upper(), "mult": mult})
                continue

            # 2) Keep known non-code dicts (e.g., time markers) untouched
            if isinstance(it, dict) and "time" in it:
                # normalize time string a bit (trim spaces)
                t = str(it.get("time", "")).strip()
                if t:
                    norm_items.append({"time": t})
                continue

            # 3) Only strings (or lists) are parsed into code items
            if isinstance(it, str):
                norm_items.extend(parse_selection_to_items(it))
            elif isinstance(it, list):
                norm_items.extend(parse_selection_to_items(it))
            # else: ignore unknown shapes silently (or log if you want)

        out["items"] = norm_items
    else:
        # legacy keys: 'codes', 'selection', 'entries'
        for k in ("codes", "selection", "entries"):
            if k in p and p[k]:
                out["items"] = parse_selection_to_items(p[k])
                break
        else:
            out["items"] = []

    return out

def load_pending():
    if not os.path.exists(PENDING_FILE): return None
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return ensure_pending_shape(raw)
    except Exception:
        return None

def save_pending(pending_obj):
    norm = ensure_pending_shape(pending_obj) or {"date": str(date.today()), "items": []}
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(norm, f, indent=2, ensure_ascii=False)

def clear_pending():
    if os.path.exists(PENDING_FILE):
        os.remove(PENDING_FILE)

# ---------- Item list editing utilities ----------

def print_items(pending, master):
    """Show the current pending items with 1-based indices (includes time rows)."""
    if not pending or not pending.get("items"):
        print("(no items)")
        return
    items = pending["items"]
    code_col = _col(master, "code") or "code"
    opt_col  = _col(master, "option") or "option"
    sect_col = _col(master, "section") or "section"

    print(f"{'#':>3}  {'Code':>10}  {'x':>5}  {'Section':<8}  {'Option / Time'}")
    print("-"*78)
    for i, it in enumerate(items, 1):
        if "time" in it and it.get("time"):
            print(f"{i:>3}  {'@'+it['time']:>10}  {'':>5}  {'':<8}  time marker")
            continue

        code = it.get("code","").upper()
        mult = float(it.get("mult",1.0))
        mrow = master[master[code_col].str.upper() == code]
        if not mrow.empty:
            row = mrow.iloc[0]
            section = str(row[sect_col])[:8]
            option  = str(row[opt_col])
        else:
            section = ""
            option  = ""
        print(f"{i:>3}  {code:>10}  {mult:>5g}  {section:<8}  {option}")
    print()

def parse_index_args(arg: str, n: int):
    """
    Parse things like '3', '2,4,7', '3-6' into a sorted list of 0-based indexes within [0, n).
    """
    idxs = set()
    for part in arg.split(","):
        part = part.strip()
        if not part: continue
        if "-" in part:
            a,b = part.split("-",1)
            try:
                a = int(a); b = int(b)
                for i in range(min(a,b), max(a,b)+1):
                    if 1 <= i <= n: idxs.add(i-1)
            except: pass
        else:
            try:
                i = int(part)
                if 1 <= i <= n: idxs.add(i-1)
            except:
                pass
    return sorted(idxs)

def load_log_into_pending(query_date, master, log):
    """
    Build a pending object from a log date (first matching row).
    """
    dc = _date_col(log); cc = _codes_col(log)
    day = log[log[dc].astype(str) == query_date]
    if day.empty:
        return None
    codes = str(day.iloc[0][cc])
    items = parse_selection_to_items(codes)
    return {"date": query_date, "items": items}

def pending_to_codestr(pending, master):
    parts = []
    for it in pending.get("items", []):
        if isinstance(it, dict) and "time" in it:
            t = str(it["time"]).strip()
            if t:
                parts.append(f"@{t}")
            continue
        if isinstance(it, dict) and "code" in it:
            code = str(it["code"]).upper()
            mult = float(it.get("mult", 1.0))
            if mult < 0:
                amag = abs(mult)
                parts.append(f"-{code}" if abs(amag-1.0) < 1e-9 else f"-{code} x{amag:g}")
            else:
                parts.append(f"{code} x{mult:g}" if abs(mult-1.0) > 1e-9 else code)
    return ", ".join(parts)

# ---------- Search / Lookup ----------

def search_master(term, master):
    term_ci = term.strip().lower()
    if master.empty: return master
    tmp = master.assign(_code=master['code'].astype(str),
                        _opt=master['option'].astype(str))
    mask = tmp.apply(lambda r: (term_ci in r['_code'].lower()) or (term_ci in r['_opt'].lower()), axis=1)
    return master[mask]

def _col(df, name):
    """Return actual column name matching `name` case-insensitively, or None."""
    name_l = name.lower()
    for c in df.columns:
        if str(c).lower() == name_l:
            return c
    return None

def _sugar_col(df):
    """Return the sugar column name (case-insensitive) among common variants, or None."""
    return (
        _col(df, "sugar_g") or
        _col(df, "sugars_g") or
        _col(df, "sugar") or
        _col(df, "sugars")
    )

def format_rows_for_print(df):
    if df is None or df.empty:
        return "(no matches)"

    # core columns (case-insensitive)
    code_col   = _col(df, "code")   or "code"
    sect_col   = _col(df, "section") or "section"
    opt_col    = _col(df, "option")  or "option"
    cal_col    = _col(df, "cal")     or "cal"
    prot_col   = _col(df, "prot_g")  or "prot_g"
    carb_col   = _col(df, "carbs_g") or "carbs_g"
    fat_col    = _col(df, "fat_g")   or "fat_g"
    gi_col     = _col(df, "GI")
    gl_col     = _col(df, "GL")
    sug_col    = _sugar_col(df)

    lines = []
    for _, r in df.iterrows():
        gi_str = f" GI={r[gi_col]}" if gi_col and pd.notna(r[gi_col]) else ""
        gl_str = f" GL={r[gl_col]}" if gl_col and pd.notna(r[gl_col]) else ""
        su_str = f" Sugars={r[sug_col]}" if sug_col and pd.notna(r[sug_col]) else ""
        lines.append(
            f"{str(r[code_col]):>8} | {str(r[sect_col]):<7} | {str(r[opt_col])}  "
            f"[cal={r[cal_col]} P={r[prot_col]} C={r[carb_col]} F={r[fat_col]}{gi_str}{gl_str}{su_str}]"
        )
    return "\n".join(lines)

def lookup_code_row(code, master):
    match = master[master['code'].str.upper() == code]
    if match.empty: return None
    return match.iloc[0].to_dict()

# ---------- Totals ----------

def recompute_totals_from_codes(codes_str, master):
    items = parse_selection_to_items(codes_str)
    totals, missing, _ = accumulate_from_items(items, master)
    return totals, missing

def accumulate_from_items(items, master):
    # Resolve column names (case-insensitive)
    cal_col   = _col(master, "cal")      or "cal"
    prot_col  = _col(master, "prot_g")   or "prot_g"
    carb_col  = _col(master, "carbs_g")  or "carbs_g"
    fat_col   = _col(master, "fat_g")    or "fat_g"
    sugar_col = _sugar_col(master)       # may be None
    gl_col    = _col(master, "GL")       # may be None

    totals = {"cal":0.0, "prot_g":0.0, "carbs_g":0.0, "fat_g":0.0, "sugar_g":0.0, "gl":0.0}
    missing, code_strs = [], []

    for it in items:
        # time-only item
        if "time" in it and it.get("time"):
            code_strs.append(f"@{it['time']}")
            continue
        # Skip non-code items (e.g., {"time": "11:00"})
        if not isinstance(it, dict) or "code" not in it:
            continue
        code = str(it["code"]).upper()
        mult = float(it.get("mult", 1.0))
        row = lookup_code_row(code, master)
        if row is None:
            missing.append(code); continue

        totals["cal"]      += float(row[cal_col])     * mult
        totals["prot_g"]   += float(row[prot_col])    * mult
        totals["carbs_g"]  += float(row[carb_col])    * mult
        totals["fat_g"]    += float(row[fat_col])     * mult
        if sugar_col and sugar_col in row and row[sugar_col] == row[sugar_col]:
            totals["sugar_g"] += float(row[sugar_col]) * mult
        if gl_col and gl_col in row and row[gl_col] == row[gl_col]:
            totals["gl"] += float(row[gl_col]) * mult

        # pretty code string with sign handling
        if mult < 0:
            amag = abs(mult)
            code_strs.append(f"-{code}" if abs(amag-1.0) < 1e-9 else f"-{code} x{amag:g}")
        else:
            code_strs.append(f"{code} x{mult:g}" if abs(mult-1.0) > 1e-9 else code)

    return totals, missing, code_strs

def show_pending(pending, master):
    if not pending:
        print("\n(No active day. Use 'start' to begin.)\n")
        return None
    items = pending.get("items", [])
    totals, missing, code_strs = accumulate_from_items(items, master)
    safe_int = lambda v: int(round(v))
    print("\n--- Current Day ---")
    print("Date:", pending.get("date"))
    print("Codes:", ", ".join(code_strs) if code_strs else "(none)")
    print(f"Calories: {safe_int(totals['cal'])}")
    print(f"Protein:  {safe_int(totals['prot_g'])} g")
    print(f"Carbs:    {safe_int(totals['carbs_g'])} g")
    print(f"Fat:      {safe_int(totals['fat_g'])} g")
    print(f"Sugars:   {safe_int(totals['sugar_g'])} g")
    if missing:
        print("Missing codes (not included):", ", ".join(missing))
    print("--------------------\n")
    return totals, missing, code_strs

# ---------- Report feature ----------

def _resolved_cols(master):
    """Case-insensitive resolve for nutrient cols; return canonical names used below."""
    return {
        "code":   _col(master, "code")    or "code",
        "option": _col(master, "option")  or "option",
        "sect":   _col(master, "section") or "section",
        "cal":    _col(master, "cal")     or "cal",
        "prot":   _col(master, "prot_g")  or "prot_g",
        "carb":   _col(master, "carbs_g") or "carbs_g",
        "fat":    _col(master, "fat_g")   or "fat_g",
        "sugar":  _sugar_col(master),     # may be None
        "gl":     _col(master, "GL"),     # may be None
    }

def _safe_float(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except Exception:
        return default

def _eval_mult_expr(expr: str) -> float:
    """
    Evaluate a very small safe subset: NUM (( '*' | '/' ) NUM)*
    Left-to-right. Each NUM may be like '5', '5.7', '.5', '0.25'
    Whitespace is allowed. No parentheses or +/− supported.
    """
    if not expr:
        return 1.0
    s = expr.strip()
    # Split into numbers and operators
    nums = re.split(r"[*/]", s)
    ops  = re.findall(r"[*/]", s)
    try:
        def _to_float(x: str) -> float:
            x = x.strip()
            if x.startswith("."):
                x = "0" + x
            return float(x)
        val = _to_float(nums[0])
        for op, raw in zip(ops, nums[1:]):
            rhs = _to_float(raw)
            if op == "*":
                val *= rhs
            else:
                # Avoid ZeroDivisionError; treat as 0 contribution if /0 entered
                val = val / rhs if rhs != 0 else 0.0
        return val
    except Exception:
        # Fallback: don’t crash on weird input; behave as 1.0 multiplier
        return 1.0

def _lookup_master_row(code, master, cols):
    """Case-insensitive code lookup; returns pandas Series or None."""
    m = master[master[cols["code"]].str.upper() == code]
    if m.empty:
        return None
    return m.iloc[0]

def build_report_from_items(items, master):
    """
    items: list of {"code":..., "mult":...} and/or {"time":"HH:MM"}
    Returns: (rows, totals, missing, display)
      rows: nutrient rows for code items
      totals: summed nutrients
      missing: missing code list
      display: list of ("time","HH:MM") or ("row", row_index) preserving original order
    """
    cols = _resolved_cols(master)
    totals = {"cal":0.0, "prot_g":0.0, "carbs_g":0.0, "fat_g":0.0, "sugar_g":0.0, "gl":0.0}
    rows, missing, display = [], [], []

    for it in items:
        # Show time markers in the report without affecting totals
        if isinstance(it, dict) and "time" in it:
            display.append(("time", str(it["time"]).strip()))
            continue

        if not isinstance(it, dict) or "code" not in it:
            continue
        code = str(it["code"]).upper()
        mult = float(it.get("mult", 1.0))
        row = _lookup_master_row(code, master, cols)
        if row is None:
            missing.append(code)
            continue

        cal   = _safe_float(row[cols["cal"]])   * mult
        prot  = _safe_float(row[cols["prot"]])  * mult
        carb  = _safe_float(row[cols["carb"]])  * mult
        fat   = _safe_float(row[cols["fat"]])   * mult
        sugar = _safe_float(row[cols["sugar"]]) * mult if cols["sugar"] else 0.0
        gl    = _safe_float(row[cols["gl"]])    * mult if cols["gl"]    else 0.0

        totals["cal"]     += cal
        totals["prot_g"]  += prot
        totals["carbs_g"] += carb
        totals["fat_g"]   += fat
        totals["sugar_g"] += sugar
        totals["gl"]      += gl

        idx = len(rows)
        rows.append({
            "code": code,
            "option": str(row[cols["option"]]),
            "section": str(row[cols["sect"]]),
            "mult": mult,
            "cal": cal, "prot_g": prot, "carbs_g": carb, "fat_g": fat,
            "sugar_g": sugar, "gl": gl,
        })
        display.append(("row", idx))

    return rows, totals, missing, display

def print_report(rows, totals, title="Report", missing=None, display=None):
    """Tabular breakdown + totals. Interleaves time markers if display is provided."""

    # local helper: format multiplier to ≤ 4 chars, right-aligned
    def _fmt_mult4(v):
        if v in ("", None):
            return ""
        try:
            x = float(v)
        except Exception:
            return ""
        s = f"{x:.2f}".rstrip("0").rstrip(".")  # e.g., 1.00->1, 1.20->1.2, 1.23->1.23
        if len(s) > 4:
            # fallback trims; keep sign if present
            if s[0] == "-":
                s = "-" + s[1:4]
            else:
                s = s[:4]
        return s

    print(f"\n=== {title} ===")
    if (not rows) and (not display):
        print("(no items)")
    else:
        print(f"{'CODE':>8}  {'Section':<8}  {'x':>4}  {'Option':<21}  "
              f"{'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
        print("-"*78)

        if display is None:
            # Iterate actual rows; time markers may be embedded in rows with _kind='time'
            for r in rows:
                if r.get("_kind") == "time":
                    print(f"{'':>8}  {'':<8}  {'':>4}  {'time: '+str(r.get('time','')):<21}  "
                          f"{'':>6} {'':>5} {'':>5} {'':>5} {'':>6} {'':>4}")
                    continue

                sect = r['section'][:8]
                opt  = str(r['option'])
                opt_display = (opt[:20] + "+") if len(opt) > 20 else opt
                mult_disp = _fmt_mult4(r.get('mult', ''))
                print(f"{r['code']:>8}  {sect:<8}  {mult_disp:>4}  {opt_display:<21}  "
                      f"{int(round(r['cal'])):>6} {int(round(r['prot_g'])):>5} "
                      f"{int(round(r['carbs_g'])):>5} {int(round(r['fat_g'])):>5} "
                      f"{int(round(r['sugar_g'])):>6} {int(round(r.get('gl',0))):>4}")
        else:
            # Follow the provided display order (which may reference row indices)
            for kind, val in display:
                if kind == "time":
                    print(f"{'':>8}  {'':<8}  {'':>4}  {'time: '+str(val):<21}  "
                          f"{'':>6} {'':>5} {'':>5} {'':>5} {'':>6} {'':>4}")
                else:
                    r = rows[val]
                    sect = r['section'][:8]
                    opt  = str(r['option'])
                    opt_display = (opt[:20] + "+") if len(opt) > 20 else opt
                    mult_disp = _fmt_mult4(r.get('mult', ''))
                    print(f"{r['code']:>8}  {sect:<8}  {mult_disp:>4}  {opt_display:<21}  "
                          f"{int(round(r['cal'])):>6} {int(round(r['prot_g'])):>5} "
                          f"{int(round(r['carbs_g'])):>5} {int(round(r['fat_g'])):>5} "
                          f"{int(round(r['sugar_g'])):>6} {int(round(r.get('gl',0))):>4}")
        print("-"*78)

    print(f"Totals →  Cal: {int(round(totals['cal']))} | "
          f"P: {int(round(totals['prot_g']))} g | "
          f"C: {int(round(totals['carbs_g']))} g | "
          f"F: {int(round(totals['fat_g']))} g | "
          f"Sugars: {int(round(totals['sugar_g']))} g | "
          f"GL: {int(round(totals.get('gl',0)))}")
    if missing:
        print("Missing (not counted):", ", ".join(missing))
    print()

def _date_col(df):
    return next((c for c in df.columns if str(c).lower()=="date"), "date")

def _codes_col(df):
    return next((c for c in df.columns if str(c).lower()=="codes"), "codes")

def _as_int(v):
    try:
        return int(round(float(v)))
    except Exception:
        return 0

def build_today_row_from_pending(pending, master):
    if not pending or not pending.get("items"):
        return None
    totals, _, code_strs = accumulate_from_items(pending["items"], master)
    safe_int = lambda v: int(round(v))
    return pd.DataFrame([{
        "date": pending.get("date", str(date.today())),
        "codes": ", ".join(code_strs),
        "cal": safe_int(totals["cal"]),
        "prot_g": safe_int(totals["prot_g"]),
        "carbs_g": safe_int(totals["carbs_g"]),
        "fat_g": safe_int(totals["fat_g"]),
        "sugar_g": safe_int(totals["sugar_g"]),
        "gl": safe_int(totals.get("gl", 0)),
    }])

def filter_log_by_dates(log, start_date=None, end_date=None):
    """Filter inclusive by YYYY-MM-DD strings (lexicographic works for ISO dates)."""
    if log.empty:
        return log
    dc = _date_col(log)
    s = str(start_date) if start_date else None
    e = str(end_date) if end_date else None
    if s:
        log = log[log[dc].astype(str) >= s]
    if e:
        log = log[log[dc].astype(str) <= e]
    return log

def ensure_gl_column_from_codes(df, master, force=False):
    """
    Ensure df has a numeric 'gl' column.
    If missing OR (all zeros/NaN in the filtered view) OR force=True,
    compute GL per row from its 'codes' string using master.
    """
    lower = {str(c).lower(): c for c in df.columns}
    codes_col = lower.get("codes", None)

    # Normalize an existing GL column to 'gl'
    gl_col = lower.get("gl", None)
    if gl_col and gl_col != "gl":
        df = df.rename(columns={gl_col: "gl"})

    has_gl = "gl" in df.columns
    if has_gl:
        df["gl"] = pd.to_numeric(df["gl"], errors="coerce").fillna(0)

    # Decide whether to recompute
    need_recompute = force or (not has_gl)
    if not need_recompute and len(df) > 0:
        # if all zeros (or NaN coerced to 0), recompute
        if (df["gl"].abs().sum() == 0):
            need_recompute = True

    if not need_recompute:
        return df

    # Recompute only if we have codes
    if not codes_col:
        if "gl" not in df.columns:
            df["gl"] = 0
        return df

    gl_vals = []
    for _, r in df.iterrows():
        codestr = str(r[codes_col]) if pd.notna(r[codes_col]) else ""
        if not codestr.strip():
            gl_vals.append(0); continue
        totals, _missing = recompute_totals_from_codes(codestr, master)
        gl_vals.append(int(round(totals.get("gl", 0))))
    df["gl"] = gl_vals
    return df

def print_summary_table(df, title="Summary"):
    """Print a date-by-date summary table (+ totals and daily avg)."""
    if df is None or df.empty:
        print("\n(no rows)\n"); return

    # Ensure numeric
    for col in ["cal","prot_g","carbs_g","fat_g","sugar_g","gl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Sort by date ascending
    dc = _date_col(df)
    df = df.sort_values(by=dc).reset_index(drop=True)

    # Header
    print(f"\n=== {title} ===")
    print(f"{'Date':<10}  {'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
    print("-"*53)

    # Rows
    for _, r in df.iterrows():
        print(f"{str(r[dc])[:10]:<10}  "
              f"{_as_int(r['cal']):>6} {_as_int(r['prot_g']):>5} {_as_int(r['carbs_g']):>5} "
              f"{_as_int(r['fat_g']):>5} {_as_int(r['sugar_g']):>6} {_as_int(r.get('gl',0)):>4}")

    # Totals & Averages
    total_days = len(df)
    tcal = int(df["cal"].sum());    acal = int(round(df["cal"].mean()))     if total_days else 0
    tprot= int(df["prot_g"].sum()); aprot= int(round(df["prot_g"].mean()))  if total_days else 0
    tcarb= int(df["carbs_g"].sum());acarb= int(round(df["carbs_g"].mean())) if total_days else 0
    tfat = int(df["fat_g"].sum());  afat = int(round(df["fat_g"].mean()))   if total_days else 0
    tsug = int(df["sugar_g"].sum());asug = int(round(df["sugar_g"].mean())) if total_days else 0
    tgl  = int(df.get("gl", pd.Series([0]*total_days)).sum())
    agl  = int(round(df.get("gl", pd.Series([0]*total_days)).mean())) if total_days else 0

    print("-"*53)
    print(f"{'TOTALS':<10}  {tcal:>6} {tprot:>5} {tcarb:>5} {tfat:>5} {tsug:>6} {tgl:>4}")
    print(f"{'DAILY AVG':<10}  {acal:>6} {aprot:>5} {acarb:>5} {afat:>5} {asug:>6} {agl:>4}\n")

def print_summary_table_with_gaps(view: pd.DataFrame, title="Summary"):
    """
    Print a date-by-date summary table over a continuous calendar.
    Missing dates show as '---'. Totals/averages use ONLY real (non-missing) days.
    """
    if view is None or view.empty:
        print("\n(no rows)\n"); return

    # Normalize names/types, keep only needed columns
    view = _normalize_summary_df(view)  # has ['date','cal','prot_g','carbs_g','fat_g','sugar_g','gl']

    # Keep a copy for totals/averages (only actual rows)
    valid = view.copy()

    # Expand to continuous calendar with NaNs on gaps
    full = _continuous_calendar(view)
    if full.empty:
        print("\n(no rows)\n"); return

    # Header
    print(f"\n=== {title} ===")
    print(f"{'Date':<10}  {'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
    print("-"*53)

    # Row printing over full calendar (gaps become NaN -> show '---')
    for d, r in full.iterrows():
        day = d.strftime("%Y-%m-%d")
        if pd.isna(r["cal"]):
            # gap row
            print(f"{day:<10}  {'---':>6} {'---':>5} {'---':>5} {'---':>5} {'---':>6} {'---':>4}")
        else:
            print(f"{day:<10}  "
                  f"{_as_int(r['cal']):>6} {_as_int(r['prot_g']):>5} {_as_int(r['carbs_g']):>5} "
                  f"{_as_int(r['fat_g']):>5} {_as_int(r['sugar_g']):>6} {_as_int(r.get('gl',0)):>4}")

    # Totals & Averages computed ONLY on valid (real) rows
    total_days = len(valid)
    tcal = int(valid["cal"].sum());     acal = int(round(valid["cal"].mean()))      if total_days else 0
    tprot= int(valid["prot_g"].sum());  aprot= int(round(valid["prot_g"].mean()))   if total_days else 0
    tcarb= int(valid["carbs_g"].sum()); acarb= int(round(valid["carbs_g"].mean()))  if total_days else 0
    tfat = int(valid["fat_g"].sum());   afat = int(round(valid["fat_g"].mean()))    if total_days else 0
    tsug = int(valid["sugar_g"].sum()); asug = int(round(valid["sugar_g"].mean()))  if total_days else 0
    tgl  = int(valid["gl"].sum());      agl  = int(round(valid["gl"].mean()))       if total_days else 0

    print("-"*53)
    print(f"{'TOTALS':<10}  {tcal:>6} {tprot:>5} {tcarb:>5} {tfat:>5} {tsug:>6} {tgl:>4}")
    print(f"{'DAILY AVG':<10}  {acal:>6} {aprot:>5} {acarb:>5} {afat:>5} {asug:>6} {agl:>4}\n")

def _normalize_summary_df(view: pd.DataFrame) -> pd.DataFrame:
    """Ensure required cols exist, numeric types, sorted by date asc."""
    keep_cols = ["date","cal","prot_g","carbs_g","fat_g","sugar_g","gl"]
    present_lower = {str(c).lower(): c for c in view.columns}

    colmap = {}
    for want in keep_cols:
        if want in view.columns: continue
        if want in present_lower:
            colmap[present_lower[want]] = want
    if colmap:
        view = view.rename(columns=colmap)

    for c in keep_cols:
        if c not in view.columns:
            view[c] = 0

    for c in ["cal","prot_g","carbs_g","fat_g","sugar_g","gl"]:
        view[c] = pd.to_numeric(view[c], errors="coerce").fillna(0)

    view["date"] = pd.to_datetime(view["date"], errors="coerce")
    view = view.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return view[keep_cols]

def make_trend_chart(df: pd.DataFrame, window: int, outfile: str = "meal_plan_trend.jpg"):
    """
    df: columns date, cal, prot_g, carbs_g, fat_g, sugar_g, gl (may have missing dates)
    window: MA window (>=1). MA averages over available points inside the last N calendar days,
            but is only drawn where a daily value exists (so it breaks across gaps).
    """
    if df.empty:
        print("(no rows to chart)")
        return

    import numpy as np

    # ---- Normalize & calendarize ----
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    full_idx = pd.date_range(start=df["date"].min(), end=df["date"].max(), freq="D")

    plot_cols = ["cal","prot_g","carbs_g","fat_g","sugar_g","gl"]
    for c in plot_cols:
        if c not in df.columns:
            df[c] = np.nan
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    caldf = df.set_index("date")[plot_cols].reindex(full_idx)

    # Rolling mean across calendar (ignores NaNs)
    roll = caldf.rolling(window=window, min_periods=1).mean()

    def _plot_with_gaps(ax, dates, values, *, color, linestyle="-", linewidth=1.5,
                        label=None, singleton_label=None, singleton_marker="+", markersize=8):
        dates = np.asarray(dates)
        y = np.asarray(values, dtype=float)

        valid = ~np.isnan(y)
        if not valid.any():
            return

        idxs = np.where(valid)[0]
        # split contiguous runs; calendar is daily so gap = jump > 1 day
        splits = np.where(np.diff(idxs) > 1)[0] + 1
        segments = np.split(idxs, splits)

        used_line_label = False
        used_single_label = False
        for seg in segments:
            if len(seg) == 1:
                i = seg[0]
                ax.plot([dates[i]], [y[i]],
                        marker=singleton_marker, color=color, markersize=markersize, linewidth=0,
                        label=(singleton_label if (singleton_label and not used_single_label and not used_line_label) else None))
                if singleton_label and not used_single_label and not used_line_label:
                    used_single_label = True
            else:
                ax.plot(dates[seg], y[seg],
                        color=color, linestyle=linestyle, linewidth=linewidth,
                        label=(label if not used_line_label else None))
                if label and not used_line_label:
                    used_line_label = True

    # ---- Plot ----
    fig, axes = plt.subplots(6, 1, figsize=(10, 14), sharex=True, constrained_layout=True)
    metrics = [
        ("cal",      "Calories"),
        ("prot_g",   "Protein (g)"),
        ("carbs_g",  "Carbs (g)"),
        ("fat_g",    "Fat (g)"),
        ("sugar_g",  "Sugars (g)"),
        ("gl",       "GL"),
    ]

    dates = caldf.index.values

    for ax, (col, label) in zip(axes, metrics):
        y_daily = caldf[col].values.astype(float)
        y_ma    = roll[col].values.astype(float)

        # **Key**: mask MA wherever there is no daily data so the MA line breaks too
        y_ma_masked = np.where(np.isnan(y_daily), np.nan, y_ma)

        # Daily: solid black; singleton '+'
        _plot_with_gaps(
            ax, dates, y_daily,
            color="black", linestyle="-", linewidth=1.5,
            label="Daily", singleton_label="Daily (+1)", singleton_marker="+", markersize=8
        )

        # MA: dashed red; singleton 'x'
        _plot_with_gaps(
            ax, dates, y_ma_masked,
            color="red", linestyle="--", linewidth=2.0,
            label=f"MA({window})", singleton_label=f"MA({window}) (×1)", singleton_marker="x", markersize=8
        )

        ax.set_ylabel(label)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", frameon=False)

    axes[-1].set_xlabel("Date")
    fig.suptitle(f"Daily Totals + Moving Average ({window} days) — gaps broken; singletons marked ('+' daily, 'x' MA)", fontsize=14)

    fig.savefig(outfile, dpi=150, format="jpg")
    plt.close(fig)
    webbrowser.open(os.path.abspath(outfile))
    print(f"Saved chart to {outfile} and opened in your default viewer.")

# >>> NEW: helpers to expand log rows by CSV order into an items list

def expand_logged_items_in_csv_order(query_date: str, log: pd.DataFrame) -> list:
    """
    Return a flat list of parsed items for a given date by traversing the CSV rows
    in their original order and concatenating each row's codes string.
    """
    if log is None or log.empty:
        return []
    dc = _date_col(log); cc = _codes_col(log)
    day_rows = log[log[dc].astype(str) == str(query_date)]
    if day_rows.empty:
        return []
    items = []
    for _, r in day_rows.iterrows():  # preserves CSV order
        codestr = str(r.get(cc, "") or "")
        if codestr.strip():
            items.extend(parse_selection_to_items(codestr))
    return items

# >>> NEW: build a DataFrame from items with 1-based idx, ready for what-if math

def _build_items_df(items: list, master: pd.DataFrame) -> pd.DataFrame:
    """
    items: list of dicts [{"code":..., "mult":...} or {"time":"HH:MM"}]
    Returns df with columns:
      idx, code, option, section, mult, cal, prot_g, carbs_g, fat_g, sugars_g, gl
    Time rows contribute zeros and show code as '@HH:MM'.
    """
    cols = _resolved_cols(master)
    rows = []
    for it in items:
        if "time" in it and it.get("time"):
            rows.append({
                "code": "@"+it["time"],
                "option": "time marker",
                "section": "",
                "mult": "",
                "cal": 0.0, "prot_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
                "sugars_g": 0.0, "gl": 0.0
            })
            continue
        code = str(it.get("code","")).upper()
        mult = float(it.get("mult", 1.0))
        mrow = _lookup_master_row(code, master, cols)
        if mrow is None:
            # Unknown code → zero contribution but still list it
            rows.append({
                "code": code, "option": "(unknown)", "section": "",
                "mult": mult,
                "cal": 0.0, "prot_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
                "sugars_g": 0.0, "gl": 0.0
            })
            continue
        cal   = _safe_float(mrow[cols["cal"]])   * mult
        prot  = _safe_float(mrow[cols["prot"]])  * mult
        carb  = _safe_float(mrow[cols["carb"]])  * mult
        fat   = _safe_float(mrow[cols["fat"]])   * mult
        sugar = _safe_float(mrow[cols["sugar"]]) * mult if cols["sugar"] else 0.0
        gl    = _safe_float(mrow[cols["gl"]])    * mult if cols["gl"]    else 0.0
        rows.append({
            "code": code,
            "option": str(mrow[cols["option"]]),
            "section": str(mrow[cols["sect"]]),
            "mult": mult,
            "cal": cal, "prot_g": prot, "carbs_g": carb, "fat_g": fat,
            "sugars_g": sugar, "gl": gl
        })
    df = pd.DataFrame(rows, columns=[
        "code","option","section","mult","cal","prot_g","carbs_g","fat_g","sugars_g","gl"
    ])
    if df.empty:
        df = pd.DataFrame(columns=["code","option","section","mult","cal","prot_g","carbs_g","fat_g","sugars_g","gl"])
    df.insert(0, "idx", range(1, len(df)+1))
    return df

# >>> NEW: single-line totals printer showing Original / Adjusted / Delta

def _render_report(base_df: pd.DataFrame, kept_df: pd.DataFrame):
    """Show original, adjusted, and delta totals using single-line format."""
    def _sum(df):
        if df is None or df.empty:
            return {"cal":0,"prot_g":0,"carbs_g":0,"fat_g":0,"GL":0,"sugars_g":0}
        return {
            "cal": df["cal"].sum(),
            "prot_g": df["prot_g"].sum(),
            "carbs_g": df["carbs_g"].sum(),
            "fat_g": df["fat_g"].sum(),
            "GL": df["gl"].sum(),
            "sugars_g": df["sugars_g"].sum(),
        }

    t0 = _sum(base_df)   # original totals
    t1 = _sum(kept_df)   # adjusted totals
    td = {k: t1[k] - t0[k] for k in t0}  # differences

    def fmt_delta(v):
        return f"{v:+.0f}" if abs(v) >= 1 else f"{v:+.1f}"

    print("\nTotals:")
    print(
        f"  Original → Cal: {t0['cal']:.0f} | P: {t0['prot_g']:.0f} g | "
        f"C: {t0['carbs_g']:.0f} g | F: {t0['fat_g']:.0f} g | Sugars: {t0['sugars_g']:.0f} g | GL: {t0['GL']:.0f}"
    )
    print(
        f"  Adjusted → Cal: {t1['cal']:.0f} | P: {t1['prot_g']:.0f} g | "
        f"C: {t1['carbs_g']:.0f} g | F: {t1['fat_g']:.0f} g | Sugars: {t1['sugars_g']:.0f} g | GL: {t1['GL']:.0f}"
    )
    print(
        f"  Delta    → Cal: {fmt_delta(td['cal'])} | P: {fmt_delta(td['prot_g'])} g | "
        f"C: {fmt_delta(td['carbs_g'])} g | F: {fmt_delta(td['fat_g'])} g | Sugars: {fmt_delta(td['sugars_g'])} g | GL: {fmt_delta(td['GL'])}"
    )
    print("")

# ---------- Hybrid Search Helpers ----------

TOKEN_RE = re.compile(r'"([^"]+)"|(\S+)', re.IGNORECASE)

def _normalize_text_for_search(s: pd.Series) -> pd.Series:
    """
    Normalize text for more natural search: lowercase, remove punctuation.
    """
    table = str.maketrans("", "", string.punctuation)
    return s.astype(str).str.lower().str.translate(table)

def _search_cols(master):
    return (
        _col(master, "code") or "code",
        _col(master, "section") or "section",
        _col(master, "option") or "option",
    )

def _search_series(master):
    code_col, sect_col, opt_col = _search_cols(master)
    combined = (
        master[code_col].astype(str).fillna("") + " " +
        master[sect_col].astype(str).fillna("") + " " +
        master[opt_col].astype(str).fillna("")
    )
    return _normalize_text_for_search(combined)

def _code_series(master):
    code_col, _, _ = _search_cols(master)
    return master[code_col].astype(str).str.lower().fillna("")

def _parse_query_to_clauses(q: str):
    """
    Returns a list of clauses; each clause is dict with:
      {"pos": [terms...], "neg": [terms...]}
    Clauses are OR-ed together. Terms inside a clause are AND-ed (with optional NOT).
    Spaces imply AND. Supports explicit AND/OR/NOT. Quotes make phrases.
    """
    # tokenize -> ['term'|'AND'|'OR'|'NOT', ...]
    raw = []
    for m in TOKEN_RE.finditer(q):
        tok = m.group(1) if m.group(1) is not None else m.group(2)
        raw.append(tok)

    # Normalize operators
    ops = {"and", "or", "not"}
    tokens = []
    for t in raw:
        tt = t.upper() if t.lower() in ops else t
        tokens.append(tt)

    # Split on OR into clauses
    clauses = []
    cur = {"pos": [], "neg": []}
    negate_next = False

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "OR":
            # finish current clause
            if not cur["pos"] and not cur["neg"]:
                # empty clause; skip
                pass
            else:
                clauses.append(cur)
            cur = {"pos": [], "neg": []}
            negate_next = False
            i += 1
            continue
        elif t == "AND":
            # AND is implicit; just skip
            i += 1
            continue
        elif t == "NOT":
            negate_next = True
            i += 1
            continue
        else:
            term = t  # keep original case for user, but we lower on compare
            if negate_next:
                cur["neg"].append(term)
                negate_next = False
            else:
                cur["pos"].append(term)
            i += 1

    if cur["pos"] or cur["neg"]:
        clauses.append(cur)

    # If no operators provided at all, treat entire query as single AND clause
    if not clauses:
        clauses = [{"pos": [], "neg": []}]

    return clauses

def _mask_for_term(master, term: str):
    """
    Code-aware term matching:
      - if term contains a dot (e.g., 'bv.' or 'VE.3'), match code prefix (startswith)
      - otherwise search normalized text (punctuation removed)
    """
    term_lc = term.lower().strip()
    s_all = _search_series(master)
    s_code = _code_series(master)

    if "." in term_lc:
        return s_code.str.startswith(term_lc)
    else:
        # punctuation removed in both term and s_all
        term_lc = term_lc.translate(str.maketrans("", "", string.punctuation))
        return s_all.str.contains(re.escape(term_lc), na=False)

def hybrid_query_mask(master, query: str):
    """
    Build a boolean mask over master using OR-of-ANDs with optional NOT terms.
    """
    if master is None or master.empty:
        return pd.Series([False] * (0 if master is None else len(master)))

    clauses = _parse_query_to_clauses(query)
    if not clauses:
        return pd.Series([True] * len(master))

    overall = pd.Series([False] * len(master))
    for clause in clauses:
        if not clause["pos"] and not clause["neg"]:
            continue
        # Start with all True for AND accumulation; then apply positive ANDs and negative NOTs
        clause_mask = pd.Series([True] * len(master))
        for t in clause["pos"]:
            clause_mask &= _mask_for_term(master, t)
        for t in clause["neg"]:
            clause_mask &= (~_mask_for_term(master, t))
        overall |= clause_mask

    return overall


# ---------- REPL ----------

HELP_TEXT = """Commands:
  start [YYYY-MM-DD]     Begin/reset today's pending JSON (default: today)
  add <codes>            Add codes (supports multipliers), e.g.:
                         add b.1 *1.5, s2.4, L.3x2
                         add (FR.1, FR.2) *.5
                         add D.10-VE.T1            # subtract ingredient
                         add D.10 - VE.T1*.5       # subtract half tomato
                         add fi.9 x5.7/4           # allows simple * and / in multipliers
  show                   Show current pending totals
  report [YYYY-MM-DD]    Detailed breakdown for current pending (default) or that date from log
  summary [start] [end] [today]
                         Show per-day Cal/P/C/F/Sug over a range (defaults to all).
                         Use 'today' to include current pending totals.
  chart [N] [start] [end] [today]
                         Plot Cal/P/C/F/Sugars with N-day moving avg (default N=7).
                         Optional start/end (YYYY-MM-DD). Add 'today' to include pending.
  edit <YYYY-MM-DD> <codes>
                         Replace that date's codes; recalculates Cal/P/C/F/Sugars from master
  delete <YYYY-MM-DD>    Delete ALL log rows for that date
  status                 Show date and number of pending items
  close                  Finalize: append totals to CSV log and clear pending JSON
  discard                Clear pending JSON without saving
  find <term>            Search in master only
  reload                 Reload master from disk
  items                  List current pending items with indices
  items <YYYY-MM-DD>     List that date's LOGGED items expanded (CSV order) with indices
  rm <idx|a,b|a-b>       Remove item(s) by 1-based index / range
  move <from> <to>       Move item at <from> to position <to> (1-based)
  setmult <idx> <mult>   Change multiplier of an item (e.g., setmult 3 .5)
  replace <idx> <codes>  Replace item at <idx> with parsed <codes> (first code used)
  ins <pos> <codes>      Insert parsed <codes> at <pos> (1-based), supports groups/mults
  whatif <idxes|ranges>  Preview totals excluding pending indices, e.g. 'whatif 4-7' or 'whatif 6,7'
  whatif <YYYY-MM-DD> <idxes|ranges>
                         Preview totals excluding indices from that date's LOGGED entries
  stash push             Save current pending on a stack
  stash pop              Restore the last stashed pending
  loadlog <YYYY-MM-DD>   Stash current day, load that log date into editor
  applylog [YYYY-MM-DD]  Write current pending back into that log date (or use active one)
  recalcgl [start] [end]
                         Recompute GL from codes for the date/range and write into the CSV.
  help                   Show this help
  quit                   Exit
"""

def repl():
    global pending_stack, _editing_date
    print("Diet logger (master-only + JSON pending). Type 'help' for commands.\n")
    master = load_master()
    log = ensure_log()
    pending = ensure_pending_shape(load_pending())
    if pending is not None:
        save_pending(pending)  # write back the cleaned, non-duplicating shape

    while True:
        cmd = input("> ").strip()
        if not cmd: continue
        low = cmd.lower()

        if low in ("quit","exit","q"):
            print("Goodbye."); break

        if low in ("help","h","?"):
            print(HELP_TEXT); continue

        if low.startswith("reload"):
            master = load_master()
            print("Master reloaded from disk."); continue

        if low.startswith("find "):
            # Hybrid search: spaces = AND, supports AND/OR/NOT and quoted phrases.
            query = cmd.split(maxsplit=1)[1]
            mask = hybrid_query_mask(master, query)
            hits = master[mask].copy()

            # Reuse your existing pretty-printer, but indent 8 spaces
            out = format_rows_for_print(hits)
            if out == "(no matches)":
                print("\n(no matches)\n")
            else:
                indented = "\n".join("        " + line for line in out.splitlines())
                print("\nSearch results:\n" + indented + "\n")
            continue

        if low.startswith("start"):
            parts = cmd.split(maxsplit=1)
            dt = parts[1].strip() if len(parts) == 2 else str(date.today())
            pending = {"date": dt, "items": []}
            save_pending(pending)
            print(f"Pending day started for {dt}."); continue

        if low == "status":
            p = ensure_pending_shape(load_pending())
            if p is None:
                print("No pending day.")
            else:
                print(f"Pending day {p.get('date')} with {len(p.get('items', []))} item(s).")
            continue

        if low.startswith("add "):
            if pending is None:
                pending = {"date": str(date.today()), "items": []}
            else:
                pending = ensure_pending_shape(pending) or {"date": str(date.today()), "items": []}

            payload = cmd[4:].strip()
            parsed = parse_selection_to_items(payload)
            if not parsed:
                print("No valid codes found to add."); continue

            pending["items"].extend(parsed)
            save_pending(pending)

            # NEW: If any added item is a fish code (FI.*), shout our thanks once.
            if any(str(it.get("code", "")).upper().startswith("FI.") for it in parsed):
                print("THANKS FOR ALL THE FISH!!!")

            show_pending(pending, master); continue

        if low == "show":
            show_pending(pending, master); continue

        if low.startswith("report"):
            parts = cmd.split(maxsplit=1)
            if len(parts) == 1:
                # Current pending day
                if not pending or not pending.get("items"):
                    print("No active day to report. Use 'start' and 'add' first.")
                else:
                    rows, totals, missing, display = build_report_from_items(pending["items"], master)
                    print_report(rows, totals, title=f"Report for {pending.get('date')}", missing=missing, display=display)
                continue
            else:
                # Report for a specific date in the log
                query_date = parts[1].strip()
                log = ensure_log()  # reload in case external edits
                if log.empty:
                    print("Log is empty."); continue
                # accept mixed-case 'date' and 'codes' column names
                date_col = next((c for c in log.columns if str(c).lower()=="date"), "date")
                codes_col = next((c for c in log.columns if str(c).lower()=="codes"), "codes")

                day_rows = log[log[date_col].astype(str) == query_date]
                if day_rows.empty:
                    print(f"No log entries found for {query_date}."); continue

                # If multiple rows for the date, concatenate their codes
                combined_codes = ", ".join([str(v) for v in day_rows[codes_col].fillna("") if str(v).strip()])
                items = parse_selection_to_items(combined_codes)

                if not items:
                    print(f"No parsable codes for {query_date}."); continue

                rows, totals, missing, display = build_report_from_items(items, master)
                print_report(rows, totals, title=f"Report for {query_date}", missing=missing, display=display)
                continue

        if low.startswith("summary"):
            # tokens: possible dates + optional 'today' flag
            tokens = cmd.split()[1:]  # strip 'summary'
            include_today = any(t.lower() in ("today", "--today") for t in tokens)
            date_tokens = [t for t in tokens if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)]

            start_date = date_tokens[0] if len(date_tokens) >= 1 else None
            end_date   = date_tokens[1] if len(date_tokens) >= 2 else None

            log = ensure_log()  # reload current log
            if log.empty and not include_today:
                print("\n(no rows)\n"); continue

            # filter by date range
            view = filter_log_by_dates(log, start_date, end_date)

            # optionally append today's pending totals
            if include_today:
                today_row = build_today_row_from_pending(pending, master)
                if today_row is not None:
                    view = pd.concat([view, today_row], ignore_index=True)

            # compute GL if missing (from codes)
            view = ensure_gl_column_from_codes(view, master, force=False)

            # keep only summary columns (ignore codes)
            keep_cols = ["date","cal","prot_g","carbs_g","fat_g","sugar_g","gl"]
            present = [c for c in keep_cols if c in view.columns or c.lower() in [str(x).lower() for x in view.columns]]
            # normalize possible case differences
            colmap = {}
            for c in view.columns:
                lc = str(c).lower()
                if lc in keep_cols and c != lc:
                    colmap[c] = lc
            if colmap:
                view = view.rename(columns=colmap)
            # ensure all required columns exist
            for c in keep_cols:
                if c not in view.columns:
                    view[c] = 0

            print_summary_table_with_gaps(view[keep_cols].copy(), title="Summary")

            # print_summary_table(view[keep_cols].copy(), title="Summary")
            continue

        # --- EDIT a past date ---
        if low.startswith("edit "):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                print("Usage: edit <YYYY-MM-DD> <codes>")
                continue

            query_date = parts[1].strip()
            new_codes  = parts[2].strip()
            log = ensure_log()  # reload

            if log.empty:
                print("Log is empty.")
                continue

            # case-insensitive column resolution
            date_col  = next((c for c in log.columns if str(c).lower()=="date"), "date")
            codes_col = next((c for c in log.columns if str(c).lower()=="codes"), "codes")

            idxs = log.index[log[date_col].astype(str) == query_date].tolist()
            if not idxs:
                print(f"No log entries found for {query_date}.")
                continue

            # Recompute totals from new_codes against master
            totals, missing = recompute_totals_from_codes(new_codes, master)
            safe_int = lambda v: int(round(v))

            # Update the FIRST matching row (common case: 1 row per day)
            i = idxs[0]
            log.at[i, codes_col] = new_codes
            log.at[i, "cal"]      = safe_int(totals["cal"])
            log.at[i, "prot_g"]   = safe_int(totals["prot_g"])
            log.at[i, "carbs_g"]  = safe_int(totals["carbs_g"])
            log.at[i, "fat_g"]    = safe_int(totals["fat_g"])
            # ensure sugar_g column exists and set it
            if "sugar_g" not in [str(c).lower() for c in log.columns]:
                log["sugar_g"] = 0
            # find exact sugar column name (may already be 'sugar_g' or variant)
            sug_exact = next((c for c in log.columns if str(c).lower()=="sugar_g"), "sugar_g")
            log.at[i, sug_exact]  = safe_int(totals["sugar_g"])
            # ensure gl column exists and set it
            if "gl" not in [str(c).lower() for c in log.columns]:
                log["gl"] = 0
            gl_exact = next((c for c in log.columns if str(c).lower()=="gl"), "gl")
            log.at[i, gl_exact] = safe_int(totals.get("gl", 0))

            save_log(log)
            print(f"Updated {query_date}.", end="")
            if missing:
                print(f"  Missing (not counted): {', '.join(missing)}")
            else:
                print()
            continue

        # --- DELETE a past date ---
        if low.startswith("delete "):
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: delete <YYYY-MM-DD>")
                continue

            query_date = parts[1].strip()
            log = ensure_log()  # reload
            if log.empty:
                print("Log is empty.")
                continue

            date_col = next((c for c in log.columns if str(c).lower()=="date"), "date")
            before = len(log)
            log = log[log[date_col].astype(str) != query_date].reset_index(drop=True)
            after = len(log)
            if before == after:
                print(f"No log entries found for {query_date}.")
                continue

            save_log(log)
            print(f"Deleted {before - after} row(s) for {query_date}.")
            continue

        # ---- item list management ----
        if low == "items":
            print_items(pending, master); continue

        # >>> NEW: items <YYYY-MM-DD> (logged-only, CSV order, expanded)
        if low.startswith("items "):
            parts = cmd.split(maxsplit=1)
            qd = parts[1].strip()
            lg = ensure_log()
            items_list = expand_logged_items_in_csv_order(qd, lg)
            if not items_list:
                print("(no items)")
            else:
                pseudo = {"date": qd, "items": items_list}
                print_items(pseudo, master)
            continue

        if low.startswith("rm "):
            if not pending or not pending.get("items"):
                print("No items to remove."); continue
            idxs = parse_index_args(cmd.split(maxsplit=1)[1], len(pending["items"]))
            if not idxs:
                print("No valid indices."); continue
            # remove in reverse order to keep indices valid
            for i in reversed(idxs):
                del pending["items"][i]
            save_pending(pending)
            print_items(pending, master); continue

        if low.startswith("move "):
            if not pending or not pending.get("items"):
                print("No items to move."); continue
            parts = cmd.split()
            if len(parts) != 3:
                print("Usage: move <from> <to>"); continue
            try:
                f = int(parts[1]); t = int(parts[2])
                n = len(pending["items"])
                if not (1 <= f <= n and 1 <= t <= n): raise ValueError
                item = pending["items"].pop(f-1)
                pending["items"].insert(t-1, item)
                save_pending(pending)
                print_items(pending, master)
            except Exception:
                print("Invalid indices. Use 1-based positions.")
            continue

        if low.startswith("setmult "):
            if not pending or not pending.get("items"):
                print("No items to edit."); continue
            parts = cmd.split()
            if len(parts) != 3:
                print("Usage: setmult <idx> <mult>"); continue
            try:
                idx = int(parts[1]) - 1
                mult_str = parts[2]
                if mult_str.startswith("."): mult_str = "0" + mult_str
                mult = float(mult_str)
                pending["items"][idx]["mult"] = mult
                save_pending(pending)
                print_items(pending, master)
            except Exception:
                print("Invalid index or multiplier.")
            continue

        if low.startswith("replace "):
            if not pending or not pending.get("items"):
                print("No items to edit."); continue
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                print("Usage: replace <idx> <codes>"); continue
            try:
                idx = int(parts[1]) - 1
                new_items = parse_selection_to_items(parts[2])
                if not new_items:
                    print("No valid codes found."); continue
                pending["items"][idx] = new_items[0]  # replace with first parsed item
                save_pending(pending)
                print_items(pending, master)
            except Exception:
                print("Invalid index.")
            continue

        if low.startswith("ins "):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                print("Usage: ins <pos> <codes>"); continue
            try:
                pos = int(parts[1]) - 1
                new_items = parse_selection_to_items(parts[2])
                if not new_items:
                    print("No valid codes found."); continue
                if pending is None:
                    pending = {"date": str(date.today()), "items": []}
                # clamp pos
                pos = max(0, min(pos, len(pending["items"])))
                for i, it in enumerate(new_items):
                    pending["items"].insert(pos+i, it)
                save_pending(pending)
                print_items(pending, master)
            except Exception:
                print("Invalid position.")
            continue

        # >>> NEW: whatif (pending or by date; indices always refer to original list numbering)
        if low.startswith("whatif"):
            tokens = cmd.split()
            if len(tokens) == 1:
                print("Usage: whatif [YYYY-MM-DD] <idxes|ranges>")
                continue

            # pending-by-default path
            target_date = None
            selectors_str = None

            # Allow: whatif YYYY-MM-DD <selectors>  OR  whatif <selectors>
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tokens[1]):
                target_date = tokens[1]
                selectors_str = " ".join(tokens[2:]).strip()
                if not selectors_str:
                    print("Usage: whatif YYYY-MM-DD <idxes|ranges>")
                    continue
            else:
                selectors_str = " ".join(tokens[1:]).strip()

            if target_date:
                # Logged-only, CSV order, expanded items
                lg = ensure_log()
                base_items = expand_logged_items_in_csv_order(target_date, lg)
                label = target_date
            else:
                # Pending-only
                p = ensure_pending_shape(load_pending())
                base_items = p.get("items", []) if p else []
                label = "pending"

            n = len(base_items)
            if n == 0:
                print(f"\nWHAT-IF PREVIEW ({label}) — nothing to show.")
                continue

            # parse selectors into 0-based indices using existing helper
            drop_0based = parse_index_args(selectors_str, n)
            drop_1based = {i+1 for i in drop_0based}

            # Build dataframes
            base_df = _build_items_df(base_items, master)
            excluded = base_df[base_df["idx"].isin(drop_1based)]
            kept = base_df[~base_df["idx"].isin(drop_1based)]

            print(f"\nWHAT-IF PREVIEW (no changes saved) — {label}")
            if excluded.empty:
                print("Excluded: (none matched)")
            else:
                print("Excluded:")
                for _, r in excluded.iterrows():
                    mult_str = f" x{r['mult']}" if r['mult'] not in ("", 1, 1.0) else ""
                    print(f"  - #{int(r['idx'])} {r['code']} '{r['option']}'{mult_str}")

            # Print remaining items snapshot (optional short list)
            if kept.empty:
                print("\nRemaining items:\n  (none)")
            else:
                print("\nRemaining items:")
                for _, r in kept.iterrows():
                    mult_str = f" x{r['mult']}" if r['mult'] not in ("", 1, 1.0) else ""
                    print(f"  • #{int(r['idx'])} {r['code']}{mult_str} '{r['option']}' "
                          f"= {r['cal']:.0f} cal, {r['carbs_g']:.1f}g carbs, GL {r['gl']:.1f}, sugars {r['sugars_g']:.1f}g")

            _render_report(base_df, kept)
            continue

        # ---- stash: session-only push/pop ----
        if low == "stash push":
            # deep-copy the current pending so later edits don’t mutate the stashed copy
            import copy
            snapshot = copy.deepcopy(pending) if pending else None
            pending_stack.append(snapshot)
            print(f"Stashed current pending. Depth={len(pending_stack)}")
            continue

        if low == "stash pop":
            if not pending_stack:
                print("Stash is empty.")
                continue
            pending = pending_stack.pop()
            # persist current state to the JSON so you don't lose it on next command
            save_pending(pending or {"date": str(date.today()), "items": []})
            print("Restored from stash.")
            show_pending(pending, master)
            continue

        # ---- load a log date into editor (auto-stash) ----
        if low.startswith("loadlog "):
            parts = cmd.split(maxsplit=1)
            qd = parts[1].strip()
            lg = ensure_log()
            p2 = load_log_into_pending(qd, master, lg)
            if p2 is None:
                print(f"No log entries found for {qd}."); continue
            # save current pending on the stash
            if "pending_stack" not in globals():
                pending_stack = []
            pending_stack.append(pending.copy() if pending else None)
            pending = p2
            # remember which date we're editing (in-session only)
            globals()["_editing_date"] = qd
            save_pending(pending)
            print(f"Loaded {qd} from log into editor (previous pending stashed).")
            print_items(pending, master); continue

        # ---- apply current pending back into a log date ----
        if low.startswith("applylog"):
            parts = cmd.split(maxsplit=1)
            if len(parts) == 1:
                qd = globals().get("_editing_date", None)
                if not qd:
                    print("No target date. Use: applylog <YYYY-MM-DD> or loadlog first.")
                    continue
            else:
                qd = parts[1].strip()

            lg = ensure_log()
            dc = _date_col(lg); cc = _codes_col(lg)
            idxs = lg.index[lg[dc].astype(str) == qd].tolist()
            if not idxs:
                print(f"No log entries found for {qd}."); continue

            # compute from current pending
            codestr = pending_to_codestr(pending, master)
            totals, _missing, _ = accumulate_from_items(pending.get("items", []), master)
            safe_int = lambda v: int(round(v))

            i = idxs[0]
            lg.at[i, cc]       = codestr
            lg.at[i, "cal"]    = safe_int(totals["cal"])
            lg.at[i, "prot_g"] = safe_int(totals["prot_g"])
            lg.at[i, "carbs_g"]= safe_int(totals["carbs_g"])
            lg.at[i, "fat_g"]  = safe_int(totals["fat_g"])
            if "sugar_g" not in [str(c).lower() for c in lg.columns]:
                lg["sugar_g"] = 0
            sug_exact = next((c for c in lg.columns if str(c).lower()=="sugar_g"), "sugar_g")
            lg.at[i, sug_exact] = safe_int(totals["sugar_g"])
            if "gl" not in [str(c).lower() for c in lg.columns]:
                lg["gl"] = 0
            gl_exact = next((c for c in lg.columns if str(c).lower()=="gl"), "gl")
            lg.at[i, gl_exact] = safe_int(totals.get("gl", 0))

            save_log(lg)
            print(f"Applied current editor state back to {qd}.")
            continue

        if low == "discard":
            clear_pending(); pending = None
            print("Pending JSON cleared (no save)."); continue

        if low == "close":
            p = ensure_pending_shape(pending)
            if p is None or not p.get("items"):
                print("Nothing to close. Start and add items first."); continue
            totals, missing, code_strs = show_pending(p, master)
            safe_int = lambda v: int(round(v))
            new_row = {
                "date": p.get("date", str(date.today())),
                "codes": ", ".join(code_strs),
                "cal": safe_int(totals["cal"]),
                "prot_g": safe_int(totals["prot_g"]),
                "carbs_g": safe_int(totals["carbs_g"]),
                "fat_g": safe_int(totals["fat_g"]),
                "sugar_g": safe_int(totals["sugar_g"]),
                "gl": safe_int(totals.get("gl", 0)),
            }
            log = pd.concat([log, pd.DataFrame([new_row])], ignore_index=True)
            save_log(log)
            clear_pending(); pending = None
            print(f"Closed and saved to {LOG_FILE}. Pending JSON cleared."); continue

        if low.startswith("chart"):
            tokens = cmd.split()[1:]  # drop 'chart'
            # defaults
            window = 7
            include_today = any(t.lower() in ("today", "--today") for t in tokens)
            # pull out integers for window and date tokens (YYYY-MM-DD)
            date_tokens = [t for t in tokens if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)]
            # window = first bare integer token if any
            int_tokens = []
            for t in tokens:
                if t.lower() in ("today","--today"):
                    continue
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
                    continue
                try:
                    int_tokens.append(int(t))
                except:
                    pass
            if int_tokens:
                window = max(1, int_tokens[0])  # clamp to >=1

            start_date = date_tokens[0] if len(date_tokens) >= 1 else None
            end_date   = date_tokens[1] if len(date_tokens) >= 2 else None

            # load and filter log
            log = ensure_log()
            view = filter_log_by_dates(log, start_date, end_date)

            # optionally append today's pending
            if include_today:
                today_row = build_today_row_from_pending(pending, master)
                if today_row is not None:
                    view = pd.concat([view, today_row], ignore_index=True)

            view = ensure_gl_column_from_codes(view, master, force=False)

            view = _normalize_summary_df(view)
            make_trend_chart(view, window, outfile="meal_plan_trend.jpg")
            continue

        if low.startswith("recalcgl"):
            tokens = cmd.split()[1:]
            date_tokens = [t for t in tokens if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)]
            start_date = date_tokens[0] if len(date_tokens) >= 1 else None
            end_date   = date_tokens[1] if len(date_tokens) >= 2 else None

            lg = ensure_log()
            if lg.empty:
                print("Log is empty."); continue

            dc = _date_col(lg); cc = _codes_col(lg)
            mask = pd.Series([True]*len(lg))
            if start_date: mask &= lg[dc].astype(str) >= start_date
            if end_date:   mask &= lg[dc].astype(str) <= end_date

            idxs = lg.index[mask].tolist()
            if not idxs:
                print("No rows in that range."); continue

            # ensure gl column exists
            if "gl" not in [str(c).lower() for c in lg.columns]:
                lg["gl"] = 0
            gl_exact = next((c for c in lg.columns if str(c).lower()=="gl"), "gl")

            changed = 0
            for i in idxs:
                codestr = str(lg.at[i, cc]) if pd.notna(lg.at[i, cc]) else ""
                totals, _missing = recompute_totals_from_codes(codestr, master)
                lg.at[i, gl_exact] = int(round(totals.get("gl", 0)))
                changed += 1

            save_log(lg)
            if start_date and end_date:
                print(f"Recomputed GL for {changed} row(s) from {start_date} to {end_date}.")
            elif start_date:
                print(f"Recomputed GL for {changed} row(s) from {start_date} onward.")
            else:
                print(f"Recomputed GL for {changed} row(s) (all rows).")
            continue

        print("Unrecognized command. Type 'help' for options.")

def main():
    return repl()

if __name__ == "__main__":
    main()
