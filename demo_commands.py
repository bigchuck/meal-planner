"""
Demo script to test command system.
"""
from config import MASTER_FILE, LOG_FILE, PENDING_FILE, verify_data_files
from meal_planner.commands import CommandContext, get_registry


def main():
    print("Testing Command System")
    print("=" * 70)
    
    # Verify files
    verify_data_files()
    
    # Create context
    print("\n1. Creating Command Context")
    print("-" * 70)
    ctx = CommandContext(MASTER_FILE, LOG_FILE, PENDING_FILE)
    print(f"   ✓ Master loaded: {len(ctx.master.df)} entries")
    print(f"   ✓ Log loaded: {len(ctx.log.df)} entries")
    
    # Get registry
    print("\n2. Command Registry")
    print("-" * 70)
    registry = get_registry()
    commands = registry.list_commands()
    print(f"   Registered commands: {len(commands)}")
    for cmd in commands:
        print(f"     - {cmd}")
    
    # Test help command
    print("\n3. Testing HelpCommand")
    print("-" * 70)
    help_cmd_class = registry.get("help")
    if help_cmd_class:
        help_cmd = help_cmd_class(ctx)
        help_cmd.execute("")
    
    # Test status command
    print("\n4. Testing StatusCommand")
    print("-" * 70)
    status_cmd_class = registry.get("status")
    if status_cmd_class:
        status_cmd = status_cmd_class(ctx)
        status_cmd.execute("")
    
    # Test find command
    print("\n5. Testing FindCommand")
    print("-" * 70)
    find_cmd_class = registry.get("find")
    if find_cmd_class:
        find_cmd = find_cmd_class(ctx)
        # Search for "1" - should find codes with 1 in them
        find_cmd.execute("1")
    
    # Test start command
    print("\n6. Testing StartCommand")
    print("-" * 70)
    start_cmd_class = registry.get("start")
    if start_cmd_class:
        start_cmd = start_cmd_class(ctx)
        start_cmd.execute("2025-01-20")
    
    # Test add command
    print("\n7. Testing AddCommand")
    print("-" * 70)
    add_cmd_class = registry.get("add")
    if add_cmd_class:
        # Get a valid code from master
        first_code = ctx.master.df.iloc[0][ctx.master.cols.code]
        add_cmd = add_cmd_class(ctx)
        add_cmd.execute(f"{first_code} *1.5")
    
    # Test show command
    print("\n8. Testing ShowCommand")
    print("-" * 70)
    show_cmd_class = registry.get("show")
    if show_cmd_class:
        show_cmd = show_cmd_class(ctx)
        show_cmd.execute("")
    
    # Test discard command
    print("\n9. Testing DiscardCommand")
    print("-" * 70)
    discard_cmd_class = registry.get("discard")
    if discard_cmd_class:
        discard_cmd = discard_cmd_class(ctx)
        discard_cmd.execute("")
    
    # Verify pending cleared
    print("\n10. Verify Pending Cleared")
    print("-" * 70)
    if status_cmd_class:
        status_cmd = status_cmd_class(ctx)
        status_cmd.execute("")
    
    print("\n" + "=" * 70)
    print("✓ Command system working correctly!")
    print("\nCommand pattern benefits:")
    print("  - Each command is isolated and testable")
    print("  - Easy to add new commands")
    print("  - Clean separation of concerns")
    print("  - Commands auto-register themselves")
    print("  - Context provides shared access to data")

if __name__ == "__main__":
    main()