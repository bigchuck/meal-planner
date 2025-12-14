"""
Log editing commands: stash, loadlog, applylog, discard.
"""
from datetime import datetime
import copy
from datetime import date as date_type
from .base import Command, register_command
from .pending_commands import ShowCommand
from meal_planner.parsers import CodeParser

"""
Stash command - expanded with metadata and subcommands.

Supports: push, pop, list, list N, get N, drop N, discard
"""
from datetime import datetime
import copy

from .base import Command, register_command


@register_command
class StashCommand(Command):
    """Stash/restore pending day."""
    
    name = "stash"
    help_text = "Manage stash (stash push|pop|list|get|drop|discard)"
    
    def execute(self, args: str) -> None:
        """
        Route to stash subcommands.
        
        Args:
            args: Subcommand and arguments
        """
        parts = args.strip().split()
        
        if not parts:
            print("Usage: stash <push|pop|list|get|drop|discard> [args]")
            print("\nExamples:")
            print("  stash push              - Save current pending to stack")
            print("  stash pop               - Restore from top of stack")
            print("  stash list              - Show all stashed entries")
            print("  stash list 2            - Show details of entry #2")
            print("  stash get 3             - Restore entry #3 (not top)")
            print("  stash drop 2            - Remove entry #2 from stack")
            print("  stash discard           - Clear entire stack")
            return
        
        subcommand = parts[0].lower()
        subargs = parts[1:]
        
        if subcommand == "push":
            self._push()
        elif subcommand == "pop":
            self._pop(subargs)
        elif subcommand == "list":
            self._list(subargs)
        elif subcommand == "get":
            self._get(subargs)
        elif subcommand == "drop":
            self._drop(subargs)
        elif subcommand == "discard":
            self._discard(subargs)
        else:
            print(f"Unknown subcommand: {subcommand}")
            print("Valid: push, pop, list, get, drop, discard")
    
    def _push(self) -> None:
        """Push current pending to stack."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        # Deep copy to avoid mutation
        snapshot = copy.deepcopy(pending) if pending else None
        
        # Create stash entry with metadata
        stash_entry = {
            "pending": snapshot,
            "timestamp": datetime.now(),
            "auto": False  # Manual push
        }
        
        self.ctx.pending_stack.append(stash_entry)
        
        stack_depth = len(self.ctx.pending_stack)
        print(f"Stashed current pending. Stack depth: {stack_depth}")
    
    def _pop(self, args: list) -> None:
        """Pop from stack and restore (with swap logic)."""
        force = "--force" in args or "-f" in args
        
        if not self.ctx.pending_stack:
            print("Stash is empty (nothing to restore).")
            return
        
        # Check if current pending needs protection
        pending_source = self.ctx.pending_source
        
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        has_current_items = current and current.get("items")
        
        # Only "normal" source needs swap protection
        if pending_source == "normal" and has_current_items and not force:
            if not self._offer_swap(current):
                # User chose to discard current
                self._destructive_pop()
                return
            else:
                # User chose swap
                self._swap_pop()
                return
        
        # Safe cases: just pop
        self._destructive_pop()
    
    def _offer_swap(self, current: dict) -> bool:
        """
        Offer to swap current pending with stashed.
        
        Args:
            current: Current pending data
        
        Returns:
            True for swap, False for discard
        """
        items = current.get("items", [])
        item_count = len(items)
        
        print(f"\nCurrent pending has {item_count} item(s).")
        print("(Y) Swap with stashed (preserves both) [default]")
        print("(n) Discard current and restore stashed")
        
        response = input("Choice (Y/n): ").strip().lower()
        
        # Default to swap on Enter
        if response in ("n", "no"):
            return False
        else:
            return True
    
    def _swap_pop(self) -> None:
        """Pop with swap (preserves current pending)."""
        # Pop what user wants
        stash_entry = self.ctx.pending_stack.pop()
        temp = self._extract_pending(stash_entry)
        
        # Push current to stack
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        snapshot = copy.deepcopy(current) if current else None
        
        new_entry = {
            "pending": snapshot,
            "timestamp": datetime.now(),
            "auto": False
        }
        
        self.ctx.pending_stack.append(new_entry)
        
        # Install popped pending
        if temp:
            self.ctx.pending_mgr.save(temp)
        else:
            self.ctx.pending_mgr.clear()
        
        # Update state
        self.ctx.editing_date = None
        self.ctx.pending_source = "stash_pop"
        
        stack_depth = len(self.ctx.pending_stack)
        print(f"Swapped pending with stashed (both preserved).")
        print(f"Stack depth: {stack_depth}")
    
    def _destructive_pop(self) -> None:
        """Pop and discard current pending."""
        stash_entry = self.ctx.pending_stack.pop()
        pending = self._extract_pending(stash_entry)
        
        if pending:
            self.ctx.pending_mgr.save(pending)
        else:
            self.ctx.pending_mgr.clear()
        
        # Update state
        self.ctx.editing_date = None
        self.ctx.pending_source = "stash_pop"
        
        print("Restored from stash.")
        
        # Show summary
        from .pending_commands import ShowCommand
        ShowCommand(self.ctx).execute("")
    
    def _list(self, args: list) -> None:
        """List stashed entries (summary or detail)."""
        if not self.ctx.pending_stack:
            print("\nStash is empty.\n")
            return
        
        # Check if requesting detail view
        if args:
            try:
                index = int(args[0])
                self._list_detail(index)
            except ValueError:
                print(f"Invalid index: {args[0]}")
            return
        
        # Summary view
        self._list_summary()
    
    def _list_summary(self) -> None:
        """Show summary of all stash entries."""
        stack_depth = len(self.ctx.pending_stack)
        
        print(f"\n=== Stash ({stack_depth} entries) ===\n")
        
        # Header
        print(f"{'#':<3} {'Date':<12} {'Items':<6} {'Stashed':<20} {'Source'}")
        print("─" * 65)
        
        # Entries (newest first, 1-based)
        for i in range(stack_depth - 1, -1, -1):
            entry = self.ctx.pending_stack[i]
            display_index = stack_depth - i
            
            pending = self._extract_pending(entry)
            
            if pending:
                entry_date = pending.get("date", "unknown")
                item_count = len(pending.get("items", []))
            else:
                entry_date = "empty"
                item_count = 0
            
            # Format age
            timestamp = entry.get("timestamp")
            if timestamp:
                age_str = self._format_age(timestamp)
            else:
                age_str = "unknown"
            
            # Format source
            is_auto = entry.get("auto", False)
            source_str = "auto (loadlog)" if is_auto else "manual"
            
            print(f"{display_index:<3} {entry_date:<12} {item_count:<6} {age_str:<20} {source_str}")
        
        print("\nUse 'stash list N' to see items, 'stash get N' to restore")
        print()
    
    def _list_detail(self, index: int) -> None:
        """Show detailed view of a stash entry."""
        stack_depth = len(self.ctx.pending_stack)
        
        if index < 1 or index > stack_depth:
            print(f"Invalid index. Stack has {stack_depth} entries. Use 'stash list' to see.")
            return
        
        # Convert to 0-based, newest-first
        actual_index = stack_depth - index
        entry = self.ctx.pending_stack[actual_index]
        
        pending = self._extract_pending(entry)
        
        if not pending or not pending.get("items"):
            print(f"\n=== Stash Entry #{index} ===")
            print("(empty)")
            print()
            return
        
        # Show header
        entry_date = pending.get("date", "unknown")
        item_count = len(pending.get("items", []))
        
        timestamp = entry.get("timestamp")
        age_str = self._format_age(timestamp) if timestamp else "unknown"
        
        is_auto = entry.get("auto", False)
        source_str = "auto from loadlog" if is_auto else "manual push"
        
        print(f"\n=== Stash Entry #{index} ===")
        print(f"Date: {entry_date}")
        print(f"Items: {item_count}")
        print(f"Stashed: {age_str} ({source_str})")
        print()
        
        # Show items list (same format as items command)
        items = pending.get("items", [])
        
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
                continue
            
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
        print(f"Use 'stash get {index}' to restore (will prompt about current pending)")
        print()
    
    def _get(self, args: list) -> None:
        """Get entry at arbitrary position (not just top)."""
        if not args:
            print("Usage: stash get <index>")
            print("Example: stash get 3")
            return
        
        force = "--force" in args or "-f" in args
        
        try:
            index = int(args[0])
        except ValueError:
            print(f"Invalid index: {args[0]}")
            return
        
        stack_depth = len(self.ctx.pending_stack)
        
        if index < 1 or index > stack_depth:
            print(f"Invalid index. Stack has {stack_depth} entries. Use 'stash list' to see.")
            return
        
        # Convert to 0-based, newest-first
        actual_index = stack_depth - index
        
        # Check if current pending needs protection
        pending_source = self.ctx.pending_source
        
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        has_current_items = current and current.get("items")
        
        # Only "normal" source needs swap protection
        if pending_source == "normal" and has_current_items and not force:
            if not self._offer_swap_for_get(current, index):
                # User chose to discard current
                self._destructive_get(actual_index)
                return
            else:
                # User chose swap
                self._swap_get(actual_index)
                return
        
        # Safe cases: just get
        self._destructive_get(actual_index)
    
    def _offer_swap_for_get(self, current: dict, index: int) -> bool:
        """Offer swap for get operation."""
        items = current.get("items", [])
        item_count = len(items)
        
        print(f"\nCurrent pending has {item_count} item(s).")
        print(f"(Y) Swap with stashed entry #{index} (preserves both) [default]")
        print(f"(n) Discard current and restore stashed entry #{index}")
        
        response = input("Choice (Y/n): ").strip().lower()
        
        # Default to swap
        if response in ("n", "no"):
            return False
        else:
            return True
    
    def _swap_get(self, actual_index: int) -> None:
        """Get with swap (preserves current pending)."""
        # Remove entry from stack
        stash_entry = self.ctx.pending_stack.pop(actual_index)
        temp = self._extract_pending(stash_entry)
        
        # Push current to top of stack
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        snapshot = copy.deepcopy(current) if current else None
        
        new_entry = {
            "pending": snapshot,
            "timestamp": datetime.now(),
            "auto": False
        }
        
        self.ctx.pending_stack.append(new_entry)
        
        # Install retrieved pending
        if temp:
            self.ctx.pending_mgr.save(temp)
        else:
            self.ctx.pending_mgr.clear()
        
        # Update state
        self.ctx.editing_date = None
        self.ctx.pending_source = "stash_pop"
        
        stack_depth = len(self.ctx.pending_stack)
        print(f"Swapped pending with stashed entry (both preserved).")
        print(f"Stack depth: {stack_depth}")
    
    def _destructive_get(self, actual_index: int) -> None:
        """Get and discard current pending."""
        stash_entry = self.ctx.pending_stack.pop(actual_index)
        pending = self._extract_pending(stash_entry)
        
        if pending:
            self.ctx.pending_mgr.save(pending)
        else:
            self.ctx.pending_mgr.clear()
        
        # Update state
        self.ctx.editing_date = None
        self.ctx.pending_source = "stash_pop"
        
        print("Restored from stash.")
        
        # Show summary
        from .pending_commands import ShowCommand
        ShowCommand(self.ctx).execute("")
    
    def _drop(self, args: list) -> None:
        """Remove entry from stack without restoring."""
        if not args:
            print("Usage: stash drop <index>")
            print("Example: stash drop 2")
            return
        
        force = "--force" in args or "-f" in args
        
        try:
            index = int(args[0])
        except ValueError:
            print(f"Invalid index: {args[0]}")
            return
        
        stack_depth = len(self.ctx.pending_stack)
        
        if index < 1 or index > stack_depth:
            print(f"Invalid index. Stack has {stack_depth} entries. Use 'stash list' to see.")
            return
        
        # Convert to 0-based, newest-first
        actual_index = stack_depth - index
        
        # Get entry info for confirmation
        entry = self.ctx.pending_stack[actual_index]
        pending = self._extract_pending(entry)
        
        if pending:
            entry_date = pending.get("date", "unknown")
            item_count = len(pending.get("items", []))
        else:
            entry_date = "empty"
            item_count = 0
        
        # Confirm unless forced
        if not force:
            print(f"Drop stash entry #{index} ({entry_date}, {item_count} items)? (y/N): ", end="")
            response = input().strip().lower()
            
            if response not in ("y", "yes"):
                print("Cancelled.")
                return
        
        # Drop entry
        self.ctx.pending_stack.pop(actual_index)
        
        new_depth = len(self.ctx.pending_stack)
        print(f"Dropped stash entry #{index}.")
        print(f"Stack now has {new_depth} entries.")
    
    def _discard(self, args: list) -> None:
        """Clear entire stash."""
        force = "--force" in args or "-f" in args
        
        stack_depth = len(self.ctx.pending_stack)
        
        if stack_depth == 0:
            print("Stash is already empty.")
            return
        
        # Show what will be lost
        print(f"\nStash has {stack_depth} entries that will be PERMANENTLY LOST:")
        
        for i in range(stack_depth - 1, -1, -1):
            entry = self.ctx.pending_stack[i]
            display_index = stack_depth - i
            
            pending = self._extract_pending(entry)
            
            if pending:
                entry_date = pending.get("date", "unknown")
                item_count = len(pending.get("items", []))
            else:
                entry_date = "empty"
                item_count = 0
            
            print(f"  #{display_index}  {entry_date}  {item_count} items")
        
        print()
        
        # Require explicit "yes"
        if force:
            print("--force flag detected, but confirming anyway for safety...")
        
        response = input("Type 'yes' to confirm: ").strip().lower()
        
        if response != "yes":
            print("Cancelled.")
            return
        
        # Clear stack
        self.ctx.pending_stack.clear()
        print("Stash cleared.")
    
    def _extract_pending(self, entry) -> dict:
        """
        Extract pending from stash entry.
        
        Handles both old format (just dict) and new format (metadata dict).
        
        Args:
            entry: Stash entry (dict or metadata dict)
        
        Returns:
            Pending data dict or None
        """
        if entry is None:
            return None
        
        # New format: {"pending": {...}, "timestamp": ..., "auto": ...}
        if isinstance(entry, dict) and "pending" in entry:
            return entry["pending"]
        
        # Old format: just the pending dict itself
        return entry
    
    def _format_age(self, timestamp: datetime) -> str:
        """
        Format timestamp as human-readable age.
        
        Args:
            timestamp: datetime when stashed
        
        Returns:
            Age string (e.g., "5 minutes ago", "2 hours ago")
        """
        now = datetime.now()
        delta = now - timestamp
        
        seconds = delta.total_seconds()
        
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            # Show date for old entries
            return timestamp.strftime("%Y-%m-%d")

@register_command
class LoadLogCommand(Command):
    """Load a log date into pending for editing."""
    
    name = "loadlog"
    help_text = "Load log date for editing (loadlog YYYY-MM-DD)"
    
    def execute(self, args: str) -> None:
        """
        Load log date into pending for editing.
        
        Prompts for confirmation if pending has items.
        Auto-stashes current pending before loading.
        Shows summary instead of full items list.
        
        Args:
            args: Date string (YYYY-MM-DD) and optional --force flag
        """
        # Parse arguments
        parts = args.strip().split()
        if not parts:
            print("Usage: loadlog <YYYY-MM-DD> [--force]")
            return
        
        query_date = parts[0]
        force = "--force" in parts or "-f" in parts
        
        # Get log entries for this date
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"No log entries found for {query_date}.")
            return
        
        # Parse codes from log
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("")
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"No codes found for {query_date}.")
            return
        
        items = CodeParser.parse(all_codes)
        
        # Check if current pending has items
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        has_current_items = current and current.get("items")
        
        # Confirm if pending has items (unless forced)
        if has_current_items and not force:
            if not self._confirm_auto_stash(current):
                print("Cancelled.")
                return
        
        # Auto-stash current pending if it has items
        if has_current_items:
            # Deep copy to avoid mutation
            snapshot = copy.deepcopy(current)
            
            # Create stash entry with metadata
            stash_entry = {
                "pending": snapshot,
                "timestamp": datetime.now(),
                "auto": True  # Mark as auto-stashed
            }
            
            self.ctx.pending_stack.append(stash_entry)
            
            stack_depth = len(self.ctx.pending_stack)
            print(f"Auto-stashed current pending (stack depth: {stack_depth})")
        
        # Load log date into pending
        pending = {
            "date": query_date,
            "items": items
        }
        
        self.ctx.pending_mgr.save(pending)
        self.ctx.editing_date = query_date
        self.ctx.pending_source = "editing"
        
        # Show summary (NOT full items list)
        item_count = len(items)
        print(f"Loaded {query_date} from log into editor ({item_count} items).")
        print("Use 'applylog' to save changes back, or 'discard' to cancel.")
        print("Use 'items' for full list.")
    
    def _confirm_auto_stash(self, current: dict) -> bool:
        """
        Confirm before auto-stashing current pending.
        
        Args:
            current: Current pending data
        
        Returns:
            True if user confirms, False if cancelled
        """
        items = current.get("items", [])
        item_count = len(items)
        current_date = current.get("date", "unknown")
        
        print(f"\nCurrent pending has {item_count} item(s) for {current_date}.")
        print("These will be AUTO-STASHED (preserved, not lost) before loading log.")
        
        response = input("Continue? (Y/n): ").strip().lower()
        
        # Default to Yes on Enter
        if response == "" or response in ("y", "yes"):
            return True
        else:
            return False
        
@register_command
class ApplyLogCommand(Command):
    """Apply pending changes back to log."""
    
    name = "applylog"
    help_text = "Apply edited pending back to log"
    
    def execute(self, args: str) -> None:
        """
        Apply pending changes back to log.
        
        Can only be used after loadlog.
        """
        if self.ctx.editing_date is None:
            print("Not in log editing mode. Use 'loadlog' first.")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None:
            print("No pending data to apply.")
            return
        
        query_date = self.ctx.editing_date
        items = pending.get("items", [])
        
        # Build codes string from items - FIXED to include meal_override
        code_parts = []
        for item in items:
            if "time" in item and item.get("time"):
                time_str = f"@{item['time']}"
                meal_override = item.get("meal_override")
                if meal_override:
                    time_str += f" ({meal_override})"
                code_parts.append(time_str)
            elif "code" in item:
                code = item["code"]
                mult = item.get("mult", 1.0)
                if abs(mult - 1.0) < 1e-9:
                    code_parts.append(code)
                else:
                    code_parts.append(f"{code} x{mult:g}")
        
        codes_str = ", ".join(code_parts)
        
        # Calculate totals
        from .pending_commands import ShowCommand
        show_cmd = ShowCommand(self.ctx)
        totals, missing, _ = show_cmd._calculate_totals(items)
        
        # Update log
        success = self.ctx.log.update_date(query_date, codes_str, totals)
        
        if success:
            self.ctx.log.save()
            print(f"Applied changes to {query_date} in log.")
            
            # Clear editing state
            self.ctx.editing_date = None
            
            # Clear pending
            self.ctx.pending_mgr.clear()

            self.ctx.pending_source = "empty"
            
        else:
            print(f"Failed to update {query_date} in log.")


"""
Discard command with state-aware confirmation.

Updated to prevent accidental data loss by checking pending_source.
"""

@register_command  
class DiscardCommand(Command):
    """Discard pending without saving."""
    
    name = "discard"
    help_text = "Discard pending (normal or loaded log)"
    
    def execute(self, args: str) -> None:
        """
        Discard current pending.
        
        Behavior depends on pending_source:
        - "empty": Nothing to discard
        - "editing": Cancel log edit (stash preserved)
        - "normal" or "stash_pop": Confirm before discarding
        
        Args:
            args: Optional "--force" or "-f" flag
        """
        # Check for force flag
        force = "--force" in args or "-f" in args
        
        # Get current state
        pending_source = self.ctx.pending_source
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        # Case 1: Empty pending - nothing to discard
        if pending_source == "empty" or not pending or not pending.get("items"):
            print("No pending to discard.")
            return
        
        # Case 2: Editing mode - just canceling edit
        if self.ctx.editing_date:
            self._discard_editing_mode(force)
            return
        
        # Case 3: Normal or stash_pop - requires confirmation
        self._discard_with_confirmation(pending, force)
    
    def _discard_editing_mode(self, force: bool) -> None:
        """
        Discard in editing mode (loaded log).
        
        Args:
            force: Force flag (still warns even with force)
        """
        # Clear pending and editing state
        self.ctx.pending_mgr.clear()
        self.ctx.editing_date = None
        self.ctx.pending_source = "empty"
        
        # Always show message, even with force
        print("Discarded log edits (original pending preserved in stash).")
        if force:
            print("Note: --force is unnecessary when canceling log edits.")
        print("Use 'stash pop' to restore original pending.")
    
    def _discard_with_confirmation(self, pending: dict, force: bool) -> None:
        """
        Discard with confirmation (normal or stash_pop source).
        
        Args:
            pending: Pending data
            force: Force flag
        """
        items = pending.get("items", [])
        item_count = len(items)
        pending_date = pending.get("date", "unknown")
        
        # Show warning even with --force
        print(f"\nPending has {item_count} item(s) for {pending_date} that will be PERMANENTLY LOST.")
        
        if force:
            print("--force flag detected, but confirming anyway for safety...")
        
        # Require explicit "yes"
        response = input("Type 'yes' to confirm discard, or Ctrl+C to cancel: ").strip().lower()
        
        if response != "yes":
            print("Discard cancelled.")
            return
        
        # Confirmed - discard
        self.ctx.pending_mgr.clear()
        self.ctx.pending_source = "empty"
        print("Pending discarded.")