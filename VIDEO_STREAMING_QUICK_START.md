# Video Streaming - Quick Start

## What Changed?

Video streaming has been refactored into a **separate dedicated module** (`http_video_streamer.py`) for better robustness, maintainability, and testability.

### Key Improvements
✓ **Better error handling** - Comprehensive error tracking and recovery  
✓ **Easier debugging** - Isolated video logic with dedicated logging  
✓ **More reliable** - Proper resource cleanup and state management  
✓ **Modular design** - Can be reused in other projects  
✓ **HTTP-based** - Uses standard MJPEG format for maximum compatibility  

## How to Use

### Start Application
```bash
python3 app.py
```

### Start Video Streaming (Frontend)
Click the **Play** button in the "Live Video Stream" panel on the web interface.

### Start Video Streaming (API)
```bash
curl -X POST http://localhost:5000/video/start
```

### Stop Video Streaming (API)
```bash
curl -X POST http://localhost:5000/video/stop
```

### Check Video Status
```bash
curl http://localhost:5000/video/status
```

### Stream to VLC/ffplay
```bash
ffplay http://localhost:5000/video_stream
```

## Files Structure

```
/home/pi/remotelab/
├── app.py                           # Main Flask application
├── http_video_streamer.py          # NEW: Video streaming module
├── test_video_streaming.py         # NEW: Video streaming tests
├── HTTP_VIDEO_STREAMING_GUIDE.md   # Detailed documentation
└── VIDEO_STREAMING_QUICK_START.md  # This file
```

## Configuration

Edit `http_video_streamer.py` to adjust:

### Resolution (854x480 default)
```python
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
```

### FPS (15 target FPS)
```python
self.target_fps = 15
```

### JPEG Quality (75 out of 100)
```python
cv2.IMWRITE_JPEG_QUALITY, 75
```

## Troubleshooting

### Video not showing?
1. Check streaming started: `curl http://localhost:5000/video/status`
2. Check camera connected: `ls /dev/video*`
3. Check logs in terminal where app is running

### High latency?
- Reduce resolution in configuration
- Reduce JPEG quality
- Use local network instead of WiFi

### Camera not found?
```bash
# Check camera
ls -la /dev/video*

# Fix permissions
sudo usermod -a -G video $(whoami)

# Reconnect camera or restart
```

### Stream stops suddenly?
Check logs for errors. Common causes:
- Camera disconnected
- Too many encoding errors
- System resource exhaustion

## Testing

Run the test script:
```bash
python3 test_video_streaming.py
```

Expected output:
```
==================================================
HTTP Video Streamer Test
==================================================

[INFO] ✓ Got HTTP video streamer instance
[INFO] Initial status: {'active': False, 'camera_ready': False, 'consecutive_errors': 0}
[INFO] Attempting to initialize camera...
[INFO] ✓ Camera initialized successfully
[INFO] Starting video stream...
[INFO] ✓ Video stream started
[INFO] Testing frame capture...
[INFO]   Frame 1: ✓ Captured 35284 bytes
...
[INFO] ✓ Video stream stopped
```

## API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/video/start` | POST | Start video streaming |
| `/video/stop` | POST | Stop video streaming |
| `/video/status` | GET | Get streaming status |
| `/video_stream` | GET | Get MJPEG stream (for img tags) |

## Browser Compatibility

✓ Chrome, Firefox, Safari, Edge  
✓ Mobile browsers (iOS Safari, Chrome Android)  
✓ VLC Media Player  
✓ ffmpeg / ffplay  

## Performance

- **Resolution:** 854x480 (configurable)
- **FPS:** 15 (target, configurable)
- **Bandwidth:** ~4-8 Mbps typical
- **Latency:** 200-500ms typical

## For More Details

See `HTTP_VIDEO_STREAMING_GUIDE.md` for comprehensive documentation including:
- Architecture details
- Configuration options
- Performance optimization
- Troubleshooting guide
- Future improvements

## Support

If video streaming isn't working:

1. **Check logs:**
   ```bash
   # Terminal where app is running will show:
   # [ERROR] Camera at index 0 cannot be opened
   # [INFO] ✓ Successfully initialized camera at index 1
   ```

2. **Run tests:**
   ```bash
   python3 test_video_streaming.py
   ```

3. **Manual test with curl:**
   ```bash
   curl http://localhost:5000/video/status
   curl -X POST http://localhost:5000/video/start
   # Then check status again
   ```

4. **Check system:**
   ```bash
   # Camera device exists
   ls /dev/video*
   
   # User has permission
   groups | grep video
   
   # OpenCV can access camera
   python3 -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL')"
   ```
