"""
Affinity tag parsing for recipe strings.

Affinity tags are embedded at the start of recipe strings using bracket notation:
    [pair:item1,item2][best-with:item3][avoid:item4][profile:tag1,tag2]

These tags describe pairing affinity metadata and are separate from ingredients.
"""
import re
from typing import Dict, List, Optional

# Regex to extract all [key:value] tags
_TAG_RE = re.compile(r'\[([a-zA-Z-]+):([^\]]*)\]')

# Known affinity tag names
AFFINITY_TAGS = ('pair', 'best-with', 'avoid', 'profile')


def parse_affinities(recipe_str: str) -> Dict[str, List[str]]:
    """
    Extract affinity tags from a recipe string.

    Args:
        recipe_str: Raw recipe string (may contain [tag:...] prefixes)

    Returns:
        Dict with keys 'pair', 'best-with', 'avoid', 'profile'.
        Each value is a list of strings (empty list if tag not present).

    Example:
        >>> parse_affinities("[pair:chicken,pork][avoid:fish],1T yogurt,1t harissa")
        {'pair': ['chicken', 'pork'], 'best-with': [], 'avoid': ['fish'], 'profile': []}
    """
    result: Dict[str, List[str]] = {tag: [] for tag in AFFINITY_TAGS}

    if not recipe_str:
        return result

    for match in _TAG_RE.finditer(recipe_str):
        key = match.group(1).lower()
        values_str = match.group(2).strip()
        if key in result:
            values = [v.strip() for v in values_str.split(',') if v.strip()]
            result[key] = values

    return result


def strip_affinities(recipe_str: str) -> str:
    """
    Remove all affinity tag blocks from a recipe string, returning only ingredients.

    Args:
        recipe_str: Raw recipe string

    Returns:
        Ingredient-only portion, stripped of leading/trailing whitespace and commas.

    Example:
        >>> strip_affinities("[pair:chicken][avoid:fish],1T yogurt,1t harissa")
        '1T yogurt,1t harissa'
    """
    if not recipe_str:
        return recipe_str or ''

    cleaned = _TAG_RE.sub('', recipe_str)
    # Strip leading comma/whitespace that may remain after tag removal
    cleaned = cleaned.lstrip(',').strip()
    return cleaned


def has_affinities(recipe_str: str) -> bool:
    """
    Return True if the recipe string contains any affinity tags.

    Args:
        recipe_str: Raw recipe string

    Returns:
        True if at least one affinity tag is present
    """
    if not recipe_str:
        return False
    return bool(_TAG_RE.search(recipe_str))


def affinity_matches(recipe_str: str, tag: str, term: str, pattern: bool = False) -> bool:
    """
    Check whether a recipe string's affinity tag contains a given term.

    Args:
        recipe_str: Raw recipe string
        tag:        Affinity tag name ('pair', 'best-with', 'avoid', 'profile')
        term:       Value to search for (case-insensitive)
        pattern:    If True, treat term as a glob-style pattern (e.g. 'med*')
                    using fnmatch.  If False, exact element match.

    Returns:
        True if the tag's value list contains the term (or matches the pattern)
    """
    affinities = parse_affinities(recipe_str)
    values = affinities.get(tag, [])

    if not values:
        return False

    term_lower = term.lower()

    if pattern:
        import fnmatch
        return any(fnmatch.fnmatch(v.lower(), term_lower) for v in values)
    else:
        return any(term_lower in v.lower() for v in values)