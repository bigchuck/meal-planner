# meal_planner/scorers/diversity_context.py
"""
Diversity context for meal recommendation scoring.

Resolves source references (pending, planning:<id>) into pre-computed
group tallies that diversity scorers consume.  Built once per scoring
session, passed to every candidate scorer call.

Classes:
    DailyCountTally      - Resolved totals per group for daily_count scorer
    IntradayMealPresence - Per-meal group presence map for intraday scorer
    InterdayGroupPresence  - Per-slot group presence across recent history days
    DiversityContext     - Container for all resolved diversity data
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
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
# IntradayMealPresence
# =============================================================================

@dataclass
class IntradayMealPresence:
    """
    Per-meal group contribution map for the intraday diversity scorer.

    Tracks, for each resolved source meal, which groups had any
    contribution and how much.  The scorer counts how many meals
    contain a group (occurrences > 0) to compute the additive penalty.

    Structure:
        meal_groups: Dict[source_label, Dict[group_name, float]]
            source_label  - e.g. "pending", "planning:N1"
            group_name    - uppercase group key from config
            float         - sum of (item_mult) for all matching codes
                            in that meal.  > 0.0 means group is present.

    Example after build with pending=turkey+eggs, planning:N1=turkey:
        {
            "pending":     {"PROTEIN": 1.0, "EGG": 2.0},
            "planning:N1": {"PROTEIN": 1.0},
        }

    Attributes:
        meal_groups:      The per-meal, per-group presence map.
        resolved_sources: Source tokens successfully resolved.
        skipped_sources:  Source tokens requested but not found.
    """
    meal_groups:      Dict[str, Dict[str, float]] = field(default_factory=dict)
    resolved_sources: List[str]                   = field(default_factory=list)
    skipped_sources:  List[str]                   = field(default_factory=list)

    def get_meal(self, source_label: str) -> Dict[str, float]:
        """Return the group map for one source meal (empty dict if absent)."""
        return self.meal_groups.get(source_label, {})

    def occurrence_count(self, group_id: str) -> int:
        """
        Count how many source meals contain this group (contribution > 0).

        Args:
            group_id: Uppercase group name.

        Returns:
            Number of source meals where the group is present.
        """
        gid = group_id.upper()
        return sum(
            1
            for meal_tally in self.meal_groups.values()
            if meal_tally.get(gid, 0.0) > 0.0
        )

@dataclass
class InterdayGroupPresence:
    """
    Per-day, per-slot group presence map for the interday diversity scorer.
    Built from closed log history for the configured lookback window.
    Structure:
        day_slots: Dict[day_offset, Dict[meal_slot, Dict[group_name, float]]]
            day_offset  - int, 1 = yesterday, 2 = two days ago, etc.
            meal_slot   - uppercase canonical meal name e.g. "LUNCH"
            group_name  - uppercase group key from config
            float       - sum of item_mult for all matching codes in that slot

    Example:
        {1: {"LUNCH": {"POULTRY": 1.5}}, 2: {"LUNCH": {"POULTRY": 1.0}}}
    """
    day_slots: Dict[int, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    resolved_days: List[int] = field(default_factory=list)
    skipped_days:  List[int] = field(default_factory=list)

    def get_slot(self, day_offset: int, meal_slot: str) -> Dict[str, float]:
        """Return group->weight map for a specific day/slot (empty dict if absent)."""
        return self.day_slots.get(day_offset, {}).get(meal_slot.upper(), {})

    def set_slot(self, day_offset: int, meal_slot: str, tally: Dict[str, float]) -> None:
        """Store group tally for a specific day/slot."""
        if day_offset not in self.day_slots:
            self.day_slots[day_offset] = {}
        self.day_slots[day_offset][meal_slot.upper()] = tally


# =============================================================================
# DiversityContext
# =============================================================================

@dataclass
class DiversityContext:
    """
    Container for all resolved diversity scoring data.

    Holds one DailyCountTally and one IntradayMealPresence (and
    placeholders for future scorers).  Built once per scoring session
    via DiversityContext.build().

    Attributes:
        daily_count: Resolved group tallies for the daily_count scorer.
                     None if the scorer is disabled or config is absent.
        intraday:    Per-meal group presence map for the intraday scorer.
                     None if the scorer is disabled or config is absent.
        interday:    Per-day/slot group presence from recent history.
                     None if the scorer is disabled or config is absent.
    """
    daily_count: Optional[DailyCountTally]     = None
    intraday:    Optional[IntradayMealPresence] = None
    interday:    Optional[InterdayGroupPresence] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(
    cls,
    thresholds,          # ThresholdsManager
    pending_mgr,         # PendingManager
    workspace_mgr,       # WorkspaceManager
    log_mgr=None,        # LogManager (optional; required for interday scorer)
    ) -> "DiversityContext":
        """
        Build a DiversityContext by resolving all configured sources.
            Args:
                thresholds:    ThresholdsManager (provides scorer configs)
                pending_mgr:   PendingManager    (provides pending items)
                workspace_mgr: WorkspaceManager  (provides planning meals by ID)
                log_mgr:       LogManager        (provides closed history for interday)

            Returns:
                Populated DiversityContext ready for the scoring pass.
        """
        ctx = cls()

        # --- daily_count ---
        dc_config = thresholds.get_daily_count_config()
        if dc_config is not None:
            ctx.daily_count = _resolve_daily_count(
                config=dc_config,
                pending_mgr=pending_mgr,
                workspace_mgr=workspace_mgr,
            )

        # --- intraday ---
        intraday_config = thresholds.get_intraday_diversity_config()
        if intraday_config is not None:
            ctx.intraday = _resolve_intraday(
                config=intraday_config,
                pending_mgr=pending_mgr,
                workspace_mgr=workspace_mgr,
            )

        # --- interday ---
        interday_config = thresholds.get_interday_config()
        if interday_config is not None and log_mgr is not None:
            ctx.interday = _resolve_interday(
                config=interday_config,
                log_mgr=log_mgr,
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


# =============================================================================
# Intraday resolution
# =============================================================================

def _resolve_intraday(
    config: Dict[str, Any],
    pending_mgr,
    workspace_mgr,
) -> IntradayMealPresence:
    """
    Resolve all sources listed in intraday config into per-meal group maps.

    Each source becomes one entry in IntradayMealPresence.meal_groups.
    The value is a dict of group_name -> total contribution for that meal.
    A missing planning source emits a warning and is recorded as an empty
    entry (warn-and-continue, same policy as daily_count).

    Args:
        config:        Normalised intraday config from get_intraday_diversity_config().
        pending_mgr:   PendingManager instance.
        workspace_mgr: WorkspaceManager instance.

    Returns:
        IntradayMealPresence with one entry per resolved source.
    """
    presence = IntradayMealPresence()
    groups   = config.get("groups", {})

    # Build code -> [group_name, ...] index (codes are a list, weight = 1.0 implicit)
    code_index = _build_intraday_code_index(groups)

    for source_token in config.get("sources", []):
        token = source_token.strip().lower()

        if token == "pending":
            items = _extract_pending_items(pending_mgr)
            if items is not None:
                meal_tally = _tally_for_intraday(items, code_index)
                presence.meal_groups["pending"] = meal_tally
                presence.resolved_sources.append("pending")
            else:
                # No pending is valid — record empty, not an error
                presence.meal_groups["pending"] = {}
                presence.resolved_sources.append("pending (empty)")

        elif token.startswith("planning:"):
            plan_id = source_token.strip()[len("planning:"):]   # preserve original case
            items   = _extract_planning_items(plan_id, workspace_mgr)
            label   = f"planning:{plan_id}"
            if items is not None:
                meal_tally = _tally_for_intraday(items, code_index)
                presence.meal_groups[label] = meal_tally
                presence.resolved_sources.append(label)
            else:
                print(
                    f"Warning: intraday: planning source "
                    f"'{label}' not found in workspace -- source skipped"
                )
                presence.meal_groups[label] = {}
                presence.skipped_sources.append(label)

        # Unknown token types caught by validation; skip silently here.

    return presence


def _build_intraday_code_index(
    groups: Dict[str, Any],
) -> Dict[str, List[str]]:
    """
    Build a flat code -> [group_name, ...] lookup from intraday group definitions.

    Intraday group codes are a plain list (no per-code weights).
    A code may appear in multiple groups; all matches are retained.

    Args:
        groups: Dict of group_name (uppercase) -> {codes: [...], ...}
                as returned by get_intraday_diversity_config().

    Returns:
        Dict mapping uppercase code string to list of group names.
    """
    index: Dict[str, List[str]] = {}
    for group_name, group_def in groups.items():
        for code in group_def.get("codes", []):
            code_upper = code.upper()
            if code_upper not in index:
                index[code_upper] = []
            index[code_upper].append(group_name)
    return index


def _tally_for_intraday(
    code_mults: List[tuple],
    code_index: Dict[str, List[str]],
) -> Dict[str, float]:
    """
    Compute per-group contribution totals for a single meal's items.

    Contribution per item = item_multiplier (codes have no individual weight
    in intraday groups).  A group's total > 0.0 means it is present in the
    meal.  A code may contribute to multiple groups simultaneously.

    Args:
        code_mults: List of (uppercase_code, mult) tuples from one source.
        code_index: Flat lookup from _build_intraday_code_index().

    Returns:
        Dict mapping group_name to total contribution for this meal.
        Groups with zero contribution are omitted.
    """
    meal_tally: Dict[str, float] = {}
    for code, mult in code_mults:
        if mult <= 0.0:
            continue
        matches = code_index.get(code)
        if matches:
            for group_name in matches:
                meal_tally[group_name] = meal_tally.get(group_name, 0.0) + mult
    return meal_tally

def _resolve_interday(
    config: Dict[str, Any],
    log_mgr,
    ) -> InterdayGroupPresence:
    """
    Build per-day, per-slot group presence from closed log history.
    Reads the configured lookback window of closed daily logs, parses each
    row's codes string (which may contain time markers) using
    parse_selection_to_items(), assigns items to meal slots via
    categorize_time(), then tallies group contributions per slot.

    Args:
        config:  Normalised interday config from get_interday_config().
                Expected keys: lookback_days (int), groups (dict,
                same structure as intraday groups).
        log_mgr: LogManager instance.

    Returns:
        InterdayGroupPresence keyed by day_offset (1 = yesterday).
    """
    from datetime import date, timedelta
    from meal_planner.parsers.code_parser import parse_selection_to_items
    from meal_planner.utils.time_utils import categorize_time

    presence    = InterdayGroupPresence()
    groups      = config.get("groups", {})
    lookback    = int(config.get("lookback_days", 3))
    today       = date.today()

    # Build code -> [group_name, ...] index (same structure as intraday)
    code_index = _build_intraday_code_index(groups)

    for offset in range(1, lookback + 1):
        target_date = str(today - timedelta(days=offset))

        try:
            rows = log_mgr.get_entries_for_date(target_date)
        except Exception as exc:
            print(f"Warning: interday: could not read log for {target_date} -- {exc}")
            presence.skipped_days.append(offset)
            continue

        if rows.empty:
            # No log for that day — not an error, just no data
            presence.skipped_days.append(offset)
            continue

        # Accumulate slot tallies across all rows for this date.
        # Each row's 'codes' string is parsed to recover time markers and
        # food codes; categorize_time() maps times to canonical meal slots.
        slot_tallies: Dict[str, Dict[str, float]] = {}

        codes_col = log_mgr.cols.codes  # resolves actual column name

        for _, row in rows.iterrows():
            codes_str = str(row.get(codes_col, "") or "")
            if not codes_str.strip():
                continue

            items = parse_selection_to_items(codes_str)

            current_slot: Optional[str] = None
            for item in items:
                if "time" in item and "code" not in item:
                    current_slot = categorize_time(
                        item["time"], item.get("meal_override")
                    )
                elif "code" in item and current_slot:
                    slot_key = current_slot.upper()
                    code     = str(item["code"]).strip().upper()
                    mult     = float(item.get("mult", 1.0))
                    if not code or mult <= 0.0:
                        continue
                    matches = code_index.get(code)
                    if matches:
                        if slot_key not in slot_tallies:
                            slot_tallies[slot_key] = {}
                        for group_name in matches:
                            slot_tallies[slot_key][group_name] = (
                                slot_tallies[slot_key].get(group_name, 0.0) + mult
                            )

        # Store resolved slot tallies and record success
        for slot_key, tally in slot_tallies.items():
            presence.set_slot(offset, slot_key, tally)

        presence.resolved_days.append(offset)

    return presence