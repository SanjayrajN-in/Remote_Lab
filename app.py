from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, send_from_directory
from flask_socketio import SocketIO, emit
import os
import subprocess
import serial.tools.list_ports
import threading
import time
import json
import socket
from werkzeug.utils import secure_filename
from queue import Queue
import cv2
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("PyAudio not available - audio features will be disabled")
import numpy as np
import base64
import io

# Import logic analyzer
from logic_analyzer import init_logic_analyzer_manager, get_logic_analyzer_manager

# Import firmware validator
from firmware_validator import FirmwareValidator

app = Flask(__name__, template_folder='page')
app.config['UPLOAD_FOLDER'] = '.'
app.config['ALLOWED_EXTENSIONS'] = {'hex', 'bin'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize logic analyzer (moved after socketio initialization)
logic_analyzer_manager = None

# Initialize firmware validator (will be reloaded for each validation)
firmware_validator = None

# Global variables for video and audio streaming
video_capture = None
audio_stream = None
serial_connection = None
video_streaming_active = False
audio_streaming_active = False
serial_monitoring_active = False

# Non-blocking queues for video/audio to prevent emit() blocking
video_frame_queue = Queue(maxsize=2)  # Keep only 2 frames max
audio_data_queue = Queue(maxsize=2)  # Keep only 2 buffers max to minimize latency and prevent accumulation

# Device configurations
ARDUINO_IDS = {'2341', '2a03', '1a86'}
ESP32_IDS = {'10c4', '303a'}
USBASP_IDS={'16c0:05dc'}
ESP_BAUD = "460800"

# Global variables for terminal output
terminal_output = []
upload_in_progress = False

# Global variables for hub controls
hub_controls = []
hub_controls_lock = threading.Lock()  # Thread safety for hub control modifications
control_values = {}
serial_value_patterns = {}
deleted_reader_controls = set()  # Track permanently deleted reader control names (prevent auto-recreation)
deleted_reader_controls_lock = threading.Lock()  # Thread safety for deleted controls tracking

# Streaming state locks to prevent race conditions
streaming_state_lock = threading.Lock()
video_init_in_progress = False
audio_init_in_progress = False

def detect_control_type(value_name, context=""):
    """Detect the appropriate control type based on value name and context"""
    name_lower = value_name.lower()

    # Skip reserved/internal oscilloscope parameters
    if any(keyword in name_lower for keyword in ['timebase', 'amplitude', 'scale', 'offset']):
        return None

    # Binary/On-Off controls (detect first as they have specific value options)
    if any(keyword in name_lower for keyword in ['enable', 'disable', 'on', 'off', 'state', 'status', 'dir', 'direction']):
        return {
            'type': 'toggle',
            'command_template': f'{value_name}={{value}}',
            'value_options': ['0', '1'],  # Default on/off values
            'display_options': ['OFF', 'ON'],
            'allow_custom_values': True  # Allow users to enter custom values
        }

    # Direction controls
    elif any(keyword in name_lower for keyword in ['dir', 'direction', 'forward', 'reverse', 'cw', 'ccw']):
        return {
            'type': 'toggle',
            'command_template': f'{value_name}={{value}}',
            'value_options': ['0', '1'],
            'display_options': ['REVERSE', 'FORWARD']
        }

    # Servo/Angle controls
    elif any(keyword in name_lower for keyword in ['servo', 'angle', 'degree', 'deg', 'pos', 'position']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 180,
            'step': 1,
            'unit': '°',
            'command_template': f'{value_name}={{value}}'
        }

    # Temperature controls
    elif any(keyword in name_lower for keyword in ['temp', 'temperature']):
        return {
            'type': 'slider',
            'min': -50,
            'max': 150,
            'step': 0.1,
            'unit': '°C',
            'command_template': f'{value_name}={{value}}'
        }

    # Speed/RPM controls
    elif any(keyword in name_lower for keyword in ['speed', 'rpm', 'velocity']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 1000,
            'step': 10,
            'unit': 'RPM',
            'command_template': f'{value_name}={{value}}'
        }

    # Voltage controls
    elif any(keyword in name_lower for keyword in ['volt', 'voltage', 'v']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 5,
            'step': 0.1,
            'unit': 'V',
            'command_template': f'{value_name}={{value}}'
        }

    # Current controls
    elif any(keyword in name_lower for keyword in ['current', 'amp', 'amps', 'i']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 5,
            'step': 0.1,
            'unit': 'A',
            'command_template': f'{value_name}={{value}}'
        }

    # Pressure controls
    elif any(keyword in name_lower for keyword in ['press', 'pressure', 'psi', 'bar']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 100,
            'step': 1,
            'unit': 'PSI',
            'command_template': f'{value_name}={{value}}'
        }

    # Distance/Position controls
    elif any(keyword in name_lower for keyword in ['dist', 'distance', 'cm', 'mm', 'inch']):
        return {
            'type': 'slider',
            'min': 0,
            'max': 100,
            'step': 1,
            'unit': 'cm',
            'command_template': f'{value_name}={{value}}'
        }

    # Default numeric control
    else:
        return {
            'type': 'slider',
            'min': 0,
            'max': 100,
            'step': 1,
            'unit': '',
            'command_template': f'{value_name}={{value}}'
        }

def analyze_serial_data_for_controls(data):
    """Analyze serial data to detect potential control values and commands"""
    global serial_value_patterns
    import re



    # First, check any existing Reader controls that have a command_template set
    # and try to parse the incoming data using that template. This allows
    # patterns like 'Test={value}RPM' or '{value}RPM' to be matched against
    # serial lines such as '3RPM' or 'Test=3RPM'.
    detected_values = {}
    detected_commands = set()

    try:
        for control in hub_controls:
            try:
                if control.get('type') == 'reader':
                    tmpl = control.get('config', {}).get('command_template')
                    if tmpl and '{value}' in tmpl:
                        # Convert the template into a permissive regex:
                        # - replace {value} first before escaping
                        # - escape literal characters
                        # - allow optional whitespace around separators like '=' or ':'
                        # Replace {value} placeholder first
                        tmpl_pattern = tmpl.replace('{value}', '<<<VALUE>>>')
                        # Escape special regex characters
                        tmpl_escaped = re.escape(tmpl_pattern)
                        # Replace the placeholder with numeric capture
                        tmpl_escaped = tmpl_escaped.replace('<<<VALUE>>>', r'([+-]?\d*\.?\d+)')
                        # Allow optional whitespace around = or :
                        tmpl_escaped = tmpl_escaped.replace(r'\=', r'\s*=\s*')
                        tmpl_escaped = tmpl_escaped.replace(r'\:', r'\s*:\s*')
                        # Replace escaped spaces with flexible whitespace
                        tmpl_escaped = tmpl_escaped.replace(r'\ ', r'\s+')

                        try:
                            m = re.search(tmpl_escaped, data, re.IGNORECASE)
                        except re.error:
                            m = None

                        if m:
                            try:
                                num = float(m.group(1))
                                detected_values[control['name']] = {
                                    'name': control['name'],
                                    'value': num,
                                    'count': 1,
                                    'last_seen': time.time()
                                }
                                
                                # Update the control value immediately
                                update_control_value(control['id'], num)
                                # Emit update to frontend
                                socketio.emit('hub_control_updated', {'control': {
                                    'id': control['id'],
                                    'current_value': num
                                }})
                            except ValueError:
                                pass
            except Exception:
                # Ignore individual control parsing errors
                continue
    except Exception:
        # If template-based parsing fails for any reason, continue to generic parsing
        detected_values = {}

    # Patterns to detect value assignments and readings (generic fallbacks)
    patterns = [
        # Variable assignments: var = value
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*[:=]\s*([+-]?\d*\.?\d+)',
        # Labeled values: label: value
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([+-]?\d*\.?\d+)',
        # Function calls with values: func(value)
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([+-]?\d*\.?\d+)\s*\)',
        # JSON-like: "key": value
        r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*([+-]?\d*\.?\d+)',
        # Value followed by unit/label without separator: 123RPM or 50Speed
        r'([+-]?\d*\.?\d+)\s*([A-Za-z_][A-Za-z0-9_]*)'
    ]

    # Patterns to detect command options from help text
    command_patterns = [
        # "Enter 'on' to turn LED on, 'off' to turn LED off"
        r"'([a-zA-Z0-9_]+)'\s*(?:\w+\s+)*([a-zA-Z0-9_]+)",
        # "Use 'on' or 'off'"
        r"'([a-zA-Z0-9_]+)'\s*or\s*'([a-zA-Z0-9_]+)'",
        # "Commands: on, off"
        r"(?:commands?|options?)\s*:\s*([a-zA-Z0-9_,\s]+)",
        # Single quoted commands
        r"'([a-zA-Z0-9_]+)'",
    ]

    # Detect command options from help text
    for pattern in command_patterns:
        matches = re.findall(pattern, data, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # Multiple commands in one match
                for cmd in match:
                    cmd = cmd.strip()
                    if cmd and len(cmd) > 0:
                        detected_commands.add(cmd.lower())
            else:
                # Single command
                cmd = match.strip()
                if cmd and len(cmd) > 0:
                    detected_commands.add(cmd.lower())

    # Update global patterns and auto-update Reader controls
    for var_name, info in detected_values.items():
        if var_name not in serial_value_patterns:
            serial_value_patterns[var_name] = info
        else:
            serial_value_patterns[var_name].update(info)

        # Auto-update Reader controls with detected values
        for control in hub_controls:
            if control['type'] == 'reader' and control['name'].lower() == var_name.lower():
                # Update the control value
                update_control_value(control['id'], info['value'])
                # Emit update to frontend
                socketio.emit('hub_control_updated', {'control': {
                    'id': control['id'],
                    'current_value': info['value']
                }})

    # Store detected commands globally
    if not hasattr(analyze_serial_data_for_controls, 'detected_commands'):
        analyze_serial_data_for_controls.detected_commands = set()

    analyze_serial_data_for_controls.detected_commands.update(detected_commands)

    # Clean up old patterns (older than 30 seconds)
    current_time = time.time()
    to_remove = []
    for var_name, info in serial_value_patterns.items():
        if current_time - info.get('last_seen', 0) > 30:
            to_remove.append(var_name)

    for var_name in to_remove:
        del serial_value_patterns[var_name]

    return list(serial_value_patterns.keys())

def create_hub_control(value_name, device_info=None, control_type=None):
    """Create a hub control for a detected value - thread-safe"""
    global hub_controls, deleted_reader_controls, hub_controls_lock, deleted_reader_controls_lock

    # Validate input
    if not value_name or not isinstance(value_name, str):
        return None

    value_name = value_name.strip()
    if not value_name:
        return None

    # Thread-safe check for deleted controls (permanently deleted)
    with deleted_reader_controls_lock:
        value_name_lower = value_name.lower()
        # Check if this control was explicitly deleted by the user
        if value_name_lower in deleted_reader_controls:
            # Control was permanently deleted - don't recreate
            print(f"Control creation skipped for '{value_name}' (reserved or deleted)")
            return None

    # Thread-safe check and creation
    with hub_controls_lock:
        # Check if control already exists
        for control in hub_controls:
            if control['name'] == value_name:
                return control

        # Use provided type or detect control type
        if control_type:
            # Validate control type
            valid_types = ['slider', 'toggle', 'reader']
            if control_type not in valid_types:
                control_type = 'slider'

            # Get base config for the specified type
            control_config = detect_control_type(value_name)
            # Skip if control type is reserved
            if control_config is None:
                return None
            # Override the type
            control_config['type'] = control_type
        else:
            # Detect control type automatically
            control_config = detect_control_type(value_name)
            # Skip if control type is reserved
            if control_config is None:
                return None

        # Generate unique ID
        control_id = f"control_{int(time.time() * 1000)}_{len(hub_controls)}"

        # Create control object
        control = {
            'id': control_id,
            'name': value_name,
            'type': control_config['type'],
            'config': control_config,
            'device': device_info or {'type': 'auto', 'port': 'auto'},
            'created': time.time(),
            'enabled': True
        }

        hub_controls.append(control)
        return control

def update_control_value(control_id, value):
    """Update the value of a control"""
    global control_values
    control_values[control_id] = {
        'value': value,
        'timestamp': time.time()
    }

def get_control_value(control_id):
    """Get the current value of a control"""
    return control_values.get(control_id, {}).get('value')

def send_control_command(control_id, value):
    """Send a control command via serial"""
    global serial_connection, hub_controls

    # Find the control
    control = None
    for c in hub_controls:
        if c['id'] == control_id:
            control = c
            break

    if not control or not serial_connection or not serial_connection.is_open:
        return False

    try:
        # For toggle controls, send the value directly (no template)
        if control['type'] == 'toggle':
            command = str(value)
        else:
            # For sliders and other controls, use command template
            command_template = control['config']['command_template']
            command = command_template.replace('{value}', str(value))

        # Send command
        serial_connection.write((command + '\n').encode('utf-8'))

        # Update control value
        update_control_value(control_id, value)

        return True
    except Exception as e:
        print(f"Error sending control command: {e}")
        return False

def initialize_video_capture():
    """Initialize video capture from webcam - try multiple camera indices"""
    global video_capture

    # Try different camera indices (0, 1, 2, etc.)
    camera_indices = [0, 1, 2, 3, 4]

    for index in camera_indices:
        try:
            print(f"Trying to open camera at index {index}")
            video_capture = cv2.VideoCapture(index)
            if video_capture.isOpened():
                # Test reading a frame to ensure camera works
                ret, test_frame = video_capture.read()
                if ret and test_frame is not None:
                    print(f"Successfully opened camera at index {index}")
                    # Set resolution to 480p (854x480) and 25 FPS
                    video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
                    video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    video_capture.set(cv2.CAP_PROP_FPS, 25)
                    return True
                else:
                    print(f"Camera at index {index} opened but could not read frame")
                    video_capture.release()
            else:
                print(f"Could not open camera at index {index}")
        except Exception as e:
            print(f"Error trying camera at index {index}: {e}")
            continue

    print("No working camera found")
    return False

def check_audio_devices():
    """Check if physical audio input devices are available and actually working"""
    if not PYAUDIO_AVAILABLE:
        print("PyAudio not available - audio features disabled")
        return False, []

    try:
        audio = pyaudio.PyAudio()
        working_devices = []

        for i in range(audio.get_device_count()):
            try:
                device_info = audio.get_device_info_by_index(i)
                device_name = device_info.get('name', 'Unknown').lower()

                # Skip virtual devices that aren't real microphones
                if any(skip_name in device_name for skip_name in ['pipewire', 'pulse', 'null', 'default', 'dummy']):
                    print(f"Skipping virtual device: {device_info.get('name', 'Unknown')} (Index: {i})")
                    continue

                if device_info.get('maxInputChannels') > 0:
                    # Test if device actually works by trying to read data
                    try:
                        test_stream = audio.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=44100,
                            input=True,
                            input_device_index=i,
                            frames_per_buffer=1024
                        )

                        # Try to read a small amount of data to verify device works
                        test_data = test_stream.read(1024, exception_on_overflow=False)
                        test_stream.close()

                        # Check if we got actual audio data (not just silence)
                        if test_data and len(test_data) > 0:
                            # Convert to numpy array to check for actual audio content
                            audio_array = np.frombuffer(test_data, dtype=np.int16)
                            # Check if there's any non-zero audio data (not just silence)
                            if np.any(audio_array != 0):
                                working_devices.append(device_info)
                                print(f"Found working physical audio device: {device_info.get('name', 'Unknown')} (Index: {i})")
                            else:
                                print(f"Device {device_info.get('name', 'Unknown')} (Index: {i}) returned only silence")
                        else:
                            print(f"Device {device_info.get('name', 'Unknown')} (Index: {i}) returned no data")

                    except Exception as e:
                        print(f"Device {device_info.get('name', 'Unknown')} (Index: {i}) not accessible: {e}")
                        continue

            except Exception as e:
                print(f"Error checking device {i}: {e}")
                continue

        audio.terminate()

        if len(working_devices) == 0:
            print("No physical audio input devices found - audio will not be available")

        return len(working_devices) > 0, working_devices
    except Exception as e:
        print(f"Error checking audio devices: {e}")
        return False, []

def initialize_audio_stream():
    """Initialize audio capture"""
    global audio_stream

    if not PYAUDIO_AVAILABLE:
        print("PyAudio not available - cannot initialize audio")
        return False

    # First check if audio devices are available
    devices_available, device_list = check_audio_devices()
    if not devices_available:
        print("No audio input devices found - audio will not be available")
        return False

    try:
        audio = pyaudio.PyAudio()

        # Try to find a working input device
        input_device_index = None
        for device in device_list:
            try:
                # Test if we can open this device
                test_stream = audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    input=True,
                    input_device_index=int(device['index']),
                    frames_per_buffer=1024
                )
                test_stream.close()
                input_device_index = int(device['index'])
                print(f"Found working audio device: {device['name']} at index {input_device_index}")
                break
            except Exception as e:
                print(f"Device {device['name']} not available: {e}")
                continue

        if input_device_index is None:
            print("No working audio input device found")
            audio.terminate()
            return False

        # Use optimized settings for cleaner audio - balance quality vs performance
        SAMPLE_RATE = 44100  # Standard CD quality, more compatible and less bandwidth
        FRAMES_PER_BUFFER = 4096  # Larger buffer (93ms) reduces jitter and network overhead
        audio_stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,  # Consistent sample rate throughout pipeline
            input=True,
            input_device_index=input_device_index,
            frames_per_buffer=FRAMES_PER_BUFFER,  # Larger buffer for better stability
            stream_callback=None  # Use blocking mode for consistent timing
        )
        print(f"Audio stream initialized at {SAMPLE_RATE}Hz with {FRAMES_PER_BUFFER} frame buffer")
        print("Audio stream initialized successfully")
        return True
    except Exception as e:
        print(f"Error initializing audio stream: {e}")
        # Make sure to clean up any partial audio objects
        try:
            if 'audio' in locals():
                audio.terminate()
        except:
            pass
        return False

def initialize_serial_connection(port, baudrate=9600):
    """Initialize serial connection for monitoring"""
    global serial_connection
    try:
        import serial
        serial_connection = serial.Serial(port, baudrate, timeout=1)
        return True
    except Exception as e:
        print(f"Error initializing serial connection: {e}")
        return False

def video_stream_thread():
    """Thread for video streaming - non-blocking with queue"""
    global video_capture, video_streaming_active, video_frame_queue

    if not video_capture or not video_capture.isOpened():
        print("Video capture not available - exiting video thread")
        return

    consecutive_errors = 0
    max_consecutive_errors = 5
    frame_interval = 1.0 / 15.0  # Target 15 FPS for better performance
    last_frame_time = time.time()

    print("Video streaming thread started")

    while video_streaming_active and video_capture and video_capture.isOpened():
        try:
            current_time = time.time()
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.01)  # Small sleep to prevent busy waiting
                continue

            ret, frame = video_capture.read()
            if ret and frame is not None:
                # Encode frame as JPEG with optimized quality
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
                if ret:
                    # Convert to base64 for transmission
                    frame_base64 = base64.b64encode(buffer).decode('utf-8')
                    try:
                        # Use non-blocking queue to avoid blocking on socketio.emit
                        video_frame_queue.put_nowait({'frame': frame_base64})
                        consecutive_errors = 0
                        last_frame_time = current_time
                    except Exception as queue_error:
                        # Queue is full, drop old frame (acceptable for video streaming)
                        try:
                            video_frame_queue.get_nowait()
                            video_frame_queue.put_nowait({'frame': frame_base64})
                        except:
                            pass
                else:
                    consecutive_errors += 1
                    print(f"Failed to encode video frame (#{consecutive_errors})")
            else:
                consecutive_errors += 1
                print(f"Failed to read video frame (#{consecutive_errors})")

            if consecutive_errors >= max_consecutive_errors:
                print("Too many consecutive video errors, stopping video thread")
                video_streaming_active = False
                break

        except Exception as e:
            consecutive_errors += 1
            print(f"Error in video stream (#{consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                print("Too many consecutive video errors, stopping video thread")
                video_streaming_active = False
                break
            time.sleep(0.1)

    print("Video streaming thread stopped")

def audio_stream_thread():
    """Thread for audio streaming - non-blocking with queue"""
    global audio_stream, audio_streaming_active, audio_data_queue
    if not PYAUDIO_AVAILABLE or not audio_stream:
        print("Audio not available - exiting audio thread")
        return

    consecutive_errors = 0
    max_consecutive_errors = 5  # Reduced for faster failure detection
    buffer_size = 4096  # Larger buffer for better stability (matches initialize_audio_stream)
    sample_rate = 44100  # Must match frontend 48000Hz for resampling, but capture at 44100
    frame_duration = buffer_size / sample_rate  # Duration of one buffer in seconds (~93ms)

    print(f"Audio streaming thread started - buffer size: {buffer_size}, sample rate: {sample_rate}Hz, frame duration: {frame_duration*1000:.1f}ms")

    while audio_streaming_active and audio_stream:
        try:
            # Read audio data - this blocks for ~frame_duration naturally
            # No additional sleep needed as read() is blocking
            data = audio_stream.read(buffer_size, exception_on_overflow=False)

            if data and len(data) > 0:
                # Queue audio data non-blocking to avoid socketio.emit lock
                try:
                    audio_data_queue.put_nowait({'audio': data.hex()})
                    consecutive_errors = 0  # Reset error counter on success
                except Exception as queue_error:
                    # Queue full, skip this frame (audio can handle dropped packets)
                    # This prevents delay accumulation from stale buffered frames
                    pass
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print("Audio stream returning empty data, stopping thread")
                    break

        except Exception as e:
            consecutive_errors += 1
            print(f"Error in audio stream (#{consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                print("Too many consecutive audio errors, stopping audio thread")
                audio_streaming_active = False  # Signal to stop
                break
            time.sleep(0.01)  # Small pause on error

    print("Audio streaming thread stopped")

def serial_monitor_thread():
    """Thread for serial monitoring - optimized for performance with proper line buffering"""
    global serial_connection, serial_monitoring_active

    if not serial_connection or not serial_connection.is_open:
        print("Serial connection not available - exiting serial thread")
        return

    consecutive_errors = 0
    max_consecutive_errors = 3
    buffer_size = 1024  # Read larger chunks for efficiency
    line_buffer = ""  # Buffer for incomplete lines

    print("Serial monitoring thread started")

    while serial_monitoring_active and serial_connection and serial_connection.is_open:
        try:
            # Use non-blocking read with timeout - prevent eventlet multiple reader error
            if serial_connection.in_waiting > 0:
                # Read available data in chunks
                data = serial_connection.read(min(serial_connection.in_waiting, buffer_size))
                if data:
                    try:
                        # Decode the data and add to line buffer
                        decoded_data = data.decode('utf-8', errors='ignore')
                        line_buffer += decoded_data

                        # Process complete lines
                        while '\n' in line_buffer:
                            line_end = line_buffer.find('\n')
                            complete_line = line_buffer[:line_end].strip()
                            line_buffer = line_buffer[line_end + 1:]  # Remove processed line

                            # Only emit non-empty lines
                            if complete_line:
                                socketio.emit('serial_data', {'data': complete_line})

                                # Analyze serial data for potential hub controls
                                detected_values = analyze_serial_data_for_controls(complete_line)
                                if detected_values:
                                    # Emit detected controls to frontend
                                    socketio.emit('hub_controls_detected', {'values': detected_values})

                                # Emit detected commands to frontend for dropdown population
                                if hasattr(analyze_serial_data_for_controls, 'detected_commands'):
                                    detected_commands = list(analyze_serial_data_for_controls.detected_commands)
                                    if detected_commands:
                                        socketio.emit('hub_commands_detected', {'commands': detected_commands})

                        consecutive_errors = 0

                    except UnicodeDecodeError:
                        # If decoding fails, emit as hex and clear buffer
                        if line_buffer:
                            socketio.emit('serial_data', {'data': f'[HEX] {line_buffer.encode().hex()}'})
                            line_buffer = ""
                        consecutive_errors = 0
            else:
                # No data available, small sleep to prevent busy waiting
                time.sleep(0.01)  # Increased sleep to prevent eventlet conflicts

        except Exception as e:
            # Filter out eventlet multiple reader errors - don't log them as they spam the console
            error_msg = str(e)
            if "Second simultaneous read" not in error_msg and "multiple_readers" not in error_msg:
                consecutive_errors += 1
                print(f"Error in serial monitor (#{consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    print("Too many consecutive serial errors, stopping serial thread")
                    serial_monitoring_active = False
                    break
            time.sleep(0.1)  # Longer pause on error

    # Send any remaining data in buffer when stopping
    if line_buffer.strip():
        socketio.emit('serial_data', {'data': line_buffer.strip()})

    print("Serial monitoring thread stopped")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
           
def find_usbasp():
    try:
        result=subprocess.run(['lsusb'],capture_output=True, text=True)
        if "16c0:05dc" in result.stdout:
            return True
    except:
        pass
    return False

def detect_avr_chip(port):
    """Detect AVR chip type by trying different signatures"""
    try:
        # Try to read device signature using avrdude
        cmd = ['avrdude', '-c', 'arduino', '-p', 'm328p', '-P', port, '-v']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if 'Device signature' in result.stderr:
            if '0x1e950f' in result.stderr or 'ATmega328P' in result.stderr:
                return 'atmega328p'
            elif '0x1e930a' in result.stderr or 'ATmega328' in result.stderr:
                return 'atmega328'
            elif '0x1e910a' in result.stderr or 'ATtiny85' in result.stderr:
                return 't85'
            elif '0x1e9206' in result.stderr or 'ATmega168' in result.stderr:
                return 'm168'
            elif '0x1e9307' in result.stderr or 'ATmega8' in result.stderr:
                return 'm8'

        # Fallback: try common AVR chips
        for chip in ['atmega328p', 'atmega328', 't85', 'm168', 'm8']:
            cmd = ['avrdude', '-c', 'arduino', '-p', chip, '-P', port, '-v']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if result.returncode == 0 or 'Device signature' in result.stderr:
                return chip

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    return 'atmega328p'  # Default fallback

def detect_avr_chip_usbasp():
    """Detect AVR chip type using USBASP programmer"""
    try:
        # First try to read signature with a common chip to get the actual signature
        cmd = ['avrdude', '-c', 'usbasp', '-p', 'm328p', '-v']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if 'Device signature' in result.stderr:
            signature_line = [line for line in result.stderr.split('\n') if 'Device signature' in line]
            if signature_line:
                signature = signature_line[0].split('=')[1].strip().replace('0x', '').upper()
                # Map signatures to chip types
                signature_map = {
                    '1E950F': 'atmega328p',
                    '1E930A': 'atmega328',
                    '1E910A': 't85',  # ATtiny85
                    '1E9206': 'm168',  # ATmega168
                    '1E9307': 'm8',    # ATmega8
                    '1E9205': 'm8',    # ATmega8A
                }
                return signature_map.get(signature, 'atmega328p')

        # Fallback: try common AVR chips
        for chip in ['atmega328p', 'atmega328', 't85', 'm168', 'm8']:
            cmd = ['avrdude', '-c', 'usbasp', '-p', chip, '-v']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if result.returncode == 0 or 'Device signature' in result.stderr:
                return chip

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    return 'atmega328p'  # Default fallback

def find_devices():
    devices = []
    for port in serial.tools.list_ports.comports():
        if port.vid is not None:
            vid = f"{port.vid:04x}"
            if vid in ARDUINO_IDS:
                chip_type = detect_avr_chip(port.device)
                devices.append(('arduino', port.device, f'AVR ({chip_type})', chip_type))
            elif vid in ESP32_IDS:
                devices.append(('esp32', port.device, 'ESP32', 'esp32'))
    if find_usbasp():
        usbasp_chip_type = detect_avr_chip_usbasp()
        devices.append(('usbasp','N/A', f'AVR ({usbasp_chip_type})', usbasp_chip_type))

    return devices

def find_firmware():
    return [f for f in os.listdir('.') if f.endswith(('.hex', '.bin'))]

def upload_firmware(device_type, port, file_path, chip_type='atmega328p'):
    global terminal_output, upload_in_progress

    upload_in_progress = True
    terminal_output = []
    terminal_output.append(f"Starting upload of {file_path} to {device_type.upper()} ({chip_type}) at {port}")

    # Emit initial progress
    socketio.emit('flash_progress', {'progress': 0, 'status': 'Starting upload...', 'in_progress': True})

    try:
        if device_type == 'arduino':
            cmd = [
                'avrdude',
                '-p', chip_type,
                '-c', 'arduino',
                '-P', port,
                '-U', f'flash:w:{file_path}:i'
            ]
        elif device_type == 'usbasp':
            cmd = [
                'avrdude',
                '-p', chip_type,
                '-c', 'usbasp',
                '-U', f'flash:w:{file_path}:i'
            ]
        elif device_type == 'esp32':
            cmd = [
                "esptool",
                "--chip", "esp32",
                "--port", port,
                "--baud", ESP_BAUD,
                "--after", "hard_reset",
                "write_flash", "-z", "0x10000", file_path
            ]

        terminal_output.append(f"Executing: {' '.join(cmd)}")
        socketio.emit('flash_progress', {'progress': 10, 'status': 'Initializing...', 'in_progress': True})

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Read output line by line and update progress
        progress = 20
        for line in iter(process.stdout.readline, ''):
            terminal_output.append(line.strip())
            print(line.strip())  # Also print to console

            line_lower = line.lower()

            # Update progress based on output - improved detection
            if 'device initialized' in line_lower or 'device signature' in line_lower:
                progress = 25
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Device connected...', 'in_progress': True})
            elif 'erasing chip' in line_lower:
                progress = 35
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Erasing chip...', 'in_progress': True})
            elif 'reading input file' in line_lower:
                progress = 45
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Reading firmware...', 'in_progress': True})
            elif 'writing' in line_lower and ('flash' in line_lower or 'bytes' in line_lower):
                progress = 60
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Writing firmware...', 'in_progress': True})
            elif 'writing |' in line_lower and '100%' in line_lower:
                progress = 75
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Writing complete...', 'in_progress': True})
            elif 'verifying' in line_lower:
                progress = 85
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Verifying firmware...', 'in_progress': True})
            elif 'reading |' in line_lower and '100%' in line_lower:
                progress = 95
                socketio.emit('flash_progress', {'progress': progress, 'status': 'Verification complete...', 'in_progress': True})

        process.wait()

        # Check return code and provide detailed error messages
        if process.returncode != 0:
            error_lines = [line for line in terminal_output if 'error' in line.lower() or 'failed' in line.lower() or 'not found' in line.lower()]
            if error_lines:
                error_msg = error_lines[-1]  # Get the last error
            else:
                error_msg = f"Flashing failed with return code {process.returncode}"
            socketio.emit('flash_progress', {'progress': 0, 'status': f'Error: {error_msg}', 'in_progress': False})
            return False

        if process.returncode == 0:
            terminal_output.append("✅ Upload successful!")
            socketio.emit('flash_progress', {'progress': 100, 'status': 'Upload successful!', 'in_progress': False})
            return True
        else:
            terminal_output.append("❌ Upload failed!")
            socketio.emit('flash_progress', {'progress': 0, 'status': 'Upload failed!', 'in_progress': False})
            return False

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        terminal_output.append(error_msg)
        socketio.emit('flash_progress', {'progress': 0, 'status': f'Error: {str(e)}', 'in_progress': False})
        return False
    finally:
        upload_in_progress = False

# SocketIO event handlers
def init_video_in_background():
     """Initialize video in background thread to avoid blocking socket event loop"""
     global video_streaming_active, video_capture, video_init_in_progress, streaming_state_lock
     try:
         print("Initializing video capture in background...")
         with streaming_state_lock:
             if video_init_in_progress:
                 print("Video initialization already in progress, skipping")
                 return
             video_init_in_progress = True
         
         if initialize_video_capture():
             print("Video capture initialized successfully, starting thread")
             with streaming_state_lock:
                 video_streaming_active = True
             video_thread = threading.Thread(target=video_stream_thread)
             video_thread.daemon = True
             video_thread.start()
             # Start dispatcher thread if not already running
             start_media_dispatcher()
             socketio.emit('streaming_status', {'type': 'video', 'status': 'started'})
         else:
             print("Failed to initialize video capture")
             socketio.emit('streaming_status', {'type': 'video', 'status': 'error', 'message': 'Could not initialize camera'})
     except Exception as e:
         print(f"Error in video initialization: {e}")
         socketio.emit('streaming_status', {'type': 'video', 'status': 'error', 'message': str(e)})
     finally:
         with streaming_state_lock:
             video_init_in_progress = False

def init_audio_in_background():
    """Initialize audio in background thread to avoid blocking socket event loop"""
    global audio_streaming_active, audio_stream, audio_init_in_progress, streaming_state_lock
    try:
        print("Initializing audio capture in background...")
        with streaming_state_lock:
            if audio_init_in_progress:
                print("Audio initialization already in progress, skipping")
                return
            audio_init_in_progress = True
        
        if initialize_audio_stream():
            print("Audio stream initialized successfully, starting thread")
            with streaming_state_lock:
                audio_streaming_active = True
            audio_thread = threading.Thread(target=audio_stream_thread)
            audio_thread.daemon = True
            audio_thread.start()
            # Start dispatcher thread if not already running
            start_media_dispatcher()
            socketio.emit('streaming_status', {'type': 'audio', 'status': 'started'})
        else:
            socketio.emit('streaming_status', {'type': 'audio', 'status': 'error', 'message': 'Could not initialize audio - no microphone detected'})
    except Exception as e:
        print(f"Error in audio initialization: {e}")
        socketio.emit('streaming_status', {'type': 'audio', 'status': 'error', 'message': str(e)})
    finally:
        with streaming_state_lock:
            audio_init_in_progress = False

@socketio.on('start_streaming')
def handle_start_streaming(data):
    global video_streaming_active, audio_streaming_active, video_capture, audio_stream
    print(f"Received start_streaming request: {data}")
    try:
        # Handle video streaming
        video_requested = data.get('video', False)
        if video_requested and not video_capture:
            # Start video in background thread to avoid blocking socket event loop
            init_thread = threading.Thread(target=init_video_in_background)
            init_thread.daemon = True
            init_thread.start()
        elif not video_requested and video_capture:
            # Stop video
            print("Stopping video capture...")
            video_streaming_active = False
            if video_capture:
                try:
                    video_capture.release()
                except Exception as e:
                    print(f"Error stopping video stream: {e}")
                video_capture = None
            emit('streaming_status', {'type': 'video', 'status': 'stopped'})

        # Handle audio streaming
        audio_requested = data.get('audio', False)
        if audio_requested and not audio_stream:
            # Start audio in background thread to avoid blocking socket event loop
            init_thread = threading.Thread(target=init_audio_in_background)
            init_thread.daemon = True
            init_thread.start()
        elif not audio_requested and audio_stream:
            # Stop audio
            print("Stopping audio capture...")
            audio_streaming_active = False
            if PYAUDIO_AVAILABLE and audio_stream:
                try:
                    audio_stream.stop_stream()
                    audio_stream.close()
                except Exception as e:
                    print(f"Error stopping audio stream: {e}")
                audio_stream = None
            emit('streaming_status', {'type': 'audio', 'status': 'stopped'})

    except Exception as e:
        emit('streaming_status', {'type': 'error', 'message': str(e)})

@socketio.on('stop_streaming')
def handle_stop_streaming():
    global video_streaming_active, audio_streaming_active, video_capture, audio_stream
    video_streaming_active = False
    audio_streaming_active = False

    # Clean up video
    if video_capture:
        try:
            video_capture.release()
        except Exception as e:
            print(f"Error stopping video stream: {e}")
        video_capture = None

    # Clean up audio
    if PYAUDIO_AVAILABLE and audio_stream:
        try:
            audio_stream.stop_stream()
            audio_stream.close()
        except Exception as e:
            print(f"Error stopping audio stream: {e}")
        audio_stream = None

    # NOTE: Serial monitor is NOT stopped by "Stop All" - only by serial monitor controls
    # This prevents accidentally disconnecting serial connections when stopping video/audio

    emit('streaming_status', {'type': 'all', 'status': 'stopped'})

@socketio.on('start_serial_monitor')
def handle_start_serial_monitor(data):
    global serial_monitoring_active, serial_connection, hub_controls, serial_value_patterns, deleted_reader_controls
    try:
        port = data.get('port')
        baudrate = data.get('baudrate', 9600)

        if not port:
            emit('serial_status', {'status': 'error', 'message': 'No port specified'})
            return

        if initialize_serial_connection(port, baudrate):
            # Clear existing hub controls and patterns when starting serial monitor
            # This ensures fresh detection of controls from the new firmware
            hub_controls.clear()
            serial_value_patterns.clear()
            deleted_reader_controls.clear()  # Reset deleted controls list for fresh firmware
            # Clear detected commands
            if hasattr(analyze_serial_data_for_controls, 'detected_commands'):
                analyze_serial_data_for_controls.detected_commands.clear()

            # Notify frontend to clear existing controls
            emit('hub_controls_cleared')

            serial_monitoring_active = True
            serial_thread = threading.Thread(target=serial_monitor_thread)
            serial_thread.daemon = True
            serial_thread.start()
            emit('serial_status', {'status': 'started', 'port': port, 'baudrate': baudrate})
        else:
            emit('serial_status', {'status': 'error', 'message': 'Could not open serial port'})

    except Exception as e:
        emit('serial_status', {'status': 'error', 'message': str(e)})

@socketio.on('stop_serial_monitor')
def handle_stop_serial_monitor():
    global serial_monitoring_active, serial_connection
    serial_monitoring_active = False

    if serial_connection and serial_connection.is_open:
        try:
            serial_connection.close()
        except Exception as e:
            print(f"Error closing serial connection: {e}")
        serial_connection = None

    # Stop serial plot if it's running
    emit('stop_serial_plot', {})
    
    emit('serial_status', {'status': 'stopped'})

@socketio.on('send_serial_data')
def handle_send_serial_data(data):
    global serial_connection
    try:
        if serial_connection and serial_connection.is_open:
            message = data.get('data', '')
            if message:
                serial_connection.write((message + '\n').encode('utf-8'))
                emit('serial_sent', {'data': message})
    except Exception as e:
        emit('serial_status', {'status': 'error', 'message': str(e)})

# Hub Controls SocketIO handlers
@socketio.on('create_hub_control')
def handle_create_hub_control(data):
    try:
        value_name = data.get('name')
        if not value_name or not isinstance(value_name, str):
            emit('hub_control_error', {'message': 'Control name is required and must be a string'})
            return

        value_name = value_name.strip()
        if not value_name:
            emit('hub_control_error', {'message': 'Control name cannot be empty'})
            return

        control_type = data.get('type', 'slider')  # Default to slider if not specified
        device_info = data.get('device', {'type': 'auto', 'port': 'auto'})

        # Validate control type
        if not isinstance(control_type, str) or control_type not in ['slider', 'toggle', 'reader']:
            control_type = 'slider'

        # Validate device info
        if not isinstance(device_info, dict):
            device_info = {'type': 'auto', 'port': 'auto'}

        control = create_hub_control(value_name, device_info, control_type)

        if control is None:
            # Control creation returned None - could be due to reserved keywords or deleted control
            # Don't emit error for auto-creation attempts to avoid spam
            print(f"Control creation skipped for '{value_name}' (reserved or deleted)")
            return

        emit('hub_control_created', {'control': control})
    except Exception as e:
        print(f"Error creating hub control: {e}")
        emit('hub_control_error', {'message': f'Failed to create control: {str(e)}'})

@socketio.on('update_hub_control')
def handle_update_hub_control(data):
    global hub_controls
    try:
        control_id = data.get('id')
        if not control_id:
            emit('hub_control_error', {'message': 'Control ID is required'})
            return

        # Find and update the control
        for control in hub_controls:
            if control['id'] == control_id:
                if 'config' in data:
                    control['config'].update(data['config'])
                if 'device' in data:
                    control['device'].update(data['device'])
                if 'enabled' in data:
                    control['enabled'] = data['enabled']

                emit('hub_control_updated', {'control': control})
                return

        emit('hub_control_error', {'message': 'Control not found'})
    except Exception as e:
        emit('hub_control_error', {'message': str(e)})

@socketio.on('delete_hub_control')
def handle_delete_hub_control(data):
    global hub_controls, control_values, deleted_reader_controls, hub_controls_lock, deleted_reader_controls_lock
    try:
        control_id = data.get('id')
        if not control_id:
            emit('hub_control_error', {'message': 'Control ID is required'})
            return

        # Validate control_id format
        if not isinstance(control_id, str) or not control_id.strip():
            emit('hub_control_error', {'message': 'Invalid control ID format'})
            return

        control_id = control_id.strip()

        # Thread-safe deletion
        with hub_controls_lock:
            # Find and remove the control
            for i, control in enumerate(hub_controls):
                if control['id'] == control_id:
                    deleted_control = hub_controls.pop(i)
                    # Clean up control values
                    if control_id in control_values:
                        del control_values[control_id]
                    
                    # If this is a reader control, track it to prevent auto-recreation
                    if deleted_control.get('type') == 'reader':
                        with deleted_reader_controls_lock:
                            deleted_reader_controls.add(deleted_control['name'].lower())
                        print(f"Marked reader control '{deleted_control['name']}' as permanently deleted")

                    emit('hub_control_deleted', {'control': deleted_control})
                    return

        # Control not found - this is not necessarily an error since controls might be deleted from other sessions
        print(f"Control {control_id} not found for deletion (might already be deleted)")
        emit('hub_control_deleted', {'control': {'id': control_id}})  # Still emit success for UI consistency
    except Exception as e:
        print(f"Error deleting hub control {data.get('id', 'unknown')}: {e}")
        emit('hub_control_error', {'message': f'Failed to delete control: {str(e)}'})

@socketio.on('send_control_command')
def handle_send_control_command(data):
    try:
        control_id = data.get('id')
        value = data.get('value')

        if not control_id:
            emit('hub_control_error', {'message': 'Control ID is required'})
            return

        success = send_control_command(control_id, value)

        if success:
            emit('control_command_sent', {'id': control_id, 'value': value})
        else:
            emit('hub_control_error', {'message': 'Failed to send command'})
    except Exception as e:
        emit('hub_control_error', {'message': str(e)})

@socketio.on('connect')
def handle_client_connect():
    """Handle new client connection"""
    print("Client connected")

@socketio.on('disconnect')
def handle_client_disconnect():
    """Clean up all resources when client disconnects (e.g., page reload)"""
    print("Client disconnected - cleaning up all resources")
    cleanup_all_resources()
    print("Resource cleanup completed")

@app.route('/')
def index():
     devices = find_devices()
     firmware = find_firmware()
     return render_template('remotelab.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    global upload_in_progress

    if upload_in_progress:
        return jsonify({'error': 'Upload already in progress'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'firmware.hex')
        file.save(file_path)

        return jsonify({'message': 'File uploaded successfully', 'filename': 'firmware.hex'}), 200

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/validate-firmware', methods=['POST'])
def validate_firmware_endpoint():
    """Validate firmware against pin usage rules before flashing"""
    try:
        chip_type = request.form.get('chip_type')
        
        if not chip_type:
            return jsonify({'error': 'Chip type is required'}), 400
        
        firmware_file = 'firmware.hex'
        if not os.path.exists(firmware_file):
            return jsonify({'error': 'No firmware file uploaded'}), 400
        
        # Create fresh validator instance to ensure config is reloaded
        validator = FirmwareValidator()
        
        # Run validation
        passed, message, violations = validator.validate_firmware(firmware_file, chip_type)
        
        return jsonify({
            'passed': passed,
            'message': message,
            'violations': violations
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-chips', methods=['GET'])
def get_available_chips():
    """Get list of available chip types with their configurations"""
    try:
        validator = FirmwareValidator()
        chips = validator.list_available_chips()
        return jsonify({'chips': chips}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-chip-rules/<chip_type>', methods=['GET'])
def get_chip_rules(chip_type):
    """Get pin restriction rules for a specific chip"""
    try:
        validator = FirmwareValidator()
        chip_info = validator.get_chip_info(chip_type)
        if chip_info:
            return jsonify(chip_info), 200
        else:
            return jsonify({'error': f'Chip type {chip_type} not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/flash', methods=['POST'])
def flash_firmware():
    global upload_in_progress

    if upload_in_progress:
        return jsonify({'error': 'Upload already in progress'}), 400

    device_type = request.form.get('device_type')
    port = request.form.get('port')

    if not device_type or not port:
        return jsonify({'error': 'Device type and port are required'}), 400

    # Get chip type from selected device
    devices = find_devices()
    chip_type = None
    for dev_type, dev_port, dev_name, dev_chip in devices:
        if dev_type == device_type and dev_port == port:
            chip_type = dev_chip
            break

    if not chip_type:
        return jsonify({'error': 'Selected device not found or chip type could not be determined'}), 400

    firmware_file = 'firmware.hex'
    if not os.path.exists(firmware_file):
        return jsonify({'error': 'No firmware file uploaded. Please upload a firmware file first.'}), 400

    # Check if file has content
    try:
        file_size = os.path.getsize(firmware_file)
        if file_size == 0:
            return jsonify({'error': 'Firmware file is empty. Please upload a valid firmware file.'}), 400
    except OSError:
        return jsonify({'error': 'Cannot access firmware file. Please re-upload.'}), 400

    # Validate device and chip type compatibility
    if device_type == 'arduino' and chip_type.startswith('t'):
        return jsonify({'error': f'Cannot upload {chip_type} firmware to Arduino device. Please select the correct device type or use a compatible programmer.'}), 400
    elif device_type == 'esp32' and not chip_type.startswith('esp'):
        return jsonify({'error': f'Cannot upload {chip_type} firmware to ESP32 device. Please select the correct device type.'}), 400

    # Start upload in background thread
    thread = threading.Thread(target=upload_firmware, args=(device_type, port, firmware_file, chip_type))
    thread.daemon = True
    thread.start()

    return jsonify({'message': 'Upload started'}), 200

@app.route('/terminal')
def get_terminal():
    return jsonify({'output': terminal_output, 'in_progress': upload_in_progress})

@app.route('/devices')
def get_devices():
    devices = find_devices()
    return jsonify({'devices': devices})

@app.route('/network')
def get_network_info():
    """Get current network information"""
    try:
        hostname = socket.gethostname()
        # Get IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to Google DNS to get local IP
        ip_address = s.getsockname()[0]
        s.close()

        return jsonify({
            'hostname': hostname,
            'ip_address': ip_address,
            'url_local': f'http://{ip_address}:5000',
            'url_hostname': f'http://{hostname}.local:5000'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def cleanup_all_resources():
    """Clean up all active resources (video, audio, serial, logic analyzer)"""
    global video_streaming_active, audio_streaming_active, serial_monitoring_active
    global video_capture, audio_stream, serial_connection
    
    # Stop video streaming
    if video_streaming_active or video_capture:
        video_streaming_active = False
        if video_capture:
            try:
                video_capture.release()
            except Exception as e:
                print(f"Error stopping video stream: {e}")
            video_capture = None
    
    # Stop audio streaming
    if audio_streaming_active or audio_stream:
        audio_streaming_active = False
        if PYAUDIO_AVAILABLE and audio_stream:
            try:
                audio_stream.stop_stream()
                audio_stream.close()
            except Exception as e:
                print(f"Error stopping audio stream: {e}")
            audio_stream = None
    
    # Stop serial monitoring and plot
    if serial_monitoring_active or serial_connection:
        serial_monitoring_active = False
        if serial_connection and serial_connection.is_open:
            try:
                serial_connection.close()
            except Exception as e:
                print(f"Error closing serial connection: {e}")
            serial_connection = None
        # Notify frontend to stop serial plot
        try:
            socketio.emit('stop_serial_plot', {})
        except Exception as e:
            print(f"Error emitting stop_serial_plot: {e}")
    
    # Stop logic analyzer if running
    try:
        if logic_analyzer_manager:
            logic_analyzer_manager.stop_acquisition()
    except Exception as e:
        print(f"Error stopping logic analyzer: {e}")

def initialize_logic_analyzer():
    """Initialize logic analyzer manager after app is created"""
    global logic_analyzer_manager
    if logic_analyzer_manager is None:
        logic_analyzer_manager = init_logic_analyzer_manager(socketio)

# Initialize logic analyzer after app creation
initialize_logic_analyzer()

# Logic Analyzer Routes
@app.route('/logic/start', methods=['POST'])
def start_logic_analyzer():
    """Start logic analyzer acquisition"""
    try:
        success, message = logic_analyzer_manager.start_acquisition()
        if success:
            return jsonify({'status': 'started', 'message': message}), 200
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/logic/stop', methods=['POST'])
def stop_logic_analyzer():
    """Stop logic analyzer acquisition"""
    try:
        success, message = logic_analyzer_manager.stop_acquisition()
        if success:
            return jsonify({'status': 'stopped', 'message': message}), 200
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/logic/status')
def get_logic_status():
    """Get logic analyzer status"""
    try:
        status = logic_analyzer_manager.get_status()
        return jsonify(status), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/config', methods=['POST'])
def configure_logic_analyzer():
    """Configure logic analyzer parameters"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400

        # Update configuration parameters
        if 'sampling_rate' in data:
            logic_analyzer_manager.set_sampling_rate(data['sampling_rate'])
        if 'channel_mode' in data:
            logic_analyzer_manager.set_channel_mode(data['channel_mode'])
        if 'timebase' in data:
            logic_analyzer_manager.set_timebase(data['timebase'])
        if 'amplitude_scale' in data:
            logic_analyzer_manager.set_amplitude_scale(data['amplitude_scale'])

        return jsonify({'status': 'configured'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/clear', methods=['POST'])
def clear_logic_analyzer():
    """Clear logic analyzer data buffers"""
    try:
        # Stop acquisition if running
        logic_analyzer_manager.stop_acquisition()

        # Clear buffers
        with logic_analyzer_manager.buffer_lock:
            logic_analyzer_manager.ch1_diff_buffer.clear()
            logic_analyzer_manager.ch2_diff_buffer.clear()
            logic_analyzer_manager.timestamp_buffer.clear()

        return jsonify({'status': 'cleared'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/config', methods=['POST'])
def configure_trigger():
    """Configure logic analyzer trigger settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400

        enabled = data.get('enabled', False)
        channel = data.get('channel', 'ch1')
        edge = data.get('edge', 'rising')
        level = data.get('level', 0)

        success = logic_analyzer_manager.set_trigger_config(enabled, channel, edge, level)
        
        if success:
            status = logic_analyzer_manager.get_status()
            return jsonify({
                'status': 'configured',
                'trigger_config': {
                    'enabled': logic_analyzer_manager.trigger_enabled,
                    'channel': logic_analyzer_manager.trigger_channel,
                    'edge': logic_analyzer_manager.trigger_edge,
                    'level': logic_analyzer_manager.trigger_level,
                    'armed': logic_analyzer_manager.trigger_armed,
                    'captured': logic_analyzer_manager.trigger_captured
                }
            }), 200
        else:
            return jsonify({'error': 'Failed to configure trigger'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/arm', methods=['POST'])
def arm_trigger():
    """Arm the trigger to wait for the next trigger event"""
    try:
        logic_analyzer_manager.arm_trigger()
        return jsonify({
            'status': 'armed',
            'trigger_armed': logic_analyzer_manager.trigger_armed,
            'trigger_captured': logic_analyzer_manager.trigger_captured
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/disarm', methods=['POST'])
def disarm_trigger():
    """Disarm the trigger"""
    try:
        logic_analyzer_manager.disarm_trigger()
        return jsonify({
            'status': 'disarmed',
            'trigger_armed': logic_analyzer_manager.trigger_armed
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/status', methods=['GET'])
def get_trigger_status():
    """Get trigger status"""
    try:
        return jsonify({
            'trigger_enabled': logic_analyzer_manager.trigger_enabled,
            'trigger_armed': logic_analyzer_manager.trigger_armed,
            'trigger_captured': logic_analyzer_manager.trigger_captured,
            'trigger_channel': logic_analyzer_manager.trigger_channel,
            'trigger_edge': logic_analyzer_manager.trigger_edge,
            'trigger_level': logic_analyzer_manager.trigger_level
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/enable', methods=['POST'])
def enable_trigger():
    """Enable trigger mode and auto-arm for next pulse"""
    try:
        data = request.get_json() or {}
        channel = data.get('channel', 'ch1')
        edge = data.get('edge', 'rising')
        
        # Configure and enable trigger
        logic_analyzer_manager.set_trigger_config(True, channel, edge)
        # Auto-arm to wait for first pulse
        logic_analyzer_manager.arm_trigger()
        
        return jsonify({
            'status': 'trigger_enabled',
            'trigger_armed': logic_analyzer_manager.trigger_armed,
            'message': f'Trigger enabled - waiting for {edge} edge on {channel}'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logic/trigger/disable', methods=['POST'])
def disable_trigger():
    """Disable trigger mode and switch to continuous capture"""
    try:
        logic_analyzer_manager.trigger_enabled = False
        logic_analyzer_manager.trigger_armed = False
        logic_analyzer_manager.trigger_captured = False
        logic_analyzer_manager.trigger_displayed = False
        
        # Clear buffers to start fresh continuous capture
        with logic_analyzer_manager.buffer_lock:
            logic_analyzer_manager.ch1_diff_buffer.clear()
            logic_analyzer_manager.ch2_diff_buffer.clear()
            logic_analyzer_manager.timestamp_buffer.clear()
        
        return jsonify({
            'status': 'trigger_disabled',
            'message': 'Switched to continuous capture mode'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Hub Controls Routes
@app.route('/hub/controls')
def get_hub_controls():
    """Get all hub controls"""
    global hub_controls, control_values
    controls_data = []
    for control in hub_controls:
        control_data = control.copy()
        control_data['current_value'] = get_control_value(control['id'])
        controls_data.append(control_data)

    return jsonify({'controls': controls_data})

@app.route('/hub/controls', methods=['POST'])
def create_hub_control_route():
    """Create a new hub control"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No control data provided'}), 400

        value_name = data.get('name')
        if not value_name:
            return jsonify({'error': 'Control name is required'}), 400

        device_info = data.get('device', {'type': 'auto', 'port': 'auto'})

        control = create_hub_control(value_name, device_info)
        return jsonify({'control': control}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hub/controls/<control_id>', methods=['PUT'])
def update_hub_control(control_id):
    """Update a hub control configuration"""
    global hub_controls
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No update data provided'}), 400

        # Find and update the control
        for control in hub_controls:
            if control['id'] == control_id:
                # Update allowed fields
                if 'config' in data:
                    control['config'].update(data['config'])
                if 'device' in data:
                    control['device'].update(data['device'])
                if 'enabled' in data:
                    control['enabled'] = data['enabled']

                return jsonify({'control': control}), 200

        return jsonify({'error': 'Control not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hub/controls/<control_id>', methods=['DELETE'])
def delete_hub_control(control_id):
    """Delete a hub control"""
    global hub_controls, control_values
    try:
        # Find and remove the control
        for i, control in enumerate(hub_controls):
            if control['id'] == control_id:
                deleted_control = hub_controls.pop(i)
                # Clean up control values
                if control_id in control_values:
                    del control_values[control_id]
                return jsonify({'message': 'Control deleted', 'control': deleted_control}), 200

        return jsonify({'error': 'Control not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hub/controls/<control_id>/send', methods=['POST'])
def send_control_command_endpoint(control_id):
    """Send a control command"""
    try:
        data = request.get_json()
        if not data or 'value' not in data:
            return jsonify({'error': 'Value is required'}), 400

        value = data['value']
        success = send_control_command(control_id, value)

        if success:
            return jsonify({'message': 'Command sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send command'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hub/detect', methods=['POST'])
def detect_hub_controls():
    """Manually trigger control detection from current serial data"""
    global serial_value_patterns, hub_controls

    try:
        detected_values = list(serial_value_patterns.keys())

        # Auto-create controls for detected values
        new_controls = []
        for value_name in detected_values:
            control = create_hub_control(value_name)
            if control:  # Only add if control was created (not None)
                new_controls.append(control)

        return jsonify({
            'detected_values': detected_values,
            'new_controls': new_controls,
            'total_controls': len(hub_controls)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



dispatcher_thread_running = False
dispatcher_lock = threading.Lock()

def start_media_dispatcher():
    """Start the media dispatcher thread if not already running"""
    global dispatcher_thread_running, dispatcher_lock
    
    with dispatcher_lock:
        if not dispatcher_thread_running:
            dispatcher_thread_running = True
            dispatcher = threading.Thread(target=media_dispatcher_thread)
            dispatcher.daemon = True
            dispatcher.start()

def media_dispatcher_thread():
    """Thread to dispatch queued video/audio data without blocking capture threads"""
    global video_frame_queue, audio_data_queue, video_streaming_active, audio_streaming_active, dispatcher_thread_running
    
    print("Media dispatcher thread started")
    
    try:
        while video_streaming_active or audio_streaming_active:
            try:
                # Emit queued video frames
                while not video_frame_queue.empty() and video_streaming_active:
                    try:
                        frame_data = video_frame_queue.get_nowait()
                        socketio.emit('video_frame', frame_data)
                    except:
                        break
                
                # Emit queued audio data - drain all queued frames to prevent accumulation
                frames_emitted = 0
                while not audio_data_queue.empty() and audio_streaming_active:
                    try:
                        audio_data = audio_data_queue.get_nowait()
                        socketio.emit('audio_data', audio_data)
                        frames_emitted += 1
                    except:
                        break
                
                # Log if queue is backing up (indicates frontend can't keep pace)
                if audio_data_queue.qsize() > 5:
                    print(f"⚠️ Audio queue backing up: {audio_data_queue.qsize()} frames queued")
                
                # Small sleep to prevent busy waiting
                time.sleep(0.001)
                
            except Exception as e:
                print(f"Error in media dispatcher: {e}")
                time.sleep(0.01)
    finally:
        dispatcher_thread_running = False
        print("Media dispatcher thread stopped")

def print_network_info():
    """Print network information on startup"""
    try:
        hostname = socket.gethostname()
        # Get IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to Google DNS to get local IP
        ip_address = s.getsockname()[0]
        s.close()

        print("🌐 Network Information:")
        print(f"   Hostname: {hostname}")
        print(f"   IP Address: {ip_address}")
        print(f"   Local Access: http://{ip_address}:5000")
        print(f"   Hostname Access: http://{hostname}.local:5000")
        print("   (Use hostname access when IP changes with different WiFi)")
        print("")
    except Exception as e:
        print(f"Could not determine network info: {e}")

if __name__ == '__main__':
    print_network_info()
    # Check if we're in production (systemd service)
    is_production = os.environ.get('FLASK_ENV') == 'production'
    print(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
    print(f"Is production: {is_production}")

    if is_production:
        print("Starting in PRODUCTION mode with eventlet...")
        # Production: Use eventlet for SocketIO support
        import eventlet
        eventlet.monkey_patch()
        socketio.run(app, host='0.0.0.0', port=5000)
    else:
        print("Starting in DEVELOPMENT mode...")
        # In development, use debug mode
        socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

# For Gunicorn deployment (WSGI application for HTTP requests only)
# Note: WebSocket/SocketIO connections require eventlet worker class
application = app  # Use Flask app directly for Gunicorn
