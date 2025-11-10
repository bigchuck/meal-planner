"""
Log editing commands: stash, loadlog, applylog.
"""
from datetime import date as date_type
from .base import Command, register_command
from .pending_commands import ShowCommand
from meal_planner.parsers import CodeParser


@register_command
class StashCommand(Command):
    """Stash/restore pending day."""
    
    name = "stash"
    help_text = "Stash pending (stash push or stash pop)"
    
    def execute(self, args: str) -> None:
        """
        Stash operations.
        
        Args:
            args: "push" or "pop"
        """
        action = args.strip().lower()
        
        if action == "push":
            self._push()
        elif action == "pop":
            self._pop()
        else:
            print("Usage: stash push or stash pop")
    
    def _push(self) -> None:
        """Push current pending to stack."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        # Deep copy to avoid mutation
        import copy
        snapshot = copy.deepcopy(pending) if pending else None
        
        self.ctx.pending_stack.append(snapshot)
        print(f"Stashed current pending. Stack depth: {len(self.ctx.pending_stack)}")
    
    def _pop(self) -> None:
        """Pop from stack and restore."""
        if not self.ctx.pending_stack:
            print("Stash is empty.")
            return
        
        pending = self.ctx.pending_stack.pop()
        
        if pending:
            self.ctx.pending_mgr.save(pending)
        else:
            self.ctx.pending_mgr.clear()
        
        # Clear editing state
        self.ctx.editing_date = None
        
        print("Restored from stash.")
        ShowCommand(self.ctx).execute("")


@register_command
class LoadLogCommand(Command):
    """Load a log date into pending for editing."""
    
    name = "loadlog"
    help_text = "Load log date for editing (loadlog YYYY-MM-DD)"
    
    def execute(self, args: str) -> None:
        """
        Load log date into pending for editing.
        
        Args:
            args: Date string (YYYY-MM-DD)
        """
        if not args.strip():
            print("Usage: loadlog <YYYY-MM-DD>")
            return
        
        query_date = args.strip()
        
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
        
        # Auto-stash current pending
        try:
            current = self.ctx.pending_mgr.load()
        except Exception:
            current = None
        
        if current and current.get("items"):
            # Stash current pending
            import copy
            self.ctx.pending_stack.append(copy.deepcopy(current))
            print(f"Auto-stashed current pending (stack depth: {len(self.ctx.pending_stack)})")
        
        # Load log date into pending
        pending = {
            "date": query_date,
            "items": items
        }
        
        self.ctx.pending_mgr.save(pending)
        self.ctx.editing_date = query_date
        
        print(f"Loaded {query_date} from log into editor.")
        print("Use 'applylog' to save changes back, or 'discard' to cancel.")
        
        # Show items
        from .item_management import ItemsCommand
        ItemsCommand(self.ctx).execute("")


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
        
        # Build codes string from items
        code_parts = []
        for item in items:
            if "time" in item and item.get("time"):
                code_parts.append(f"@{item['time']}")
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
        else:
            print(f"Failed to update {query_date} in log.")


@register_command  
class DiscardCommand(Command):
    """Discard pending without saving."""
    
    name = "discard"
    help_text = "Discard pending (normal or loaded log)"
    
    def execute(self, args: str) -> None:
        """
        Discard current pending.
        
        If in log editing mode, just clears pending and exits that mode.
        Stash remains intact for potential pop.
        """
        if self.ctx.editing_date:
            # Discarding log edit
            self.ctx.pending_mgr.clear()
            self.ctx.editing_date = None
            print("Discarded log edits. Use 'stash pop' to restore original pending.")
        else:
            # Discarding normal pending
            self.ctx.pending_mgr.clear()
            print("Pending discarded.")