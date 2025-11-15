# MJPEG Video Stream - Quick Command Reference

## Starting the Application

```bash
# Navigate to the RemoteLab directory
cd /home/pi/remotelab

# Start the Flask application
python3 app.py

# Or if using systemd service (if configured)
sudo systemctl restart remotelab
```

## HTTP Endpoint Commands

### Start Video Streaming

```bash
curl -X POST http://localhost:5000/video/start

# Expected response:
# {"message":"Video stream started","status":"started"}
```

### Stop Video Streaming

```bash
curl -X POST http://localhost:5000/video/stop

# Expected response:
# {"message":"Video stream stopped","status":"stopped"}
```

### Get MJPEG Stream (Direct Access)

```bash
# View stream headers (first 2KB)
curl -s http://localhost:5000/video_stream --range 0-2048 | xxd | head -20

# Test with timeout (don't let it run forever)
timeout 5 curl http://localhost:5000/video_stream | xxd | head -30
```

## Browser Testing

### Open Web Interface
```bash
# If running locally
http://localhost:5000

# If running on different machine
http://remotelab.local:5000
or
http://<IP_ADDRESS>:5000
```

## VLC Media Player

### GUI Method
1. Open VLC
2. File → Open Network Stream
3. Enter: `http://localhost:5000/video_stream`
4. Click Play

### Command Line
```bash
# Start VLC with MJPEG stream
vlc http://localhost:5000/video_stream

# With specific options
vlc --vv http://localhost:5000/video_stream  # Verbose
vlc --loop http://localhost:5000/video_stream  # Loop when finished
vlc --fullscreen http://localhost:5000/video_stream  # Fullscreen
```

## FFmpeg

### Capture Frames
```bash
# Capture 10 seconds as individual PNG files
ffmpeg -i http://localhost:5000/video_stream -t 10 -f image2 frame_%03d.png

# Capture 1 frame per second
ffmpeg -i http://localhost:5000/video_stream -t 10 -vf fps=1 frame_%03d.png

# Capture specific duration with quality
ffmpeg -i http://localhost:5000/video_stream -t 30 -c:v mjpeg -q:v 5 output.avi
```

### Convert to Video Files
```bash
# Convert to MP4 (H.264)
ffmpeg -i http://localhost:5000/video_stream -t 30 -c:v libx264 -preset fast output.mp4

# Convert to WebM
ffmpeg -i http://localhost:5000/video_stream -t 30 -c:v libvpx -crf 10 output.webm

# Convert to AVI
ffmpeg -i http://localhost:5000/video_stream -t 30 output.avi
```

### Stream Analysis
```bash
# Show stream information
ffmpeg -i http://localhost:5000/video_stream -t 1 2>&1 | grep -E "Video:|Duration:"

# Count frames (run for 10 seconds)
time ffmpeg -i http://localhost:5000/video_stream -t 10 -f null - 2>&1 | grep frame
```

## System Monitoring

### Monitor Resource Usage
```bash
# Watch Python process (memory and CPU)
watch -n 1 'ps aux | grep app.py | grep -v grep'

# More detailed process info
ps aux | grep app.py

# Monitor real-time with top
top -p $(pgrep -f "python3 app.py")
```

### Monitor Network Bandwidth
```bash
# Watch network traffic
watch -n 1 'ifstat'

# Using iftop (install if needed: sudo apt install iftop)
sudo iftop -i eth0

# Using nethogs (install if needed: sudo apt install nethogs)
sudo nethogs
```

### Check Camera
```bash
# List available video devices
ls -la /dev/video*

# Test camera directly
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-ctrls

# Simple camera test with ffmpeg
ffmpeg -f v4l2 -list_formats all -i /dev/video0
ffmpeg -f v4l2 -i /dev/video0 -t 5 test_direct.mp4
```

## Logging and Debugging

### View Application Logs
```bash
# If running in foreground, logs appear in console
# If running as service:
journalctl -u remotelab -f  # Follow service logs

# View recent logs
journalctl -u remotelab -n 50  # Last 50 lines
```

### Enable Debug Logging
```bash
# Edit app.py and add after imports:
import logging
logging.basicConfig(level=logging.DEBUG)

# Or set environment variable:
FLASK_ENV=development FLASK_DEBUG=1 python3 app.py
```

## Maintenance Commands

### Restart Application
```bash
# If running as systemd service
sudo systemctl restart remotelab
sudo systemctl status remotelab

# If running manually, stop with Ctrl+C and restart
python3 app.py
```

### Check Port Status
```bash
# See what's using port 5000
lsof -i :5000
netstat -tuln | grep 5000

# Kill process on port 5000 if needed
fuser -k 5000/tcp
```

### Reset/Clear Streams
```bash
# Stop all streams via API
curl -X POST http://localhost:5000/video/stop

# Kill all curl/ffmpeg/vlc processes (be careful!)
pkill -f "curl.*video_stream"
pkill -f "ffmpeg.*video_stream"
pkill vlc
```

## Development/Testing Workflow

### Quick Test Cycle
```bash
# Terminal 1: Run the app
python3 app.py

# Terminal 2: Test the endpoints
# Start video
curl -X POST http://localhost:5000/video/start
sleep 2

# Test stream (5 seconds)
timeout 5 curl http://localhost:5000/video_stream > /tmp/test_stream.mjpeg

# Stop video
curl -X POST http://localhost:5000/video/stop

# Check file
file /tmp/test_stream.mjpeg
```

### Rapid Testing in Browser
```bash
# Terminal 1: Run app
python3 app.py

# Terminal 2: Open browser and test manually
firefox http://localhost:5000 &
```

### Load Testing
```bash
# Simulate 5 concurrent clients
for i in {1..5}; do
  timeout 10 curl http://localhost:5000/video_stream > /dev/null &
done

# Wait for all to finish
wait

# Check how many connections were active
ps aux | grep curl | grep -v grep | wc -l
```

## Troubleshooting Commands

### Is the app running?
```bash
pgrep -f "python3 app.py"  # Shows PID if running
curl http://localhost:5000  # Should return 200
```

### Is the camera working?
```bash
ls -la /dev/video* | wc -l  # Should show at least 1
cat /proc/asound/cards      # For audio devices
lsusb | grep -i camera      # USB camera check
```

### Network accessibility
```bash
# From local machine
curl http://localhost:5000/video_stream --max-time 2 > /dev/null && echo "OK" || echo "FAIL"

# From another machine (replace IP)
curl http://192.168.1.100:5000/video_stream --max-time 2 > /dev/null && echo "OK" || echo "FAIL"

# Check if port is listening
netstat -tuln | grep 5000
```

### Firewall Issues
```bash
# Check UFW status
sudo ufw status
sudo ufw status numbered

# If port 5000 blocked
sudo ufw allow 5000
sudo ufw allow 5000/tcp
```

## Useful Aliases (add to ~/.bashrc)

```bash
# Add these to ~/.bashrc for easier commands
alias remotelab-start='cd /home/pi/remotelab && python3 app.py'
alias remotelab-stream='curl http://localhost:5000/video_stream | xxd | head -20'
alias remotelab-start-video='curl -X POST http://localhost:5000/video/start && echo ""'
alias remotelab-stop-video='curl -X POST http://localhost:5000/video/stop && echo ""'
alias remotelab-test='curl -s http://localhost:5000 | head -50'
alias remotelab-log='journalctl -u remotelab -f'

# Then use:
# remotelab-start
# remotelab-stream
# remotelab-start-video
# remotelab-stop-video
```

## Quick Health Check Script

```bash
#!/bin/bash
# Save as check_remotelab.sh

echo "Remote Lab Health Check"
echo "======================="

# Check if running
if pgrep -f "python3 app.py" > /dev/null; then
    echo "✓ App is running"
else
    echo "✗ App is NOT running"
    exit 1
fi

# Check if responding
if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "✓ App is responding"
else
    echo "✗ App is NOT responding"
fi

# Check if video endpoints exist
if curl -s -X POST http://localhost:5000/video/start | grep -q "started"; then
    echo "✓ Video /start endpoint works"
    curl -s -X POST http://localhost:5000/video/stop > /dev/null
    echo "✓ Video /stop endpoint works"
else
    echo "✗ Video endpoints not responding"
fi

# Check camera
if [ -c /dev/video0 ]; then
    echo "✓ Camera device exists"
else
    echo "✗ Camera device not found"
fi

echo ""
echo "Health check complete!"
```

## Performance Monitoring Script

```bash
#!/bin/bash
# Save as monitor_remotelab.sh

echo "Remote Lab Performance Monitor"
echo "=============================="

while true; do
    clear
    echo "Timestamp: $(date)"
    echo ""
    
    # Show memory/CPU
    echo "Process Stats:"
    ps aux | grep "python3 app.py" | grep -v grep | awk '{print "  CPU: "$3"%, Memory: "$4"%"}'
    
    # Show network
    echo ""
    echo "Network Stats:"
    curl -s http://localhost:5000/video_stream --max-time 1 | wc -c | awk '{printf "  Last sec: %.0f bytes/sec\n", $1}'
    
    # Show connections
    echo ""
    echo "Connections:"
    netstat -tan | grep 5000 | grep ESTABLISHED | wc -l | awk '{print "  Active: "$1}'
    
    sleep 5
done
```

## Common Issues & Quick Fixes

```bash
# Port already in use
sudo lsof -i :5000
sudo kill -9 <PID>

# Memory leak
pkill -f "python3 app.py"
python3 app.py

# Camera not detected
v4l2-ctl --list-devices

# Network not accessible
sudo ufw allow 5000
sudo systemctl restart networking

# Python dependency missing
pip3 install flask flask-socketio python-socketio opencv-python
```
