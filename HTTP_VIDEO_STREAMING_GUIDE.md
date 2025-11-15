# HTTP Video Streaming Implementation Guide

## Overview

This document describes the HTTP-based video streaming architecture for the Remote Lab project. The system uses MJPEG (Motion JPEG) format for robust, browser-compatible video streaming.

## Architecture

### Modular Design
The video streaming functionality has been separated into a dedicated module for better maintainability and robustness:

- **`http_video_streamer.py`** - Dedicated HTTP video streaming module
- **`app.py`** - Main Flask application (uses the streamer module)

### Why Separate Module?

1. **Separation of Concerns** - Video logic is isolated from main application logic
2. **Easier Testing** - Can test video streaming independently
3. **Better Error Handling** - Dedicated error handling and logging for video
4. **Reusability** - Can be used in other projects
5. **Maintainability** - Easier to debug and update video-related code

## Architecture Details

### HTTPVideoStreamer Class

**File:** `http_video_streamer.py`

The main class that handles all video streaming operations:

```python
class HTTPVideoStreamer:
    def initialize_camera(camera_indices=[0, 1, 2, 3, 4])
    def start_streaming()
    def stop_streaming()
    def get_frame()
    def generate_mjpeg_stream()
    def get_status()
```

**Key Features:**
- Automatic camera detection (tries multiple indices 0-4)
- Graceful error handling with consecutive error tracking
- FPS limiting (configurable target FPS)
- JPEG encoding with quality optimization
- Proper MJPEG boundary formatting for HTTP streaming

### Video Streaming Flow

```
Browser Request
    ↓
GET /video_stream
    ↓
Flask Route Handler
    ↓
HTTPVideoStreamer.generate_mjpeg_stream()
    ↓
While streaming_active:
    - Get frame from camera
    - Encode to JPEG
    - Add MJPEG boundaries
    - Yield to client
    ↓
Browser receives multipart/x-mixed-replace stream
    ↓
<img> tag updates continuously
```

## API Endpoints

### 1. Start Video Stream
```http
POST /video/start
```

**Response:**
```json
{
  "status": "started",
  "message": "Video stream started"
}
```

### 2. Stop Video Stream
```http
POST /video/stop
```

**Response:**
```json
{
  "status": "stopped",
  "message": "Video stream stopped"
}
```

### 3. Get Video Stream (MJPEG)
```http
GET /video_stream
```

**Response:** Continuous MJPEG stream with boundary markers
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Each frame is a JPEG image with proper boundaries

### 4. Get Video Status
```http
GET /video/status
```

**Response:**
```json
{
  "active": true,
  "camera_ready": true,
  "consecutive_errors": 0
}
```

## Integration with app.py

### Initialization

```python
# In app.py
from http_video_streamer import initialize_http_video_streaming, get_http_video_streamer

# After app creation
http_video_streamer = initialize_http_video_streaming(app, socketio)
```

The `initialize_http_video_streaming()` function:
- Creates a HTTPVideoStreamer instance
- Registers all video streaming routes with Flask
- Returns the streamer instance for reference

### Cleanup

```python
def cleanup_all_resources():
    # Stop video streaming
    streamer = get_http_video_streamer()
    if streamer.streaming_active:
        streamer.stop_streaming()
```

## Frontend Integration

### HTML
```html
<!-- Video element using img tag for MJPEG -->
<img id="videoElement" src="/video_stream" alt="Live Video Stream" />
```

### JavaScript
```javascript
// Start video streaming
fetch('/video/start', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'started') {
            // Show video element
            videoElement.style.display = 'block';
        }
    });

// Stop video streaming
fetch('/video/stop', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'stopped') {
            // Hide video element
            videoElement.style.display = 'none';
        }
    });
```

## Configuration

### Camera Settings (in http_video_streamer.py)

```python
# Resolution
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Frame rate
cap.set(cv2.CAP_PROP_FPS, 25)

# Target streaming FPS (independent from capture FPS)
self.target_fps = 15
```

### JPEG Encoding Quality

```python
# Quality: 75 (0-100, higher = better quality but larger file)
# Optimize: 1 (enable optimization)
cv2.imencode('.jpg', frame, [
    cv2.IMWRITE_JPEG_QUALITY, 75,
    cv2.IMWRITE_JPEG_OPTIMIZE, 1
])
```

### Error Handling

```python
# Max consecutive errors before stopping stream
self.max_consecutive_errors = 5
```

## Testing

### Run Test Script

```bash
python3 test_video_streaming.py
```

This will:
1. Initialize the streamer
2. Attempt to initialize camera
3. Start video streaming
4. Capture 5 test frames
5. Stop video streaming
6. Report results

### Manual Testing

1. **Start the Flask app:**
   ```bash
   python3 app.py
   ```

2. **Open in browser:** `http://localhost:5000`

3. **Check video status:**
   ```bash
   curl http://localhost:5000/video/status
   ```

4. **Start streaming:**
   ```bash
   curl -X POST http://localhost:5000/video/start
   ```

5. **Stream with ffmpeg/VLC:**
   ```bash
   ffplay http://localhost:5000/video_stream
   ```

6. **Stop streaming:**
   ```bash
   curl -X POST http://localhost:5000/video/stop
   ```

## Performance Metrics

### Typical Performance

| Metric | Value |
|--------|-------|
| Resolution | 854x480 |
| Capture FPS | 25 |
| Stream FPS | 15 (target) |
| JPEG Quality | 75 |
| Average Frame Size | ~30-50 KB |
| Bandwidth (theoretical) | ~4-8 Mbps @ 15 FPS |

### Optimization Tips

1. **Reduce resolution for lower bandwidth:**
   - Change frame width/height
   - Trade quality for lower bandwidth

2. **Reduce JPEG quality:**
   - Lower the quality parameter (e.g., 60 instead of 75)
   - Trade quality for lower bandwidth

3. **Reduce target FPS:**
   - Decrease `self.target_fps` value
   - Reduces bandwidth and CPU usage

4. **Frame skipping:**
   - Rate limiting ensures consistent FPS
   - Prevents overcapturing on high-speed cameras

## Troubleshooting

### Video Not Playing in Browser

**Check:**
1. Server is running: `curl http://localhost:5000/video/status`
2. Video stream started: Response should show `"active": true`
3. Camera is connected and detected
4. Browser supports MJPEG in img tags (most modern browsers do)

### Camera Not Found

**Solutions:**
1. Check camera is connected: `ls -la /dev/video*`
2. Check camera permissions: `ls -l /dev/video0`
3. Give user permission: `sudo usermod -a -G video $(whoami)`
4. Try different camera indices in `initialize_camera()`

### Stream Starts Then Stops

**Check logs for:**
1. Too many consecutive errors (check `max_consecutive_errors`)
2. Camera errors
3. JPEG encoding failures

**Solutions:**
1. Reduce resolution and quality
2. Check system resources (CPU, memory)
3. Update camera drivers

### High Latency

**Reduce latency by:**
1. Reducing JPEG quality
2. Reducing resolution
3. Increasing target FPS
4. Using local network instead of WiFi

### Frame Drops

**Causes:**
1. Network congestion
2. High quality/resolution
3. CPU overload

**Solutions:**
1. Reduce quality/resolution
2. Reduce target FPS
3. Check system load: `top`

## Logging

The module includes comprehensive logging:

```python
import logging
logger = logging.getLogger(__name__)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
```

Log levels:
- `DEBUG` - Frame-level details
- `INFO` - Status messages and initialization
- `WARNING` - Non-critical issues
- `ERROR` - Critical failures

## MJPEG Format

The MJPEG stream follows the standard format:

```
--frame\r\n
Content-Type: image/jpeg\r\n
Content-Length: {size}\r\n
Content-Transfer-Encoding: binary\r\n
X-Timestamp: {timestamp}\r\n
\r\n
{JPEG_DATA}\r\n
--frame\r\n
...
```

This format is:
- Widely supported by browsers
- Compatible with VLC and ffmpeg
- Doesn't require WebGL or special codecs
- Works on slow networks better than H264/H265

## Future Improvements

1. **Resolution Options** - Allow dynamic resolution selection
2. **Quality Control** - Runtime quality adjustment
3. **Bitrate Limiting** - Cap bandwidth usage
4. **Multiple Streams** - Support multiple camera angles
5. **Recording** - Save video to disk
6. **Motion Detection** - Only send frames on motion
7. **Codec Options** - Support H264, WebP, etc.

## References

- OpenCV VideoCapture: https://docs.opencv.org/master/d8/dfe/classcv_1_1VideoCapture.html
- MJPEG Format: https://en.wikipedia.org/wiki/Motion_JPEG
- HTTP Streaming: https://en.wikipedia.org/wiki/HTTP_Live_Streaming

## Support

For issues or improvements:
1. Check logs for error messages
2. Run test script to verify installation
3. Check camera detection
4. Review performance metrics
