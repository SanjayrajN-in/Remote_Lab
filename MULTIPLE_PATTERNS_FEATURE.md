# Multiple Custom Patterns Feature

## Overview
Enhanced the serial plot custom pattern functionality to support creating multiple custom patterns for both CH1 and CH2 channels, with dynamic add/remove capabilities.

## Key Features

### 1. Multiple Pattern Support
- **CH1 Channel**: Add unlimited custom patterns for Channel 1
- **CH2 Channel**: Add unlimited custom patterns for Channel 2
- Each pattern can have a unique format string to extract values from serial data

### 2. Dynamic UI
- **+ Add Button**: Click the "+ Add CH1 Pattern" or "+ Add CH2 Pattern" button to create new patterns
- **Remove (×) Button**: Each pattern has a remove button to delete it instantly
- **Empty State**: Shows "No patterns added yet" when no patterns exist
- **Real-time Updates**: Patterns are reflected immediately across all slides

### 3. Pattern Format
- Use `{value}` placeholder to extract numeric values
- Examples:
  - `{value}RPM` - Extract RPM values
  - `temp: {value}°C` - Extract temperature values
  - `value1 = {value}` - Custom format with text

### 4. Pattern Management
- Patterns are stored in `serialPlotData.ch1.patterns` and `serialPlotData.ch2.patterns` as arrays
- Each pattern has:
  - `id`: Unique identifier
  - `value`: The pattern format string
- Patterns are created with auto-generated IDs to avoid conflicts

### 5. Cross-Slide Functionality
- Multiple patterns work seamlessly across different oscilloscope slides
- Patterns persist when switching between GPIO and Serial plot slides
- All detected values appear in the dropdown selector for both channels

## How to Use

### Adding a Pattern
1. Navigate to the serial plot slide
2. In the "Custom Patterns" section, find either "CH1 Patterns" or "CH2 Patterns"
3. Click the "+ Add CH1 Pattern" or "+ Add CH2 Pattern" button
4. Enter your pattern format (e.g., `{value}RPM`)
5. Press Enter or Tab to confirm
6. The pattern appears in the value dropdown automatically

### Multiple Patterns Example
```
CH1 Patterns:
- {value}RPM
- speed: {value} km/h
- rpm_value={value}

CH2 Patterns:
- {value}°C
- temp: {value}
```

When serial data comes in like `RPM=5000` or `speed: 5000 km/h`, the system will extract and plot the value 5000.

### Removing a Pattern
1. Click the "×" button next to the pattern you want to remove
2. The pattern is immediately deleted
3. If it was selected for plotting, plotting will stop for that pattern

## Technical Details

### Data Structure
```javascript
serialPlotData = {
  ch1: {
    patterns: [
      { id: 'pattern_ch1_xxx_yyy', value: '{value}RPM' },
      { id: 'pattern_ch1_yyy_zzz', value: 'temp: {value}°C' }
    ],
    selectedValue: 'CH1_Pattern1',
    values: [],
    timestamps: [],
    // ... other properties
  },
  ch2: {
    patterns: [
      { id: 'pattern_ch2_xxx_yyy', value: '{value}°C' }
    ],
    // ... similar structure
  }
}
```

### Pattern Naming
Each detected pattern gets a unique name:
- First CH1 pattern: `CH1_Pattern1`
- Second CH1 pattern: `CH1_Pattern2`
- First CH2 pattern: `CH2_Pattern1`
- And so on...

### Event Handlers
- `change` event: Triggers when user confirms the pattern
- `input` event: Updates the pattern data in real-time as user types
- `click` on remove button: Deletes the pattern and updates the display

### Backward Compatibility
- Legacy `customFormat` field is still supported for existing code
- New multi-pattern system takes precedence if both are present
- Migration is transparent to the user

## Functions

### `setupCustomFormatHandlers()`
Initializes the multiple pattern system and sets up event listeners for add buttons.

### `addPatternInput(channel)`
Dynamically adds a new pattern input field to the specified channel (ch1 or ch2).

**Parameters:**
- `channel`: 'ch1' or 'ch2'

### `renderPatterns(channel)`
Renders all patterns for a channel from the data structure.

**Parameters:**
- `channel`: 'ch1' or 'ch2'

Automatically shows placeholder text when no patterns exist.

### `parseValueFromFormat(data, format)`
Extracts a numeric value from serial data using the provided format pattern.

**Parameters:**
- `data`: Serial data string
- `format`: Pattern format with {value} placeholder

**Returns:** Parsed numeric value or null if not matched

## UI Elements

### HTML Structure
```html
<div id="customFormatSection">
  <div id="ch1PatternsContainer"></div>
  <button id="addCH1PatternBtn">+ Add CH1 Pattern</button>
  
  <div id="ch2PatternsContainer"></div>
  <button id="addCH2PatternBtn">+ Add CH2 Pattern</button>
</div>
```

### Styling
- Uses Tailwind CSS for responsive design
- Blue accent for "add" buttons (`bg-blue-500/20`)
- Red accent for "remove" buttons (`bg-red-500/20`)
- Hover effects for better UX
- Text remains clearly visible with proper contrast

## Features Working Across Slides
- Pattern definitions persist when switching slides
- New patterns immediately appear in dropdown selectors
- Selected patterns continue plotting across slide transitions
- Data is preserved and not lost when switching between GPIO and Serial

## Example Use Case

### Temperature Monitoring
Create multiple patterns to monitor temperature in different formats:

```
CH1 Pattern 1: sensor_temp={value}
CH1 Pattern 2: T:{value}°C
CH1 Pattern 3: {value}
```

Select any pattern to plot, and all formats can coexist, allowing flexibility in how temperature data is transmitted and parsed.

## Notes
- Pattern IDs are unique per instance and regenerated on page load
- Empty patterns are skipped during parsing (doesn't affect performance)
- Maximum data points per pattern: 1000 (configurable via `maxPoints`)
- Patterns are case-sensitive when matching serial data
