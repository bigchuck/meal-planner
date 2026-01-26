"""
Search/find command for querying the master database.
"""
from typing import List, Dict, Any, Optional

from .base import Command, register_command
from meal_planner.utils import ColumnResolver


@register_command
class FindCommand(Command):
    """Search the master database."""
    
    name = ("find", "f")
    help_text = "Search master database (e.g., find chicken [--limit N] [--skip N] [--available])"
    
    def execute(self, args: str) -> None:
        """
        Search master for term.
        
        Args:
            args: Search term with optional flags:
                --limit N: Show only N results
                --skip N: Skip first N results  
                --available: Filter to items in inventory (batch items only)
        """
        if not args.strip():
            print("Usage: find <search term> [--limit N] [--skip N] [--available]")
            return
        
        # Parse flags
        import shlex
        try:
            parts = shlex.split(args.strip())
        except ValueError:
            parts = args.strip().split()
        
        limit = None
        skip = 0
        available_only = False
        query_parts = []
        
        i = 0
        while i < len(parts):
            if parts[i] == "--limit" and i + 1 < len(parts):
                try:
                    limit = int(parts[i + 1])
                    if limit < 0:
                        print("Error: --limit must be non-negative")
                        return
                    i += 2
                except ValueError:
                    print(f"Error: --limit requires a number, got '{parts[i + 1]}'")
                    return
            elif parts[i] == "--skip" and i + 1 < len(parts):
                try:
                    skip = int(parts[i + 1])
                    if skip < 0:
                        print("Error: --skip must be non-negative")
                        return
                    i += 2
                except ValueError:
                    print(f"Error: --skip requires a number, got '{parts[i + 1]}'")
                    return
            elif parts[i] == "--available":
                available_only = True
                i += 1
            else:
                query_parts.append(parts[i])
                i += 1
        
        if not query_parts:
            print("Usage: find <search term> [--limit N] [--skip N] [--available]")
            return
        
        query = ' '.join(query_parts)
        results = self.ctx.master.search(query)

        # Also search aliases if available
        alias_results = []
        if self.ctx.aliases:
            alias_results = self.ctx.aliases.search(query)

        # Filter for inventory if requested
        if available_only:
            results = self._filter_available(results)
            # Don't filter aliases - they're just shortcuts
        
        if results.empty and not alias_results:
            print(f"\nNo matches found for '{query}'.\n")
            return
        
        # Count total before pagination
        total_results = len(results) + len(alias_results)
        
        # Apply pagination to results
        if not results.empty:
            # Skip
            if skip > 0:
                results = results.iloc[skip:]
            
            # Limit
            if limit is not None:
                results = results.iloc[:limit]
        
        # Apply pagination to alias results
        if alias_results:
            # For aliases, we need to handle them as a list
            remaining_skip = max(0, skip - len(results) if skip > len(results) else 0)
            alias_results = alias_results[remaining_skip:]
            
            if limit is not None:
                remaining_limit = limit - len(results)
                if remaining_limit > 0:
                    alias_results = alias_results[:remaining_limit]
                else:
                    alias_results = []
        
        # Calculate range for display message
        start_idx = skip + 1
        end_idx = skip + len(results) + len(alias_results)
        
        # Format results
        print(f"\nSearch results for '{query}':")
        
        # Show pagination info
        if total_results > 0:
            if limit is not None or skip > 0:
                print(f"Showing {start_idx}-{end_idx} of {total_results} results")
            else:
                print(f"Showing all {total_results} results")
        
        if available_only:
            print("(filtered to inventory batch items)")
        
        print()

        if not results.empty:
            print(self._format_results(results))

        if alias_results:
            print(self._format_alias_results(alias_results))

        print()

    def _format_results(self, df) -> str:
        """
        Format search results for display.
        
        Args:
            df: DataFrame of results
        
        Returns:
            Formatted string
        """
        if df.empty:
            return "(no matches)"
        
        cols = ColumnResolver(df)
        
        lines = []
        for _, row in df.iterrows():
            code = str(row[cols.code])
            section = str(row[cols.section])
            option = str(row[cols.option])
            cal = row[cols.cal]
            prot = row[cols.prot_g]
            carb = row[cols.carbs_g]
            fat = row[cols.fat_g]
            
            # Build nutrition string
            nutr_parts = [f"cal={cal}", f"P={prot}", f"C={carb}", f"F={fat}"]
            
            # Add GI/GL if present
            if cols.gi and row[cols.gi] == row[cols.gi]:  # not NaN
                nutr_parts.append(f"GI={int(row[cols.gi])}")
            if cols.gl and row[cols.gl] == row[cols.gl]:
                nutr_parts.append(f"GL={int(row[cols.gl])}")
            
            # Add sugar if present
            if cols.sugar_g and row[cols.sugar_g] == row[cols.sugar_g]:
                nutr_parts.append(f"Sugars={int(row[cols.sugar_g])}")
            
            nutr_str = " ".join(nutr_parts)
            
            lines.append(
                f"  {code:>8} | {section:<7} | {option} [{nutr_str}]"
            )
        
        return "\n".join(lines)
    
    def _format_alias_results(self, results: List[tuple]) -> str:
        """Format alias search results."""
        if not results:
            return ""
        
        lines = []
        for code, alias_data in results:
            name = alias_data.get('name', '')
            codes = alias_data.get('codes', '')
            lines.append(f"  {code:>8} | ALIAS    | {name} [expands to: {codes}]")
        
        return "\n".join(lines)
    
    def _filter_available(self, df):
        """
        Filter results to only items in inventory (batch items).
        
        Args:
            df: DataFrame of search results
        
        Returns:
            Filtered DataFrame
        """
        if df.empty:
            return df
        
        # Try to load workspace to get inventory
        try:
            workspace_data = self.ctx.workspace_mgr.load()
            inventory = workspace_data.get("inventory", {})
            batch_items = inventory.get("batch", {})
            
            if not batch_items:
                # No batch items, return empty
                return df.iloc[0:0]  # Empty dataframe with same structure
            
            # Get codes from batch inventory
            batch_codes = set(code.upper() for code in batch_items.keys())
            
            # Filter dataframe
            cols = self.ctx.master.cols
            mask = df[cols.code].str.upper().isin(batch_codes)
            
            return df[mask]
        
        except Exception as e:
            print(f"\nWarning: Could not access inventory: {e}")
            return df