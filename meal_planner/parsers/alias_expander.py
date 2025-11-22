# meal_planner/parsers/alias_expander.py
"""
Alias expansion utilities.
"""
from typing import List, Dict, Any, Optional
from meal_planner.parsers.code_parser import CodeParser


def expand_aliases(codes_str: str, alias_manager) -> List[Dict[str, Any]]:
    """
    Parse codes string and expand any aliases.
    
    Args:
        codes_str: Codes string that may contain aliases
        alias_manager: AliasManager instance
    
    Returns:
        List of expanded items
    """
    if not alias_manager:
        return CodeParser.parse(codes_str)
    
    # First parse to get initial items
    items = CodeParser.parse(codes_str)
    
    # Expand any aliases
    expanded = []
    for item in items:
        if "code" in item:
            code = item["code"]
            alias_data = alias_manager.lookup_alias(code)
            
            if alias_data:
                # It's an alias - expand it
                alias_codes = alias_data.get("codes", "")
                alias_items = CodeParser.parse(alias_codes)
                expanded.extend(alias_items)
            else:
                # Regular code
                expanded.append(item)
        else:
            # Time marker or other
            expanded.append(item)
    
    return expanded