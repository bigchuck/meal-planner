"""
Search/find command for querying the master database.
"""
from .base import Command, register_command
from meal_planner.utils import ColumnResolver


@register_command
class FindCommand(Command):
    """Search the master database."""
    
    name = "find"
    help_text = "Search master database (e.g., find chicken)"
    
    def execute(self, args: str) -> None:
        """
        Search master for term.
        
        Args:
            args: Search term
        """
        if not args.strip():
            print("Usage: find <search term>")
            return
        
        query = args.strip()
        results = self.ctx.master.search(query)
        
        if results.empty:
            print(f"\nNo matches found for '{query}'.\n")
            return
        
        # Format results
        print(f"\nSearch results for '{query}':")
        print(self._format_results(results))
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