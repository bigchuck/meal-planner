"""
Advanced search utilities with boolean logic support.
"""
import re
import string
import pandas as pd
from typing import List, Dict, Tuple

from .columns import ColumnResolver


# Regex for tokenizing (quoted strings or words)
TOKEN_RE = re.compile(r'"([^"]+)"|(\S+)', re.IGNORECASE)


def normalize_text_for_search(s: pd.Series) -> pd.Series:
    """
    Normalize text for search: lowercase, remove punctuation.
    
    Args:
        s: Pandas Series of text
    
    Returns:
        Normalized Series
    """
    table = str.maketrans("", "", string.punctuation)
    return s.astype(str).str.lower().str.translate(table)


def parse_search_query(query: str) -> List[Dict[str, List[str]]]:
    """
    Parse search query into clauses with boolean logic and parenthetical grouping.
    
    Returns list of clauses where:
    - Clauses are OR-ed together
    - Within a clause, positive terms are AND-ed, negative terms are NOT-ed
    - Spaces = AND, explicit AND/OR/NOT supported
    - Parentheses group expressions
    - Quoted strings = exact phrases
    
    Args:
        query: Search query string
    
    Returns:
        List of clause dicts with 'pos' and 'neg' term lists
    
    Examples:
        >>> parse_search_query("chicken")
        [{'pos': ['chicken'], 'neg': []}]
        
        >>> parse_search_query("green beans")
        [{'pos': ['green', 'beans'], 'neg': []}]
        
        >>> parse_search_query('"green beans"')
        [{'pos': ['green beans'], 'neg': []}]
        
        >>> parse_search_query("chicken OR fish")
        [{'pos': ['chicken'], 'neg': []}, {'pos': ['fish'], 'neg': []}]
        
        >>> parse_search_query("beans NOT green")
        [{'pos': ['beans'], 'neg': ['green']}]
        
        >>> parse_search_query("ve. and (carrot or celery)")
        [{'pos': ['ve.', 'carrot'], 'neg': []}, {'pos': ['ve.', 'celery'], 'neg': []}]
    """
    # CRITICAL: Add spaces around parentheses so they tokenize separately
    query = query.replace('(', ' ( ').replace(')', ' ) ')
    
    # Tokenize (handles quoted strings)
    raw_tokens = []
    for match in TOKEN_RE.finditer(query):
        # match.group(1) = quoted, match.group(2) = unquoted
        token = match.group(1) if match.group(1) else match.group(2)
        raw_tokens.append(token)
    
    # Normalize operators (but keep original case for non-operators)
    ops = {"and", "or", "not"}
    tokens = []
    for t in raw_tokens:
        if t.lower() in ops:
            tokens.append(t.upper())
        elif t in ("(", ")"):
            tokens.append(t)  # Keep parentheses as-is
        else:
            tokens.append(t)
    
    # Parse with parenthetical grouping support
    try:
        expr, final_pos = _parse_or(tokens, 0)
        
        # Verify we consumed all tokens
        if final_pos != len(tokens):
            return _parse_simple(tokens)
        
        # Convert expression tree to DNF (Disjunctive Normal Form)
        # Then extract clauses
        return _expression_to_clauses(expr)
    except Exception:
        # Fallback to original simple parsing on error
        return _parse_simple(tokens)


def _parse_or(tokens: List[str], pos: int) -> Tuple[Dict, int]:
    """Parse OR level (lowest precedence)."""
    left, pos = _parse_and(tokens, pos)
    
    while pos < len(tokens) and tokens[pos] == "OR":
        pos += 1  # Skip OR
        right, pos = _parse_and(tokens, pos)
        left = {'op': 'OR', 'left': left, 'right': right}
    
    return left, pos


def _parse_and(tokens: List[str], pos: int) -> Tuple[Dict, int]:
    """Parse AND level."""
    left, pos = _parse_not(tokens, pos)
    
    while pos < len(tokens) and tokens[pos] not in ("OR", ")"):
        # Check for explicit AND
        if tokens[pos] == "AND":
            pos += 1  # Skip explicit AND
            if pos >= len(tokens):
                break
        
        # Next token should be a term/expression
        right, pos = _parse_not(tokens, pos)
        left = {'op': 'AND', 'left': left, 'right': right}
    
    return left, pos


def _parse_not(tokens: List[str], pos: int) -> Tuple[Dict, int]:
    """Parse NOT level."""
    if pos < len(tokens) and tokens[pos] == "NOT":
        pos += 1  # Skip NOT
        expr, pos = _parse_primary(tokens, pos)
        return {'op': 'NOT', 'expr': expr}, pos
    
    return _parse_primary(tokens, pos)


def _parse_primary(tokens: List[str], pos: int) -> Tuple[Dict, int]:
    """Parse primary expression (term or parenthesized expression)."""
    if pos >= len(tokens):
        raise ValueError("Unexpected end of expression")
    
    token = tokens[pos]
    
    if token == "(":
        # Parenthesized expression
        pos += 1  # Skip (
        expr, pos = _parse_or(tokens, pos)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ValueError("Missing closing parenthesis")
        pos += 1  # Skip )
        return expr, pos
    elif token in (")", "OR", "AND", "NOT"):
        raise ValueError(f"Unexpected token: {token}")
    else:
        # Regular term
        return {'op': 'TERM', 'term': token}, pos + 1


def _expression_to_clauses(expr: Dict) -> List[Dict[str, List[str]]]:
    """
    Convert expression tree to list of clauses (DNF - Disjunctive Normal Form).
    
    Each clause is {'pos': [...], 'neg': [...]}
    Clauses are OR-ed together, terms within are AND-ed.
    """
    # Convert to DNF (distribute ANDs over ORs)
    dnf = _to_dnf(expr)
    
    # Extract clauses
    if dnf['op'] == 'OR':
        # Multiple clauses
        clauses = []
        _collect_or_clauses(dnf, clauses)
        return [_clause_from_and_expr(c) for c in clauses]
    else:
        # Single clause
        return [_clause_from_and_expr(dnf)]


def _to_dnf(expr: Dict) -> Dict:
    """Convert expression to Disjunctive Normal Form."""
    op = expr['op']
    
    if op == 'TERM':
        return expr
    
    elif op == 'NOT':
        # Push NOT down to terms (De Morgan's laws)
        inner = _to_dnf(expr['expr'])
        if inner['op'] == 'TERM':
            return {'op': 'NOT_TERM', 'term': inner['term']}
        elif inner['op'] == 'NOT_TERM':
            return {'op': 'TERM', 'term': inner['term']}
        elif inner['op'] == 'AND':
            # NOT (A AND B) = (NOT A) OR (NOT B)
            left = _to_dnf({'op': 'NOT', 'expr': inner['left']})
            right = _to_dnf({'op': 'NOT', 'expr': inner['right']})
            return _to_dnf({'op': 'OR', 'left': left, 'right': right})
        elif inner['op'] == 'OR':
            # NOT (A OR B) = (NOT A) AND (NOT B)
            left = _to_dnf({'op': 'NOT', 'expr': inner['left']})
            right = _to_dnf({'op': 'NOT', 'expr': inner['right']})
            return _to_dnf({'op': 'AND', 'left': left, 'right': right})
        return inner
    
    elif op == 'AND':
        left = _to_dnf(expr['left'])
        right = _to_dnf(expr['right'])
        
        # Distribute over OR: A AND (B OR C) = (A AND B) OR (A AND C)
        if right['op'] == 'OR':
            # A AND (B OR C) = (A AND B) OR (A AND C)
            l_and_rl = {'op': 'AND', 'left': left, 'right': right['left']}
            l_and_rr = {'op': 'AND', 'left': left, 'right': right['right']}
            # Recursively convert the distributed parts
            return _to_dnf({'op': 'OR', 'left': _to_dnf(l_and_rl), 'right': _to_dnf(l_and_rr)})
        elif left['op'] == 'OR':
            # (A OR B) AND C = (A AND C) OR (B AND C)
            ll_and_r = {'op': 'AND', 'left': left['left'], 'right': right}
            lr_and_r = {'op': 'AND', 'left': left['right'], 'right': right}
            # Recursively convert the distributed parts
            return _to_dnf({'op': 'OR', 'left': _to_dnf(ll_and_r), 'right': _to_dnf(lr_and_r)})
        else:
            return {'op': 'AND', 'left': left, 'right': right}
    
    elif op == 'OR':
        left = _to_dnf(expr['left'])
        right = _to_dnf(expr['right'])
        return {'op': 'OR', 'left': left, 'right': right}
    
    return expr


def _collect_or_clauses(expr: Dict, clauses: List[Dict]) -> None:
    """Collect OR-separated clauses."""
    if expr['op'] == 'OR':
        _collect_or_clauses(expr['left'], clauses)
        _collect_or_clauses(expr['right'], clauses)
    else:
        clauses.append(expr)


def _clause_from_and_expr(expr: Dict) -> Dict[str, List[str]]:
    """Extract clause (pos/neg lists) from AND expression."""
    pos = []
    neg = []
    _collect_and_terms(expr, pos, neg)
    return {'pos': pos, 'neg': neg}


def _collect_and_terms(expr: Dict, pos: List[str], neg: List[str]) -> None:
    """Collect AND-ed terms."""
    op = expr['op']
    
    if op == 'TERM':
        pos.append(expr['term'])
    elif op == 'NOT_TERM':
        neg.append(expr['term'])
    elif op == 'AND':
        _collect_and_terms(expr['left'], pos, neg)
        _collect_and_terms(expr['right'], pos, neg)
    # OR at this level shouldn't happen in DNF, but ignore if it does


def _parse_simple(tokens: List[str]) -> List[Dict[str, List[str]]]:
    """
    Fallback simple parser (original behavior without parentheses).
    Used if expression parsing fails.
    """
    # Split on OR into clauses
    clauses = []
    current = {"pos": [], "neg": []}
    negate_next = False
    i = 0
    
    while i < len(tokens):
        t = tokens[i]
        
        if t == "OR":
            # Finish current clause
            if current["pos"] or current["neg"]:
                clauses.append(current)
            current = {"pos": [], "neg": []}
            negate_next = False
            i += 1
            continue
        
        elif t == "AND":
            # AND is implicit, just skip
            i += 1
            continue
        
        elif t == "NOT":
            negate_next = True
            i += 1
            continue
        
        elif t in ("(", ")"):
            # Ignore parentheses in fallback mode
            i += 1
            continue
        
        else:
            # Regular term
            if negate_next:
                current["neg"].append(t)
                negate_next = False
            else:
                current["pos"].append(t)
            i += 1
    
    # Don't forget last clause
    if current["pos"] or current["neg"]:
        clauses.append(current)
    
    # If no operators provided, treat as single AND clause
    if not clauses:
        clauses = [{"pos": [], "neg": []}]
    
    return clauses


def match_term_in_dataframe(df: pd.DataFrame, term: str, cols: ColumnResolver) -> pd.Series:
    """
    Create boolean mask for term matching in DataFrame.
    
    Code-aware:
    - Terms with "." are treated as code prefixes (e.g., "fr." matches "FR.1")
    - Other terms search all columns (code, section, option)
    
    Args:
        df: DataFrame to search
        term: Search term (case-insensitive)
        cols: Column resolver
    
    Returns:
        Boolean Series (mask)
    """
    term_lower = term.lower().strip()
    
    # Build searchable columns
    search_code = df[cols.code].astype(str).str.lower()
    search_section = df[cols.section].astype(str).str.lower()
    search_option = df[cols.option].astype(str).str.lower()
    
    # Code pattern (contains a dot)
    if '.' in term_lower:
        # Match code prefix (startswith)
        term_escaped = re.escape(term_lower)
        return search_code.str.match(f'^{term_escaped}', na=False)
    
    # General text search (all columns, punctuation removed)
    search_all = normalize_text_for_search(
        search_code + " " + search_section + " " + search_option
    )
    term_normalized = term_lower.translate(str.maketrans("", "", string.punctuation))
    
    return search_all.str.contains(re.escape(term_normalized), na=False)


def hybrid_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """
    Execute hybrid search with boolean logic on DataFrame.
    
    Args:
        df: Master DataFrame to search
        query: Search query with optional boolean operators
    
    Returns:
        Filtered DataFrame
    
    Examples:
        >>> hybrid_search(master, "chicken")
        >>> hybrid_search(master, "green beans")  # AND
        >>> hybrid_search(master, '"green beans"')  # exact phrase
        >>> hybrid_search(master, "chicken OR fish")
        >>> hybrid_search(master, "beans NOT green")
        >>> hybrid_search(master, "fr.")  # code prefix
        >>> hybrid_search(master, "ve. and (carrot or celery)")  # grouped
    """
    if df.empty:
        return df
    
    cols = ColumnResolver(df)
    clauses = parse_search_query(query)
    
    if not clauses:
        return df
    
    # OR together all clauses
    overall_mask = pd.Series([False] * len(df))
    
    for clause in clauses:
        # Start with all True for this clause
        clause_mask = pd.Series([True] * len(df))
        
        # AND all positive terms
        for term in clause["pos"]:
            clause_mask &= match_term_in_dataframe(df, term, cols)
        
        # NOT all negative terms
        for term in clause["neg"]:
            clause_mask &= ~match_term_in_dataframe(df, term, cols)
        
        # OR this clause with overall
        overall_mask |= clause_mask
    
    return df[overall_mask].copy()