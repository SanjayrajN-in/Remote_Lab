# Fullscreen Video Streaming with Zoom and Pan

## Features

This implementation adds fullscreen video streaming capabilities to the Remote Lab Interface with advanced zoom and pan functionality.

### Core Features
- **Fullscreen Mode**: Opens video stream in a new browser tab with full screen capability
- **Zoom Control**: 
  - Zoom range: 0.5x to 5x magnification
  - Multiple zoom methods:
    - Zoom slider in header
    - Mouse wheel scroll
    - Keyboard: `+` / `-` keys
    - Touch pinch gesture
    - Touch buttons (+/-) on mobile
- **Pan Control**:
  - Drag with mouse to pan around zoomed video
  - Keyboard controls: Arrow keys or WASD
  - Touch drag on mobile
  - Pan offset display in info overlay

### UI Components

#### Header Controls
- **Zoom Slider**: Visual slider for precise zoom control with real-time display
- **Reset Button**: Reset zoom to 100% and pan offset to (0, 0)
- **Info Button**: Toggle information overlay showing stream status and controls
- **Close Button**: Close fullscreen window and stop streaming

#### Status Bar
- Connection status indicator (green when connected, red when error)
- Stream status (Connecting, Streaming, Disconnected)
- FPS display
- Resolution information

#### Info Overlay
- Stream connection status
- Current zoom level
- Pan offset coordinates
- FPS counter
- Keyboard shortcut reference

#### Keyboard Hints
- Help panel showing all available keyboard shortcuts
- Toggleable with 'H' key
- Automatically hidden on mobile devices

#### Touch Controls
- Visible only on mobile/tablet devices
- Zoom in/out buttons
- Pan via drag gesture

## Usage

### Opening Fullscreen
1. Start the video stream in the main interface (hover over video and click play)
2. Click the **"Fullscreen"** button next to "Live Video Stream" title
3. The fullscreen video player opens in a new tab

### Keyboard Shortcuts
- **↑↓←→** or **WASD**: Pan the view
- **+** / **-**: Zoom in/out
- **Mouse Wheel**: Zoom in/out
- **Drag Mouse**: Pan around (grab and drag)
- **R**: Reset view to original position and zoom
- **I**: Toggle information overlay
- **H**: Toggle keyboard hints
- **Space**: Fit to screen (auto-zoom to fit)
- **ESC**: Close fullscreen window

### Mouse Controls
- **Scroll Wheel**: Zoom in/out with sensitivity adjustment
- **Click and Drag**: Pan around the video when zoomed in
- **Hover**: Cursor changes to grab/grabbing to indicate pannable area

### Touch Controls
- **Two-Finger Pinch**: Zoom in/out
- **Drag**: Pan around the video
- **Touch Buttons**: Use +/- buttons for zoom on mobile

## Technical Details

### Files Modified/Created

1. **`/home/pi/remotelab/page/fullscreen_video.html`** (NEW)
   - Fullscreen video player interface
   - Canvas-based video rendering
   - All zoom and pan functionality
   - Socket.IO integration for video streaming
   - Responsive design for desktop and mobile

2. **`/home/pi/remotelab/page/remotelab.html`** (MODIFIED)
   - Added Fullscreen button in video stream section
   - Button click handler to open fullscreen window

3. **`/home/pi/remotelab/app.py`** (MODIFIED)
   - Added `/page/<path:page>` route to serve HTML pages from page folder
   - Enables serving of fullscreen_video.html

### Architecture

#### Video Streaming
- Uses existing Socket.IO connection from parent window
- Receives JPEG frames via `video_frame` event
- Renders frames to HTML5 Canvas
- FPS calculation and display

#### Zoom & Pan System
- **Zoom**: Canvas context `scale()` transform (0.5x to 5x)
- **Pan**: Canvas context `translate()` transform with state tracking
- **Rendering**: Frames redrawn with transforms applied each time

#### State Management
- Centralized `state` object tracks:
  - Current zoom level
  - Pan X/Y offsets
  - Frame dimensions
  - FPS metrics
  - Streaming status

#### Input Handling
- Mouse: Wheel zoom, drag pan, buttons
- Keyboard: Arrow keys, WASD, +/-, R, I, H, Space, ESC
- Touch: Pinch zoom, drag pan, button zoom
- All handlers prevent conflicts and propagation

### Configuration

```javascript
const config = {
    maxZoom: 5,              // Maximum zoom level
    minZoom: 0.5,            // Minimum zoom level
    panSpeed: 20,            // Pan speed in pixels per key press
    zoomSensitivity: 0.1,    // Zoom change per key press or scroll
    fpsUpdateInterval: 1000  // FPS calculation interval in ms
};
```

## Browser Compatibility

- **Desktop**: Chrome, Firefox, Safari, Edge (full support)
- **Mobile**: iOS Safari, Chrome Mobile (with touch controls)
- **Requirements**: HTML5 Canvas, WebSocket (Socket.IO), ES6 JavaScript

## Performance Notes

- Canvas rendering is optimized with proper state saving/restoring
- FPS counter updates every 1 second
- Frame queue prevents memory accumulation
- Smooth animations using requestAnimationFrame indirectly (via Socket.IO updates)
- Touch performance optimized for mobile devices

## Troubleshooting

### Video not loading
- Check that video stream is active in main window
- Verify Socket.IO connection in console
- Check browser console for errors

### Zoom not working
- Verify mouse wheel support in browser
- Try keyboard (+/-) alternative
- Check that page has focus

### Pan not responding
- Ensure video is zoomed in first
- Try keyboard controls if mouse drag not working
- On mobile, use two-finger drag

### Performance issues
- Reduce zoom level if FPS drops
- Check browser resources
- Try fullscreen instead of windowed mode

## Future Enhancements

- Video recording in fullscreen mode
- Screenshot capability
- Full-screen native browser fullscreen API integration
- Grid overlay for measurement
- Color picker tool
- Frame playback/pause controls
- Video rotation/flip controls
- Aspect ratio lock option
