# Fullscreen Video - Quick Reference

## How to Open Fullscreen Video

1. In main Remote Lab interface, hover over video stream
2. Click play button (►) to start streaming
3. Click **"Fullscreen"** button (next to video title)
4. Video opens in new tab with zoom/pan controls

## Zoom Controls

| Method | Action | Keys/Gestures |
|--------|--------|-----------------|
| **Slider** | Drag left/right | Mouse drag on header slider |
| **Keyboard** | Zoom in | `+` or `=` key |
| **Keyboard** | Zoom out | `-` or `_` key |
| **Mouse** | Zoom | Scroll wheel up/down |
| **Touch** | Zoom in/out | Pinch gesture (2 fingers) |
| **Mobile** | Zoom in/out | +/- buttons on screen |

**Zoom Range**: 0.5x (50%) to 5x (500%)

## Pan Controls

| Method | Action | Keys/Gestures |
|--------|--------|-----------------|
| **Mouse** | Pan | Click and drag |
| **Keyboard** | Pan up | ↑ or `W` |
| **Keyboard** | Pan down | ↓ or `S` |
| **Keyboard** | Pan left | ← or `A` |
| **Keyboard** | Pan right | → or `D` |
| **Touch** | Pan | Drag with 1 finger |

**Note**: Pan only works when zoom > 1x

## Action Buttons

| Button | Keyboard | Effect |
|--------|----------|--------|
| **Reset** | `R` | Reset zoom to 100% and pan to center |
| **Info** | `I` | Toggle information overlay |
| **Close** | `ESC` | Close fullscreen and stop stream |
| **Fullscreen** | `Space` | Fit video to screen (auto-zoom) |
| **Help** | `H` | Toggle keyboard shortcuts |

## Info Overlay Contents

```
Stream Status:     Connected / Connecting / Disconnected
Zoom Level:        Current zoom percentage (100% = 1x)
Pan Offset:        (X, Y) coordinates of pan position
FPS:               Current frames per second
+ Keyboard Help:   Shortcut reference
```

## On Mobile Devices

**Available Controls**:
- +/- buttons (bottom center)
- Pinch to zoom
- Drag to pan
- Tap to show/hide hints
- ESC button closes fullscreen

**Hidden on Mobile**:
- Keyboard hints (shown in info overlay instead)
- Keyboard shortcuts (use buttons instead)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No video appears | Start stream in main window first |
| Zoom buttons don't work | Try keyboard (+/-) instead |
| Pan doesn't work | Zoom in first (zoom > 1x required) |
| FPS very low | Close other browser tabs |
| Video freezes | Check connection or restart stream |
| Controls not responding | Click fullscreen window to focus |

## Display Indicators

**Status Bar (bottom)**:
- 🟢 Green dot = Connected and streaming
- 🔴 Red dot = Connection error
- Text shows current state

**Info Overlay**:
- Toggleable with "Info" button or `I` key
- Shows all metrics and keyboard shortcuts
- Can be left open or hidden

## Performance Tips

- ✓ Use zoom 1x-2x for best performance
- ✓ Keep browser updated for best compatibility
- ✓ Close unnecessary browser tabs
- ✓ Use Chrome for best FPS
- ✓ On mobile, use WiFi not mobile data

## Common Workflows

### Zoom In on Detail
1. Use slider or scroll wheel to increase zoom
2. Drag mouse to pan to area of interest
3. Press `R` to reset when done

### Full Screen View
1. Press `Space` to fit video to window
2. Zoom will adjust automatically

### Get Information
1. Press `I` to show info overlay
2. See current FPS, zoom, pan offset
3. Press `I` again to hide

### Quick Reset
1. Press `R` to reset everything
2. Zoom returns to 100%
3. Pan returns to center
4. Back to original view

## Keyboard Shortcut Cheat Sheet

```
ZOOM & PAN
  +/-         Zoom in/out
  Scroll      Zoom in/out
  ↑↓←→ WASD   Pan view

ACTIONS
  R           Reset zoom/pan
  Space       Fit to screen
  I           Toggle info
  H           Toggle hints
  ESC         Close window
```

## Default Settings

- **Initial Zoom**: 100% (1x)
- **Initial Pan**: Centered (0, 0)
- **Min Zoom**: 50% (0.5x)
- **Max Zoom**: 500% (5x)
- **Pan Speed**: 20 pixels per key
- **Zoom Step**: 10% per key press or scroll

## Window Features

- **Size**: Opens at 1280x720 (adjustable)
- **Resizable**: Can drag window edges
- **Movable**: Can drag title bar
- **Stays On Top**: Optional (depends on browser)
- **Fullscreen API**: Press F11 for browser fullscreen (optional)

## Socket.IO Connection

- Auto-connects to same server
- Receives video frames as JPEG
- Stops streaming when window closes
- Auto-reconnects on disconnect
- Shows connection status in status bar

## Tips & Tricks

1. **Fast Zoom**: Use scroll wheel (fastest method)
2. **Precise Pan**: Use arrow keys for pixel-perfect movement
3. **Quick Reset**: Press `R` instead of dragging
4. **Mobile Pan**: Use 1-finger drag (not 2-finger zoom)
5. **Screenshot**: Use browser screenshot (might freeze stream briefly)
6. **Multiple Windows**: Open multiple fullscreen windows for comparison

## Keyboard Layout

```
WASD/Arrows    Space        +/-
  Pan            Fit      Zoom

  I              R         H
 Info          Reset    Hints

            ESC
           Close
```

---

**For Complete Documentation**: See `FULLSCREEN_VIDEO_GUIDE.md`
**For Setup Instructions**: See `FULLSCREEN_SETUP.md`
**For Technical Details**: See `IMPLEMENTATION_SUMMARY.md`
