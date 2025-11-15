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
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.target_fps = 15
        self.frame_interval = 1.0 / self.target_fps
        self.last_frame_time = time.time()
        
    def _test_camera(self, index):
        """Test if a camera at given index works - returns (index, cap, success) tuple"""
        try:
            cap = cv2.VideoCapture(index)
            
            # Set a timeout for the open operation
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 500)
            
            if not cap.isOpened():
                logger.debug(f"Camera at index {index} cannot be opened")
                return (index, None, False)
            
            # Try reading a frame with minimal delay
            for attempt in range(2):
                time.sleep(0.05)  # Small delay to let camera stabilize
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    logger.debug(f"✓ Camera at index {index} is working")
                    return (index, cap, True)
            
            logger.debug(f"Camera at index {index} opened but cannot read frame")
            cap.release()
            return (index, None, False)
                
        except Exception as e:
            logger.debug(f"Error testing camera at index {index}: {e}")
            try:
                cap.release()
            except:
                pass
            return (index, None, False)
    
    def initialize_camera(self, camera_indices=[0, 1, 2, 3, 4]):
        """
        Initialize video capture from webcam using parallel detection
        Try multiple camera indices simultaneously for faster initialization
        """
        logger.info(f"Attempting to initialize camera from indices (parallel): {camera_indices}")
        
        test_cameras = {}
        found_camera = False
        
        # Test all cameras in parallel
        executor = ThreadPoolExecutor(max_workers=len(camera_indices))
        futures = {executor.submit(self._test_camera, idx): idx for idx in camera_indices}
        
        try:
            for future in as_completed(futures):
                index, cap, success = future.result()
                test_cameras[index] = (cap, success)
                
                # Use first working camera found
                if success and not found_camera:
                    found_camera = True
                    # Configure camera settings
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 25)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer to get fresh frames
                    
                    self.video_capture = cap
                    logger.info(f"✓ Successfully initialized camera at index {index}")
                    
                    # Cancel remaining futures (non-blocking)
                    for f in futures:
                        f.cancel()
                    
                    # Clean up other test cameras that already completed
                    for idx, (test_cap, was_success) in test_cameras.items():
                        if idx != index and test_cap is not None:
                            try:
                                test_cap.release()
                            except:
                                pass
                    
                    executor.shutdown(wait=False)
                    return True
        finally:
            # Clean up executor and remaining cameras
            for idx, (test_cap, was_success) in test_cameras.items():
                if test_cap is not None:
                    try:
                        test_cap.release()
                    except:
                        pass
            executor.shutdown(wait=False)
        
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
            
            # Force garbage collection (faster cleanup)
            gc.collect()
            time.sleep(0.1)  # Minimal wait for resources to be freed
            
            logger.info("Initializing new camera...")
            if not self.initialize_camera():
                logger.info("Failed to initialize camera for streaming")
                return False
            
            self.streaming_active = True
            self.consecutive_errors = 0
            self.last_frame_time = time.time()
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
        
        # Wait a bit to allow generators to exit gracefully
        time.sleep(0.05)
        
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
    
    def generate_mjpeg_stream(self):
        """
        Generator for MJPEG stream
        Yields MJPEG frame boundaries and JPEG data
        """
        if not self.streaming_active:
            logger.info("Cannot generate MJPEG stream - streaming not active")
            return
        
        logger.info("Starting MJPEG frame generation")
        frame_count = 0
        
        try:
            while self.streaming_active:
                success, frame_bytes = self.get_frame()
                
                if success and frame_bytes:
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
                else:
                    time.sleep(0.01)  # Small sleep to prevent busy waiting
                    
        except Exception as e:
            logger.info(f"Error in MJPEG generator: {e}")
        finally:
            logger.info(f"MJPEG frame generation stopped after {frame_count} frames")
    
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
        """Stop video streaming endpoint"""
        try:
            streamer.stop_streaming()
            return {'status': 'stopped', 'message': 'Video stream stopped'}, 200
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
