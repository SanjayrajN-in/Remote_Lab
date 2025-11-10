# Serial Plot Custom Format Fix

## Problem
When using a custom format (e.g., `Temperature={value}C`) in the serial plot, the plot would not display after clicking the "Start" button, even though data was being collected.

## Root Causes

1. **Missing Custom Format Validation**: The start button checked if `selectedValue` was set, but when using custom formats, users don't select from the dropdown - they only enter a format. This caused the start button to reject the plot with "Please select at least one value to plot".

2. **Plot Drawing Condition**: The `drawSerialPlot()` function had a strict condition that required `selectedValue` to be set. When using custom format, `selectedValue` would be empty (since no dropdown selection was made), causing the plot to not render even if data existed.

3. **Missing Initialization**: The `serialPlotData` object wasn't initialized with the `customFormat` property, so when the format was set, it wasn't properly preserved through state transitions.

## Solutions Applied

### 1. Fixed Start Button Validation (Line 2654-2660)
**Before:**
```javascript
if (!serialPlotData.ch1.selectedValue && !serialPlotData.ch2.selectedValue) {
    alert('Please select at least one value to plot');
    return;
}
```

**After:**
```javascript
const hasCH1 = serialPlotData.ch1.selectedValue || serialPlotData.ch1.customFormat;
const hasCH2 = serialPlotData.ch2.selectedValue || serialPlotData.ch2.customFormat;

if (!hasCH1 && !hasCH2) {
    alert('Please select at least one value to plot or enter a custom format');
    return;
}
```

**Why:** Now the start button accepts EITHER a dropdown selection OR a custom format.

### 2. Preserved Custom Format in Data Reset (Line 2664-2672)
**Before:**
```javascript
serialPlotData[channel] = {
    values: [],
    timestamps: [],
    selectedValue: serialPlotData[channel].selectedValue,
    maxPoints: serialPlotData[channel].maxPoints,
    minValue: Infinity,
    maxValue: -Infinity,
    scale: 1.0
};
```

**After:**
```javascript
serialPlotData[channel] = {
    values: [],
    timestamps: [],
    selectedValue: serialPlotData[channel].selectedValue,
    customFormat: serialPlotData[channel].customFormat,  // Preserved!
    maxPoints: serialPlotData[channel].maxPoints,
    minValue: Infinity,
    maxValue: -Infinity,
    scale: 1.0
};
```

**Why:** When clearing old data for a new plot, we need to preserve the custom format so incoming data continues to be parsed correctly.

### 3. Fixed Plot Drawing Condition (Line 3004-3005)
**Before:**
```javascript
if (!data.selectedValue || !data.values || data.values.length === 0) return null;
```

**After:**
```javascript
const hasSelection = data.selectedValue || (data.customFormat && data.values && data.values.length > 0);
if (!hasSelection || !data.values || data.values.length === 0) return null;
```

**Why:** Now the plot will render if EITHER a dropdown value is selected OR if custom format is set AND data exists.

### 4. Fixed Plot Label Display (Line 3048-3050)
**Before:**
```javascript
name: data.selectedValue,
```

**After:**
```javascript
name: data.selectedValue || (data.customFormat ? `${channel.toUpperCase()}_Custom` : 'Unknown'),
```

**Why:** When using custom format, display a friendly label like "CH1_Custom" instead of undefined/empty.

### 5. Fixed Measurement Labels (Line 3087-3106)
**Before:**
```javascript
} else if (serialPlotData.ch1.selectedValue) {
```

**After:**
```javascript
} else if (serialPlotData.ch1.selectedValue || serialPlotData.ch1.customFormat) {
    const label = serialPlotData.ch1.selectedValue || 'CH1_Custom';
```

**Why:** Show "No Data" messages for custom formats as well as selected values.

### 6. Added Custom Format Initialization (Line 1857-1880)
**Before:**
```javascript
ch1: {
    values: [],
    timestamps: [],
    selectedValue: null,
    maxPoints: 1000,
    ...
}
```

**After:**
```javascript
ch1: {
    values: [],
    timestamps: [],
    selectedValue: null,
    customFormat: null,  // Custom format pattern for value extraction
    maxPoints: 1000,
    ...
}
```

**Why:** Properly initialize the customFormat field so it exists throughout the application lifecycle.

## How Custom Format Works

1. User enters a pattern like `"Temperature={value}C"` in the custom format field
2. The pattern is stored in `serialPlotData.ch1.customFormat`
3. When serial data arrives (e.g., `"Current Temperature=23.5C"`), the pattern is used to extract the value (23.5)
4. The extracted value is added to the plot data
5. The plot renders using this data

## Testing

To verify the fix works:
1. Open the remote lab interface
2. Connect to a device that sends formatted data
3. In the Serial Plot tab, enter a custom format (e.g., `Temp={value}C`)
4. Click "Start" (should work now without requiring a dropdown selection)
5. Verify the plot appears and updates as data arrives

## Notes

- Custom format takes precedence and doesn't require a dropdown selection
- The plot can use EITHER a dropdown-selected value OR a custom format, but not both simultaneously for the same channel
- Data collected via custom format is labeled as "CH1_Custom" or "CH2_Custom" in the plot display
