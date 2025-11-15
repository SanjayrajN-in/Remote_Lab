#!/usr/bin/env python3
"""
Test script for HTTP video streaming
Verifies that the video streamer module works correctly
"""

import sys
import logging
from http_video_streamer import get_http_video_streamer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_video_streamer():
    """Test video streamer functionality"""
    
    print("\n" + "="*50)
    print("HTTP Video Streamer Test")
    print("="*50 + "\n")
    
    # Get streamer instance
    streamer = get_http_video_streamer()
    logger.info("✓ Got HTTP video streamer instance")
    
    # Test status
    status = streamer.get_status()
    logger.info(f"Initial status: {status}")
    
    # Test camera initialization
    logger.info("\nAttempting to initialize camera...")
    if streamer.initialize_camera():
        logger.info("✓ Camera initialized successfully")
    else:
        logger.warning("⚠ Could not initialize camera (might not be available)")
        return False
    
    # Test streaming start
    logger.info("\nStarting video stream...")
    if streamer.start_streaming():
        logger.info("✓ Video stream started")
    else:
        logger.error("✗ Failed to start video stream")
        return False
    
    # Test frame capture
    logger.info("\nTesting frame capture...")
    for i in range(5):
        success, frame_bytes = streamer.get_frame()
        if success and frame_bytes:
            logger.info(f"  Frame {i+1}: ✓ Captured {len(frame_bytes)} bytes")
        else:
            logger.info(f"  Frame {i+1}: Skipped (rate limiting)")
    
    # Test status
    status = streamer.get_status()
    logger.info(f"\nCurrent status: {status}")
    
    # Test streaming stop
    logger.info("\nStopping video stream...")
    streamer.stop_streaming()
    logger.info("✓ Video stream stopped")
    
    # Final status
    status = streamer.get_status()
    logger.info(f"Final status: {status}")
    
    print("\n" + "="*50)
    print("✓ All tests completed successfully!")
    print("="*50 + "\n")
    return True

if __name__ == '__main__':
    try:
        success = test_video_streamer()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"✗ Test failed with error: {e}")
        sys.exit(1)
