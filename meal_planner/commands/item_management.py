"""
Item management commands: rm, move, setmult, ins, items.
"""
from datetime import date

from .base import Command, register_command
from meal_planner.parsers import CodeParser, eval_multiplier_expression
from meal_planner.utils import ColumnResolver


@register_command
class ItemsCommand(Command):
    """List current pending items with indices."""
    
    name = "items"
    help_text = "List pending items with 1-based indices"
    
    def execute(self, args: str) -> None:
        """Display pending items with indices."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("(no items)")
            return
        
        items = pending["items"]
        
        print(f"{'#':>3} {'Code':>10} {'x':>5} {'Section':<8} {'Option / Time'}")
        print("-" * 78)
        
        for i, item in enumerate(items, 1):
            if "time" in item and item.get("time"):
                time_code = f"@{item['time']}"
                meal_override = item.get("meal_override")
                if meal_override:
                    description = f"time marker ({meal_override})"
                else:
                    description = "time marker"
                print(f"{i:>3} {time_code:>10} {'':>5} {'':<8} {description}")
            
            if "code" not in item:
                continue
            
            code = item.get("code", "").upper()
            mult = float(item.get("mult", 1.0))
            
            # Look up in master
            row = self.ctx.master.lookup_code(code)
            if row:
                cols = self.ctx.master.cols
                section = str(row[cols.section])[:8]
                option = str(row[cols.option])
            else:
                section = ""
                option = "(not found)"
            
            print(f"{i:>3} {code:>10} {mult:>5g} {section:<8} {option}")
        
        print()


@register_command
class RemoveCommand(Command):
    """Remove items from pending."""
    
    name = "rm"
    help_text = "Remove items (rm 3 or rm 2,4 or rm 3-5)"
    
    def execute(self, args: str) -> None:
        """
        Remove items by index.
        
        Args:
            args: Indices like "3", "2,4", "3-5"
        """
        if not args.strip():
            print("Usage: rm <index|indices>")
            print("Examples: rm 3, rm 2,4, rm 3-5")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("No items to remove.")
            return
        
        items = pending["items"]
        n = len(items)
        
        # Parse indices
        indices = self._parse_indices(args.strip(), n)
        
        if not indices:
            print("No valid indices.")
            return
        
        # Remove in reverse order to maintain indices
        for idx in reversed(sorted(indices)):
            del items[idx]
        
        pending["items"] = items
        self.ctx.pending_mgr.save(pending)
        
        print(f"Removed {len(indices)} item(s).")
        
        # Show updated list
        ItemsCommand(self.ctx).execute("")
    
    def _parse_indices(self, arg: str, n: int) -> list:
        """Parse index specification into 0-based list."""
        indices = set()
        
        for part in arg.split(","):
            part = part.strip()
            if not part:
                continue
            
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    start = int(a.strip())
                    end = int(b.strip())
                    for i in range(min(start, end), max(start, end) + 1):
                        if 1 <= i <= n:
                            indices.add(i - 1)
                except ValueError:
                    pass
            else:
                try:
                    i = int(part)
                    if 1 <= i <= n:
                        indices.add(i - 1)
                except ValueError:
                    pass
        
        return sorted(indices)


@register_command
class MoveCommand(Command):
    """Move an item to a different position."""
    
    name = "move"
    help_text = "Move item (move 3 1 moves item 3 to position 1)"
    
    def execute(self, args: str) -> None:
        """
        Move item from one position to another.
        
        Args:
            args: "from_index to_index" (1-based)
        """
        parts = args.strip().split()
        if len(parts) != 2:
            print("Usage: move <from> <to>")
            print("Example: move 3 1")
            return
        
        try:
            from_idx = int(parts[0])
            to_idx = int(parts[1])
        except ValueError:
            print("Invalid indices. Use integers.")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("No items to move.")
            return
        
        items = pending["items"]
        n = len(items)
        
        if not (1 <= from_idx <= n and 1 <= to_idx <= n):
            print(f"Indices must be between 1 and {n}.")
            return
        
        # Convert to 0-based
        from_idx -= 1
        to_idx -= 1
        
        # Move item
        item = items.pop(from_idx)
        items.insert(to_idx, item)
        
        pending["items"] = items
        self.ctx.pending_mgr.save(pending)
        
        print(f"Moved item from position {from_idx + 1} to {to_idx + 1}.")
        
        # Show updated list
        ItemsCommand(self.ctx).execute("")


@register_command
class SetMultCommand(Command):
    """Set multiplier for an item."""
    
    name = "setmult"
    help_text = "Set multiplier (setmult 3 1.5 or setmult 3 5.7/4)"
    
    def execute(self, args: str) -> None:
        """
        Set multiplier for item.
        
        Args:
            args: "index multiplier" where multiplier can be arithmetic
        """
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            print("Usage: setmult <index> <multiplier>")
            print("Examples: setmult 3 1.5, setmult 3 5.7/4")
            return
        
        try:
            idx = int(parts[0])
        except ValueError:
            print("Invalid index. Use integer.")
            return
        
        mult_str = parts[1].strip()
        
        # Handle leading dot
        if mult_str.startswith("."):
            mult_str = "0" + mult_str
        
        # Evaluate multiplier
        try:
            mult = eval_multiplier_expression(mult_str)
        except Exception:
            print(f"Invalid multiplier: {mult_str}")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("No items to modify.")
            return
        
        items = pending["items"]
        n = len(items)
        
        if not (1 <= idx <= n):
            print(f"Index must be between 1 and {n}.")
            return
        
        # Convert to 0-based
        idx -= 1
        
        # Check if it's a code item
        if "code" not in items[idx]:
            print("Cannot set multiplier on time marker.")
            return
        
        # Set multiplier
        items[idx]["mult"] = mult
        
        pending["items"] = items
        self.ctx.pending_mgr.save(pending)
        
        print(f"Set multiplier for item {idx + 1} to {mult}.")
        
        # Show updated list
        ItemsCommand(self.ctx).execute("")


@register_command
class InsertCommand(Command):
    """Insert items at a position."""
    
    name = "ins"
    help_text = "Insert items (ins 3 B.1 *1.5, S2.4)"
    
    def execute(self, args: str) -> None:
        """
        Insert items at position.
        
        Args:
            args: "position codes" where codes are parsed like add command
        """
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            print("Usage: ins <position> <codes>")
            print("Example: ins 3 B.1 *1.5, S2.4")
            return
        
        try:
            pos = int(parts[0])
        except ValueError:
            print("Invalid position. Use integer.")
            return
        
        codes_str = parts[1].strip()
        
        # Parse codes
        new_items = CodeParser.parse(codes_str)
        
        if not new_items:
            print("No valid codes found.")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None:
            pending = {
                "date": str(date.today()),
                "items": []
            }
        
        items = pending["items"]
        n = len(items)
        
        # Clamp position
        pos = max(1, min(pos, n + 1))
        
        # Convert to 0-based
        pos -= 1
        
        # Insert items
        for i, item in enumerate(new_items):
            items.insert(pos + i, item)
        
        pending["items"] = items
        self.ctx.pending_mgr.save(pending)
        
        print(f"Inserted {len(new_items)} item(s) at position {pos + 1}.")
        
        # Show updated list
        ItemsCommand(self.ctx).execute("")