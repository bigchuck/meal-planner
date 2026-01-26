# meal_planner/commands/materialize_command.py
"""
Materialize command - convert aliases to master entries or create scaled portions.

Converts aliases into concrete master.csv entries with calculated nutrition,
or creates scaled versions of existing master entries.
"""
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import pandas as pd
from .base import Command, register_command
from .data_management import create_backup, natural_sort_key
from meal_planner.parsers.code_parser import parse_one_code_mult, eval_multiplier_expression


@register_command
class MaterializeCommand(Command):
    """Materialize alias or create scaled master entry."""
    
    name = "materialize"
    help_text = "Materialize alias or scale master entry (materialize CODE [mult] [as NEW.CODE])"
    
    def execute(self, args: str) -> None:
        """
        Materialize alias or scale master entry.
        
        Syntax:
            materialize <source_code> [multiplier] [as NEW.CODE]
            
        Preview mode (no "as"): Shows what will be created
        Execution mode (with "as"): Creates the entry
        
        Args:
            args: Command arguments
        """
        if not args.strip():
            print("Usage: materialize <source_code> [multiplier] [as NEW.CODE]")
            print("\nPreview mode (shows what will be created):")
            print("  materialize AL.4")
            print("  materialize SO.19d 0.5")
            print("\nExecution mode (creates entry):")
            print("  materialize AL.4 as CM.5")
            print("  materialize SO.19d 0.5 as SO.19e")
            return
        
        # Parse arguments
        parts = args.strip().split()
        
        # Extract source code
        source_code = parts[0].upper()
        
        # Check for "as" keyword
        as_index = None
        for i, part in enumerate(parts[1:], 1):
            if part.lower() == "as":
                as_index = i
                break
        
        # Extract multiplier and target code
        multiplier = 1.0
        target_code = None
        
        if as_index:
            # Execution mode
            if as_index + 1 >= len(parts):
                print("\nError: Missing target code after 'as'")
                print("Usage: materialize <source> [mult] as <target>")
                print()
                return
            
            target_code = parts[as_index + 1].upper()
            
            # Multiplier is between source and "as" (if present)
            if as_index > 1:
                mult_str = parts[1]
                multiplier = self._parse_multiplier(mult_str)
                if multiplier is None:
                    return
        else:
            # Preview mode
            if len(parts) > 1:
                mult_str = parts[1]
                multiplier = self._parse_multiplier(mult_str)
                if multiplier is None:
                    return
        
        # Determine if source is alias or master entry
        is_alias = self.ctx.aliases and self.ctx.aliases.has_alias(source_code)
        is_master = self.ctx.master.lookup_code(source_code) is not None
        
        if not is_alias and not is_master:
            print(f"\nError: '{source_code}' not found as alias or master entry")
            print()
            return
        
        # For master entries, multiplier is required even in preview mode
        if is_master and not is_alias and multiplier == 1.0 and len(parts) == 1:
            print(f"\nError: Multiplier required for scaling master entries")
            print(f"Usage: materialize {source_code} <multiplier> [as NEW.CODE]")
            print("Example: materialize SO.19d 0.5")
            print()
            return
        
        if target_code:
            # Execution mode
            self._execute_materialize(source_code, multiplier, target_code, is_alias)
        else:
            # Preview mode
            self._preview_materialize(source_code, multiplier, is_alias)
    
    def _parse_multiplier(self, mult_str: str) -> Optional[float]:
        """Parse multiplier string into float."""
        # Handle leading dot
        if mult_str.startswith("."):
            mult_str = "0" + mult_str
        
        # Try as bare expression first
        try:
            multiplier = eval_multiplier_expression(mult_str)
            if multiplier > 0:
                return multiplier
        except:
            pass
        
        # Try with prefix
        test_snippet = f"DUM.MY {mult_str}"
        parsed = parse_one_code_mult(test_snippet)
        
        if parsed and 'mult' in parsed:
            multiplier = parsed['mult']
            if multiplier > 0:
                return multiplier
        
        print(f"\nError: Invalid multiplier '{mult_str}'")
        print("Supported formats: 1.5, 0.225, 1/7, .9/4, x1/7, *1/7")
        print()
        return None
    
    def _preview_materialize(self, source_code: str, multiplier: float, is_alias: bool) -> None:
        """Show preview of what will be materialized."""
        if is_alias:
            self._preview_alias(source_code, multiplier)
        else:
            self._preview_master(source_code, multiplier)
    
    def _preview_alias(self, alias_code: str, multiplier: float) -> None:
        """Preview materializing an alias."""
        alias_data = self.ctx.aliases.lookup_alias(alias_code)
        if not alias_data:
            print(f"\nError: Alias '{alias_code}' not found")
            print()
            return
        
        # Parse alias components
        from meal_planner.parsers import CodeParser
        codes_str = alias_data.get('codes', '')
        components = CodeParser.parse(codes_str)
        
        # Resolve components and calculate nutrition
        print(f"\nAlias {alias_code} resolves to:")
        
        total_nutrition = {
            'cal': 0, 'prot_g': 0, 'carbs_g': 0, 'fat_g': 0,
            'GI': 0, 'GL': 0, 'sugar_g': 0
        }
        weighted_gi = 0
        total_carbs = 0
        
        valid_components = []
        
        for comp in components:
            if 'code' not in comp:
                continue
            
            code = comp['code']
            comp_mult = comp.get('mult', 1.0)
            
            row = self.ctx.master.lookup_code(code)
            if not row:
                print(f"  Warning: Component {code} not found in master.csv")
                continue
            
            cols = self.ctx.master.cols
            food_name = row[cols.option]
            
            # Apply component multiplier and materialize multiplier
            effective_mult = comp_mult * multiplier
            
            print(f"  {code} x{effective_mult:g} ({food_name})")
            
            # Accumulate nutrition
            cal = float(row.get(cols.cal, 0)) * effective_mult
            prot = float(row.get(cols.prot_g, 0)) * effective_mult
            carbs = float(row.get(cols.carbs_g, 0)) * effective_mult
            fat = float(row.get(cols.fat_g, 0)) * effective_mult
            gi = float(row.get(cols.gi, 0))
            sugar = float(row.get(cols.sugar_g, 0)) * effective_mult
            
            total_nutrition['cal'] += cal
            total_nutrition['prot_g'] += prot
            total_nutrition['carbs_g'] += carbs
            total_nutrition['fat_g'] += fat
            total_nutrition['sugar_g'] += sugar
            
            # Weighted GI calculation
            if carbs > 0:
                weighted_gi += gi * carbs
                total_carbs += carbs
            
            valid_components.append({
                'code': code,
                'mult': effective_mult,
                'name': food_name
            })
        
        if not valid_components:
            print("\nError: No valid components found")
            print()
            return
        
        # Calculate weighted GI and GL
        if total_carbs > 0:
            total_nutrition['GI'] = weighted_gi / total_carbs
        total_nutrition['GL'] = (total_nutrition['GI'] * total_nutrition['carbs_g']) / 100
        
        # Show combined nutrition
        print(f"\nCombined nutrition:")
        print(f"  {total_nutrition['cal']:.0f} cal, "
              f"{total_nutrition['prot_g']:.1f}g prot, "
              f"{total_nutrition['carbs_g']:.1f}g carbs, "
              f"{total_nutrition['fat_g']:.1f}g fat")
        print(f"  GI: {total_nutrition['GI']:.0f}, GL: {total_nutrition['GL']:.1f}")
        
        # Suggest code
        suggested_code = self._suggest_combo_code()
        
        # Build description
        alias_name = alias_data.get('name', alias_code)
        if multiplier != 1.0:
            description = f"{alias_name} [from {alias_code} x{multiplier:g}]"
        else:
            description = f"{alias_name} [from {alias_code}]"
        
        print(f"\nSuggested code: {suggested_code}")
        print(f"Description: \"{description}\"")
        print(f"\nTo create, use: materialize {alias_code}", end="")
        if multiplier != 1.0:
            print(f" {multiplier:g}", end="")
        print(f" as {suggested_code}")
        print()
    
    def _preview_master(self, source_code: str, multiplier: float) -> None:
        """Preview scaling a master entry."""
        row = self.ctx.master.lookup_code(source_code)
        if not row:
            print(f"\nError: '{source_code}' not found in master.csv")
            print()
            return
        
        cols = self.ctx.master.cols
        food_name = row[cols.option]
        
        # Calculate scaled nutrition
        current_cal = float(row.get(cols.cal, 0))
        new_cal = current_cal * multiplier
        
        print(f"\nScaling {source_code} ({food_name}) at {multiplier:g}x:")
        print(f"  Current: {current_cal:.0f} cal per portion")
        print(f"  New: {new_cal:.0f} cal per portion")
        
        # Show all scaled nutrition
        scaled_nutrition = {
            'cal': new_cal,
            'prot_g': float(row.get(cols.prot_g, 0)) * multiplier,
            'carbs_g': float(row.get(cols.carbs_g, 0)) * multiplier,
            'fat_g': float(row.get(cols.fat_g, 0)) * multiplier,
            'GI': float(row.get(cols.gi, 0)),  # GI doesn't scale
            'sugar_g': float(row.get(cols.sugar_g, 0)) * multiplier
        }
        scaled_nutrition['GL'] = (scaled_nutrition['GI'] * scaled_nutrition['carbs_g']) / 100
        
        print(f"  {scaled_nutrition['prot_g']:.1f}g prot, "
              f"{scaled_nutrition['carbs_g']:.1f}g carbs, "
              f"{scaled_nutrition['fat_g']:.1f}g fat")
        
        # Suggest code
        suggested_code = self._suggest_scaled_code(source_code, multiplier)
        
        # Build description
        description = f"{food_name} [from {source_code} x{multiplier:g}]"
        
        print(f"\nSuggested code: {suggested_code}")
        print(f"Description: \"{description}\"")
        print(f"\nTo create, use: materialize {source_code} {multiplier:g} as {suggested_code}")
        print()
    
    def _suggest_combo_code(self) -> str:
        """Suggest next available CM.xxx code."""
        master_df = self.ctx.master.df
        code_col = self.ctx.master.cols.code
        
        # Find all CM codes
        cm_codes = master_df[master_df[code_col].str.match(r'^CM\.\d+$', case=False, na=False)]
        
        if cm_codes.empty:
            return "CM.1"
        
        # Extract numbers
        import re
        numbers = []
        for code in cm_codes[code_col]:
            match = re.match(r'^CM\.(\d+)$', code, re.IGNORECASE)
            if match:
                numbers.append(int(match.group(1)))
        
        if not numbers:
            return "CM.1"
        
        # Return next number
        max_num = max(numbers)
        return f"CM.{max_num + 1}"
    
    def _suggest_scaled_code(self, source_code: str, multiplier: float) -> str:
        """Suggest code for scaled master entry."""
        # Try letter suffix first (SO.19d -> SO.19e)
        import re
        match = re.match(r'^([A-Z]+\.\d+)([a-z]?)$', source_code, re.IGNORECASE)
        
        if match:
            base = match.group(1)
            current_suffix = match.group(2).lower() if match.group(2) else ''
            
            if current_suffix:
                # Try next letter
                next_letter = chr(ord(current_suffix) + 1)
                if next_letter <= 'z':
                    candidate = f"{base}{next_letter}"
                    if not self.ctx.master.lookup_code(candidate):
                        return candidate
            else:
                # Try adding 'a'
                candidate = f"{base}a"
                if not self.ctx.master.lookup_code(candidate):
                    return candidate
        
        # Fall back to numeric suffix
        base = source_code
        for i in range(2, 100):
            candidate = f"{base}{i}"
            if not self.ctx.master.lookup_code(candidate):
                return candidate
        
        return f"{source_code}_new"
    
    def _execute_materialize(self, source_code: str, multiplier: float, 
                            target_code: str, is_alias: bool) -> None:
        """Execute materialization."""
        # Check if target code already exists
        if self.ctx.master.lookup_code(target_code):
            print(f"\nError: Code '{target_code}' already exists in master.csv")
            print(f"Use a different code or check with: addcode {target_code}")
            print()
            return
        
        # Validate target code format
        if not self._validate_code_format(target_code):
            print(f"\nError: Invalid code format '{target_code}'")
            print("Code should be like: CM.1, SO.19e, FI.8x2")
            print()
            return
        
        if is_alias:
            self._materialize_alias(source_code, multiplier, target_code)
        else:
            self._materialize_scaled(source_code, multiplier, target_code)
    
    def _validate_code_format(self, code: str) -> bool:
        """Validate code format."""
        import re
        # Accept codes like: CM.1, SO.19e, FI.8x2
        return bool(re.match(r'^[A-Z]{2,4}\.[A-Z0-9]+[a-z0-9]*$', code, re.IGNORECASE))
    
    def _materialize_alias(self, alias_code: str, multiplier: float, target_code: str) -> None:
        """Materialize an alias into master and nutrients."""
        alias_data = self.ctx.aliases.lookup_alias(alias_code)
        if not alias_data:
            print(f"\nError: Alias '{alias_code}' not found")
            print()
            return
        
        # Parse and resolve components
        from meal_planner.parsers import CodeParser
        codes_str = alias_data.get('codes', '')
        components = CodeParser.parse(codes_str)
        
        # Calculate nutrition
        nutrition_data, components_info = self._calculate_alias_nutrition(
            components, multiplier
        )
        
        if not nutrition_data:
            print("\nError: Could not calculate nutrition (invalid components)")
            print()
            return
        
        # Create master entry
        section = "Combo"
        alias_name = alias_data.get('name', alias_code)
        
        if multiplier != 1.0:
            description = f"{alias_name} [from {alias_code} x{multiplier:g}]"
        else:
            description = f"{alias_name} [from {alias_code}]"
        
        self._add_master_entry(target_code, section, description, nutrition_data)
        
        # Create nutrients entry if manager exists
        if self.ctx.nutrients:
            nutrients_data = self._calculate_alias_nutrients(components, multiplier)
            if nutrients_data:
                self._add_nutrients_entry(target_code, nutrients_data)
        
        # Create recipe entry
        self._add_recipe_entry(target_code, alias_code, multiplier, components_info, True)
        
        print(f"\n✓ Materialized {alias_code} as {target_code}")
        print(f"  Section: {section}")
        print(f"  Description: {description}")
        print(f"  Nutrition: {nutrition_data['cal']:.0f} cal, "
              f"{nutrition_data['prot_g']:.1f}g prot, "
              f"{nutrition_data['carbs_g']:.1f}g carbs, "
              f"{nutrition_data['fat_g']:.1f}g fat")
        print()
    
    def _materialize_scaled(self, source_code: str, multiplier: float, target_code: str) -> None:
        """Create scaled version of master entry."""
        row = self.ctx.master.lookup_code(source_code)
        if not row:
            print(f"\nError: '{source_code}' not found in master.csv")
            print()
            return
        
        cols = self.ctx.master.cols
        
        # Scale nutrition
        nutrition_data = {
            'cal': float(row.get(cols.cal, 0)) * multiplier,
            'prot_g': float(row.get(cols.prot_g, 0)) * multiplier,
            'carbs_g': float(row.get(cols.carbs_g, 0)) * multiplier,
            'fat_g': float(row.get(cols.fat_g, 0)) * multiplier,
            'GI': float(row.get(cols.gi, 0)),  # GI doesn't scale
            'sugar_g': float(row.get(cols.sugar_g, 0)) * multiplier
        }
        nutrition_data['GL'] = (nutrition_data['GI'] * nutrition_data['carbs_g']) / 100
        
        # Preserve section
        section = row.get(cols.section, '')
        
        # Build description
        food_name = row[cols.option]
        description = f"{food_name} [from {source_code} x{multiplier:g}]"
        
        # Create master entry
        self._add_master_entry(target_code, section, description, nutrition_data)
        
        # Scale nutrients if available
        if self.ctx.nutrients:
            nutrients_row = self.ctx.nutrients.get_nutrients_for_code(source_code)
            if nutrients_row is not None:
                nutrients_data = self._scale_nutrients(nutrients_row, multiplier)
                self._add_nutrients_entry(target_code, nutrients_data)
        
        # Create recipe entry
        self._add_recipe_entry(target_code, source_code, multiplier, 
                              [{'code': source_code, 'mult': multiplier, 
                                'name': food_name}], False)
        
        print(f"\n✓ Materialized {source_code} x{multiplier:g} as {target_code}")
        print(f"  Section: {section}")
        print(f"  Description: {description}")
        print(f"  Nutrition: {nutrition_data['cal']:.0f} cal, "
              f"{nutrition_data['prot_g']:.1f}g prot")
        print()
    
    def _calculate_alias_nutrition(self, components: list, multiplier: float) -> Tuple[Optional[Dict], list]:
        """Calculate nutrition for alias components."""
        total_nutrition = {
            'cal': 0, 'prot_g': 0, 'carbs_g': 0, 'fat_g': 0,
            'GI': 0, 'GL': 0, 'sugar_g': 0
        }
        weighted_gi = 0
        total_carbs = 0
        
        components_info = []
        
        for comp in components:
            if 'code' not in comp:
                continue
            
            code = comp['code']
            comp_mult = comp.get('mult', 1.0)
            
            row = self.ctx.master.lookup_code(code)
            if not row:
                return None, []
            
            cols = self.ctx.master.cols
            food_name = row[cols.option]
            
            effective_mult = comp_mult * multiplier
            
            # Accumulate nutrition
            cal = float(row.get(cols.cal, 0)) * effective_mult
            prot = float(row.get(cols.prot_g, 0)) * effective_mult
            carbs = float(row.get(cols.carbs_g, 0)) * effective_mult
            fat = float(row.get(cols.fat_g, 0)) * effective_mult
            gi = float(row.get(cols.gi, 0))
            sugar = float(row.get(cols.sugar_g, 0)) * effective_mult
            
            total_nutrition['cal'] += cal
            total_nutrition['prot_g'] += prot
            total_nutrition['carbs_g'] += carbs
            total_nutrition['fat_g'] += fat
            total_nutrition['sugar_g'] += sugar
            
            if carbs > 0:
                weighted_gi += gi * carbs
                total_carbs += carbs
            
            components_info.append({
                'code': code,
                'mult': effective_mult,
                'name': food_name
            })
        
        # Calculate weighted GI and GL
        if total_carbs > 0:
            total_nutrition['GI'] = weighted_gi / total_carbs
        total_nutrition['GL'] = (total_nutrition['GI'] * total_nutrition['carbs_g']) / 100
        
        return total_nutrition, components_info
    
    def _calculate_alias_nutrients(self, components: list, multiplier: float) -> Optional[Dict]:
        """Calculate micronutrients for alias components."""
        if not self.ctx.nutrients:
            return None
        
        # Get available nutrient columns
        nutrients_df = self.ctx.nutrients.df
        if nutrients_df.empty:
            return None
        
        nutrient_cols = [col for col in nutrients_df.columns if col != 'code']
        
        # Initialize totals
        totals = {col: 0.0 for col in nutrient_cols}
        
        for comp in components:
            if 'code' not in comp:
                continue
            
            code = comp['code']
            comp_mult = comp.get('mult', 1.0)
            effective_mult = comp_mult * multiplier
            
            nutrients_row = self.ctx.nutrients.get_nutrients_for_code(code)
            if nutrients_row is None:
                continue
            
            # Add scaled nutrients
            for col in nutrient_cols:
                value = nutrients_row.get(col, 0)
                if pd.notna(value):
                    totals[col] += float(value) * effective_mult
        
        return totals
    
    def _scale_nutrients(self, nutrients_row, multiplier: float) -> Dict:
        """Scale nutrients by multiplier."""
        scaled = {}
        # Handle dict or Series
        cols = nutrients_row.keys() if hasattr(nutrients_row, 'keys') else nutrients_row.index
        for col in cols:
            if col == 'code':
                continue
            value = nutrients_row[col]
            if pd.notna(value):
                scaled[col] = float(value) * multiplier
            else:
                scaled[col] = 0
        return scaled
    
    def _add_master_entry(self, code: str, section: str, description: str, 
                         nutrition: Dict) -> None:
        """Add entry to master.csv."""
        # Create backup
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        # Load current master
        master_df = self.ctx.master.df.copy()
        cols = self.ctx.master.cols
        
        # Build new row
        new_row = {
            cols.code: code,
            cols.section: section,
            cols.option: description,
            cols.cal: round(nutrition['cal'], 2),
            cols.prot_g: round(nutrition['prot_g'], 2),
            cols.carbs_g: round(nutrition['carbs_g'], 2),
            cols.fat_g: round(nutrition['fat_g'], 2),
            cols.gi: round(nutrition['GI'], 2),
            cols.gl: round(nutrition['GL'], 2),
            cols.sugar_g: round(nutrition['sugar_g'], 2)
        }
        
        # Add row
        new_row_df = pd.DataFrame([new_row])
        master_df = pd.concat([master_df, new_row_df], ignore_index=True)
        
        # Sort naturally
        master_df['_sort_key'] = master_df[cols.code].apply(natural_sort_key)
        master_df = master_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        master_df = master_df.reset_index(drop=True)
        
        # Save
        master_df.to_csv(self.ctx.master.filepath, index=False)
        self.ctx.master.reload()
    
    def _add_nutrients_entry(self, code: str, nutrients: Dict) -> None:
        """Add entry to nutrients.csv."""
        # Create backup
        backup_path = create_backup(self.ctx.nutrients.filepath, self.ctx)
        
        # Load current nutrients
        nutrients_df = self.ctx.nutrients.df.copy()
        
        # Build new row
        new_row = {'code': code}
        for key, value in nutrients.items():
            new_row[key] = round(value, 2)
        new_row.update(nutrients)
        
        # Add row
        new_row_df = pd.DataFrame([new_row])
        nutrients_df = pd.concat([nutrients_df, new_row_df], ignore_index=True)
        
        # Sort naturally
        nutrients_df['_sort_key'] = nutrients_df['code'].apply(natural_sort_key)
        nutrients_df = nutrients_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        nutrients_df = nutrients_df.reset_index(drop=True)
        
        # Save
        nutrients_df.to_csv(self.ctx.nutrients.filepath, index=False)
        self.ctx.nutrients.load()
    
    def _add_recipe_entry(self, code: str, source_code: str, multiplier: float,
                         components_info: list, is_alias: bool) -> None:
        """Add recipe documentation entry."""
        if not self.ctx.recipes:
            return
        
        # Create backup
        backup_path = create_backup(self.ctx.recipes.filepath, self.ctx)
        
        # Build recipe text
        today = datetime.now().strftime("%Y-%m-%d")
        
        if is_alias:
            recipe_lines = [
                f"Materialized on {today} from {source_code} at {multiplier:g}x",
                "",
                "Components:"
            ]
            for comp in components_info:
                recipe_lines.append(f"  {comp['code']} x{comp['mult']:g} ({comp['name']})")
        else:
            comp = components_info[0]  # Single component for scaled entries
            original_cal = comp.get('original_cal', 0)
            new_cal = original_cal * multiplier if original_cal else 0
            
            recipe_lines = [
                f"Materialized on {today} from {source_code} at {multiplier:g}x",
                "",
                f"Source: {source_code} ({comp['name']})"
            ]
            if original_cal:
                recipe_lines.append(f"Original: {original_cal:.0f} cal")
                recipe_lines.append(f"Scaled to: {multiplier:g}x portion ({new_cal:.0f} cal)")
        
        recipe_lines.append("")
        recipe_lines.append("Note: This is a static snapshot. Changes to source components will not propagate.")
        
        recipe_text = "\n".join(recipe_lines)
        
        # Load recipes
        recipes_df = self.ctx.recipes.df.copy()
        
        # Build new row
        new_row = {
            'code': code,
            'ingredients': recipe_text
        }
        
        # Add row
        new_row_df = pd.DataFrame([new_row])
        recipes_df = pd.concat([recipes_df, new_row_df], ignore_index=True)
        
        # Sort naturally
        recipes_df['_sort_key'] = recipes_df['code'].apply(natural_sort_key)
        recipes_df = recipes_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        recipes_df = recipes_df.reset_index(drop=True)
        
        # Save
        recipes_df.to_csv(self.ctx.recipes.filepath, index=False)
        self.ctx.recipes.load()