# MJPEG Stream Testing Guide

## Quick Start

### Test 1: Web Browser (Easiest)
1. Open browser to: `http://localhost:5000` or `http://remotelab.local:5000`
2. Click the video play button (play icon on video area)
3. You should see live video from camera
4. Click stop button to stop streaming
5. Placeholder message should reappear

### Test 2: VLC Media Player

```bash
# Start VLC
vlc

# Via GUI:
# File > Open Network Stream > Enter: http://localhost:5000/video_stream

# Via command line:
vlc http://localhost:5000/video_stream
```

Expected result: Live video feed in VLC window

### Test 3: FFmpeg (Command Line)

```bash
# Test stream connection (should output MJPEG info):
ffmpeg -i http://localhost:5000/video_stream -t 5 -f image2 test_frames_%03d.png

# Test 10-second capture:
ffmpeg -i http://localhost:5000/video_stream -t 10 -c copy output.avi

# Test with re-encoding to MP4:
ffmpeg -i http://localhost:5000/video_stream -t 30 -c:v libx264 -preset fast output.mp4
```

### Test 4: CURL (Basic Connectivity)

```bash
# Download first 2000 bytes of stream (should be MJPEG headers):
curl -s -X GET "http://localhost:5000/video_stream" --range 0-2000 | xxd | head -20

# Expected output: Binary JPEG data starting with FF D8 FF
```

### Test 5: HTTP Endpoints

```bash
# Start video stream:
curl -X POST http://localhost:5000/video/start

# Expected response:
# {"message":"Video stream started","status":"started"}

# Stop video stream:
curl -X POST http://localhost:5000/video/stop

# Expected response:
# {"message":"Video stream stopped","status":"stopped"}
```

## Performance Testing

### Test 6: Memory Leak Detection

```bash
# Monitor memory usage while streaming:
watch -n 1 'ps aux | grep "app.py" | grep -v grep'

# Run for 30+ minutes
# Watch for continuous memory growth
# Should remain stable after warm-up
```

### Test 7: Bandwidth Monitoring

```bash
# Monitor bandwidth with iftop:
iftop -i eth0  # or your network interface

# Expected: ~15 FPS × ~30KB per frame = ~450 KB/s

# Or use nethogs:
nethogs -d 1
```

### Test 8: Frame Rate Verification

```bash
# Use ffmpeg to count frames received over 10 seconds:
time ffmpeg -i http://localhost:5000/video_stream -t 10 -f null - 2>&1 | grep "frame"

# Expected: approximately 150 frames (15 FPS × 10 seconds)
```

## Stress Testing

### Test 9: Multiple Concurrent Streams

```bash
# Open 3 concurrent VLC instances:
vlc http://localhost:5000/video_stream &
vlc http://localhost:5000/video_stream &
vlc http://localhost:5000/video_stream &

# Expected: All three should display video smoothly

# Stop all:
pkill vlc
```

### Test 10: Rapid Start/Stop Cycles

```bash
# Bash script to test 10 rapid cycles:
for i in {1..10}; do
  echo "Cycle $i: Starting..."
  curl -s -X POST http://localhost:5000/video/start > /dev/null
  sleep 2
  echo "Cycle $i: Stopping..."
  curl -s -X POST http://localhost:5000/video/stop > /dev/null
  sleep 1
done

# Check for any memory growth or resource leaks
ps aux | grep "app.py" | grep -v grep
```

## Audio Testing

Since audio still uses Socket.IO, test separately:

```bash
# Audio should continue to work with Socket.IO
# Click audio buttons in web interface
# Verify audio plays through browser speaker

# Check audio queue in background:
# Monitor console output for dispatcher thread messages
```

## Error Scenario Testing

### Test 11: Camera Disconnect

1. While video is streaming, physically disconnect camera
2. Watch for:
   - Graceful error handling (no crashes)
   - Browser shows appropriate error
   - /video/stop endpoint still works
   - App remains responsive

### Test 12: Network Interruption

```bash
# Simulate network latency:
tc qdisc add dev lo root netem delay 500ms

# Test streaming quality:
ffmpeg -i http://localhost:5000/video_stream -t 10 test.avi

# Remove latency:
tc qdisc del dev lo root
```

### Test 13: Invalid Requests

```bash
# Test GET instead of POST for control endpoints:
curl -X GET http://localhost:5000/video/start

# Expected: 405 Method Not Allowed

# Test multiple start requests:
curl -X POST http://localhost:5000/video/start
curl -X POST http://localhost:5000/video/start

# Expected: Both succeed without error
```

## Browser Debugging

### Test 14: Browser Console

1. Open browser DevTools (F12)
2. Go to Network tab
3. Click video play button
4. Watch for:
   - POST request to `/video/start` (should return 200)
   - `/video_stream` connection (streaming indicator)
5. Monitor Console for JavaScript errors

### Test 15: Browser Performance

1. Open DevTools Performance tab
2. Start recording
3. Click video play
4. Record for 10 seconds
5. Check CPU usage:
   - Should be low (<5% for video decoding)
   - Smooth 60fps main thread

## Compatibility Testing

### Test 16: Different Browsers

- Chrome/Chromium
- Firefox
- Safari (mobile)
- Edge
- Opera

All should display video without issues.

### Test 17: Mobile Testing

```bash
# Access from phone on same network:
# http://remotelab.local:5000  (if mDNS available)
# or http://[IP_ADDRESS]:5000

# Test on:
- iOS Safari
- Android Chrome
- Mobile Firefox
```

## Rollback Testing

If issues found:

```bash
# Check git status:
git status

# View changes:
git diff app.py | head -50

# If needed to rollback:
git checkout app.py
```

## Expected Results Summary

| Test | Expected | Status |
|------|----------|--------|
| Browser video | Live feed displays | |
| VLC stream | Video plays in VLC | |
| FFmpeg capture | Frames saved to disk | |
| Concurrent streams | Multiple streams work | |
| 30min duration | Memory stable, no leaks | |
| Rapid cycles | No errors, clean shutdown | |
| Error handling | Graceful degradation | |
| Performance | 15 FPS maintained | |

## Troubleshooting

### Video not displaying
1. Check if camera connected: `ls /dev/video*`
2. Check app logs for errors
3. Verify /video_stream endpoint returns data: `curl http://localhost:5000/video_stream | xxd | head -5`
4. Check browser console (F12) for errors

### High memory usage
1. Monitor with `watch -n 1 'ps aux | grep app.py'`
2. Check if multiple video streams active
3. Restart app if memory grows unbounded

### Slow video
1. Check network bandwidth: `iftop`
2. Reduce JPEG quality in generate_mjpeg_frames()
3. Reduce target FPS (change frame_interval)
4. Check camera resolution: may be capturing high resolution

### VLC can't connect
1. Verify endpoint working: `curl -I http://localhost:5000/video_stream`
2. Check firewall: `sudo ufw status`
3. Verify IP address: `hostname -I`
4. Try 127.0.0.1 instead of hostname

### FFmpeg connection timeout
1. Start video stream first (POST /video/start)
2. Then connect FFmpeg within 30 seconds
3. Check if another process blocking the port
