"""
Order command - rank foods by nutrient content.
"""
from typing import Optional, Tuple, List
import pandas as pd

from .base import Command, register_command


@register_command
class OrderCommand(Command):
    """Rank foods by nutrient content."""
    
    name = "order"
    help_text = "Rank foods by nutrient (order for help)"
    
    # Available nutrients
    MACROS = ['cal', 'prot_g', 'carbs_g', 'fat_g', 'sugar_g', 'gl', 'gi']
    MICROS = ['fiber_g', 'sodium_mg', 'potassium_mg', 'vitA_mcg', 'vitC_mg', 'iron_mg']
    
    def execute(self, args: str) -> None:
        """Execute order command."""
        if not args.strip():
            self._show_help()
            return
        
        # Parse arguments
        try:
            per100cal, nutrient_expr, direction, limit, search_query = self._parse_args(args)
        except ValueError as e:
            print(f"\nError: {e}\n")
            print("Use 'order' with no arguments for help.\n")
            return
        
        # Validate nutrient expression
        try:
            is_ratio, fields = self._parse_nutrient_expr(nutrient_expr)
        except ValueError as e:
            print(f"\nError: {e}\n")
            return
        
        if is_ratio and per100cal:
            print("\nError: --per100cal cannot be used with ratio expressions.\n")
            return
        
        # Validate fields exist
        for field in fields:
            if not self._validate_nutrient(field):
                print(f"\nError: Unknown nutrient '{field}'")
                print(f"Available macros: {', '.join(self.MACROS)}")
                print(f"Available micros: {', '.join(self.MICROS)}\n")
                return
        
        # Get data
        master_df = self.ctx.master.df.copy()
        
        # Apply search filter if provided
        if search_query:
            import shlex
            try:
                query_parts = shlex.split(search_query)
            except ValueError:
                query_parts = search_query.split()
            
            query = self._transform_code_list(query_parts)

            from meal_planner.utils.search import hybrid_search
            master_df = hybrid_search(master_df, search_query)
            
            if master_df.empty:
                print(f"\nNo results found for search: '{search_query}'\n")
                return
        
        # Calculate target metric for each row
        results = []
        cols = self.ctx.master.cols
        
        for idx, row in master_df.iterrows():
            code = row[cols.code]
            
            # Get values for calculation
            values = {}
            all_valid = True
            
            for field in fields:
                val = self._get_nutrient_value(row, field)
                if val is None or pd.isna(val):
                    all_valid = False
                    break
                values[field] = float(val)
            
            if not all_valid:
                continue
            
            # Calculate metric
            if is_ratio:
                numerator = values[fields[0]]
                denominator = values[fields[1]]
                if denominator == 0:
                    continue
                metric = numerator / denominator
            else:
                metric = values[fields[0]]
            
            # Apply per-100-cal normalization if requested
            if per100cal:
                cal = float(row[cols.cal]) if pd.notna(row[cols.cal]) else 0
                if cal == 0:
                    continue
                metric = (metric / cal) * 100
            
            results.append({
                'code': code,
                'section': row[cols.section],
                'option': row[cols.option],
                'metric': metric
            })
        
        if not results:
            print(f"\nNo valid results found (codes may be missing '{nutrient_expr}' data).\n")
            return
        
        # Sort
        reverse = (direction == '-d')
        results.sort(key=lambda x: x['metric'], reverse=reverse)
        
        # Limit
        results = results[:limit]
        
        # Display
        self._display_results(results, nutrient_expr, direction, search_query, per100cal)
    
    def _parse_args(self, args: str) -> Tuple[bool, str, str, int, str]:
        """
        Parse command arguments.
        
        Returns:
            (per100cal_flag, nutrient_expr, direction, limit, search_query)
        
        Raises:
            ValueError: If arguments are invalid
        """
        tokens = args.strip().split()
        
        # Check for --per100cal flag
        per100cal = False
        if tokens and tokens[0] == '--per100cal':
            per100cal = True
            tokens = tokens[1:]
        
        # Need at least 3 tokens: nutrient, direction, limit
        if len(tokens) < 3:
            raise ValueError("Missing required arguments")
        
        nutrient_expr = tokens[0]
        direction = tokens[1]
        
        # Validate direction
        if direction not in ['-d', '-a']:
            raise ValueError(f"Direction must be -d or -a, got '{direction}'")
        
        # Parse limit
        try:
            limit = int(tokens[2])
            if limit <= 0:
                raise ValueError("Limit must be positive")
        except ValueError:
            raise ValueError(f"Limit must be a positive integer, got '{tokens[2]}'")
        
        # Everything after limit is search query
        search_query = ' '.join(tokens[3:]) if len(tokens) > 3 else ''
        
        return per100cal, nutrient_expr, direction, limit, search_query

    def _transform_code_list(self, query_parts: List[str]) -> str:
        """Transform comma-separated code list into OR expression."""
        joined = ' '.join(query_parts)
        
        if ',' in joined:
            codes = [part.strip() for part in joined.split(',')]
            
            import re
            code_pattern = re.compile(r'^[A-Z]{2,3}\.[A-Za-z0-9]+$', re.IGNORECASE)
            
            if all(code_pattern.match(code) for code in codes if code):
                return ' OR '.join(codes)
        
        return ' '.join(query_parts)
    
    def _parse_nutrient_expr(self, expr: str) -> Tuple[bool, List[str]]:
        """
        Parse nutrient expression into fields.
        
        Returns:
            (is_ratio, [field1, field2]) or (False, [field])
        
        Raises:
            ValueError: If expression format is invalid
        """
        if '/' in expr:
            parts = expr.split('/')
            if len(parts) != 2:
                raise ValueError(f"Invalid ratio format: '{expr}'")
            if not parts[0].strip() or not parts[1].strip():
                raise ValueError(f"Invalid ratio format: '{expr}'")
            return True, [parts[0].strip(), parts[1].strip()]
        else:
            return False, [expr.strip()]
    
    def _validate_nutrient(self, field: str) -> bool:
        """Check if nutrient field is valid."""
        return field in self.MACROS or field in self.MICROS
    
    def _get_nutrient_value(self, row: pd.Series, field: str):
        """Get nutrient value from row, checking both master and nutrients."""
        cols = self.ctx.master.cols
        
        # Check master columns first
        master_mapping = {
            'cal': cols.cal,
            'prot_g': cols.prot_g,
            'carbs_g': cols.carbs_g,
            'fat_g': cols.fat_g,
            'sugar_g': cols.sugar_g,
            'gl': cols.gl,
            'gi': cols.gi,
        }
        
        if field in master_mapping:
            col = master_mapping[field]
            return row.get(col)
        
        # Check micronutrients
        if field in self.MICROS and self.ctx.master:
            code = row[cols.code]
            nutrients = self.ctx.master.get_nutrients(code)
            if nutrients:
                return nutrients.get(field)
        
        return None
    
    def _display_results(self, results: List[dict], nutrient_expr: str, 
                        direction: str, search_query: str, per100cal: bool):
        """Display formatted results."""
        dir_label = "descending" if direction == '-d' else "ascending"
        
        # Build title
        if per100cal:
            title = f"=== Top {len(results)} by {nutrient_expr} per 100 cal ({dir_label}) ==="
        else:
            title = f"=== Top {len(results)} by {nutrient_expr} ({dir_label}) ==="
        
        print(f"\n{title}")
        
        if search_query:
            print(f'Search: "{search_query}"')
        
        print()
        
        # Determine column header and format
        if '/' in nutrient_expr:
            metric_header = nutrient_expr
            metric_format = lambda x: f"{x:.3f}"
        else:
            # Extract unit from field name (e.g., fiber_g -> g, sodium_mg -> mg)
            if '_' in nutrient_expr:
                unit = nutrient_expr.split('_')[1]
                if per100cal:
                    metric_header = f"{nutrient_expr} (per 100 cal)"
                else:
                    metric_header = f"{nutrient_expr} ({unit})"
            else:
                metric_header = nutrient_expr
            
            metric_format = lambda x: f"{x:.1f}"
        
        # Header
        print(f"{'Rank':>4}  {'Code':<10} {'Section':<8} {metric_header:>15}    {'Option'}")
        print("─" * 80)
        
        # Rows
        for rank, result in enumerate(results, 1):
            code = result['code']
            section = str(result['section'])[:8]
            option = result['option']
            metric = metric_format(result['metric'])
            
            print(f"{rank:>4}  {code:<10} {section:<8} {metric:>15}    {option}")
        
        print()
    
    def _show_help(self):
        """Display help information."""
        print("""
Usage: order [--per100cal] <nutrient_expr> <-d|-a> <limit> [search_query]

Flags:
  --per100cal    Normalize values to per 100 calories

Nutrient Expressions:
  Macros:  cal, prot_g, carbs_g, fat_g, sugar_g, gl, gi
  Micros:  fiber_g, sodium_mg, potassium_mg, vitA_mcg, vitC_mg, iron_mg
  Ratios:  <nutrient>/<nutrient> (no spaces, e.g., prot_g/cal)

Direction:
  -d    Descending (highest first)
  -a    Ascending (lowest first)

Limit:
  Number of results to show (use 99999 for unlimited)

Search Query:
  Optional filter using 'find' syntax
  Supports: code patterns, boolean logic (AND, OR, NOT), text search
  If omitted: searches entire database

Examples:
  order fiber_g -d 15 ve.
  order prot_g/cal -d 20 chicken OR fish
  order --per100cal sugar_g -a 99999
  order gl -a 10 "st. NOT potato"
""")