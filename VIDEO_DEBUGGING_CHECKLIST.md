# Video Streaming Debugging Checklist

Use this checklist to diagnose and fix video streaming issues.

## Quick Diagnostics

### Step 1: Check if App is Running
```bash
# Check if port 5000 is listening
netstat -tuln | grep 5000

# Or try to access the app
curl http://localhost:5000/
```

**Expected:** Returns HTML page (200 OK)

**If fails:** 
- Start the app: `python3 app.py`
- Check for errors in terminal

---

### Step 2: Check if Video Routes are Registered
```bash
curl http://localhost:5000/video/status
```

**Expected output:**
```json
{
  "active": false,
  "camera_ready": false,
  "consecutive_errors": 0
}
```

**If fails with 404:**
- App didn't initialize video module
- Check app startup logs for: `✓ HTTP video streaming initialized`

**If fails with connection error:**
- App is not running
- Start it: `python3 app.py`

---

### Step 3: Check Camera Detection
```bash
# List camera devices
ls -la /dev/video*

# Check permissions
groups | grep video
```

**Expected:**
- At least one `/dev/video0` (or higher)
- User in `video` group

**If no /dev/video devices:**
- Camera not connected
- Camera driver not loaded
- USB device not visible

**If permission denied:**
```bash
sudo usermod -a -G video $USER
# Log out and back in, or:
newgrp video
```

---

### Step 4: Test Camera with OpenCV
```bash
python3 << 'EOF'
import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Camera {i}: {'✓ OK' if ret else '✗ Cannot read frame'}")
        cap.release()
    else:
        print(f"Camera {i}: Cannot open")
EOF
```

**Expected:**
```
Camera 0: ✓ OK
Camera 1: Cannot open
...
```

**If all fail:**
- Camera driver issue
- Try: `sudo modprobe uvcvideo` (for USB cameras)
- Check dmesg: `dmesg | tail -20`

---

### Step 5: Start Video Streaming
```bash
# Start streaming
curl -X POST http://localhost:5000/video/start

# Check status
curl http://localhost:5000/video/status
```

**Expected:**
```json
{
  "active": true,
  "camera_ready": true,
  "consecutive_errors": 0
}
```

**If `"active": false`:**
- Check app logs for error messages
- Camera initialization failed
- Run camera test again (Step 4)

**If `"camera_ready": false`:**
- Camera can't be accessed
- Permission issue
- Camera already in use by another app

---

### Step 6: Test MJPEG Stream
```bash
# Test with ffplay (if installed)
ffplay http://localhost:5000/video_stream

# Or with curl (get first 1000 bytes)
curl -m 2 http://localhost:5000/video_stream | head -c 1000 | od -c | head

# Or check content type
curl -I http://localhost:5000/video_stream
```

**Expected:**
- ffplay: Video window appears
- curl: Starts showing binary JPEG data
- curl -I: Content-Type: `multipart/x-mixed-replace; boundary=frame`

**If no data:**
- Stream not started (run Step 5)
- Camera not capturing frames
- Check consecutive_errors count

---

## Detailed Issue Resolution

### Issue: "Video Stream Offline" in Browser

**Diagnosis:**
1. Open browser console: F12 → Console
2. Check for JavaScript errors
3. Check Network tab:
   - GET `/video_stream` → status?

**Solutions:**

**If 404 error:**
- Route not registered
- Check: `curl http://localhost:5000/video/status`
- Restart app: `python3 app.py`

**If 503 error:**
- Streaming not started
- Click "Play" button
- Or: `curl -X POST http://localhost:5000/video/start`

**If 200 but no image:**
- Check img src: DevTools → Inspector → find `<img id="videoElement">`
- Should be: `src="/video_stream"`
- Check that element is visible: `display: block` (not `none`)

---

### Issue: Video Starts Then Stops

**Check error log:**
```bash
# Terminal where app.py is running should show:
# [ERROR] Too many consecutive errors
# [ERROR] Camera disconnected
# [ERROR] Frame encoding failed
```

**Common causes and fixes:**

**Cause: Camera disconnected**
- Solution: Reconnect USB camera
- Restart app: `python3 app.py`

**Cause: Too many encoding errors**
- Solution: Reduce JPEG quality in `http_video_streamer.py`:
  ```python
  cv2.IMWRITE_JPEG_QUALITY, 60  # From 75
  ```
- Or reduce resolution

**Cause: High CPU usage**
- Check: `top -b -n 1 | grep python`
- Solution:
  - Reduce resolution
  - Reduce target FPS: `self.target_fps = 10` (from 15)
  - Increase consecutive_errors threshold

**Cause: Camera in exclusive mode**
- Another app is using camera
- Check: `lsof | grep /dev/video`
- Kill blocking process or restart

---

### Issue: High Latency / Video Lag

**Measurement:**
1. Compare local clock with video timestamp
2. Should be < 500ms typically

**Common causes:**

**Network latency:**
- Test: `ping -c 4 localhost`
- Should be < 5ms on local machine
- WiFi slows it down

**High quality settings:**
- Current defaults: 854x480 @ 75 quality
- Optimize:
  ```python
  # In http_video_streamer.py
  cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
  cv2.IMWRITE_JPEG_QUALITY, 60
  self.target_fps = 10
  ```

**Browser buffering:**
- Refresh page: F5
- Try different browser
- Clear browser cache

---

### Issue: Frame Drops / Stuttering

**Check frame rate:**
```bash
# Watch streaming status
watch 'curl -s http://localhost:5000/video/status | jq .'
```

**Monitor consecutive_errors:**
- Should stay at 0
- If increasing, camera or encoding issue

**Solutions:**

**Reduce load:**
```python
# In http_video_streamer.py
self.target_fps = 10  # From 15
cap.set(cv2.CAP_PROP_FPS, 20)  # From 25
```

**Check system resources:**
```bash
# Monitor CPU and memory
top -p $(pgrep -f 'python.*app.py')

# Check disk I/O
iostat -x 1
```

**Use wired network:**
- WiFi has higher latency and packet loss
- Use Ethernet for best performance

---

### Issue: Camera Not Found

**Step-by-step fix:**

1. **Check device exists:**
   ```bash
   ls -la /dev/video*
   ```
   If nothing, camera not connected or driver not loaded

2. **Check permissions:**
   ```bash
   ls -la /dev/video0  # Or /dev/video1, etc.
   # Should be readable by your user
   ```
   If not:
   ```bash
   sudo usermod -a -G video $USER
   ```

3. **Check driver loaded:**
   ```bash
   lsmod | grep uvcvideo  # For USB cameras
   lsmod | grep bcm2835   # For Raspberry Pi CSI camera
   ```
   If not loaded:
   ```bash
   # For USB cameras
   sudo modprobe uvcvideo
   
   # For RPi camera (if using PiCamera instead of USB)
   sudo vcgencmd get_camera
   ```

4. **Test with OpenCV:**
   ```bash
   python3 -c "
   import cv2
   cap = cv2.VideoCapture(0)
   if cap.isOpened():
       ret, frame = cap.read()
       print('✓ Camera works' if ret else '✗ Cannot read frame')
       cap.release()
   else:
       print('✗ Cannot open camera')
   "
   ```

5. **Check if camera is busy:**
   ```bash
   lsof | grep /dev/video
   # If another process uses it, close it
   ```

6. **Restart device:**
   ```bash
   # Disconnect USB camera
   sleep 2
   # Reconnect USB camera
   sleep 2
   python3 app.py
   ```

---

## Testing Commands

### Comprehensive Test Suite
```bash
# 1. Check app is running
echo "1. Checking app..."
curl -s http://localhost:5000/ > /dev/null && echo "✓ App running" || echo "✗ App not running"

# 2. Check video module
echo "2. Checking video module..."
curl -s http://localhost:5000/video/status | grep -q '"active"' && echo "✓ Video module loaded" || echo "✗ Video module not loaded"

# 3. Check camera detection
echo "3. Checking camera..."
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('✓ Camera found' if cap.isOpened() else '✗ Camera not found'); cap.release()"

# 4. Start streaming
echo "4. Starting stream..."
curl -X POST -s http://localhost:5000/video/start | grep -q '"started"' && echo "✓ Stream started" || echo "✗ Stream failed to start"

# 5. Check stream status
echo "5. Checking stream status..."
curl -s http://localhost:5000/video/status | grep -q '"active": true' && echo "✓ Stream active" || echo "✗ Stream not active"

# 6. Stop streaming
echo "6. Stopping stream..."
curl -X POST -s http://localhost:5000/video/stop | grep -q '"stopped"' && echo "✓ Stream stopped" || echo "✗ Stream failed to stop"

echo "Done!"
```

### Individual Endpoint Tests
```bash
# Start stream
curl -X POST http://localhost:5000/video/start

# Check status
curl http://localhost:5000/video/status

# Get stream (test with ffplay)
ffplay http://localhost:5000/video_stream

# Stop stream
curl -X POST http://localhost:5000/video/stop
```

---

## App Log Analysis

When debugging, watch app logs:

```bash
# If app running in foreground
python3 app.py 2>&1 | tee app.log

# Watch logs in real-time
tail -f app.log | grep -i "video\|error\|camera"

# Find all errors
grep ERROR app.log

# Find all video-related messages
grep -i video app.log
```

### Common Log Messages

```
✓ HTTP video streaming initialized
   → Video module loaded correctly

✓ Camera initialized successfully at index 0
   → Camera found and configured

✓ Video stream started
   → Streaming is active

Starting MJPEG frame generation
   → Frames being generated

Too many consecutive errors, stopping
   → Camera lost or encoding failed
```

---

## Performance Monitoring

### Check Frame Rate
```bash
# Monitor status changes
while true; do
    STATUS=$(curl -s http://localhost:5000/video/status)
    echo "$(date): $STATUS"
    sleep 1
done
```

### Check CPU Usage
```bash
# Monitor Python process
watch -n 1 'ps aux | grep python'

# Or with top
top -p $(pgrep -f "python.*app.py")
```

### Check Network Traffic
```bash
# Watch traffic on eth0 (adjust for your interface)
iftop -i eth0
# Or:
nethogs eth0
```

---

## Advanced Debugging

### Enable Debug Logging
```python
# Add to app.py before app.run()
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('http_video_streamer')
logger.setLevel(logging.DEBUG)
```

### Check Memory Usage
```bash
# Monitor memory
watch -n 1 'ps aux | grep python | grep app'

# Or with detailed memory info
python3 << 'EOF'
import psutil
import sys
try:
    p = psutil.Process()
    print(f"Memory: {p.memory_info().rss / 1024 / 1024:.1f} MB")
    print(f"CPU: {p.cpu_percent():.1f}%")
except:
    print("Install psutil: pip install psutil")
EOF
```

### Trace System Calls
```bash
# Trace camera operations
strace -e openat,ioctl python3 app.py 2>&1 | grep video

# Trace network operations
strace -e network python3 app.py 2>&1 | head -50
```

---

## When All Else Fails

### Complete System Check
```bash
#!/bin/bash
echo "=== System Check ==="
echo "Python: $(python3 --version)"
echo "OpenCV: $(python3 -c 'import cv2; print(cv2.__version__)')"
echo "Camera: $(ls /dev/video* 2>/dev/null | wc -l) device(s) found"
echo "App PID: $(pgrep -f 'python.*app.py')"
echo "Port 5000: $(netstat -tuln 2>/dev/null | grep 5000 | wc -l) listener(s)"
echo "Video status: $(curl -s http://localhost:5000/video/status)"
```

### Factory Reset Procedure
```bash
# 1. Stop current app
pkill -f "python.*app.py"

# 2. Disconnect/reconnect camera
# USB: unplug and replug

# 3. Restart app
cd /home/pi/remotelab
python3 app.py
```

### Get Help
Include this information when reporting issues:
1. Output of system check above
2. Full app log output
3. Browser console errors (F12 → Console)
4. Terminal errors when starting app
5. Output of test script: `python3 test_video_streaming.py`

---

## Success Criteria

✓ Video "Offline" placeholder disappears  
✓ Live video appears in web interface  
✓ Can drag/pan the video (if in fullscreen mode)  
✓ Video continues without stuttering  
✓ No errors in app logs  
✓ Browser console has no video-related errors  

Good luck!
