# Unified Custom Patterns Feature

## Overview
Simplified and enhanced the serial plot custom pattern functionality. Now uses ONE unified pattern list that automatically applies to both CH1 and CH2 channels - clean, simple, and efficient.

## Key Features

### 1. Single Pattern Container
- **One unified "Custom Patterns" section** for both channels
- Add unlimited custom patterns in one place
- All patterns are available for selection in both CH1 and CH2 dropdowns
- No duplication or confusion

### 2. How It Works
- Create a pattern once → Use it in CH1, CH2, or both
- Example patterns:
  - `{value}RPM`
  - `temp: {value}°C`
  - `speed: {value} km/h`
  - `voltage: {value}V`

3. **Dynamic UI**
- **+ Add Pattern Button**: Click to create new patterns
- **Remove (×) Button**: Delete patterns instantly
- **Empty State**: Shows "No patterns added yet" when no patterns exist
- **Real-time Updates**: Changes reflect immediately across all slides

## Usage

### Step 1: Add Pattern
Click the "+ Add Pattern" button to create a new pattern input field.

### Step 2: Enter Pattern Format
Type your pattern using `{value}` placeholder:
```
{value}RPM
temp: {value}°C
speed: {value} km/h
voltage={value}V
```

### Step 3: Press Enter to Confirm
The pattern is saved and immediately appears in both CH1 and CH2 dropdown selectors.

### Step 4: Select in Channel
- Use the dropdown in "CH1 Value" to select a pattern
- Use the dropdown in "CH2 Value" to select the same or different pattern
- Both can use the same pattern or different patterns

### Step 5: Remove if Needed
Click the "×" button next to any pattern to delete it.

## Pattern Naming

Each pattern gets a unique name automatically:
- First pattern: `Pattern1`
- Second pattern: `Pattern2`
- Third pattern: `Pattern3`
- And so on...

These names appear in the CH1 and CH2 value dropdowns.

## Data Structure

```javascript
// Global pattern storage
window.customPatterns = [
  { id: 'pattern_xxx_yyy', value: '{value}RPM' },
  { id: 'pattern_yyy_zzz', value: 'temp: {value}°C' },
  { id: 'pattern_zzz_www', value: 'speed: {value}' }
]
```

Each pattern is stored globally and accessible to both channels.

## Cross-Slide Functionality

✓ Patterns persist when switching slides  
✓ New patterns immediately appear in dropdowns on all slides  
✓ Selected patterns continue plotting across slide transitions  
✓ Works seamlessly with GPIO and Serial plot slides  

## Example Use Cases

### Temperature Monitoring
```
Pattern 1: TEMP={value}
Pattern 2: T:{value}°C
Pattern 3: temp: {value}
```
Select Pattern 1 for CH1, Pattern 2 for CH2 to monitor same data in different formats.

### Multi-Sensor Setup
```
Pattern 1: {value}RPM        (Motor speed)
Pattern 2: {value}°C         (Temperature)
Pattern 3: {value}V          (Voltage)
```
Select different patterns for different channels based on sensor.

### Data Extraction
```
Pattern 1: sensor_data={value}
Pattern 2: Data:{value}
Pattern 3: {value}
```
Multiple formats to handle different data transmission styles.

## Technical Details

### Functions

**`setupCustomFormatHandlers()`**  
Initializes the pattern system and sets up event listeners.

**`addPatternInput()`**  
Dynamically adds a new pattern input field to the unified container.

**`renderPatterns()`**  
Renders all patterns from the global data structure with event handlers.

**`parseValueFromFormat(data, format)`**  
Extracts numeric value from serial data using the pattern format.

### Event Handling

- `change` event: Confirms pattern entry
- `input` event: Real-time pattern data updates
- `click` on remove button: Deletes the pattern

### Pattern Matching

The system uses regex patterns to extract values:
- Pattern: `{value}RPM`
- Serial data: `Engine RPM=5000`
- Extracts: `5000`

## UI Elements

### Add Pattern Button
```html
<button id="addPatternBtn">
  <span>+</span> Add Pattern
</button>
```
Styled with blue accent (bg-blue-500/20)

### Pattern Input
```html
<input 
  class="pattern-input"
  placeholder="e.g., {value}RPM or temp: {value}°C"
/>
```

### Remove Button
```html
<button class="remove-pattern-btn">×</button>
```
Styled with red accent (bg-red-500/20)

## Backward Compatibility

- Legacy `customFormat` field (single string) still supported
- New unified patterns take precedence
- Automatic migration transparent to users

## Features

✓ **Unified Storage** - One list for both channels  
✓ **Dynamic Creation** - Add/remove patterns anytime  
✓ **Automatic Names** - Pattern1, Pattern2, etc.  
✓ **Real-time Updates** - Changes reflected immediately  
✓ **Cross-Channel** - Use same pattern in both channels  
✓ **Persistent** - Saved across slide transitions  
✓ **Easy Deletion** - Remove with × button  

## Notes

- Pattern IDs are unique and auto-generated
- Empty patterns are skipped during parsing
- Maximum data points per pattern: 1000
- Patterns are case-sensitive when matching serial data
- All patterns appear in both CH1 and CH2 dropdowns
