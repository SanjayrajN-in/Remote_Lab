"""
HTTP Video Streamer Module
Handles MJPEG video streaming via HTTP endpoints
Separated from main app.py for better modularity and robustness
"""

import cv2
import time
import threading
import logging
import gc

# Configure logging
logger = logging.getLogger(__name__)

class HTTPVideoStreamer:
    """Manages HTTP MJPEG video streaming"""
    
    def __init__(self):
        self.video_capture = None
        self.streaming_active = False
        self.frame_buffer = None
        self.buffer_lock = threading.Lock()
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.target_fps = 25  # Single encoding shared across all clients
        self.frame_interval = 1.0 / self.target_fps
        self.last_frame_time = time.time()
        self.encoded_frame_buffer = None  # Pre-encoded frame shared across clients
        self.frame_ready_event = threading.Event()  # Signal when new frame is ready
        self.capture_thread = None  # Reference to capture thread
        self.active_clients = 0  # Track number of active stream readers
        self.clients_lock = threading.Lock()  # Lock for client counter
        
    def initialize_camera(self, camera_indices=[0, 1, 2, 3, 4]):
        """
        Initialize video capture from webcam
        Try multiple camera indices if needed
        """
        logger.info(f"Attempting to initialize camera from indices: {camera_indices}")
        
        for index in camera_indices:
            try:
                cap = cv2.VideoCapture(index)
                if not cap.isOpened():
                    logger.warning(f"Camera at index {index} cannot be opened")
                    continue
                
                # Add delay for camera to stabilize
                time.sleep(0.2)
                
                # Test reading a frame - try multiple times
                for attempt in range(3):
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        break
                    time.sleep(0.1)
                
                if not ret or test_frame is None:
                    logger.warning(f"Camera at index {index} opened but cannot read frame")
                    cap.release()
                    continue
                
                # Configure camera settings
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 25)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer to get fresh frames
                
                self.video_capture = cap
                logger.info(f"✓ Successfully initialized camera at index {index}")
                return True
                
            except Exception as e:
                logger.warning(f"Error trying camera at index {index}: {e}")
                try:
                    cap.release()
                except:
                    pass
                continue
        
        logger.error("Failed to initialize camera from all available indices")
        return False
    
    def start_streaming(self):
        """Start the video streaming"""
        if self.streaming_active and self.video_capture and self.video_capture.isOpened():
            logger.info("Video streaming already active")
            return True
        
        try:
            logger.info("Starting video stream - closing any existing camera...")
            # Always close and re-initialize camera to ensure clean state
            if self.video_capture:
                try:
                    self.video_capture.release()
                    logger.info("Previous camera released")
                except Exception as e:
                    logger.warning(f"Error releasing previous camera: {e}")
                self.video_capture = None
            
            # Force garbage collection
            gc.collect()
            time.sleep(0.3)  # Wait for resources to be freed
            
            logger.info("Initializing new camera...")
            if not self.initialize_camera():
                logger.info("Failed to initialize camera for streaming")
                return False
            
            self.streaming_active = True
            self.consecutive_errors = 0
            self.last_frame_time = time.time()
            self.encoded_frame_buffer = None
            self.frame_ready_event.clear()
            
            # Start background frame capture thread (encodes once, shared across all clients)
            self.capture_thread = self.start_frame_capture_thread()
            
            logger.info("✓ Video streaming started - camera ready")
            return True
            
        except Exception as e:
            logger.error(f"Error starting video stream: {e}")
            self.streaming_active = False
            return False
    
    def stop_streaming(self):
        """Stop the video streaming and cleanup"""
        logger.info("Stopping video stream...")
        self.streaming_active = False
        
        # Signal capture thread to wake up and exit
        self.frame_ready_event.set()
        
        # Wait for capture thread to finish
        if self.capture_thread and self.capture_thread.is_alive():
            logger.info("Waiting for capture thread to exit...")
            self.capture_thread.join(timeout=1.0)
            if self.capture_thread.is_alive():
                logger.warning("Capture thread did not exit cleanly")
        
        # Release camera
        if self.video_capture:
            try:
                self.video_capture.release()
                logger.info("✓ Video capture released")
            except Exception as e:
                logger.warning(f"Error releasing video capture: {e}")
            finally:
                self.video_capture = None
        
        # Reset state
        self.consecutive_errors = 0
        self.last_frame_time = time.time()
        self.encoded_frame_buffer = None
        self.capture_thread = None
        
        # Force garbage collection to free camera resources
        gc.collect()
        time.sleep(0.2)  # Wait for resources to be freed
        logger.info("✓ Video stream stopped")
    
    def get_frame(self):
        """
        Capture and return the current frame
        Returns: (success, frame_bytes_jpeg) tuple
        """
        if not self.streaming_active or not self.video_capture:
            return False, None
        
        try:
            # Rate limiting for consistent FPS
            current_time = time.time()
            elapsed = current_time - self.last_frame_time
            
            # Only skip frame if we're ahead of schedule (not if we're behind)
            if elapsed < self.frame_interval:
                return False, None  # Skip this frame to maintain target FPS
            
            ret, frame = self.video_capture.read()
            if not ret or frame is None:
                self.consecutive_errors += 1
                logger.warning(f"Failed to read frame (error count: {self.consecutive_errors})")
                
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.error("Too many consecutive frame read errors, stopping stream")
                    self.stop_streaming()
                    return False, None
                
                return False, None
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode(
                '.jpg',
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 75, cv2.IMWRITE_JPEG_OPTIMIZE, 1]
            )
            
            if not ret:
                self.consecutive_errors += 1
                logger.warning(f"Failed to encode frame (error count: {self.consecutive_errors})")
                
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.error("Too many consecutive encoding errors, stopping stream")
                    self.stop_streaming()
                    return False, None
                
                return False, None
            
            # Reset error counter on success
            self.consecutive_errors = 0
            # Update timing - use actual elapsed time or frame interval, whichever is larger
            self.last_frame_time = current_time
            
            return True, buffer.tobytes()
            
        except Exception as e:
            self.consecutive_errors += 1
            logger.error(f"Error in get_frame: {e}")
            
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.stop_streaming()
            
            return False, None
    
    def start_frame_capture_thread(self):
        """Start background thread that captures and encodes frames once"""
        def capture_loop():
            logger.info("Frame capture thread started")
            while self.streaming_active:
                try:
                    # Get raw frame from camera
                    if not self.video_capture or not self.video_capture.isOpened():
                        time.sleep(0.1)
                        continue
                    
                    current_time = time.time()
                    elapsed = current_time - self.last_frame_time
                    
                    # Rate limiting
                    if elapsed < self.frame_interval:
                        time.sleep(0.01)
                        continue
                    
                    ret, frame = self.video_capture.read()
                    if not ret or frame is None:
                        self.consecutive_errors += 1
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            logger.error("Too many frame read errors, stopping")
                            self.stop_streaming()
                        time.sleep(0.05)
                        continue
                    
                    # Encode frame ONCE - lower quality to reduce CPU
                    ret, buffer = cv2.imencode(
                        '.jpg',
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 60, cv2.IMWRITE_JPEG_OPTIMIZE, 0]  # Reduced quality, no optimization
                    )
                    
                    if not ret:
                        self.consecutive_errors += 1
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            logger.error("Too many encoding errors, stopping")
                            self.stop_streaming()
                        time.sleep(0.05)
                        continue
                    
                    # Store in shared buffer and signal all clients
                    with self.buffer_lock:
                        self.encoded_frame_buffer = buffer.tobytes()
                    
                    self.consecutive_errors = 0
                    self.last_frame_time = current_time
                    self.frame_ready_event.set()
                    
                except Exception as e:
                    logger.error(f"Error in capture loop: {e}")
                    time.sleep(0.1)
            
            logger.info("Frame capture thread stopped")
        
        thread = threading.Thread(target=capture_loop, daemon=True)
        thread.start()
        return thread

    def generate_mjpeg_stream(self):
        """
        Generator for MJPEG stream
        Yields MJPEG frame boundaries and pre-encoded JPEG data (shared across clients)
        """
        if not self.streaming_active:
            logger.info("Cannot generate MJPEG stream - streaming not active")
            return
        
        # Increment active client counter
        with self.clients_lock:
            self.active_clients += 1
            logger.info(f"MJPEG client connected (total: {self.active_clients})")
        
        frame_count = 0
        
        try:
            while self.streaming_active:
                # Wait for new frame (timeout to allow clean exits)
                self.frame_ready_event.wait(timeout=0.5)
                self.frame_ready_event.clear()
                
                with self.buffer_lock:
                    if self.encoded_frame_buffer is None:
                        continue
                    frame_bytes = self.encoded_frame_buffer
                
                if frame_bytes:
                    frame_count += 1
                    # Yield MJPEG frame with proper boundaries
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n'
                        b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                        b'Content-Transfer-Encoding: binary\r\n'
                        b'X-Timestamp: ' + str(int(time.time() * 1000)).encode() + b'\r\n'
                        b'\r\n' + frame_bytes + b'\r\n'
                    )
                    
        except Exception as e:
            logger.info(f"Error in MJPEG generator: {e}")
        finally:
            # Decrement active client counter
            with self.clients_lock:
                self.active_clients -= 1
                logger.info(f"MJPEG client disconnected (total: {self.active_clients} remaining)")
    
    def get_status(self):
        """Get streaming status"""
        return {
            'active': self.streaming_active,
            'camera_ready': self.video_capture is not None and self.video_capture.isOpened(),
            'consecutive_errors': self.consecutive_errors
        }


# Global instance
_streamer = None

def get_http_video_streamer():
    """Get or create the global HTTP video streamer instance"""
    global _streamer
    if _streamer is None:
        _streamer = HTTPVideoStreamer()
    return _streamer

def initialize_http_video_streaming(app, socketio):
    """
    Initialize HTTP video streaming routes in Flask app
    Should be called after app creation
    """
    streamer = get_http_video_streamer()
    
    @app.route('/video_stream')
    def video_stream():
        """MJPEG video stream endpoint"""
        logger.info("GET /video_stream request received")
        if not streamer.streaming_active:
            logger.info("Video stream requested but streaming not active")
            return "Streaming not active", 503
        
        try:
            logger.info("Creating MJPEG stream generator")
            def generate():
                """Wrapper generator to handle client disconnections"""
                logger.info("MJPEG generator started")
                frame_count = 0
                try:
                    for frame_data in streamer.generate_mjpeg_stream():
                        # Check if streaming is still active
                        if not streamer.streaming_active:
                            logger.info("Streaming stopped, closing generator")
                            break
                        frame_count += 1
                        yield frame_data
                except GeneratorExit:
                    logger.info(f"Client disconnected from video stream (sent {frame_count} frames)")
                except Exception as e:
                    logger.info(f"Error in video stream generator: {e}")
                finally:
                    logger.info(f"MJPEG generator ended after sending {frame_count} frames")
            
            response = app.response_class(
                generate(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
            # Add headers to prevent connection caching
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Connection'] = 'close'
            response.headers['Pragma'] = 'no-cache'
            return response
        except Exception as e:
            logger.info(f"Error in video_stream endpoint: {e}")
            return f"Error: {str(e)}", 500
    
    @app.route('/video/start', methods=['POST'])
    def start_video():
        """Start video streaming endpoint"""
        try:
            success = streamer.start_streaming()
            if success:
                return {'status': 'started', 'message': 'Video stream started'}, 200
            else:
                return {'status': 'error', 'message': 'Could not initialize camera'}, 500
        except Exception as e:
            logger.error(f"Error in start_video: {e}")
            return {'status': 'error', 'message': str(e)}, 500
    
    @app.route('/video/stop', methods=['POST'])
    def stop_video():
        """Stop video streaming endpoint - only stops when no clients remain"""
        try:
            with streamer.clients_lock:
                active = streamer.active_clients
            
            # Only stop if this is the last client
            if active <= 1:
                streamer.stop_streaming()
                return {'status': 'stopped', 'message': 'Video stream stopped'}, 200
            else:
                logger.info(f"Video stream has {active} other clients, not stopping")
                return {'status': 'ok', 'message': f'Client disconnected, {active-1} clients remaining'}, 200
        except Exception as e:
            logger.error(f"Error in stop_video: {e}")
            return {'status': 'error', 'message': str(e)}, 500
    
    @app.route('/video/status', methods=['GET'])
    def get_video_status():
        """Get video streaming status"""
        try:
            status = streamer.get_status()
            return status, 200
        except Exception as e:
            logger.error(f"Error in get_video_status: {e}")
            return {'error': str(e)}, 500
    
    logger.info("✓ HTTP video streaming routes initialized")
    return streamer
