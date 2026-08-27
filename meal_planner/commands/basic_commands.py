"""
Basic commands: help, quit, reload.
"""
from .base import Command, register_command, get_registry
from .help_categories import CATEGORIES


@register_command
class HelpCommand(Command):
    """Show help information."""

    name = ("help", "h", "?")
    category = "System"
    help_text = "Show this help message (help [command|category] [subcommand|--detail])"
    overview_help = (
        "help  —  Show available commands, grouped by category\n"
        "\n"
        "Usage:\n"
        "  help                          List all commands, grouped by category\n"
        "  help <category>               List commands in one category\n"
        "  help <command>                Show a command's syntax and description\n"
        "  help <command> --detail       Show full detail: every flag and example\n"
        "  help <command> <subcommand>   Show help for one subcommand (commands that have them)\n"
        "\n"
        f"Categories: {', '.join(CATEGORIES)}"
    )

    def execute(self, args: str) -> None:
        """Display help for all commands, a category, or one command."""
        registry = get_registry()
        arg_str = args.strip()

        if not arg_str:
            self._show_grouped(registry)
            return

        category_match = self._match_category(arg_str)
        if category_match:
            self._show_category(registry, category_match)
            return

        tokens = arg_str.split()
        cmd_name = tokens[0].lower()
        cmd_class = registry.get(cmd_name)

        if cmd_class is None:
            print(f"\nUnknown command or category: '{arg_str}'\n")
            return

        rest = tokens[1:]

        if rest and rest[0] == "--detail":
            detail = cmd_class.detailed_help or cmd_class.overview_help or cmd_class.help_text
            print(f"\n{detail}\n")
            return

        if rest:
            subcommand = rest[0].lower()
            sub_help = cmd_class.subcommand_help or {}
            if subcommand in sub_help:
                print(f"\n{sub_help[subcommand]}\n")
            else:
                print(f"\nUnknown subcommand '{subcommand}' for '{cmd_name}'.")
                if sub_help:
                    print(f"Available subcommands: {', '.join(sorted(sub_help.keys()))}")
                print()
            return

        overview = cmd_class.overview_help or cmd_class.detailed_help or cmd_class.help_text
        print(f"\n{overview}\n")

    def _match_category(self, text: str) -> str | None:
        """Case-insensitive match of the full args string against a category name."""
        for cat in CATEGORIES:
            if text.lower() == cat.lower():
                return cat
        return None

    def _group_by_category(self, registry) -> dict:
        """Group all registered command classes by their category."""
        commands = registry.get_all_commands()
        commands.sort(key=lambda c: c.name if isinstance(c.name, str) else c.name[0])

        grouped: dict = {}
        for cmd_class in commands:
            grouped.setdefault(cmd_class.category, []).append(cmd_class)
        return grouped

    def _print_command_lines(self, cmd_classes: list) -> None:
        """Print one summary line per command class."""
        for cmd_class in cmd_classes:
            if isinstance(cmd_class.name, str):
                names = cmd_class.name
            else:
                names = ", ".join(cmd_class.name)
            print(f"  {names:20} {cmd_class.help_text}")

    def _show_grouped(self, registry) -> None:
        """List every command, grouped by category."""
        if self.ctx.mode_mgr.is_active:
            mode = self.ctx.mode_mgr.active_mode
            print(f"\n*** Currently in {mode.prompt_display} mode ***")
            print("Commands shown below can be used WITHOUT the mode prefix")
            print("Prefix with '.' to use global commands")
            print()

        print("\nAvailable Commands:")
        print("=" * 70)

        by_category = self._group_by_category(registry)

        for cat in CATEGORIES:
            cmd_classes = by_category.get(cat, [])
            if not cmd_classes:
                continue
            print(f"\n{cat}")
            print("-" * len(cat))
            self._print_command_lines(cmd_classes)

        print("\n" + "=" * 70)
        print("Type 'help <command>' for details, 'help <category>' to filter by category.")
        print()

    def _show_category(self, registry, category: str) -> None:
        """List only the commands in one category."""
        by_category = self._group_by_category(registry)
        cmd_classes = by_category.get(category, [])

        print(f"\n{category}")
        print("=" * 70)
        self._print_command_lines(cmd_classes)
        print()


@register_command
class QuitCommand(Command):
    """Exit the application."""

    name = ("quit", "q")
    category = "System"
    help_text = "Exit the application"
    overview_help = "quit (or q)  —  Exit the application immediately. Workspace is auto-saved on exit."

    def execute(self, args: str) -> None:
        """Exit with message."""
        print("SO LONG, CRABBY!")
        raise SystemExit(0)

@register_command
class ReloadCommand(Command):
    """Reload data files from disk."""

    name = "reload"
    category = "System"
    help_text = "Reload data files (reload [--config|--master|--alias|--user|--all])"
    overview_help = (
        "reload  —  Reload data files from disk without restarting\n"
        "\n"
        "Usage:\n"
        "  reload              Reload everything (master, config, aliases, user prefs)\n"
        "  reload --master     Reload just the master database\n"
        "  reload --config     Reload just meal_plan_config.json (thresholds)\n"
        "  reload --alias      Reload just the alias file\n"
        "  reload --user       Reload just user preferences\n"
        "  reload --all        Same as no flags\n"
        "\n"
        "Flags can be combined, e.g. 'reload --master --config'."
    )

    def execute(self, args: str) -> None:
        """Reload data files based on flags."""
        args_lower = args.strip().lower()
        
        # Determine what to reload
        reload_all = not args_lower or args_lower == "--all"
        reload_master = reload_all or "--master" in args_lower
        reload_config = reload_all or "--config" in args_lower
        reload_alias = reload_all or "--alias" in args_lower
        reload_user = reload_all or "--user" in args_lower
        
        reloaded = []
        
        # Reload master
        if reload_master:
            self.ctx.reload_master()
            count = len(self.ctx.master.df)
            reloaded.append(f"master ({count} entries)")
        
        # Reload config/thresholds
        if reload_config:
            self.ctx.reload_config()
            reloaded.append("config")
        
        # Reload aliases
        if reload_alias:
            if self.ctx.aliases:
                self.ctx.reload_aliases()
                count = len(self.ctx.aliases.aliases)
                reloaded.append(f"aliases ({count} entries)")
            elif reload_all:
                # Only mention if explicitly requested or --all
                reloaded.append("aliases (not configured)")
        
        # Reload user preferences
        if reload_user:
            if self.ctx.user_prefs:
                self.ctx.reload_user_prefs()
                reloaded.append("user preferences")
            elif reload_all:
                reloaded.append("user preferences (not configured)")
        
        # Show what was reloaded
        if reloaded:
            print(f"Reloaded: {', '.join(reloaded)}")
        else:
            print("No files reloaded")