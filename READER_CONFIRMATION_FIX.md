# Reader Control Template Fix

## Problem
When adding a reader control, the default template was too generic:
- Default was `{value}RPM` or just `{value}`
- Would match almost any number in serial output
- Example: if serial sends `"123"`, it matches immediately even if data format is different
- This caused unintended values to appear without user verification

## Solution
Changed default template to be **specific to the control name** instead of generic:

### Backend Changes (app.py)

**In `detect_control_type()`** (line 113, etc.):
- Changed default template from `'{value}'` to `f'{value_name}={{value}}'`
- Example: Reader named "Temperature" gets default `"Temperature={value}"`
- Now only matches specific patterns like `"Temperature=25.3"`, not random `"25.3"`

### Frontend Changes (remotelab.html)

**In `renderHubControl()`** for readers (line 3334):
- Changed default from `'{value}RPM'` to `control.name + '={value}'`
- Placeholder now shows: `"e.g., Temperature={value}"`
- Matches the backend default

## How It Works

1. User creates reader named "Temperature"
2. Default template shown: `"Temperature={value}"`
3. Serial monitor running: sends `"Temp=23.5"`, `"Speed=100"`, etc.
4. Only `"Temp=23.5"` matches pattern (not `"Speed=100"`)
5. User confirms ✓ or adjusts pattern as needed

## Benefits
- **Reduces false positives** — less likely to match unrelated data
- **Self-documenting** — default template clearly shows what data it expects
- **No confirmation delays** — values update immediately once pattern is set (user controls timing)
- **Simpler code** — no extra state management needed
- **Matches real-world patterns** — Arduino/ESP32 code typically sends `"Name=value"` format
