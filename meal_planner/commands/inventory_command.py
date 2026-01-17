# meal_planner/commands/inventory_command.py
"""
Inventory command - manage leftovers, batch items, and rotating items.
"""
from .base import Command, register_command
from datetime import datetime


@register_command
class InventoryCommand(Command):
    """Manage inventory (leftovers, batch items, rotating items)."""
    
    name = "inventory"
    help_text = "Manage inventory (inventory add/remove/depleted/restore/list)"
    
    def execute(self, args: str) -> None:
        """
        Execute inventory command.
        
        Syntax:
            inventory add <code> [<multiplier>] --leftover|--batch|--rotating [note]
            inventory remove <code>
            inventory depleted <code>
            inventory restore <code> [<multiplier>]
            inventory list
        
        Args:
            args: Subcommand and parameters
        """
        # Check if in planning mode
        if not self.ctx.mode_mgr.is_active or self.ctx.mode_mgr.active_mode.mode_type != "plan":
            print("\nError: Inventory commands only available in planning mode")
            print("Use: mode plan")
            print()
            return
        
        if not args.strip():
            self._show_help()
            return
        
        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""
        
        if subcommand == "add":
            self._add(subargs)
        elif subcommand == "remove":
            self._remove(subargs)
        elif subcommand == "depleted":
            self._depleted(subargs)
        elif subcommand == "restore":
            self._restore(subargs)
        elif subcommand == "list":
            self._list()
        else:
            print(f"\nUnknown inventory subcommand: {subcommand}")
            self._show_help()
    
    def _show_help(self) -> None:
        """Show inventory command help."""
        print("""
Inventory Management Commands:

  inventory add <code> [<mult>] --leftover|--batch|--rotating [note]
      Add item to inventory
      --leftover: Single-use item from previous meal
      --batch: Multi-portion item (soup, meatballs, etc.)
      --rotating: Persistent item that cycles (granola, cole slaw)
      
      Examples:
        inventory add FI.8 0.225 --leftover "salmon from dinner"
        inventory add SO.13d 0.5 --batch "lentil soup"
        inventory add GR.H1 --rotating "homemade granola"
  
  inventory remove <code>
      Remove item from inventory (consumed or discarded)
      
      Examples:
        inventory remove FI.8
        inventory remove SO.13d
  
  inventory depleted <code>
      Mark rotating item as depleted (still tracked, not available)
      
      Examples:
        inventory depleted GR.H1
  
  inventory restore <code> [<mult>]
      Restore rotating item to available status
      
      Examples:
        inventory restore GR.H1
        inventory restore GR.H1 1.5
  
  inventory list
      Show all inventory items

Notes:
  - Multipliers are fractions of master.csv portions
  - Default multiplier is 1.0 if omitted
  - Inventory auto-saves after each change
""")
    
    def _add(self, args: str) -> None:
        """
        Add item to inventory.
        
        Args:
            args: "<code> [<mult>] --leftover|--batch|--rotating [note]"
        """
        if not args.strip():
            print("\nUsage: inventory add <code> [<mult>] --leftover|--batch|--rotating [note]")
            print("Example: inventory add FI.8 0.225 --leftover \"from dinner\"")
            print()
            return
        
        # Parse arguments
        import shlex
        try:
            parts = shlex.split(args)
        except ValueError:
            parts = args.split()
        
        if len(parts) < 2:
            print("\nError: Must specify code and type (--leftover, --batch, or --rotating)")
            print("Usage: inventory add <code> [<mult>] --leftover|--batch|--rotating [note]")
            print()
            return
        
        # Extract code
        code = parts[0].upper()
        
        # Validate code exists in master
        if not self._validate_code(code):
            print(f"\nError: Food code '{code}' not found in master.csv")
            print()
            return
        
        # Parse remaining parts to find type flag and multiplier
        multiplier = 1.0
        inv_type = None
        note = ""
        
        # Map flag names to workspace keys
        type_mapping = {
            "--leftover": "leftovers",
            "--batch": "batch",
            "--rotating": "rotating"
        }
        
        i = 1
        while i < len(parts):
            part = parts[i]
            
            if part in type_mapping:
                inv_type = type_mapping[part]  # Map to workspace key
                # Everything after type flag is the note
                if i + 1 < len(parts):
                    note = " ".join(parts[i+1:])
                break
            else:
                # Try to parse as multiplier
                try:
                    multiplier = float(part)
                    if multiplier <= 0:
                        print(f"\nError: Multiplier must be positive, got {multiplier}")
                        print()
                        return
                except ValueError:
                    print(f"\nError: Expected multiplier or type flag, got '{part}'")
                    print()
                    return
            i += 1
        
        if inv_type is None:
            print("\nError: Must specify type: --leftover, --batch, or --rotating")
            print()
            return
        
        # Get workspace data
        workspace = self._load_workspace()
        
        # Check if item already exists (before we add it)
        item_exists = code in workspace["inventory"][inv_type]
        
        # Add or update item
        timestamp = datetime.now().isoformat()
        
        item_data = {
            "multiplier": multiplier,
            "added": timestamp,
            "note": note
        }
        
        # Add type-specific fields
        if inv_type == "rotating":
            # Check if already exists
            if item_exists:
                existing = workspace["inventory"]["rotating"][code]
                item_data["status"] = existing.get("status", "available")
                # Preserve original added date
                item_data["added"] = existing.get("added", timestamp)
                if existing.get("status") == "depleted":
                    item_data["depleted_date"] = existing.get("depleted_date")
            else:
                item_data["status"] = "available"
        
        workspace["inventory"][inv_type][code] = item_data
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Get food name for display
        food_name = self._get_food_name(code)
        master_portion = self._get_master_portion(code)
        
        # Display-friendly type names
        type_display = {
            "leftovers": "leftover",
            "batch": "batch item",
            "rotating": "rotating item"
        }
        
        # Show confirmation
        action = "Updated" if item_exists else "Added"
        print(f"\n{action} {code} ({food_name}) as {type_display[inv_type]}")
        print(f"  Multiplier: {multiplier}x (master portion: {master_portion})")
        if note:
            print(f"  Note: {note}")
        print()
    
    def _remove(self, args: str) -> None:
        """
        Remove item from inventory.
        
        Args:
            args: "<code>"
        """
        if not args.strip():
            print("\nUsage: inventory remove <code>")
            print("Example: inventory remove FI.8")
            print()
            return
        
        code = args.strip().upper()
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Find and remove from appropriate category
        removed = False
        inv_type = None
        
        for category in ["leftovers", "batch", "rotating"]:
            if code in workspace["inventory"][category]:
                del workspace["inventory"][category][code]
                removed = True
                inv_type = category
                break
        
        if not removed:
            print(f"\nError: {code} not found in inventory")
            print("Use 'inventory list' to see available items")
            print()
            return
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Display-friendly type names
        type_display = {
            "leftovers": "leftovers",
            "batch": "batch items",
            "rotating": "rotating items"
        }
        
        food_name = self._get_food_name(code)
        print(f"\nRemoved {code} ({food_name}) from {type_display[inv_type]}")
        print()
    
    def _depleted(self, args: str) -> None:
        """
        Mark rotating item as depleted.
        
        Args:
            args: "<code>"
        """
        if not args.strip():
            print("\nUsage: inventory depleted <code>")
            print("Example: inventory depleted GR.H1")
            print()
            return
        
        code = args.strip().upper()
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Check if code is in rotating items
        if code not in workspace["inventory"]["rotating"]:
            print(f"\nError: {code} not found in rotating items")
            print("Note: Only rotating items can be marked as depleted")
            print("Use 'inventory list' to see rotating items")
            print()
            return
        
        # Mark as depleted
        item = workspace["inventory"]["rotating"][code]
        item["status"] = "depleted"
        item["depleted_date"] = datetime.now().isoformat()
        
        # Save workspace
        self._save_workspace(workspace)
        
        food_name = self._get_food_name(code)
        print(f"\nMarked {code} ({food_name}) as depleted")
        print()
    
    def _restore(self, args: str) -> None:
        """
        Restore rotating item to available.
        
        Args:
            args: "<code> [<mult>]"
        """
        if not args.strip():
            print("\nUsage: inventory restore <code> [<mult>]")
            print("Example: inventory restore GR.H1")
            print("         inventory restore GR.H1 1.5")
            print()
            return
        
        parts = args.split()
        code = parts[0].upper()
        
        # Parse optional multiplier
        multiplier = None
        if len(parts) > 1:
            try:
                multiplier = float(parts[1])
                if multiplier <= 0:
                    print(f"\nError: Multiplier must be positive, got {multiplier}")
                    print()
                    return
            except ValueError:
                print(f"\nError: Invalid multiplier '{parts[1]}'")
                print()
                return
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Check if code is in rotating items
        if code not in workspace["inventory"]["rotating"]:
            print(f"\nError: {code} not found in rotating items")
            print("Use 'inventory list' to see rotating items")
            print()
            return
        
        # Restore item
        item = workspace["inventory"]["rotating"][code]
        item["status"] = "available"
        
        # Update multiplier if provided
        if multiplier is not None:
            item["multiplier"] = multiplier
        
        # Remove depleted_date if present
        if "depleted_date" in item:
            del item["depleted_date"]
        
        # Save workspace
        self._save_workspace(workspace)
        
        food_name = self._get_food_name(code)
        mult_str = f" at {multiplier}x" if multiplier is not None else ""
        print(f"\nRestored {code} ({food_name}) to available{mult_str}")
        print()
    
    def _list(self) -> None:
        """Show all inventory items."""
        workspace = self._load_workspace()
        inventory = workspace["inventory"]
        
        # Check if inventory is empty
        has_items = any(len(inventory[cat]) > 0 for cat in ["leftovers", "batch", "rotating"])
        
        if not has_items:
            print("\nInventory is empty")
            print()
            return
        
        print("\n=== INVENTORY ===")
        print()
        
        # Show leftovers
        if inventory["leftovers"]:
            print("Leftovers (single-use items):")
            for code, item in sorted(inventory["leftovers"].items()):
                food_name = self._get_food_name(code)
                master_portion = self._get_master_portion(code)
                mult = item["multiplier"]
                added = item["added"][:10]  # Just date
                note = item.get("note", "")
                
                print(f"  {code} ({food_name}): {mult}x (master: {master_portion})")
                print(f"    Added: {added}")
                if note:
                    print(f"    Note: {note}")
                print()
        
        # Show batch items
        if inventory["batch"]:
            print("Batch items (multi-portion):")
            for code, item in sorted(inventory["batch"].items()):
                food_name = self._get_food_name(code)
                master_portion = self._get_master_portion(code)
                mult = item["multiplier"]
                added = item["added"][:10]
                note = item.get("note", "")
                
                print(f"  {code} ({food_name}): {mult}x per use (master: {master_portion})")
                print(f"    Added: {added}")
                if note:
                    print(f"    Note: {note}")
                print()
        
        # Show rotating items
        if inventory["rotating"]:
            print("Rotating items (persistent):")
            for code, item in sorted(inventory["rotating"].items()):
                food_name = self._get_food_name(code)
                master_portion = self._get_master_portion(code)
                mult = item["multiplier"]
                status = item["status"]
                added = item["added"][:10]
                note = item.get("note", "")
                
                status_str = "AVAILABLE" if status == "available" else "DEPLETED"
                print(f"  {code} ({food_name}): {status_str}, {mult}x (master: {master_portion})")
                print(f"    Added: {added}")
                if status == "depleted" and "depleted_date" in item:
                    depleted = item["depleted_date"][:10]
                    print(f"    Depleted: {depleted}")
                if note:
                    print(f"    Note: {note}")
                print()
    
    # Helper methods
    
    def _load_workspace(self):
        """Load workspace data from disk."""
        if self.ctx.workspace_mgr:
            return self.ctx.workspace_mgr.load()
        return {"inventory": {"leftovers": {}, "batch": {}, "rotating": {}}}
    
    def _save_workspace(self, workspace):
        """Save workspace data to disk."""
        if self.ctx.workspace_mgr:
            self.ctx.workspace_mgr.save(workspace)
    
    def _validate_code(self, code: str) -> bool:
        """Check if code exists in master.csv."""
        # Use MasterLoader's lookup_code method
        row = self.ctx.master.lookup_code(code)
        return row is not None
    
    def _get_food_name(self, code: str) -> str:
        """Get food name from master.csv."""
        row = self.ctx.master.lookup_code(code)
        if row:
            # Use column resolver to get correct column name
            col = self.ctx.master.cols.option
            return row.get(col, "Unknown")
        return "Unknown"
    
    def _get_master_portion(self, code: str) -> str:
        """Get master portion string from master.csv."""
        row = self.ctx.master.lookup_code(code)
        if row:
            # Get amount and unit columns
            amount = row.get('amount', '')
            unit = row.get('unit', '')
            return f"{amount} {unit}".strip()
        return "Unknown"