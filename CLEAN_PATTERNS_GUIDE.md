# Clean & Simple Custom Patterns Guide

## Overview
The custom patterns system is now **simplified and cleaner**:
- Single input field to add patterns
- Patterns appear automatically in dropdowns
- Remove patterns by right-clicking in dropdown
- No clutter, no duplicates

## Quick Start

### Adding a Pattern

1. **Find the "Add Custom Pattern" section** at the top of the Serial Plot slide
2. **Type your pattern** in the text field:
   ```
   {value}RPM
   temp: {value}°C
   speed: {value}km/h
   ```
3. **Press Enter or click +** to add it
4. Pattern instantly appears in both **CH1 Value** and **CH2 Value** dropdowns

### Using a Pattern

1. Open **CH1 Value** dropdown
2. Select your pattern (e.g., `Pattern1 (1245.50) [remove: right-click]`)
3. CH1 now plots data extracted using that pattern
4. Repeat for CH2 Value dropdown if needed

### Removing a Pattern

1. Open **CH1 Value** or **CH2 Value** dropdown
2. Select the pattern you want to remove
3. **Right-click** on it
4. Click **"OK"** to confirm removal
5. Pattern is removed from everywhere

## UI Layout

```
┌─────────────────────────────────┐
│ Add Custom Pattern              │
├─────────────────────────────────┤
│ [Pattern Input Field]    [+]    │
│ Patterns appear in Value dropdowns below
└─────────────────────────────────┘

    ↓ Patterns appear here ↓

┌─────────────────────────────────┐
│ CH1 Value                       │
├─────────────────────────────────┤
│ ▼ Select Value                  │
│   - Pattern1 (1245.50) [remove: right-click]
│   - Pattern2 (45.23) [remove: right-click]
│   - TempSensor (45.23)
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ CH2 Value                       │
├─────────────────────────────────┤
│ ▼ Select Value                  │
│   - Pattern1 (1245.50) [remove: right-click]
│   - Pattern2 (45.23) [remove: right-click]
│   - TempSensor (45.23)
└─────────────────────────────────┘
```

## Examples

### Example 1: Temperature in Multiple Formats
Your device sends: `TEMP=45.2` or `Temperature: 45.2°C` or `T:45.2`

**Step 1:** Add patterns
```
Pattern 1: TEMP={value}
Pattern 2: Temperature: {value}°C
Pattern 3: T:{value}
```

**Step 2:** Use one pattern
- Select "Pattern1" in CH1 Value dropdown
- Data extracts as: 45.2

### Example 2: Two Sensors
Motor speed and temperature from serial port

**Patterns:**
```
Pattern 1: {value}RPM
Pattern 2: {value}°C
```

**Usage:**
- CH1 Value: Select "Pattern1" (plots RPM)
- CH2 Value: Select "Pattern2" (plots temperature)

### Example 3: Same Data, Both Channels
Comparing same sensor reading

**Patterns:**
```
Pattern 1: speed={value}
```

**Usage:**
- CH1 Value: Select "Pattern1"
- CH2 Value: Select "Pattern1"
- Both channels show identical data

## Key Features

✅ **Single Input** - One field for adding patterns  
✅ **Auto Dropdown** - Patterns appear in dropdowns automatically  
✅ **Right-Click Remove** - Remove patterns from dropdown  
✅ **No Duplicates** - System checks for duplicate patterns  
✅ **No Mess** - Clean display, no pattern list clutter  
✅ **Real-time** - Changes apply immediately  
✅ **Cross-Channel** - Use same pattern in both channels  

## How Removal Works

When you remove a pattern:
1. Right-click a pattern in the dropdown
2. Confirm with OK
3. Pattern is deleted from:
   - CH1 dropdown ✓
   - CH2 dropdown ✓
   - Data storage ✓
   - Everywhere instantly ✓

## Pattern Names

Patterns are auto-named:
- First pattern: `Pattern1`
- Second pattern: `Pattern2`
- Third pattern: `Pattern3`

No manual naming needed!

## Dropdown Hints

The dropdown text shows:
```
Pattern1 (1245.50) [remove: right-click]
```

- `Pattern1` = Pattern name
- `(1245.50)` = Last received value
- `[remove: right-click]` = How to remove it

## Common Issues & Solutions

**Q: I added a pattern but don't see it in dropdown?**
- Make sure you pressed Enter or clicked the + button
- The pattern should appear instantly

**Q: Pattern appears in CH1 but not CH2?**
- It's there! Both dropdowns show the same patterns
- Just select it in CH2 Value dropdown

**Q: How do I edit a pattern?**
- Remove it (right-click in dropdown)
- Add a new one with the correct format

**Q: Can I use the same pattern name twice?**
- No, duplicates are blocked
- You'll get an alert if you try

**Q: Right-click doesn't work?**
- Make sure you right-click on the selected pattern option
- A confirmation dialog should appear

## Pattern Format Examples

| Purpose | Pattern | Serial Data | Extracts |
|---------|---------|-------------|----------|
| Simple | `{value}` | `45.2` | 45.2 |
| Label = Value | `RPM={value}` | `RPM=5000` | 5000 |
| Text prefix | `{value}°C` | `45.2°C` | 45.2 |
| Text before & after | `Speed: {value} km/h` | `Speed: 60 km/h` | 60 |
| Complex format | `sensor1={value}\ntemp` | `sensor1=45.2` | 45.2 |

## Technical Details

**Storage:** `window.customPatterns` array  
**Naming:** Auto-generated (Pattern1, Pattern2, ...)  
**Display:** Both CH1 and CH2 dropdowns  
**Remove:** Right-click in dropdown  
**Data:** Extracted using regex pattern matching  

## No More Clutter!

### Before (Messy):
```
Custom Patterns
CH1 Patterns
  [Input field] [×]
  [Input field] [×]
  No patterns added yet
  
CH2 Patterns
  [Input field] [×]
  No patterns added yet
```

### Now (Clean):
```
Add Custom Pattern
[Input field] [+]
Patterns appear in Value dropdowns below
```

Done! Everything else happens in the dropdowns.
