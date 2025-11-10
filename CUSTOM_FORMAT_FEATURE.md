# Serial Plot Custom Format Feature

## Overview
Added a custom value format input section to the serial plot controls. This allows users to manually enter custom parsing patterns when the auto-detect dropdown doesn't successfully detect serial data values.

## UI Changes

### New Control Section
A new "Custom Format" section has been added below the CH1/CH2 value dropdowns in the serial plot slide controls. It contains:

1. **CH1 Custom Format Input** - Text field for entering CH1 value extraction pattern
2. **CH2 Custom Format Input** - Text field for entering CH2 value extraction pattern

Both fields include:
- Placeholder examples: `value1 = {value}` or `{value}RPM`
- Clear labels indicating which channel the pattern is for
- Separated with a border for visual distinction

## How It Works

### Format Pattern Syntax
The custom format uses `{value}` as a placeholder for the numeric value to be extracted.

**Examples:**
- `{value}RPM` - Matches any line with a number followed by "RPM"
- `value1 = {value}` - Matches lines with "value1 = " followed by a number
- `Temp: {value}C` - Matches temperature readings with "Temp: " and "C" suffix
- `{value}` - Simple number extraction

### Pattern Processing
1. When a custom format is entered in either CH1 or CH2 field, the pattern is stored in `serialPlotData.ch1.customFormat` or `serialPlotData.ch2.customFormat`
2. Each incoming serial line is checked against custom patterns first
3. If a custom format extracts a value, it's stored as `CH1_Custom` or `CH2_Custom` in the value patterns
4. If custom format fails to extract a value, the system falls back to auto-detection (existing behavior)

### Implementation Details

**Key Functions Added:**

1. **`setupCustomFormatHandlers()`**
   - Initializes event listeners for custom format inputs
   - Stores patterns when user changes the input value
   - Called when serial plot slide is displayed

2. **`parseValueFromFormat(data, format)`**
   - Converts custom format pattern to regex
   - Escapes special regex characters in the pattern
   - Replaces `{value}` with a number capture group: `([+-]?\d*\.?\d+)`
   - Returns the extracted numeric value or null if no match

3. **Modified `addToSerialTerminal(data)`**
   - Now checks custom formats before auto-detection
   - Creates values as `CH1_Custom` and `CH2_Custom`
   - Falls back to auto-detection if custom format doesn't match
   - Updates dropdowns when new custom values are detected

## Usage Example

**Scenario:** Device sends data like `"Speed: 45.3 RPM"` but auto-detect doesn't parse it

1. Switch to the serial plot slide
2. In the custom format fields, enter: `Speed: {value} RPM` for CH1
3. Click away or press Enter to save the pattern
4. As serial data arrives, the speed value (45.3) will be automatically extracted
5. The value will appear in the CH1/CH2 dropdown as `CH1_Custom`
6. Select it from the dropdown to start plotting

## Benefits

- **Flexible parsing** - Works with any serial format
- **No code changes needed** - Users can define patterns on-the-fly
- **Fallback support** - Still uses auto-detection if custom format doesn't match
- **Clear indication** - Custom values labeled as "CH1_Custom" / "CH2_Custom"
- **Regex-safe** - Automatically escapes special characters in the format

## Technical Notes

- Patterns are stored per-slide instance
- Custom values are buffered like auto-detected values (max 1000 points)
- Pattern changes update the serial plot immediately
- Regex errors are caught and logged to console for debugging

## Future Enhancements

- Pattern validation feedback in UI
- Save/load pattern templates
- Support for multiple custom patterns per channel
- Advanced regex patterns (optional expert mode)
