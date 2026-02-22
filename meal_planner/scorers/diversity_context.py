# meal_planner/scorers/diversity_context.py
"""
Diversity context for meal recommendation scoring.

Resolves source references (pending, planning:<id>) into pre-computed
group tallies that diversity scorers consume.  Built once per scoring
session, passed to every candidate scorer call.

Classes:
    DailyCountTally   - Resolved totals per group for daily_count scorer
    DiversityContext  - Container for all resolved diversity data
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# =============================================================================
# DailyCountTally
# =============================================================================

@dataclass
class DailyCountTally:
    """
    Pre-resolved group totals accumulated from all configured sources.

    Built once before the scoring pass begins.  Each key is a group_id
    (uppercase).  The value is the sum of code-weights found across all
    source meals.

    Example:
        {"EGG": 1.0}   <- one egg found in pending, candidate adds its own
    """
    totals: Dict[str, float] = field(default_factory=dict)
    # Source tokens that were successfully resolved (for diagnostics)
    resolved_sources: List[str] = field(default_factory=list)
    # Source tokens that were requested but not found (for diagnostics)
    skipped_sources: List[str] = field(default_factory=list)

    def get(self, group_id: str) -> float:
        """Return accumulated total for a group (0.0 if not seen)."""
        return self.totals.get(group_id.upper(), 0.0)

    def add(self, group_id: str, amount: float) -> None:
        """Add amount to a group total."""
        gid = group_id.upper()
        self.totals[gid] = self.totals.get(gid, 0.0) + amount


# =============================================================================
# DiversityContext
# =============================================================================

@dataclass
class DiversityContext:
    """
    Container for all resolved diversity scoring data.

    Holds one DailyCountTally (and placeholders for future scorers).
    Built once per scoring session via DiversityContext.build().

    Attributes:
        daily_count: Resolved group tallies for the daily_count scorer.
                     None if the scorer is disabled or config is absent.
    """
    daily_count: Optional[DailyCountTally] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        thresholds,          # ThresholdsManager
        pending_mgr,         # PendingManager
        workspace_mgr,       # WorkspaceManager
    ) -> "DiversityContext":
        """
        Build a DiversityContext by resolving all configured sources.

        Args:
            thresholds:    ThresholdsManager (provides get_daily_count_config)
            pending_mgr:   PendingManager    (provides pending items)
            workspace_mgr: WorkspaceManager  (provides planning meals by ID)

        Returns:
            Populated DiversityContext ready for the scoring pass.
        """
        ctx = cls()

        dc_config = thresholds.get_daily_count_config()
        if dc_config is None:
            # Scorer disabled or absent — leave daily_count as None
            return ctx

        ctx.daily_count = _resolve_daily_count(
            config=dc_config,
            pending_mgr=pending_mgr,
            workspace_mgr=workspace_mgr,
        )
        return ctx


# =============================================================================
# Internal resolution helpers
# =============================================================================

def _resolve_daily_count(
    config: Dict[str, Any],
    pending_mgr,
    workspace_mgr,
) -> DailyCountTally:
    """
    Resolve all sources listed in daily_count config and accumulate group totals.

    Args:
        config:        Normalised daily_count config dict from ThresholdsManager.
        pending_mgr:   PendingManager instance.
        workspace_mgr: WorkspaceManager instance.

    Returns:
        DailyCountTally with accumulated totals.
    """
    tally = DailyCountTally()
    groups = config.get("groups", [])

    # Build a fast lookup: uppercase_code -> (group_id, weight)
    # First match wins when a code could theoretically appear in multiple groups.
    code_index = _build_code_index(groups)

    for source_token in config.get("sources", []):
        token = source_token.strip().lower()

        if token == "pending":
            items = _extract_pending_items(pending_mgr)
            if items is not None:
                _accumulate(items, code_index, tally)
                tally.resolved_sources.append("pending")
            else:
                # Pending absent is not an error - nothing to count
                tally.resolved_sources.append("pending (empty)")

        elif token.startswith("planning:"):
            plan_id = source_token.strip()[len("planning:"):]   # preserve original case
            items = _extract_planning_items(plan_id, workspace_mgr)
            if items is not None:
                _accumulate(items, code_index, tally)
                tally.resolved_sources.append(f"planning:{plan_id}")
            else:
                # Warn and continue — do not disable the scorer
                print(
                    f"Warning: daily_count: planning source "
                    f"'planning:{plan_id}' not found in workspace -- source skipped"
                )
                tally.skipped_sources.append(f"planning:{plan_id}")

        # Unknown token types are already caught by validation; skip silently here.

    return tally


def _build_code_index(
    groups: List[Dict[str, Any]],
) -> Dict[str, List[tuple]]:
    """
    Build a flat code -> [(group_id, weight), ...] lookup from group definitions.

    A code may appear in multiple groups; all matches are retained so that
    accumulation contributes the code's weight to every qualifying group.

    Args:
        groups: List of group dicts from normalised config.

    Returns:
        Dict mapping uppercase code string to list of (group_id, weight) tuples.
    """
    index: Dict[str, List[tuple]] = {}
    for group in groups:
        gid = group["group_id"]   # already uppercase from accessor
        for code, weight in group.get("codes", {}).items():
            code_upper = code.upper()
            if code_upper not in index:
                index[code_upper] = []
            index[code_upper].append((gid, float(weight)))
    return index


def _extract_pending_items(pending_mgr) -> Optional[List[str]]:
    """
    Extract food codes from the pending meal.

    Time marker dicts are skipped; only dicts with a 'code' key are used.

    Args:
        pending_mgr: PendingManager instance.

    Returns:
        List of (uppercase_code, mult) tuples, or None if pending is empty/absent.
    """
    try:
        pending = pending_mgr.load()
    except Exception as exc:
        print(f"Warning: daily_count: could not load pending -- {exc}")
        return None

    if pending is None:
        return None

    raw_items = pending.get("items", [])
    if not raw_items:
        return None

    return _codes_from_items(raw_items)


def _extract_planning_items(
    plan_id: str,
    workspace_mgr,
) -> Optional[List[str]]:
    """
    Extract food codes from a specific planning meal in the workspace.

    Args:
        plan_id:       Workspace meal ID (original case from config).
        workspace_mgr: WorkspaceManager instance.

    Returns:
        List of (uppercase_code, mult) tuples, or None if ID not found.
    """
    try:
        workspace = workspace_mgr.load()
    except Exception as exc:
        print(f"Warning: daily_count: could not load workspace -- {exc}")
        return None

    meals = workspace.get("meals", {})

    # Case-insensitive ID lookup
    plan_id_upper = plan_id.upper()
    matched_meal = None
    for meal_id, meal_data in meals.items():
        if meal_id.upper() == plan_id_upper:
            matched_meal = meal_data
            break

    if matched_meal is None:
        return None

    raw_items = matched_meal.get("items", [])
    return _codes_from_items(raw_items) if raw_items else []  # type: ignore[return-value]


def _codes_from_items(items: List[Dict[str, Any]]) -> List[tuple]:
    """
    Extract (code, multiplier) pairs from a raw items list.

    Skips time marker dicts (those without a 'code' key).
    Multiplier defaults to 1.0 when the field is absent.

    Args:
        items: List of item dicts (may include time markers).

    Returns:
        List of (uppercase_code, mult) tuples.
    """
    result = []
    for item in items:
        if isinstance(item, dict) and "code" in item:
            code = str(item["code"]).strip().upper()
            if code:
                mult = float(item.get("mult", 1.0))
                result.append((code, mult))
    return result


def _accumulate(
    code_mults: List[tuple],
    code_index: Dict[str, List[tuple]],
    tally: DailyCountTally,
) -> None:
    """
    Add contributions into the tally for all matched groups.

    Contribution per item = code_value * item_multiplier.
    A code may match multiple groups; each receives its contribution
    independently (multi-group accumulation).

    Args:
        code_mults: List of (uppercase_code, mult) tuples from one source.
        code_index: Flat lookup built from group definitions.
        tally:      DailyCountTally to update in place.
    """
    for code, mult in code_mults:
        matches = code_index.get(code)
        if matches is not None:
            for group_id, code_value in matches:
                tally.add(group_id, code_value * mult)