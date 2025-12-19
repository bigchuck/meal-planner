# meal_planner/commands/explain_command.py
"""
Explain command - show educational content from documentation files.

Displays markdown documentation for nutrition and meal planning concepts.
"""
import shlex
from pathlib import Path
from .base import Command, register_command
from config import DOCS_DIR


@register_command
class ExplainCommand(Command):
    """Show explanation of a concept from documentation."""
    
    name = "explain"
    help_text = "Explain a concept from docs (explain gi, explain glycemic-load)"
    
    def execute(self, args: str) -> None:
        """
        Show explanation from markdown documentation.
        
        Args:
            args: "<topic>" - topic name (use hyphens for multi-word: glycemic-load)
        
        Examples:
            explain                  -> List available topics
            explain gi               -> Show GI explanation
            explain glycemic-load    -> Show glycemic load explanation
            explain risk-scoring     -> Show risk scoring explanation
        """
        if not args.strip():
            self._list_topics()
            return
        
        # Parse topic (no meal names, no dates, no flags - just the topic)
        topic = self._normalize_topic(args.strip())
        
        # Show the explanation
        self._show_explanation(topic)
    
    def _normalize_topic(self, topic: str) -> str:
        """
        Normalize topic to filename format.
        
        Args:
            topic: Raw topic string
        
        Returns:
            Normalized topic (lowercase, spaces to hyphens)
        """
        return topic.lower().replace(" ", "-")
    
    def _show_explanation(self, topic: str) -> None:
        """
        Show explanation for a topic from markdown files.
        
        Looks in personal docs first, then templates.
        
        Args:
            topic: Normalized topic name
        """
        from meal_planner.utils.docs_renderer import render_explanation
        
        # Try personal docs first (user's custom docs)
        personal_file = DOCS_DIR / "personal" / f"{topic}.md"
        
        # Then try templates (default docs)
        template_file = DOCS_DIR / "templates" / f"{topic}.md"
        
        if personal_file.exists():
            render_explanation(personal_file, context="personal")
        elif template_file.exists():
            render_explanation(template_file, context="template")
        else:
            print(f"\nNo explanation found for '{topic}'")
            print("\nAvailable topics:")
            self._list_topics()
    
    def _list_topics(self) -> None:
        """List all available explanation topics from docs directory."""
        templates_dir = DOCS_DIR / "templates"
        personal_dir = DOCS_DIR / "personal"
        
        topics = set()
        
        # Collect from templates
        if templates_dir.exists():
            for f in templates_dir.glob("*.md"):
                topics.add(f.stem)
        
        # Collect from personal (skip files starting with _)
        if personal_dir.exists():
            for f in personal_dir.glob("*.md"):
                if not f.name.startswith("_"):
                    topics.add(f.stem)
        
        if not topics:
            print("\nNo explanations available yet.")
            print("\nTo add explanations:")
            print("  1. Create markdown files in docs/templates/ (default docs)")
            print("  2. Or in docs/personal/ (your custom docs)")
            print("\nExample: docs/templates/gi.md")
            return
        
        print("\nAvailable explanations:")
        for topic in sorted(topics):
            print(f"  {topic}")
        
        print("\nUsage:")
        print("  explain <topic>")
        print("\nExamples:")
        print("  explain gi")
        print("  explain glycemic-load")
        print("  explain risk-scoring")
        print()