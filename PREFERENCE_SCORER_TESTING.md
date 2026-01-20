# Preference Scorer Testing Guide

## Setup

1. **Add config to meal_plan_config.json:**
```json
"recommendation_weights": {
  "nutrient_gap": 1.0,
  "preference": 0.8,  // Enable preference scorer
  ...
}

"scorers": {
  "preference": {
    "frozen_item_bonus": 0.05,
    "staple_item_bonus": 0.03,
    "unavailable_item_penalty": 0.5,
    "base_score": 0.5
  }
}
```

2. **Configure user preferences (meal_plan_user_preferences.json):**
```json
{
  "frozen_portions": {
    "items": {
      "MT.10": 2.0,
      "FI.3": 1.5
    }
  },
  "staple_foods": {
    "codes": ["EG.1", "BV.4", "VE.T1"]
  },
  "unavailable_items": {
    "codes": ["SW.7", "DA.3"]
  }
}
```

3. **Add display method to RecommendCommand** (see preference_scorer_integration.txt)

## Test Scenarios

### Scenario A: Meal with Frozen Items
```bash
# Create meal using frozen items
> plan invent lunch
> plan add N1 MT.10, FI.3, VE.T1
> recommend score N1

Expected Output:
  Frozen Items: 2
    MT.10, FI.3
  Frozen Bonus: +0.10 (2 items * 0.05)
  Final Score: ~0.60 (0.5 base + 0.10)
```

### Scenario B: Meal with Staples
```bash
# Create meal using staples
> plan invent breakfast
> plan add N2 EG.1 *2, BV.4, VE.T1
> recommend score N2

Expected Output:
  Staple Items: 3
    EG.1, BV.4, VE.T1
  Staple Bonus: +0.09 (3 items * 0.03)
  Final Score: ~0.59 (0.5 base + 0.09)
```

### Scenario C: Meal with Unavailable Items
```bash
# Create meal using unavailable items
> plan invent dinner
> plan add N3 MT.10, SW.7, DA.3
> recommend score N3

Expected Output:
  Unavailable Items: 2
    SW.7, DA.3
  Unavailable Penalty: -1.0 (2 items * 0.5)
  Final Score: 0.0 (0.5 base - 1.0, clamped to 0.0)
```

### Scenario D: Mixed Meal
```bash
# Meal with frozen, staples, and unavailable
> plan invent mixed
> plan add N4 EG.1, MT.10, SW.7
> recommend score N4

Expected Output:
  Frozen Items: 1 (MT.10)
  Staple Items: 1 (EG.1)
  Unavailable Items: 1 (SW.7)
  
  Frozen Bonus: +0.05
  Staple Bonus: +0.03
  Unavailable Penalty: -0.50
  
  Final Score: 0.08 (0.5 + 0.05 + 0.03 - 0.50, clamped to 0.08)
```

### Scenario E: No Preferences
```bash
# Meal with generic items (no frozen/staples/unavailable)
> plan search lunch --history 5
> recommend score <id>

Expected Output:
  Frozen Items: 0
  Staple Items: 0
  Unavailable Items: 0
  
  Final Score: 0.50 (base score, no bonuses or penalties)
```

## Checklist

- [ ] Scorer initializes with config
- [ ] Frozen items identified correctly
- [ ] Staple items identified correctly
- [ ] Unavailable items identified correctly
- [ ] Bonuses calculated correctly
- [ ] Penalties calculated correctly
- [ ] Score clamped to 0.0-1.0 range
- [ ] Display shows item counts and lists
- [ ] Display shows bonus/penalty breakdown
- [ ] Works with both workspace and pending meals

## Common Issues

**Issue: All counts show 0**
- Check user preferences file loaded correctly
- Verify food codes match exactly (case-insensitive matching implemented)

**Issue: Score too high/low**
- Review bonus/penalty values in config
- Check base_score setting (default 0.5)
- Verify unavailable_item_penalty isn't too harsh

**Issue: Items not identified**
- Ensure user_prefs is available in context
- Check food codes in meal match codes in preferences

## Adjusting Sensitivity

Tune these config values:

**Increase frozen/staple importance:**
```json
"frozen_item_bonus": 0.10,  // Was 0.05
"staple_item_bonus": 0.06   // Was 0.03
```

**Reduce unavailable penalty:**
```json
"unavailable_item_penalty": 0.3  // Was 0.5
```

**Change baseline:**
```json
"base_score": 0.6  // Was 0.5 (higher baseline = more forgiving)
```
