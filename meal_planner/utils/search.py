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
    Parse search query into clauses with boolean logic.
    
    Returns list of clauses where:
    - Clauses are OR-ed together
    - Within a clause, positive terms are AND-ed, negative terms are NOT-ed
    - Spaces = AND, explicit AND/OR/NOT supported
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
    """
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
        tokens.append(t.upper() if t.lower() in ops else t)
    
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