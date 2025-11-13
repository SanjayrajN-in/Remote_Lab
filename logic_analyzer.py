import time
import threading
import json
import lgpio
import numpy as np
from collections import deque

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False

# Global instances
_logic_analyzer_manager = None

def init_logic_analyzer_manager(socketio):
    """Initialize the global logic analyzer manager instance"""
    global _logic_analyzer_manager
    if _logic_analyzer_manager is None:
        _logic_analyzer_manager = LogicAnalyzerManager(socketio)
    return _logic_analyzer_manager

def get_logic_analyzer_manager():
    """Get the global logic analyzer manager instance"""
    return _logic_analyzer_manager

class LogicAnalyzerManager:
    """Manages logic analyzer operations using Raspberry Pi GPIO"""

    def __init__(self, socketio):
        self.socketio = socketio
        self.acquiring = False
        self.lgpio_available = LGPIO_AVAILABLE
        self.chip = None

        # GPIO pin configuration for stepper motor control
        self.PIN_CH1_POS = 17  # Channel 1 positive
        self.PIN_CH1_NEG = 18  # Channel 1 negative
        self.PIN_CH2_POS = 22  # Channel 2 positive
        self.PIN_CH2_NEG = 23  # Channel 2 negative

        # Simple acquisition parameters
        self.sampling_rate = 10000  # 10 kHz sampling (safer default)
        self.buffer_size = 100000     # Buffer for 10 seconds at 10kHz (supports wide timebases)
        self.stream_interval = 0.05  # Send data every 50ms


        # Simple data buffers - just the differential values
        self.ch1_diff_buffer = deque(maxlen=self.buffer_size)
        self.ch2_diff_buffer = deque(maxlen=self.buffer_size)
        self.timestamp_buffer = deque(maxlen=self.buffer_size)

        # Control parameters
        self.channel_mode = 'both'  # 'ch1', 'ch2', 'both'
        self.timebase = 0.00001    # 10uS/div default (minimum)
        self.amplitude_scale = 1.0

        # Trigger functionality
        self.trigger_enabled = False
        self.trigger_channel = 'ch1'  # 'ch1' or 'ch2'
        self.trigger_edge = 'rising'  # 'rising' or 'falling'
        self.trigger_level = 0  # -1, 0, or 1 (differential value)
        self.trigger_armed = False
        self.trigger_captured = False
        self.trigger_displayed = False  # Flag to prevent re-streaming after capture
        self.pre_trigger_buffer_size = 5000  # Samples before trigger
        self.post_trigger_buffer_size = 10000  # Samples after trigger
        self.trigger_timeout = 5.0  # Seconds to wait for trigger before timeout
        self.trigger_start_time = None
        
        # Pre-trigger buffer for capturing before trigger event
        self.pre_trigger_ch1 = deque(maxlen=self.pre_trigger_buffer_size)
        self.pre_trigger_ch2 = deque(maxlen=self.pre_trigger_buffer_size)
        self.pre_trigger_timestamps = deque(maxlen=self.pre_trigger_buffer_size)

        # Threading
        self.acquisition_thread = None
        self.stream_thread = None
        self.stop_event = threading.Event()
        self.buffer_lock = threading.Lock()

    def initialize_gpio(self):
        """Initialize GPIO pins for logic analyzer"""
        if not self.lgpio_available:
            return False, "lgpio not available"

        try:
            # Open GPIO chip
            self.chip = lgpio.gpiochip_open(0)

            # Set up input pins
            pins = [self.PIN_CH1_POS, self.PIN_CH1_NEG, self.PIN_CH2_POS, self.PIN_CH2_NEG]
            for pin in pins:
                lgpio.gpio_claim_input(self.chip, pin)

            return True, "GPIO initialized successfully"
        except Exception as e:
            self.cleanup_gpio()
            return False, f"GPIO initialization failed: {str(e)}"

    def cleanup_gpio(self):
        """Clean up GPIO resources"""
        try:
            if self.chip:
                lgpio.gpiochip_close(self.chip)
                self.chip = None
        except Exception as e:
            print(f"Error cleaning up GPIO: {e}")

    def start_acquisition(self):
        """Start logic analyzer acquisition"""
        if not self.lgpio_available:
            return False, "lgpio not available"

        if self.acquiring:
            return False, "Already acquiring"

        try:
            # Initialize GPIO
            success, message = self.initialize_gpio()
            if not success:
                return False, message

            # Reset buffers and stop event
            self.ch1_diff_buffer.clear()
            self.ch2_diff_buffer.clear()
            self.timestamp_buffer.clear()
            self.stop_event.clear()

            self.acquiring = True

            # Test socket connection
            self.socketio.emit('test_event', {'message': 'Logic analyzer started'})

            # Start acquisition thread
            self.acquisition_thread = threading.Thread(target=self._acquisition_loop)
            self.acquisition_thread.daemon = True
            self.acquisition_thread.start()

            # Start streaming thread
            self.stream_thread = threading.Thread(target=self._streaming_loop)
            self.stream_thread.daemon = True
            self.stream_thread.start()

            return True, "Logic analyzer acquisition started"
        except Exception as e:
            self.stop_acquisition()
            return False, f"Failed to start acquisition: {str(e)}"

    def stop_acquisition(self):
        """Stop logic analyzer acquisition"""
        try:
            self.acquiring = False
            self.stop_event.set()

            # Wait for threads to finish
            if self.acquisition_thread and self.acquisition_thread.is_alive():
                self.acquisition_thread.join(timeout=1.0)

            if self.stream_thread and self.stream_thread.is_alive():
                self.stream_thread.join(timeout=1.0)

            # Clean up GPIO
            self.cleanup_gpio()

            return True, "Logic analyzer acquisition stopped"
        except Exception as e:
            return False, f"Failed to stop acquisition: {str(e)}"

    def set_sampling_rate(self, rate):
        """Set sampling rate in Hz"""
        try:
            self.sampling_rate = int(rate)
            return True
        except Exception as e:
            return False

    def set_channel_mode(self, mode):
        """Set channel display mode: 'ch1', 'ch2', 'both'"""
        if mode in ['ch1', 'ch2', 'both']:
            self.channel_mode = mode
            return True
        return False

    def set_timebase(self, timebase):
        """Set timebase (seconds per division)"""
        try:
            # Ensure timebase is within reasonable bounds
            timebase_val = float(timebase)
            if timebase_val < 0.00001:  # Minimum 10uS
                timebase_val = 0.00001
            elif timebase_val > 10.0:  # Maximum 10s
                timebase_val = 10.0
            self.timebase = timebase_val
            return True
        except Exception as e:
            return False

    def set_amplitude_scale(self, scale):
        """Set amplitude scaling"""
        try:
            self.amplitude_scale = float(scale)
            return True
        except Exception as e:
            return False

    def set_trigger_config(self, enabled, channel='ch1', edge='rising', level=0):
        """Configure trigger settings"""
        try:
            self.trigger_enabled = bool(enabled)
            if channel in ['ch1', 'ch2']:
                self.trigger_channel = channel
            if edge in ['rising', 'falling']:
                self.trigger_edge = edge
            # Level should be -1, 0, or 1 (differential value)
            if level in [-1, 0, 1]:
                self.trigger_level = level
            
            # Reset trigger state when reconfiguring
            if self.trigger_enabled:
                self.trigger_armed = True
                self.trigger_captured = False
                self.trigger_displayed = False
                self.trigger_start_time = time.time()
                self.pre_trigger_ch1.clear()
                self.pre_trigger_ch2.clear()
                self.pre_trigger_timestamps.clear()
            
            return True
        except Exception as e:
            print(f"Error setting trigger config: {e}")
            return False

    def _check_trigger_condition(self, prev_ch_value, curr_ch_value):
        """Check if trigger condition is met"""
        if not self.trigger_enabled or not self.trigger_armed:
            return False
        
        if self.trigger_edge == 'rising':
            # Rising edge: transition from <= 0 to >= 1
            return prev_ch_value <= 0 and curr_ch_value >= 1
        elif self.trigger_edge == 'falling':
            # Falling edge: transition from >= 1 to <= 0
            return prev_ch_value >= 1 and curr_ch_value <= 0
        
        return False

    def arm_trigger(self):
        """Arm the trigger to wait for the next trigger event"""
        self.trigger_armed = True
        self.trigger_captured = False
        self.trigger_displayed = False
        self.trigger_start_time = time.time()
        self.ch1_diff_buffer.clear()
        self.ch2_diff_buffer.clear()
        self.timestamp_buffer.clear()
        self.pre_trigger_ch1.clear()
        self.pre_trigger_ch2.clear()
        self.pre_trigger_timestamps.clear()
        return True

    def disarm_trigger(self):
        """Disarm the trigger"""
        self.trigger_armed = False
        self.trigger_captured = False
        return True



    def _acquisition_loop(self):
        """Continuous acquisition loop - samples GPIO pins and stores data"""
        sample_interval = 1.0 / self.sampling_rate
        last_sample_time = time.time()
        sample_count = 0
        prev_ch1_diff = 0
        prev_ch2_diff = 0
        post_trigger_count = 0

        while self.acquiring and not self.stop_event.is_set():
            try:
                current_time = time.time()

                # Simple timing check - take one sample when due
                if current_time - last_sample_time >= sample_interval:
                    # Read all GPIO pins as atomically as possible
                    # Group reads to minimize timing gaps between pins
                    pin_reads = []
                    pins = [self.PIN_CH1_POS, self.PIN_CH1_NEG, self.PIN_CH2_POS, self.PIN_CH2_NEG]

                    # Read all pins in rapid succession
                    for pin in pins:
                        pin_reads.append(lgpio.gpio_read(self.chip, pin))

                    ch1_pos, ch1_neg, ch2_pos, ch2_neg = pin_reads

                    # Compute differences: pos - neg gives +1, 0, or -1
                    # Channel 1: pin17 (pos) - pin18 (neg)
                    ch1_diff = ch1_pos - ch1_neg
                    # Channel 2: pin22 (pos) - pin23 (neg)
                    ch2_diff = ch2_pos - ch2_neg

                    # Handle trigger logic
                    trigger_fired = False
                    
                    with self.buffer_lock:
                        # If trigger is enabled and armed, check for trigger condition
                        if self.trigger_enabled and self.trigger_armed and not self.trigger_captured:
                            trigger_channel_prev = prev_ch1_diff if self.trigger_channel == 'ch1' else prev_ch2_diff
                            trigger_channel_curr = ch1_diff if self.trigger_channel == 'ch1' else ch2_diff
                            
                            if self._check_trigger_condition(trigger_channel_prev, trigger_channel_curr):
                                # Trigger condition met!
                                self.trigger_captured = True
                                self.trigger_displayed = False  # Will be set to True when first streamed
                                trigger_fired = True
                                post_trigger_count = 0
                                
                                # Move pre-trigger data to main buffer
                                if len(self.pre_trigger_ch1) > 0:
                                    self.ch1_diff_buffer.extend(self.pre_trigger_ch1)
                                    self.ch2_diff_buffer.extend(self.pre_trigger_ch2)
                                    self.timestamp_buffer.extend(self.pre_trigger_timestamps)
                                
                                # Emit trigger event to frontend
                                self.socketio.emit('trigger_captured', {
                                    'trigger_channel': self.trigger_channel,
                                    'trigger_edge': self.trigger_edge,
                                    'trigger_time': current_time
                                })
                        
                        # Determine capture mode and destination buffer
                        if self.trigger_enabled:
                            # Trigger mode is active
                            if self.trigger_captured:
                                # Post-trigger capture: fill main buffer
                                self.ch1_diff_buffer.append(ch1_diff)
                                self.ch2_diff_buffer.append(ch2_diff)
                                self.timestamp_buffer.append(current_time)
                                post_trigger_count += 1
                                
                                # Stop capturing after post-trigger buffer is full
                                if post_trigger_count >= self.post_trigger_buffer_size:
                                    self.trigger_armed = False
                            else:
                                # Waiting for trigger: accumulate only in pre-trigger buffer
                                self.pre_trigger_ch1.append(ch1_diff)
                                self.pre_trigger_ch2.append(ch2_diff)
                                self.pre_trigger_timestamps.append(current_time)
                        else:
                            # Continuous capture mode (trigger disabled)
                            self.ch1_diff_buffer.append(ch1_diff)
                            self.ch2_diff_buffer.append(ch2_diff)
                            self.timestamp_buffer.append(current_time)
                        
                        # Check for trigger timeout
                        if self.trigger_enabled and self.trigger_armed and not self.trigger_captured:
                            if self.trigger_start_time and current_time - self.trigger_start_time > self.trigger_timeout:
                                # Timeout - disarm and emit timeout event
                                self.trigger_armed = False
                                self.socketio.emit('trigger_timeout', {
                                    'trigger_channel': self.trigger_channel,
                                    'trigger_edge': self.trigger_edge,
                                    'timeout_duration': self.trigger_timeout
                                })

                    sample_count += 1
                    prev_ch1_diff = ch1_diff
                    prev_ch2_diff = ch2_diff
                    last_sample_time = current_time

                # Small sleep to prevent CPU hogging
                time.sleep(0.0001)

            except Exception as e:
                print(f"Acquisition loop error: {e}")
                break

    def _analyze_pwm_signal(self, data, timestamps):
        """Analyze PWM signal to calculate frequency and duty cycle"""
        if len(data) < 10 or len(timestamps) < 10:
            return 0.0, 0.0

        try:
            # Convert to numpy arrays for efficient processing
            signal = np.array(data)
            times = np.array(timestamps)

            # Find edges (transitions)
            diff_signal = np.diff(signal.astype(int))
            rising_edges = np.where(diff_signal == 1)[0] + 1
            falling_edges = np.where(diff_signal == -1)[0] + 1

            if len(rising_edges) < 2 and len(falling_edges) < 2:
                # No clear PWM pattern, try to estimate from signal levels
                high_count = np.sum(signal >= 0.5)
                total_count = len(signal)
                if total_count > 0:
                    duty_cycle = (high_count / total_count) * 100.0
                else:
                    duty_cycle = 0.0

                # Estimate frequency from zero crossings or signal changes
                changes = np.where(np.diff(signal.astype(int)) != 0)[0]
                if len(changes) >= 4:  # Need at least 2 full cycles
                    # Calculate period from average distance between changes
                    periods = np.diff(times[changes])
                    if len(periods) > 0:
                        avg_period = np.mean(periods)
                        frequency = 1.0 / avg_period if avg_period > 0 else 0.0
                    else:
                        frequency = 0.0
                else:
                    frequency = 0.0

                return frequency, duty_cycle

            # Analyze PWM pattern
            all_edges = np.sort(np.concatenate([rising_edges, falling_edges]))
            if len(all_edges) < 4:  # Need at least 2 full cycles
                return 0.0, 0.0

            # Calculate periods between rising edges
            if len(rising_edges) >= 2:
                periods = np.diff(times[rising_edges])
                avg_period = np.mean(periods)
                frequency = 1.0 / avg_period if avg_period > 0 else 0.0
            else:
                # Fallback: use time span and edge count
                time_span = times[-1] - times[0]
                edge_count = len(all_edges)
                if time_span > 0 and edge_count > 0:
                    # Estimate frequency from edges per second
                    frequency = edge_count / (2 * time_span)  # Divide by 2 for full cycles
                else:
                    frequency = 0.0

            # Calculate duty cycle
            high_time = 0.0
            total_time = times[-1] - times[0]

            # Calculate time spent high
            for i in range(len(rising_edges)):
                rise_idx = rising_edges[i]
                if i < len(falling_edges):
                    fall_idx = falling_edges[i]
                    if fall_idx > rise_idx:
                        high_time += times[fall_idx] - times[rise_idx]

            if total_time > 0:
                duty_cycle = (high_time / total_time) * 100.0
            else:
                duty_cycle = 0.0

            return frequency, duty_cycle

        except Exception as e:
            print(f"Error analyzing PWM signal: {e}")
            return 0.0, 0.0

    def _streaming_loop(self):
        """Stream differential data to frontend"""
        stream_count = 0
        last_rearm_time = 0

        while self.acquiring and not self.stop_event.is_set():
            try:
                self.stop_event.wait(self.stream_interval)

                if not self.acquiring:
                    break

                current_time = time.time()
                stream_count += 1

                # Get buffer sizes with thread safety
                with self.buffer_lock:
                    buffer_size = len(self.ch1_diff_buffer)
                    
                    # In trigger mode: stream after trigger is captured
                    if self.trigger_enabled:
                        if not self.trigger_captured:
                            # Waiting for trigger - don't stream anything to keep display frozen
                            continue
                        
                        # Still capturing post-trigger - don't stream yet to prevent movement
                        if self.trigger_armed:
                            continue
                        
                        # Trigger complete - check if we should auto-rearm for live continuous capture
                        if self.trigger_displayed and current_time - last_rearm_time > 0.2:
                            # Auto-rearm for next capture after small delay (allows display update)
                            self.trigger_displayed = False
                            self.trigger_captured = False
                            self.trigger_armed = True
                            self.trigger_start_time = time.time()
                            self.ch1_diff_buffer.clear()
                            self.ch2_diff_buffer.clear()
                            self.timestamp_buffer.clear()
                            self.pre_trigger_ch1.clear()
                            self.pre_trigger_ch2.clear()
                            self.pre_trigger_timestamps.clear()
                            last_rearm_time = current_time
                            continue
                        
                        # Check if we have data to send
                        if buffer_size == 0:
                            continue
                    else:
                        # Continuous mode - always stream if we have data
                        if buffer_size == 0:
                            continue

                    # Calculate samples to send based on timebase
                    target_time_window = self.timebase * 10  # 10 divisions
                    target_samples = int(target_time_window * self.sampling_rate)
                    max_samples = min(target_samples, buffer_size)  # No artificial cap, use all available
                    max_samples = max(max_samples, 500)  # Minimum 500 samples for stability

                    # Send data based on mode
                    if self.trigger_enabled and self.trigger_captured and not self.trigger_armed:
                        # Trigger mode: respect timebase windowing on captured data
                        # Calculate how many samples to show based on timebase
                        start_idx = max(0, buffer_size - max_samples)
                        data_to_send = {
                            'timestamp': current_time,
                            'sampling_rate': self.sampling_rate,
                            'timebase': self.timebase,
                            'scale': self.amplitude_scale,
                            'channel_mode': self.channel_mode,
                            'ch1_data': list(self.ch1_diff_buffer)[start_idx:],
                            'ch2_data': list(self.ch2_diff_buffer)[start_idx:],
                            'timestamps': list(self.timestamp_buffer)[start_idx:],
                            'trigger_armed': self.trigger_armed,
                            'trigger_captured': self.trigger_captured
                        }
                        # Mark as displayed
                        self.trigger_displayed = True
                    else:
                        # Continuous mode: rolling window
                        start_idx = max(0, buffer_size - max_samples)
                        data_to_send = {
                            'timestamp': current_time,
                            'sampling_rate': self.sampling_rate,
                            'timebase': self.timebase,
                            'scale': self.amplitude_scale,
                            'channel_mode': self.channel_mode,
                            'ch1_data': list(self.ch1_diff_buffer)[start_idx:],
                            'ch2_data': list(self.ch2_diff_buffer)[start_idx:],
                            'timestamps': list(self.timestamp_buffer)[start_idx:],
                            'trigger_armed': False,
                            'trigger_captured': False
                        }

                # Send data to frontend
                self.socketio.emit('logic_analyzer_data', data_to_send)

            except Exception as e:
                print(f"Logic analyzer streaming error: {e}")
                break

    def get_status(self):
        """Get current status of logic analyzer"""
        return {
            'acquiring': self.acquiring,
            'lgpio_available': self.lgpio_available,
            'sampling_rate': self.sampling_rate,
            'channel_mode': self.channel_mode,
            'timebase': self.timebase,
            'amplitude_scale': self.amplitude_scale,
            'buffer_size': len(self.ch1_diff_buffer),
            'trigger_enabled': self.trigger_enabled,
            'trigger_armed': self.trigger_armed,
            'trigger_captured': self.trigger_captured,
            'trigger_displayed': self.trigger_displayed,
            'trigger_channel': self.trigger_channel,
            'trigger_edge': self.trigger_edge,
            'trigger_level': self.trigger_level,
            'pre_trigger_size': len(self.pre_trigger_ch1)
        }
