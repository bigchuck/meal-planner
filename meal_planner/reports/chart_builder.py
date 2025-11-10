"""
Chart builder for nutrient trends with moving averages.

Generates matplotlib charts showing daily values and rolling averages,
with gaps preserved (missing dates show as breaks in the line).
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Headless backend
import matplotlib.pyplot as plt
import webbrowser
import os
from pathlib import Path
from typing import Optional


class ChartBuilder:
    """
    Builds trend charts with moving averages.
    
    Creates multi-panel charts showing:
    - Daily values (solid line)
    - Moving average (dashed line)
    - Gaps in data (line breaks)
    - Single-day values (marked with +/x)
    """
    
    def __init__(self, output_file: Path = Path("meal_plan_trend.jpg")):
        """
        Initialize chart builder.
        
        Args:
            output_file: Output file path
        """
        self.output_file = output_file
    
    def build_from_dataframe(self, df: pd.DataFrame, window: int = 7,
                            title: Optional[str] = None) -> None:
        """
        Build chart from DataFrame with date and nutrient columns.
        
        Args:
            df: DataFrame with columns: date, cal, prot_g, carbs_g, fat_g, sugar_g, gl
            window: Moving average window (days)
            title: Chart title (optional)
        """
        if df.empty:
            print("(no data to chart)")
            return
        
        # Normalize and prepare data
        df = self._prepare_data(df)
        
        if df.empty:
            print("(no valid data to chart)")
            return
        
        # Create continuous calendar index
        full_df = self._create_continuous_calendar(df)
        
        # Calculate rolling averages
        roll_df = full_df.rolling(window=window, min_periods=1).mean()
        
        # Create the chart
        self._create_chart(full_df, roll_df, window, title)
        
        # Open in browser
        webbrowser.open(os.path.abspath(self.output_file))
        print(f"Chart saved to {self.output_file} and opened in browser.")
    
    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame: convert date, ensure numeric columns."""
        df = df.copy()
        
        # Convert date
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        
        if df.empty:
            return df
        
        # Ensure numeric columns
        for col in ["cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "gl"]:
            if col not in df.columns:
                df[col] = 0
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df
    
    def _create_continuous_calendar(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create continuous daily calendar from min to max date.
        Missing dates become NaN (creates gaps in charts).
        """
        if df.empty:
            return df
        
        # Date range
        full_idx = pd.date_range(
            start=df["date"].min(),
            end=df["date"].max(),
            freq="D"
        )
        
        # Reindex with full date range
        df = df.set_index("date").reindex(full_idx)
        
        return df
    
    def _create_chart(self, daily_df: pd.DataFrame, ma_df: pd.DataFrame,
                     window: int, title: Optional[str]) -> None:
        """Create and save the multi-panel chart."""
        # Metrics to plot
        metrics = [
            ("cal", "Calories"),
            ("prot_g", "Protein (g)"),
            ("carbs_g", "Carbs (g)"),
            ("fat_g", "Fat (g)"),
            ("sugar_g", "Sugars (g)"),
            ("gl", "Glycemic Load"),
        ]
        
        # Create figure with 6 subplots
        fig, axes = plt.subplots(6, 1, figsize=(10, 14), sharex=True, 
                                constrained_layout=True)
        
        dates = daily_df.index.values
        
        # Plot each metric
        for ax, (col, label) in zip(axes, metrics):
            y_daily = daily_df[col].values.astype(float)
            y_ma = ma_df[col].values.astype(float)
            
            # Mask MA where daily data is missing (to create gaps)
            y_ma_masked = np.where(np.isnan(y_daily), np.nan, y_ma)
            
            # Plot with gap handling
            self._plot_with_gaps(
                ax, dates, y_daily,
                color="black", linestyle="-", linewidth=1.5,
                label="Daily", singleton_marker="+", singleton_label="Daily (+1)"
            )
            
            self._plot_with_gaps(
                ax, dates, y_ma_masked,
                color="red", linestyle="--", linewidth=2.0,
                label=f"MA({window})", singleton_marker="x", 
                singleton_label=f"MA({window}) (x1)"
            )
            
            ax.set_ylabel(label)
            ax.grid(True, alpha=0.25)
            ax.legend(loc="upper left", frameon=False)
        
        # X-axis label
        axes[-1].set_xlabel("Date")
        
        # Title
        if title:
            fig.suptitle(title, fontsize=14)
        else:
            fig.suptitle(
                f"Daily Totals + Moving Average ({window} days) - "
                f"gaps broken; singletons marked ('+' daily, 'x' MA)",
                fontsize=14
            )
        
        # Save
        fig.savefig(self.output_file, dpi=150, format="jpg")
        plt.close(fig)
    
    def _plot_with_gaps(self, ax, dates, values, *, color, linestyle="-",
                       linewidth=1.5, label=None, singleton_label=None,
                       singleton_marker="+", markersize=8):
        """
        Plot data with gaps (NaN breaks line) and special handling for singletons.
        
        Args:
            ax: Matplotlib axis
            dates: Date values
            values: Y values (may contain NaN for gaps)
            color: Line color
            linestyle: Line style
            linewidth: Line width
            label: Label for line segments
            singleton_label: Label for isolated points
            singleton_marker: Marker for singletons
            markersize: Marker size
        """
        dates = np.asarray(dates)
        y = np.asarray(values, dtype=float)
        valid = ~np.isnan(y)
        
        if not valid.any():
            return
        
        # Find valid indices
        idxs = np.where(valid)[0]
        
        # Split into contiguous segments (calendar is daily, so gap = jump > 1 day)
        splits = np.where(np.diff(idxs) > 1)[0] + 1
        segments = np.split(idxs, splits)
        
        used_line_label = False
        used_single_label = False
        
        for seg in segments:
            if len(seg) == 1:
                # Singleton point
                i = seg[0]
                lbl = (singleton_label 
                      if (singleton_label and not used_single_label and not used_line_label)
                      else None)
                
                ax.plot([dates[i]], [y[i]],
                       marker=singleton_marker, color=color, 
                       markersize=markersize, linewidth=0,
                       label=lbl)
                
                if lbl:
                    used_single_label = True
            else:
                # Line segment (2+ points)
                lbl = label if not used_line_label else None
                
                ax.plot(dates[seg], y[seg],
                       color=color, linestyle=linestyle, linewidth=linewidth,
                       label=lbl)
                
                if lbl:
                    used_line_label = True