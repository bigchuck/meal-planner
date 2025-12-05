# meal_planner/utils/docs_renderer.py
"""
Markdown documentation renderer for terminal display.
"""
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

console = Console()


def render_explanation(filepath: Path, context: str = "template") -> None:
    """
    Render markdown file to terminal.
    
    Args:
        filepath: Path to markdown file
        context: "template" or "personal" (for attribution)
    """
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print(f"\nError reading {filepath.name}: {e}\n")
        return
    
    # Show source indicator
    if context == "personal":
        console.print(f"[dim](from your personal docs)[/dim]\n")
    
    # Render markdown
    md = Markdown(content)
    console.print(md)
    console.print()  # Trailing newline


def list_available_topics(docs_dir: Path) -> list:
    """
    Get list of available explanation topics.
    
    Args:
        docs_dir: Base docs directory
    
    Returns:
        Sorted list of topic names
    """
    topics = set()
    
    # Scan templates
    templates_dir = docs_dir / "templates"
    if templates_dir.exists():
        for f in templates_dir.glob("*.md"):
            topics.add(f.stem)
    
    # Scan personal (exclude private notes starting with _)
    personal_dir = docs_dir / "personal"
    if personal_dir.exists():
        for f in personal_dir.glob("*.md"):
            if not f.name.startswith("_"):
                topics.add(f.stem)
    
    return sorted(topics)