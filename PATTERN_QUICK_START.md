# Custom Patterns - Quick Start Guide

## The Simplest Way to Use It

### Before (Two separate inputs for CH1 and CH2)
❌ Had to create separate patterns for each channel  
❌ Duplication of effort  
❌ Confusing UI with multiple sections  

### Now (One unified pattern list for both)
✅ Create ONE pattern  
✅ Use it in CH1, CH2, or both  
✅ Simple, clean UI  

---

## 3-Step Usage

### 1️⃣ Click "+ Add Pattern"
```
[+ Add Pattern]
```
This creates a new text field.

### 2️⃣ Type Your Pattern
```
Enter: {value}RPM
or:    temp: {value}°C
or:    voltage={value}V
```

The `{value}` is replaced with actual numbers from your serial data.

### 3️⃣ Select in Channel Dropdown
- Go to "CH1 Value" dropdown → Select "Pattern1"
- Go to "CH2 Value" dropdown → Select "Pattern1" or different pattern

Done! The data will now plot.

---

## Real Examples

### Example 1: Single Sensor, Multiple Formats
Your device sends temperature in different formats:
```
TEMP=45.2
T:45.2°C
temperature: 45.2
```

Create 3 patterns:
```
Pattern 1: TEMP={value}
Pattern 2: T:{value}°C
Pattern 3: temperature: {value}
```

Then select "Pattern1" in CH1 dropdown (system will extract 45.2 from "TEMP=45.2").

### Example 2: Two Different Sensors
```
Pattern 1: {value}RPM        ← Motor speed
Pattern 2: {value}°C         ← Temperature
```

- CH1 Value: Select "Pattern1" (plots RPM)
- CH2 Value: Select "Pattern2" (plots Temperature)

Both channels plot different data from same serial stream.

### Example 3: Same Sensor, Both Channels
```
Pattern 1: {value}RPM
```

- CH1 Value: Select "Pattern1"
- CH2 Value: Select "Pattern1"

Both channels show same RPM data (useful for comparison).

---

## Removing Patterns

Click the **×** button next to any pattern to delete it.

```
[Pattern input field] [×]
```

---

## Key Points

1. **One list for both channels** - Create patterns once, use anywhere
2. **Patterns auto-appear in dropdowns** - After you create a pattern, it shows up in both CH1 and CH2 selectors
3. **No limits** - Add as many patterns as you need
4. **Works across slides** - Patterns persist when switching slides
5. **Real-time** - Changes apply immediately

---

## Common Pattern Examples

| Purpose | Pattern | Example Match |
|---------|---------|---|
| Simple value | `{value}` | `45.2` |
| With unit | `{value}RPM` | `5000RPM` |
| Label = value | `TEMP={value}` | `TEMP=45.2` |
| With text | `temp: {value}°C` | `temp: 45.2°C` |
| Speed | `{value}km/h` | `60km/h` |
| Voltage | `V={value}` | `V=12.5` |

---

## Troubleshooting

**Q: I created a pattern but don't see it in the dropdown?**  
A: Make sure you pressed Enter or clicked outside the input to confirm it.

**Q: Nothing is plotting?**  
A: Check if your serial data matches your pattern format exactly (case-sensitive).

**Q: Can I use the same pattern in both CH1 and CH2?**  
A: Yes! Select the same pattern in both dropdowns.

**Q: How do I remove a pattern?**  
A: Click the **×** button next to it.

**Q: Can I use special characters in patterns?**  
A: Yes, but avoid regex special chars. Use {value} as placeholder.

---

## What Changed from Before?

| Before | Now |
|--------|-----|
| Two separate sections (CH1, CH2) | One unified section |
| Two "Add" buttons | One "Add" button |
| Channel-specific patterns | Global patterns |
| More UI clutter | Cleaner, simpler UI |

Everything else works exactly the same!
