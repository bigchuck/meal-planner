# Thresholds Configuration Quick Reference

## File Location
`meal_plan_thresholds.json` in project root directory

## Top-Level Structure
```json
{
  "version": "1.0",
  "daily_targets": { ... },
  "glucose_scoring": { ... },
  "curve_classification": { ... },
  "explain_messages": { ... }
}
```

## Section Details

### daily_targets
Used by: `report --risk`

Per-day thresholds that are divided by meal_count for per-meal checks.

```json
"daily_targets": {
  "sugar_g": 50,           // Daily sugar threshold
  "glycemic_load": 100,    // Daily GL threshold
  "protein_g": 100,        // Daily protein minimum
  "fat_pct": 35,           // Fat % of calories max
  "carbs_pct": 60,         // Carbs % of calories max
  "calories_min": 1200,    // Very low calorie threshold
  "calories_max": 3000     // Very high calorie threshold
}
```

### glucose_scoring
Used by: `glucose` command and `explain` command

Range-based scoring for glucose risk calculation.

**Range Array Pattern:**
```json
[
  {"max": 5, "score": 0.0},
  {"max": 20, "score": 2.0},
  {"max": null, "score": 10.0}  // Last entry must have max: null
]
```

**Fields:**
- `carb_risk_ranges` - Maps carb grams to risk scores (0-10)
- `gi_speed_factors` - GI multipliers (0.8, 1.0, 1.2)
- `fat_delay_ranges` - Fat grams to delay risk (0-7)
- `protein_tail_ranges` - Protein grams to tail risk (0-4)
- `fiber_buffer_ranges` - Fiber grams to buffer score (0-5)
- `risk_score_weights` - Component weights in final calculation
- `risk_rating_thresholds` - Score to rating mapping

**Weight Application:**
```
risk_score = base_carb_risk 
           + (0.6 * fat_delay)
           + (0.5 * protein_tail)
           - (0.7 * fiber_buffer)
```

### curve_classification
Used by: `glucose` command

Rules for classifying expected glucose curve shapes.

**Rule Pattern:**
```json
"spike_then_dip": {
  "min_carbs": 25,
  "min_gi": 60,
  "max_fat": 10,
  "max_fiber": 4,
  "label": "Spike Then Possible Dip",
  "curve_description": "Fast, low-fiber carbs..."
}
```

**Rules Applied in Order:**
1. `very_low_carb_max` - Simple threshold for low-carb meals
2. `delayed_spike` - High fat delays absorption
3. `double_hump` - Mixed macros create two phases
4. `blunted_spike` - High fiber smooths curve
5. `spike_then_dip` - Fast carbs risk hypoglycemia
6. `default` - Fallback for other patterns

**Template Variables:**
Some descriptions support templates:
- `{carbs}` - Carb grams (int)
- `{fiber}` - Fiber grams (int)
- `{risk_score}` - Risk score (float)

### explain_messages
Used by: `explain` command

Educational messages shown to users based on nutrient ranges.

**Message Range Pattern:**
```json
"carb_ranges": [
  {"max": 5, "message": "Negligible carb load - minimal impact"},
  {"max": 20, "message": "Low carb load - small impact"},
  {"max": null, "message": "Very high carb load - major impact"}
]
```

**Fields:**
- `carb_ranges` - Carb gram interpretations
- `gi_ranges` - GI level interpretations
- `fat_ranges` - Fat gram interpretations
- `protein_ranges` - Protein gram interpretations
- `fiber_ranges` - Fiber gram interpretations
- `risk_score_interpretation` - Overall risk messages

## Validation Requirements

1. **File must exist** - No defaults
2. **Valid JSON syntax** - No trailing commas, proper quotes
3. **All sections required** - Cannot omit sections
4. **All fields required** - Each section needs its fields
5. **Correct types** - Numbers as numbers, not strings
6. **Range ordering** - Ascending max values
7. **Range termination** - Last entry must have `max: null`

## Common Customizations

### Adjust for Lower Carb Diet
```json
"daily_targets": {
  "carbs_pct": 40,  // Lower from 60
  "protein_g": 120  // Raise from 100
}
```

### More Sensitive to Sugar
```json
"daily_targets": {
  "sugar_g": 30  // Lower from 50
}
```

### Stricter Risk Ratings
```json
"risk_rating_thresholds": [
  {"max": 2.5, "rating": "low"},     // Was 3
  {"max": 5, "rating": "medium"},    // Was 6
  {"max": 7.5, "rating": "high"},    // Was 8.5
  {"max": null, "rating": "very_high"}
]
```

### Adjust GI Sensitivity
```json
"gi_speed_factors": [
  {"max": 40, "factor": 0.7},   // More reduction for low GI
  {"max": 60, "factor": 1.0},
  {"max": null, "factor": 1.4}  // Bigger penalty for high GI
]
```

## Troubleshooting

### Error: "Missing required section"
Check that all four sections exist:
- daily_targets
- glucose_scoring
- curve_classification
- explain_messages

### Error: "must be an array"
Range fields must use `[...]` not `{...}`

### Error: "must be greater than previous max"
Range values must increase:
```json
// WRONG:
[{"max": 20}, {"max": 10}]

// CORRECT:
[{"max": 10}, {"max": 20}]
```

### Error: "last entry should have 'max': null"
Last range entry needs null to catch all higher values:
```json
[
  {"max": 5, "score": 0.0},
  {"max": 10, "score": 2.0},
  {"max": null, "score": 5.0}  // Required
]
```

## Backup and Recovery

Before editing:
```bash
cp meal_plan_thresholds.json meal_plan_thresholds.json.backup
```

If you break the file:
1. Check error message for specific issue
2. Validate JSON syntax with a JSON validator
3. Compare against this reference
4. Restore from backup if needed

## Version History

- **1.0** - Initial externalization of hardcoded thresholds
