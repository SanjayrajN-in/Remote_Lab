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

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '.'
app.config['ALLOWED_EXTENSIONS'] = {'hex', 'bin'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize logic analyzer (moved after socketio initialization)
logic_analyzer_manager = None

# Global variables for video and audio streaming
video_capture = None
audio_stream = None
serial_connection = None
video_streaming_active = False
audio_streaming_active = False
serial_monitoring_active = False

# Device configurations
ARDUINO_IDS = {'2341', '2a03', '1a86'}
ESP32_IDS = {'10c4', '303a'}
USBASP_IDS={'16c0:05dc'}
ESP_BAUD = "460800"

# Global variables for terminal output
terminal_output = []
upload_in_progress = False

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

        # Use optimized settings for cleaner audio - ensure consistent sample rate
        SAMPLE_RATE = 48000  # Use 48kHz for better quality and compatibility
        audio_stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,  # Consistent sample rate throughout pipeline
            input=True,
            input_device_index=input_device_index,
            frames_per_buffer=2048  # Larger buffer for better stability
        )
        print(f"Audio stream initialized at {SAMPLE_RATE}Hz")
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
    """Thread for video streaming - optimized for performance"""
    global video_capture, video_streaming_active

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
                    socketio.emit('video_frame', {'frame': frame_base64})
                    consecutive_errors = 0
                    last_frame_time = current_time
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
    """Thread for audio streaming - optimized for performance"""
    global audio_stream, audio_streaming_active
    if not PYAUDIO_AVAILABLE or not audio_stream:
        print("Audio not available - exiting audio thread")
        return

    consecutive_errors = 0
    max_consecutive_errors = 5  # Reduced for faster failure detection
    buffer_size = 2048  # Match the configured buffer size

    print("Audio streaming thread started")

    while audio_streaming_active and audio_stream:
        try:
            # Read audio data with timeout to prevent blocking
            data = audio_stream.read(buffer_size, exception_on_overflow=False)

            if data and len(data) > 0:
                # Send raw binary data as hex to reduce processing overhead
                socketio.emit('audio_data', {'audio': data.hex()})
                consecutive_errors = 0  # Reset error counter on success
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print("Audio stream returning empty data, stopping thread")
                    break

            # Optimized sleep timing for 48kHz audio (2048 samples = ~42.7ms)
            # Sleep for slightly less than the buffer duration to maintain sync
            time.sleep(0.040)  # ~40ms sleep for smooth streaming

        except Exception as e:
            consecutive_errors += 1
            print(f"Error in audio stream (#{consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                print("Too many consecutive audio errors, stopping audio thread")
                audio_streaming_active = False  # Signal to stop
                break
            time.sleep(0.1)  # Longer pause on error

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
@socketio.on('start_streaming')
def handle_start_streaming(data):
    global video_streaming_active, audio_streaming_active, video_capture, audio_stream
    print(f"Received start_streaming request: {data}")
    try:
        # Handle video streaming
        video_requested = data.get('video', False)
        if video_requested and not video_capture:
            # Start video
            print("Initializing video capture...")
            if initialize_video_capture():
                print("Video capture initialized successfully, starting thread")
                video_streaming_active = True
                video_thread = threading.Thread(target=video_stream_thread)
                video_thread.daemon = True
                video_thread.start()
                print("Emitting video started status")
                emit('streaming_status', {'type': 'video', 'status': 'started'})
            else:
                print("Failed to initialize video capture")
                emit('streaming_status', {'type': 'video', 'status': 'error', 'message': 'Could not initialize camera'})
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
            # Start audio
            if initialize_audio_stream():
                audio_streaming_active = True
                audio_thread = threading.Thread(target=audio_stream_thread)
                audio_thread.daemon = True
                audio_thread.start()
                emit('streaming_status', {'type': 'audio', 'status': 'started'})
            else:
                # Audio failed but don't affect other streams
                emit('streaming_status', {'type': 'audio', 'status': 'error', 'message': 'Could not initialize audio - no microphone detected'})
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
    global serial_monitoring_active, serial_connection
    try:
        port = data.get('port')
        baudrate = data.get('baudrate', 9600)

        if not port:
            emit('serial_status', {'status': 'error', 'message': 'No port specified'})
            return

        if initialize_serial_connection(port, baudrate):
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

@app.route('/')
def index():
    devices = find_devices()
    firmware = find_firmware()
    return send_from_directory('page', 'remotelab.html')

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
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'firmware')
        file.save(file_path)

        return jsonify({'message': 'File uploaded successfully', 'filename': 'firmware'}), 200

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/flash', methods=['POST'])
def flash_firmware():
    global upload_in_progress

    if upload_in_progress:
        return jsonify({'error': 'Upload already in progress'}), 400

    device_type = request.form.get('device_type')
    port = request.form.get('port')
    chip_type = request.form.get('chip_type', 'atmega328p')  # Default fallback

    if not device_type or not port:
        return jsonify({'error': 'Device type and port are required'}), 400

    firmware_file = 'firmware'
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
