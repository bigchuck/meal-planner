# meal_planner/commands/explain_command.py
"""
Explain command - show educational content about concepts.
"""
from pathlib import Path
from .base import Command, register_command
from config import DOCS_DIR


@register_command
class ExplainCommand(Command):
    """Show explanation of a concept."""
    
    name = "explain"
    help_text = "Explain a concept (explain gi, explain BREAKFAST curve-types)"
    
    def execute(self, args: str) -> None:
        """
        Show explanation from docs.
        
        Args:
            args: "<topic>" or "<MEAL> <topic>"
        """
        if not args.strip():
            self._list_topics()
            return
        
        parts = args.strip().split(maxsplit=1)
        
        # Check if first part is a meal name (all caps meals from report)
        potential_meal = parts[0].upper()
        meal_names = ["BREAKFAST", "LUNCH", "DINNER", "MORNING SNACK", 
                     "AFTERNOON SNACK", "EVENING"]
        
        if potential_meal in meal_names and len(parts) > 1:
            # explain <MEAL> <topic>
            meal = potential_meal
            topic = self._normalize_topic(parts[1])
            self._show_meal_explanation(meal, topic)
        else:
            # explain <topic>
            topic = self._normalize_topic(args.strip())
            self._show_general_explanation(topic)
    
    def _normalize_topic(self, topic: str) -> str:
        """Normalize topic to filename format."""
        return topic.lower().replace(" ", "-")
    
    def _show_general_explanation(self, topic: str) -> None:
        """Show general explanation for a topic."""
        from meal_planner.utils.docs_renderer import render_explanation
        
        # Try personal docs first, then templates
        personal_file = DOCS_DIR / "personal" / f"{topic}.md"
        template_file = DOCS_DIR / "templates" / f"{topic}.md"
        
        if personal_file.exists():
            render_explanation(personal_file, context="personal")
        elif template_file.exists():
            render_explanation(template_file, context="template")
        else:
            print(f"\nNo explanation found for '{topic}'")
            print("\nAvailable topics:")
            self._list_topics()
    
    def _show_meal_explanation(self, meal: str, topic: str) -> None:
        """Show meal-specific explanation."""
        from meal_planner.utils.docs_renderer import render_explanation
        
        # Try meal-specific doc
        meal_filename = meal.lower().replace(" ", "-")
        personal_file = DOCS_DIR / "personal" / f"{meal_filename}-{topic}.md"
        template_file = DOCS_DIR / "templates" / f"{meal_filename}-{topic}.md"
        
        if personal_file.exists():
            render_explanation(personal_file, context="personal")
        elif template_file.exists():
            render_explanation(template_file, context="template")
        else:
            # Fall back to general explanation
            print(f"\n(No {meal}-specific explanation for '{topic}', showing general...)\n")
            self._show_general_explanation(topic)
    
    def _list_topics(self) -> None:
        """List all available explanation topics."""
        templates_dir = DOCS_DIR / "templates"
        personal_dir = DOCS_DIR / "personal"
        
        topics = set()
        
        # Collect from templates
        if templates_dir.exists():
            for f in templates_dir.glob("*.md"):
                topics.add(f.stem)
        
        # Collect from personal
        if personal_dir.exists():
            for f in personal_dir.glob("*.md"):
                if not f.name.startswith("_"):  # Skip private notes
                    topics.add(f.stem)
        
        if not topics:
            print("\nNo explanations available yet.")
            print("Add markdown files to docs/templates/ or docs/personal/")
            return
        
        print("\nAvailable explanations:")
        for topic in sorted(topics):
            # Check if meal-specific
            if any(meal.lower().replace(" ", "-") in topic 
                   for meal in ["BREAKFAST", "LUNCH", "DINNER"]):
                print(f"  {topic} (meal-specific)")
            else:
                print(f"  {topic}")
        
        print("\nUsage:")
        print("  explain <topic>              - General explanation")
        print("  explain <MEAL> <topic>       - Meal-specific explanation")
        print()