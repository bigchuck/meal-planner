# meal_planner/commands/add_resolver.py
"""
Search-mode resolver for add/insert commands.

Handles fuzzy lookup, conflict list display, row selection (#N),
and --last log scan. Returns resolved items or signals the caller
to fall back to the existing code-parser path.

Public API:
    resolve_add_args(args, ctx, lookback_days=3)
        -> list of item dicts   : proceed with add
        -> None                 : already handled (error/conflict shown); caller returns
        -> 'fallback'           : use existing CodeParser / expand_aliases path
"""
import re
import shlex
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

# Matches multiplier tokens: x1.5, x.5, x1/7, *2, *0.5
_MULTIPLIER_RE = re.compile(r'^[x\*][\d./]+$', re.IGNORECASE)
# Matches row selector tokens: #1, #12
_ROW_RE = re.compile(r'^#(\d+)$')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_parse_multiplier(token: str) -> Optional[float]:
    """Return float if token is a multiplier (x1.5, *0.5, x1/7), else None."""
    if not _MULTIPLIER_RE.match(token):
        return None
    expr = token[1:]          # strip leading x or *
    try:
        if '/' in expr:
            num, den = expr.split('/', 1)
            val = float(num) / float(den)
        else:
            val = float(expr)
        return val if val > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _parse_add_tokens(
    args: str,
) -> Tuple[str, Optional[int], Optional[float], bool, Optional[str]]:
    """
    Decompose raw args string into (criteria, row_selector, multiplier, use_last, error).

    Strips --last, trailing #N, and trailing multiplier from tokens.
    Returns error string (non-None) on mutual-exclusion violation.
    """
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.strip().split()

    # Extract --last flag
    use_last = '--last' in tokens
    tokens = [t for t in tokens if t != '--last']

    # Extract trailing #N row selector
    row_selector = None
    if tokens:
        m = _ROW_RE.match(tokens[-1])
        if m:
            row_selector = int(m.group(1))
            tokens = tokens[:-1]

    # Mutual exclusion
    if use_last and row_selector is not None:
        return '', None, None, False, "cannot combine row selector (#N) with --last"

    # Extract trailing multiplier (only if it looks like x/*)
    multiplier = None
    if tokens:
        val = _try_parse_multiplier(tokens[-1])
        if val is not None:
            multiplier = val
            tokens = tokens[:-1]

    criteria = ' '.join(tokens)
    return criteria, row_selector, multiplier, use_last, None


def _format_conflict_list(results, master) -> str:
    """Format multi-result DataFrame as numbered list matching find display style."""
    cols = master.cols
    lines = []
    for i, (_, row) in enumerate(results.iterrows(), 1):
        code = str(row[cols.code])
        section = str(row[cols.section])
        option = str(row[cols.option])
        cal  = row[cols.cal]
        prot = row[cols.prot_g]
        carb = row[cols.carbs_g]
        fat  = row[cols.fat_g]
        nutr = f"cal={cal} P={prot} C={carb} F={fat}"
        lines.append(f"  #{i:<3} {code:>8} | {section:<7} | {option} [{nutr}]")
    return '\n'.join(lines)


def _find_last_in_log(
    ctx,
    matching_codes: set,
    lookback_days: int,
) -> Optional[Dict[str, Any]]:
    """
    Scan backwards through today's pending then the log CSV for the most recent
    item whose code is in matching_codes.

    Returns {code, mult} or None.
    """
    from meal_planner.parsers import CodeParser

    # 1. Check today's pending first (most recent possible match)
    try:
        pending = ctx.pending_mgr.load()
    except Exception:
        pending = None

    if pending and pending.get('items'):
        for item in reversed(pending['items']):
            if 'code' in item and item['code'].upper() in matching_codes:
                return {'code': item['code'].upper(), 'mult': float(item.get('mult', 1.0))}

    # 2. Scan committed log entries, newest date first
    today = date.today()
    cutoff = str(today - timedelta(days=lookback_days))

    df = ctx.log.df.copy()
    date_col  = ctx.log.cols.date
    codes_col = ctx.log.cols.codes

    df[date_col] = df[date_col].astype(str)
    df = df[df[date_col] >= cutoff]
    df = df.sort_values(date_col, ascending=False)

    for _, entry in df.iterrows():
        codes_str = str(entry.get(codes_col, '') or '').strip()
        if not codes_str:
            continue
        items = CodeParser.parse(codes_str)
        for item in reversed(items):
            if 'code' in item and item['code'].upper() in matching_codes:
                return {'code': item['code'].upper(), 'mult': float(item.get('mult', 1.0))}

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_add_args(
    args: str,
    ctx,
    lookback_days: int = 3,
) -> Union[List[Dict[str, Any]], None, str]:
    """
    Resolve add/insert args with optional fuzzy search.

    Routing rules
    -------------
    1. --last or #N present             -> search mode (always)
    2. Criteria contains a comma        -> 'fallback' (multi-code existing path)
    3. Single token, no search flags    -> direct lookup; if hit return it,
                                           if miss fall through to search
    4. Multiple tokens, no comma        -> search mode

    Returns
    -------
    list[dict]  Items to add.
    None        Already handled (error or conflict list printed); caller should return.
    'fallback'  Use existing CodeParser / expand_aliases path unchanged.
    """
    criteria, row_selector, multiplier, use_last, err = _parse_add_tokens(args)

    if err:
        print(f"\nError: {err}\n")
        return None

    tokens = criteria.split()

    # Nothing left after stripping flags / multiplier with no search indicators
    if not tokens and not use_last and row_selector is None:
        return 'fallback'

    # Comma in criteria -> multi-code string, use existing path
    if ',' in criteria and not use_last and row_selector is None:
        return 'fallback'
    
    # Hyphen in criteria -> subtraction syntax (e.g. "-CH.3", "SO.3-MT.11"),
    # use existing path so CodeParser's subtraction handling can run
    if '-' in criteria and not use_last and row_selector is None:
        return 'fallback'

    # Time marker (e.g. @8:30) -> existing path
    if criteria.startswith('@'):
        return 'fallback'

    # Single token, no explicit search indicators -> try direct code lookup first
    if len(tokens) == 1 and not use_last and row_selector is None:
        direct = ctx.master.lookup_code(tokens[0])
        if direct is not None:
            item = {'code': tokens[0].upper()}
            if multiplier is not None:
                item['mult'] = multiplier
            return [item]
        # Could be an alias -> let existing path handle it
        if ctx.aliases and ctx.aliases.lookup_alias(tokens[0]):
            return 'fallback'
        # Not a known code or alias -> fall through to search with that single token

    # -----------------------------------------------------------------------
    # Search mode
    # -----------------------------------------------------------------------
    if not criteria.strip():
        print("\nError: no search criteria provided\n")
        return None

    results = ctx.master.search(criteria)

    # --last path: find most recent matching code in log/pending
    if use_last:
        if results.empty:
            print(f"\nNo master entries matching '{criteria}'\n")
            return None

        matching_codes = {str(r).upper() for r in results[ctx.master.cols.code]}
        item = _find_last_in_log(ctx, matching_codes, lookback_days)

        if item is None:
            print(f"\nNo log entry in last {lookback_days} days matching '{criteria}'\n")
            return None

        if multiplier is not None:
            item['mult'] = multiplier         # command multiplier overrides log mult
        return [item]

    # Standard search (no --last)
    if results.empty:
        print(f"\nNo matches found for '{criteria}'\n")
        return None

    if len(results) == 1:
        code = str(results.iloc[0][ctx.master.cols.code]).upper()
        item = {'code': code}
        if multiplier is not None:
            item['mult'] = multiplier
        return [item]

    # Multiple results
    if row_selector is not None:
        if row_selector < 1 or row_selector > len(results):
            print(
                f"\nRow #{row_selector} not found "
                f"('{criteria}' returned {len(results)} results)\n"
            )
            return None
        row = results.iloc[row_selector - 1]
        code = str(row[ctx.master.cols.code]).upper()
        item = {'code': code}
        if multiplier is not None:
            item['mult'] = multiplier
        return [item]

    # Conflict list — print and exit; no state retained
    print(f"\nMultiple matches for '{criteria}':")
    print(_format_conflict_list(results, ctx.master))
    print(f"\nTo select, re-enter with a row number, e.g.:  add {criteria} #2\n")
    return None