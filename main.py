"""
Meal Planner - Main Entry Point

A refactored, modular meal planning and nutrition tracking application.
"""
from config import MASTER_FILE, LOG_FILE, PENDING_FILE, USER_PREFS_FILE, verify_data_files, MODE
from meal_planner.commands import CommandContext, get_registry


def print_welcome():
    """Print welcome message."""
    print("=" * 70)
    print("  Meal Plan Logger")
    print("  Type 'help' for commands, 'quit' to exit")
    print("=" * 70)
    print()


def repl():
    """
    Main Read-Eval-Print Loop.
    
    Handles user input and dispatches to registered commands.
    """
    # Verify data files exist
    try:
        verify_data_files()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease check your configuration and ensure data files exist.")
        return
    
    # Print welcome
    print_welcome()
    
    # Create command context (shared state for all commands)
    from config import ALIASES_FILE, THRESHOLDS_FILE, \
                        WORKSPACE_FILE, STAGING_BUFFER_FILE, EMAIL_CONFIG_FILE, EMAIL_SEND_LOG
    ctx = CommandContext(MASTER_FILE, LOG_FILE, PENDING_FILE, ALIASES_FILE, 
                        THRESHOLDS_FILE, USER_PREFS_FILE, WORKSPACE_FILE,
                        STAGING_BUFFER_FILE, EMAIL_CONFIG_FILE, EMAIL_SEND_LOG)

    import atexit
    # Register auto-save on exit
    def save_on_exit():
        """Save workspace before program exits."""
        ctx.save_workspace()

    atexit.register(save_on_exit)

    # Get command registry
    registry = get_registry()
    
    # Main loop
    while True:
        # Build prompt based on mode
        if ctx.mode_mgr.is_active:
            prompt = f"[{ctx.mode_mgr.active_mode.prompt_display}]> "
        else:
            prompt = "> "

        try:
            # Get input
            user_input = input(prompt).strip()
            
            # Skip empty input
            if not user_input:
                continue
            
            # Handle mode exit keyword
            if ctx.mode_mgr.is_active and user_input.lower() == "exit":
                message = ctx.mode_mgr.exit_mode()
                print(message)
                continue
            
            # Check for global command escape (dot prefix)
            if ctx.mode_mgr.is_active and user_input.startswith('.'):
                # Strip dot and process as global command
                user_input = user_input[1:].strip()
                if not user_input:
                    continue
                # Fall through to normal dispatch
            else:
                # Apply mode prefix if in mode
                user_input = ctx.mode_mgr.apply_mode_prefix(user_input)

            # Parse command and arguments
            parts = user_input.split(maxsplit=1)
            cmd_name = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            # Look up command
            cmd_class = registry.get(cmd_name)
            
            if cmd_class is None:
                print(f"Unknown command: '{cmd_name}'. Type 'help' for available commands.")
                continue
            
            # Execute command
            try:
                cmd = cmd_class(ctx)
                cmd.execute(args)
                # Track usage using canonical name (first alias)
                canonical_name = cmd.name if isinstance(cmd.name, str) else cmd.name[0]
                ctx.usage.track(canonical_name)

                # After each command, validate mode is still valid
                if ctx.mode_mgr.is_active:
                    warning = ctx.mode_mgr.auto_exit_if_invalid()
                    if warning:
                        print(f"\n{warning}\n")
 
            except SystemExit:
                # Quit command raises SystemExit
                raise
            except Exception as e:
                print(f"Error executing command: {e}")
                # In development mode, show full traceback
                if MODE == "DEVELOPMENT":
                    import traceback
                    traceback.print_exc()
        
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D
            print("\nGoodbye!")
            break
        except SystemExit:
            # Quit command
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            if MODE == "DEVELOPMENT":
                import traceback
                traceback.print_exc()


def main():
    """Main entry point."""
    try:
        repl()
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"Fatal error: {e}")
        if MODE == "DEVELOPMENT":
            import traceback
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())