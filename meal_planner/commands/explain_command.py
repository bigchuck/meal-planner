# meal_planner/commands/explain_command.py
"""
Explain command - show educational content about concepts.
"""
from pathlib import Path
from typing import Optional
from .base import Command, register_command
from config import DOCS_DIR
from meal_planner.models import DailyTotals
from meal_planner.utils.time_utils import MEAL_NAMES


@register_command
class ExplainCommand(Command):
    """Show explanation of a concept."""
    
    name = "explain"
    help_text = "Explain a concept (explain gi, explain DINNER risk-scoring)"
    
    def execute(self, args: str) -> None:
        """
        Show explanation from docs or contextualized from data.
        
        Args:
            args: "<topic>" or "<MEAL> <topic>"
        """
        if not args.strip():
            self._list_topics()
            return
        
        parts = args.strip().split(maxsplit=1)
        
        # Check if first part is a meal name
        potential_meal = parts[0].upper()
        
        if potential_meal in MEAL_NAMES and len(parts) > 1:
            # explain <MEAL> <topic>
            meal = potential_meal
            topic = self._normalize_topic(parts[1])
            
            # Check if we can provide contextualized explanation
            if topic == "risk-scoring":
                meal_data = self._get_meal_data(meal)
                if meal_data:
                    self._show_personalized_risk_explanation(meal, meal_data)
                    return
            
            # Fall back to file-based
            self._show_meal_explanation(meal, topic)
        else:
            # explain <topic>
            topic = self._normalize_topic(args.strip())
            self._show_general_explanation(topic)
    
    def _normalize_topic(self, topic: str) -> str:
        """Normalize topic to filename format."""
        return topic.lower().replace(" ", "-")
    
    def _get_meal_data(self, meal_name: str) -> Optional[DailyTotals]:
        """Get actual meal data from pending or most recent log."""
        from meal_planner.reports.report_builder import ReportBuilder
        from meal_planner.parsers import CodeParser
        
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        # Try pending first
        try:
            pending = self.ctx.pending_mgr.load()
            if pending and pending.get("items"):
                items = pending.get("items", [])
                report = builder.build_from_items(items, title="Analysis")
                breakdown = report.get_meal_breakdown()
                
                if breakdown:
                    for m_name, m_time, m_totals in breakdown:
                        if m_name == meal_name:
                            return m_totals
        except Exception:
            pass
        
        # Try most recent log entry with this meal
        try:
            # Get last few days of log
            import pandas as pd
            from datetime import date, timedelta
            
            end_date = str(date.today())
            start_date = str(date.today() - timedelta(days=7))
            
            log_df = self.ctx.log.get_date_range(start_date, end_date)
            if not log_df.empty:
                # Try most recent date
                date_col = self.ctx.log.cols.date
                codes_col = self.ctx.log.cols.codes
                
                for _, row in log_df.sort_values(date_col, ascending=False).iterrows():
                    codes_str = str(row[codes_col])
                    if not codes_str or codes_str == "nan":
                        continue
                    
                    items = CodeParser.parse(codes_str)
                    report = builder.build_from_items(items, title="Analysis")
                    breakdown = report.get_meal_breakdown()
                    
                    if breakdown:
                        for m_name, m_time, m_totals in breakdown:
                            if m_name == meal_name:
                                return m_totals
        except Exception:
            pass
        
        return None
    
    def _show_personalized_risk_explanation(self, meal_name: str, totals: DailyTotals) -> None:
        """Show risk explanation personalized to actual meal data."""
        from meal_planner.commands.glucose_command import (
            _safe_get, _carb_risk_score, _gi_speed_factor,
            _fat_delay_score, _protein_tail_score, _fiber_buffer_score
        )
        
        # Calculate GI
        gi = None
        if totals.carbs_g > 0:
            gi = (totals.glycemic_load / totals.carbs_g) * 100
        
        # Build meal dict
        meal_dict = {
            'carbs_g': totals.carbs_g,
            'fat_g': totals.fat_g,
            'protein_g': totals.protein_g,
            'fiber_g': totals.fiber_g,
            'gi': gi
        }
        
        # Calculate components
        carb_risk = _carb_risk_score(meal_dict['carbs_g'])
        gi_factor = _gi_speed_factor(gi)
        base_carb_risk = min(carb_risk * gi_factor, 10.0)
        fat_delay = _fat_delay_score(meal_dict['fat_g'])
        protein_tail = _protein_tail_score(meal_dict['protein_g'])
        fiber_buffer = _fiber_buffer_score(meal_dict['fiber_g'])
        
        raw_score = (
            base_carb_risk
            + 0.6 * fat_delay
            + 0.5 * protein_tail
            - 0.7 * fiber_buffer
        )
        risk_score = max(0.0, min(10.0, raw_score))
        
        # Display personalized explanation
        print(f"\n{'═' * 70}")
        print(f"Risk Scoring Explanation for {meal_name}")
        print(f"{'═' * 70}\n")
        
        print(f"Your {meal_name.lower()} meal composition:")
        print(f"  Carbs:   {totals.carbs_g:6.1f}g")
        print(f"  Protein: {totals.protein_g:6.1f}g")
        print(f"  Fat:     {totals.fat_g:6.1f}g")
        print(f"  Fiber:   {totals.fiber_g:6.1f}g")
        if gi:
            print(f"  GI:      {gi:6.0f}")
        print()
        
        print(f"Risk Score: {risk_score:.1f} / 10\n")
        
        print("How this score was calculated:\n")
        
        # Base carb risk
        print(f"1. Base Carb Risk: {carb_risk:.1f}")
        self._explain_carb_risk(totals.carbs_g, carb_risk)
        print()
        
        # GI speed factor
        if gi:
            print(f"2. GI Speed Factor: {gi_factor:.1f}x")
            self._explain_gi_factor(gi, gi_factor)
            print(f"   → Base risk after GI: {base_carb_risk:.1f}")
            print()
        
        # Fat delay
        if fat_delay > 0:
            print(f"3. Fat Delay Risk: +{fat_delay:.1f}")
            self._explain_fat_delay(totals.fat_g, fat_delay)
            print()
        
        # Protein tail
        if protein_tail > 0:
            print(f"4. Protein Tail Risk: +{protein_tail:.1f}")
            self._explain_protein_tail(totals.protein_g, protein_tail)
            print()
        
        # Fiber buffer
        if fiber_buffer > 0:
            print(f"5. Fiber Buffer: -{fiber_buffer:.1f}")
            self._explain_fiber_buffer(totals.fiber_g, fiber_buffer)
            print()
        
        # Summary
        print(f"{'─' * 70}")
        print(f"Total Risk Score: {risk_score:.1f} / 10")
        print()
        
        # Interpretation
        if risk_score < 3:
            rating = "LOW"
            msg = "Minimal glucose impact expected"
        elif risk_score < 6:
            rating = "MEDIUM"
            msg = "Moderate spike likely"
        elif risk_score < 8.5:
            rating = "HIGH"
            msg = "Significant spike expected"
        else:
            rating = "VERY HIGH"
            msg = "Large spike very likely"
        
        print(f"Rating: {rating} - {msg}")
        print()
    
    def _explain_carb_risk(self, carbs_g: float, risk: float) -> None:
        """Explain carb risk component."""
        print(f"   Your meal has {carbs_g:.1f}g carbs.")
        if carbs_g <= 5:
            print("   Negligible carb load - minimal impact")
        elif carbs_g <= 20:
            print("   Low carb load - small impact")
        elif carbs_g <= 40:
            print("   Moderate carb load - noticeable impact")
        elif carbs_g <= 70:
            print("   High carb load - significant impact")
        else:
            print("   Very high carb load - major impact")
    
    def _explain_gi_factor(self, gi: float, factor: float) -> None:
        """Explain GI speed factor."""
        print(f"   Your meal's GI is {gi:.0f}.")
        if gi < 40:
            print("   Low GI means slow absorption (reduces risk by 20%)")
        elif gi < 60:
            print("   Medium GI means moderate absorption (neutral)")
        else:
            print("   High GI means fast absorption (increases risk by 20%)")
    
    def _explain_fat_delay(self, fat_g: float, risk: float) -> None:
        """Explain fat delay component."""
        print(f"   Your meal has {fat_g:.1f}g fat.")
        if fat_g <= 5:
            print("   Minimal fat - no delay effect")
        elif fat_g <= 15:
            print("   Low fat - slight delay in absorption")
        elif fat_g <= 25:
            print("   Moderate fat - noticeable delay (watch for late spike)")
        elif fat_g <= 35:
            print("   High fat - significant delay (pizza effect likely)")
        else:
            print("   Very high fat - major delay and potential insulin resistance")
    
    def _explain_protein_tail(self, protein_g: float, risk: float) -> None:
        """Explain protein tail component."""
        print(f"   Your meal has {protein_g:.1f}g protein.")
        if protein_g <= 10:
            print("   Low protein - minimal tail effect")
        elif protein_g <= 20:
            print("   Moderate protein - slight extended curve")
        elif protein_g <= 35:
            print("   Good protein - noticeable tail (second rise possible)")
        else:
            print("   High protein - significant tail effect (watch 3-4 hours later)")
    
    def _explain_fiber_buffer(self, fiber_g: float, buffer: float) -> None:
        """Explain fiber buffer component."""
        print(f"   Your meal has {fiber_g:.1f}g fiber.")
        if fiber_g <= 2:
            print("   Minimal fiber - little spike protection")
        elif fiber_g <= 6:
            print("   Some fiber - moderate spike blunting")
        elif fiber_g <= 10:
            print("   Good fiber - significant spike reduction")
        else:
            print("   Excellent fiber - strong spike protection")
    
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
        """Show meal-specific explanation from files."""
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
        
        # Add dynamic topics
        topics.add("risk-scoring (contextualized when used with meal)")
        
        if not topics:
            print("\nNo explanations available yet.")
            print("Add markdown files to docs/templates/ or docs/personal/")
            return
        
        print("\nAvailable explanations:")
        for topic in sorted(topics):
            print(f"  {topic}")
        
        print("\nUsage:")
        print("  explain <topic>              - General explanation")
        print("  explain <MEAL> <topic>       - Contextualized to actual meal data")
        print()
