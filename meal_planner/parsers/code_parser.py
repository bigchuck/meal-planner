"""
Code parsing utilities for meal plan entries.

Handles parsing of meal codes with multipliers, time markers, and groupings:
- Simple codes: "B.1", "S2.4"
- With multipliers: "B.1 *1.5", "L.3x2", "FI.9 x5.7/4"
- Groups: "(FR.1, FR.2) *.5"
- Subtractions: "D.10-VE.T1", "D.10 - VE.T1*.5"
- Time markers: "@11", "@11:30"
"""
import re
from typing import List, Dict, Any, Union


# Regex patterns
CODE_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)",
    re.IGNORECASE
)

MULT_RE = re.compile(
    r"[*x×]\s*([0-9]*\.?[0-9]+(?:\s*[*/]\s*[0-9]*\.?[0-9]+)*)",
    re.IGNORECASE
)

TIME_RE = re.compile(r"^@(\d{1,2})(?::(\d{2}))?$")


def normalize_time(hour: int, minute: int = 0) -> str:
    """
    Normalize and validate time to HH:MM format.
    
    Args:
        hour: Hour (0-23)
        minute: Minute (0-59)
    
    Returns:
        Zero-padded HH:MM string
    
    Raises:
        ValueError: If time is invalid
    """
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time: {hour}:{minute}")
    return f"{hour:02d}:{minute:02d}"


def eval_multiplier_expression(expr: str) -> float:
    """
    Evaluate a simple arithmetic multiplier expression.
    
    Supports: NUM (('*' | '/') NUM)*
    Left-to-right evaluation. No parentheses or +/- supported.
    
    Args:
        expr: Expression like "1.5", "5.7/4", ".5*2/3"
    
    Returns:
        Evaluated result
    
    Examples:
        >>> eval_multiplier_expression("1.5")
        1.5
        >>> eval_multiplier_expression("5.7/4")
        1.425
        >>> eval_multiplier_expression(".5*2")
        1.0
    """
    if not expr:
        return 1.0
    
    s = expr.strip()
    
    # Split into numbers and operators
    nums = re.split(r"[*/]", s)
    ops = re.findall(r"[*/]", s)
    
    try:
        def to_float(x: str) -> float:
            x = x.strip()
            if x.startswith("."):
                x = "0" + x
            return float(x)
        
        val = to_float(nums[0])
        for op, raw in zip(ops, nums[1:]):
            rhs = to_float(raw)
            if op == "*":
                val *= rhs
            else:  # op == "/"
                val = val / rhs if rhs != 0 else 0.0
        
        return val
    except Exception:
        # Fallback: treat as 1.0 multiplier on error
        return 1.0


def split_top_level(s: str) -> List[str]:
    """
    Split string by commas not inside parentheses.
    
    Args:
        s: String to split (e.g., "B.1, (FR.1, FR.2) *.5, L.3")
    
    Returns:
        List of parts split by top-level commas
    
    Example:
        >>> split_top_level("B.1, (FR.1, FR.2), L.3")
        ['B.1', '(FR.1, FR.2)', 'L.3']
    """
    parts, buf, depth = [], [], 0
    
    for ch in s:
        if ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == ',' and depth == 0:
            part = ''.join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(ch)
    
    tail = ''.join(buf).strip()
    if tail:
        parts.append(tail)
    
    return parts


def parse_one_code_mult(snippet: str) -> Dict[str, Any]:
    """
    Parse a single code with optional multiplier.
    
    Args:
        snippet: String like "D.10", "VE.T1*.5", "B.1 x2"
    
    Returns:
        Dictionary with 'code' and 'mult', or None if time token
    
    Example:
        >>> parse_one_code_mult("B.1 *1.5")
        {'code': 'B.1', 'mult': 1.5}
    """
    # Skip if it's a time token
    if TIME_RE.match(snippet.strip()):
        return None
    
    m_code = CODE_RE.search(snippet)
    if not m_code:
        return None
    
    code = m_code.group(1).upper()
    
    # Look for multiplier
    m_mult = MULT_RE.search(snippet)
    if m_mult:
        mult_str = m_mult.group(1)
        if mult_str.startswith("."):
            mult_str = "0" + mult_str
        mult = eval_multiplier_expression(mult_str)
    else:
        mult = 1.0
    
    return {"code": code, "mult": mult}


def parse_selection_to_items(selection: Union[str, List]) -> List[Dict[str, Any]]:
    """
    Parse meal selection into list of items (codes and time markers).
    
    Accepts various formats:
    - Single codes: "B.1", "S2.4 *1.5"
    - Lists: ["B.1", "S2.4", "@11"]
    - Groups: "(FR.1, FR.2) *.5"
    - Subtractions: "D.10-VE.T1", "D.10 - VE.T1*.5"
    - Time markers: "@11", "@11:30"
    
    Args:
        selection: String or list of meal codes/times
    
    Returns:
        List of dicts with either:
        - {"code": "B.1", "mult": 1.5} for meal codes
        - {"time": "HH:MM"} for time markers
    
    Example:
        >>> parse_selection_to_items("B.1 *1.5, @11, S2.4")
        [
            {'code': 'B.1', 'mult': 1.5},
            {'time': '11:00'},
            {'code': 'S2.4', 'mult': 1.0}
        ]
    """
    items = []
    
    # Convert to list of chunks
    if isinstance(selection, list):
        chunks = [str(c) for c in selection]
    else:
        s = str(selection).strip()
        chunks = split_top_level(s)
    
    for chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        
        # Time token: @11 or @11:30
        m_time = TIME_RE.match(c)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2)) if m_time.group(2) else 0
            try:
                items.append({"time": normalize_time(h, m)})
            except ValueError:
                pass  # Skip invalid times
            continue
        
        # Group form: (code1, code2) *mult
        if c.startswith("(") and ")" in c:
            close = c.rfind(")")
            inside = c[1:close]
            after = c[close+1:]
            
            # Find all codes inside parentheses
            codes = [m.upper().strip() for m in CODE_RE.findall(inside)]
            
            # Group multiplier (default 1.0)
            m_mult = MULT_RE.search(after)
            if m_mult:
                mult_str = m_mult.group(1)
                if mult_str.startswith("."):
                    mult_str = "0" + mult_str
                gmult = eval_multiplier_expression(mult_str)
            else:
                gmult = 1.0
            
            for code in codes:
                items.append({"code": code, "mult": gmult})
            continue
        
        # Subtraction form: D.10-VE.T1 or D.10 - VE.T1*.5
        if "-" in c:
            parts_minus = [p.strip() for p in c.split("-")]
            
            # First part (positive)
            first_time = TIME_RE.match(parts_minus[0])
            if first_time:
                h = int(first_time.group(1))
                m = int(first_time.group(2)) if first_time.group(2) else 0
                try:
                    items.append({"time": normalize_time(h, m)})
                except ValueError:
                    pass
            else:
                first = parse_one_code_mult(parts_minus[0])
                if first:
                    items.append(first)
            
            # Subsequent parts (negative)
            for sub in parts_minus[1:]:
                # Skip time tokens after '-'
                if TIME_RE.match(sub):
                    continue
                
                one = parse_one_code_mult(sub)
                if one:
                    one["mult"] = -abs(float(one.get("mult", 1.0)))
                    items.append(one)
            continue
        
        # Single item (code or time)
        m_time = TIME_RE.match(c)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2)) if m_time.group(2) else 0
            try:
                items.append({"time": normalize_time(h, m)})
            except ValueError:
                pass
            continue
        
        one = parse_one_code_mult(c)
        if one:
            items.append(one)
    
    return items


def items_to_code_string(items: List[Dict[str, Any]]) -> str:
    """
    Convert items list back to a readable code string.
    
    Args:
        items: List of item dicts (codes and times)
    
    Returns:
        Formatted string like "B.1 x1.5, @11:00, S2.4"
    
    Example:
        >>> items = [
        ...     {'code': 'B.1', 'mult': 1.5},
        ...     {'time': '11:00'},
        ...     {'code': 'S2.4', 'mult': 1.0}
        ... ]
        >>> items_to_code_string(items)
        'B.1 x1.5, @11:00, S2.4'
    """
    parts = []
    
    for it in items:
        # Time marker
        if "time" in it and it.get("time"):
            t = str(it["time"]).strip()
            if t:
                parts.append(f"@{t}")
            continue
        
        # Code with multiplier
        if "code" in it:
            code = str(it["code"]).upper()
            mult = float(it.get("mult", 1.0))
            
            if mult < 0:
                amag = abs(mult)
                if abs(amag - 1.0) < 1e-9:
                    parts.append(f"-{code}")
                else:
                    parts.append(f"-{code} x{amag:g}")
            else:
                if abs(mult - 1.0) > 1e-9:
                    parts.append(f"{code} x{mult:g}")
                else:
                    parts.append(code)
    
    return ", ".join(parts)


class CodeParser:
    """
    Stateful parser for meal codes.
    
    Provides a cleaner API for parsing and formatting meal selections.
    """
    
    @staticmethod
    def parse(selection: Union[str, List]) -> List[Dict[str, Any]]:
        """Parse selection into items list."""
        return parse_selection_to_items(selection)
    
    @staticmethod
    def format(items: List[Dict[str, Any]]) -> str:
        """Format items list into readable string."""
        return items_to_code_string(items)
    
    @staticmethod
    def is_time_marker(item: Dict[str, Any]) -> bool:
        """Check if item is a time marker."""
        return "time" in item and item.get("time") is not None
    
    @staticmethod
    def is_code(item: Dict[str, Any]) -> bool:
        """Check if item is a meal code."""
        return "code" in item and item.get("code") is not None
    
    @staticmethod
    def get_codes_only(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter items to only meal codes (exclude time markers)."""
        return [it for it in items if CodeParser.is_code(it)]
    
    @staticmethod
    def get_time_markers(items: List[Dict[str, Any]]) -> List[str]:
        """Extract all time markers from items."""
        return [it["time"] for it in items if CodeParser.is_time_marker(it)]