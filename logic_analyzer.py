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
    print("lgpio not available - logic analyzer will not function")

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
        self.handle = None

        # GPIO pin configuration for Raspberry Pi 5
        self.PIN_CH1_POS = 17  # Channel 1 positive pulse
        self.PIN_CH1_NEG = 18  # Channel 1 negative pulse
        self.PIN_CH2_POS = 22  # Channel 2 positive pulse
        self.PIN_CH2_NEG = 23  # Channel 2 negative pulse

        # Acquisition parameters
        self.sampling_rate = 1000000  # 1 MHz default for very high-frequency signals
        self.buffer_size = 50000     # Larger circular buffer size for high-frequency data
        self.stream_interval = 0.02  # Send data every 20ms for better responsiveness

        # Data buffers
        self.ch1_buffer = deque(maxlen=self.buffer_size)
        self.ch2_buffer = deque(maxlen=self.buffer_size)
        self.timestamp_buffer = deque(maxlen=self.buffer_size)

        # Control parameters
        self.channel_mode = 'both'  # 'ch1', 'ch2', 'both'
        self.timebase = 0.001      # 1ms/div default
        self.amplitude_scale = 1.0

        # Trigger parameters
        self.trigger_enabled = False
        self.trigger_channel = 1  # 1 or 2
        self.trigger_edge = 'rising'  # 'rising', 'falling', 'both'
        self.trigger_level = 0.5  # Trigger threshold (0-1)
        self.pre_trigger_samples = 1000  # Samples to keep before trigger
        self.trigger_timeout = 1.0  # Timeout in seconds for trigger wait

        # Threading
        self.acquisition_thread = None
        self.stream_thread = None
        self.stop_event = threading.Event()

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
                print(f"Claimed GPIO pin {pin} as input")

            print("GPIO initialized successfully")
            return True, "GPIO initialized successfully"
        except Exception as e:
            self.cleanup_gpio()
            print(f"GPIO initialization failed: {str(e)}")
            return False, f"GPIO initialization failed: {str(e)}"

    def cleanup_gpio(self):
        """Clean up GPIO resources"""
        try:
            if self.handle:
                lgpio.gpiochip_close(self.handle)
                self.handle = None
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
            self.ch1_buffer.clear()
            self.ch2_buffer.clear()
            self.timestamp_buffer.clear()
            self.stop_event.clear()

            self.acquiring = True
            print("Starting logic analyzer acquisition...")

            # Test socket connection
            self.socketio.emit('test_event', {'message': 'Logic analyzer started'})

            # Start acquisition thread
            self.acquisition_thread = threading.Thread(target=self._acquisition_loop)
            self.acquisition_thread.daemon = True
            self.acquisition_thread.start()
            print("Acquisition thread started")

            # Start streaming thread
            self.stream_thread = threading.Thread(target=self._streaming_loop)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            print("Streaming thread started")

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
            self.timebase = float(timebase)
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



    def _acquisition_loop(self):
        """Optimized acquisition loop for high-frequency sampling with trigger support"""
        sample_interval = 1.0 / self.sampling_rate
        last_sample_time = time.time()
        sample_count = 0

        # Trigger state variables
        triggered = False
        trigger_start_time = time.time() if self.trigger_enabled else None
        pre_trigger_ch1 = deque(maxlen=self.pre_trigger_samples) if self.trigger_enabled else None
        pre_trigger_ch2 = deque(maxlen=self.pre_trigger_samples) if self.trigger_enabled else None
        pre_trigger_timestamps = deque(maxlen=self.pre_trigger_samples) if self.trigger_enabled else None

        # Previous values for edge detection
        prev_ch1 = None
        prev_ch2 = None

        while self.acquiring and not self.stop_event.is_set():
            try:
                current_time = time.time()

                # Maintain precise sampling rate
                if current_time - last_sample_time >= sample_interval:
                    # Read GPIO pins for differential signals
                    ch1_pos = lgpio.gpio_read(self.chip, self.PIN_CH1_POS)
                    ch1_neg = lgpio.gpio_read(self.chip, self.PIN_CH1_NEG)
                    ch2_pos = lgpio.gpio_read(self.chip, self.PIN_CH2_POS)
                    ch2_neg = lgpio.gpio_read(self.chip, self.PIN_CH2_NEG)

                    # Calculate differential signals (POS - NEG) and determine logic level
                    # 1-0 = 1 → High (+ve pulse)
                    # 1-1 = 0 → Low
                    # 0-1 = -1 → Low (-ve pulse)
                    # 0-0 = 0 → Low

                    ch1_diff = ch1_pos - ch1_neg  # -1, 0, or 1
                    ch2_diff = ch2_pos - ch2_neg  # -1, 0, or 1

                    # Convert to digital logic levels (0 = Low, 1 = High)
                    ch1_logic = 1 if ch1_diff == 1 else 0  # Only +1 diff is High
                    ch2_logic = 1 if ch2_diff == 1 else 0  # Only +1 diff is High

                    # Store as float for consistency
                    ch1_float = float(ch1_logic)
                    ch2_float = float(ch2_logic)

                    # Handle triggering
                    if self.trigger_enabled and not triggered:
                        # Store pre-trigger data
                        if pre_trigger_ch1 is not None:
                            pre_trigger_ch1.append(ch1_float)
                            pre_trigger_ch2.append(ch2_float)
                            pre_trigger_timestamps.append(current_time)

                        # Check for trigger condition
                        trigger_detected = False

                        if self.trigger_channel == 1:
                            trigger_detected = self._check_trigger_condition(ch1_float, prev_ch1, self.trigger_edge, self.trigger_level)
                        elif self.trigger_channel == 2:
                            trigger_detected = self._check_trigger_condition(ch2_float, prev_ch2, self.trigger_edge, self.trigger_level)

                        if trigger_detected:
                            triggered = True
                            print(f"Trigger detected on CH{self.trigger_channel} at sample {sample_count}")

                            # Add pre-trigger data to main buffers
                            if pre_trigger_ch1:
                                self.ch1_buffer.extend(pre_trigger_ch1)
                                self.ch2_buffer.extend(pre_trigger_ch2)
                                self.timestamp_buffer.extend(pre_trigger_timestamps)

                    # Add current sample to buffers (if triggered or no trigger enabled)
                    if not self.trigger_enabled or triggered:
                        self.ch1_buffer.append(ch1_float)
                        self.ch2_buffer.append(ch2_float)
                        self.timestamp_buffer.append(current_time)

                        sample_count += 1

                        # Print status less frequently for high sample rates
                        if sample_count % 10000 == 0:
                            print(f"Sample {sample_count}: CH1({ch1_pos}-{ch1_neg}={ch1_diff})={ch1_logic}, CH2({ch2_pos}-{ch2_neg}={ch2_diff})={ch2_logic}, Buffer: {len(self.ch1_buffer)}, Rate: {self.sampling_rate}Hz")

                    # Update previous values for edge detection
                    prev_ch1 = ch1_float
                    prev_ch2 = ch2_float
                    last_sample_time = current_time

                    # Check trigger timeout
                    if self.trigger_enabled and not triggered and trigger_start_time:
                        if current_time - trigger_start_time > self.trigger_timeout:
                            print(f"Trigger timeout after {self.trigger_timeout}s, starting acquisition anyway")
                            triggered = True
                            # Add any pre-trigger data we have
                            if pre_trigger_ch1:
                                self.ch1_buffer.extend(pre_trigger_ch1)
                                self.ch2_buffer.extend(pre_trigger_ch2)
                                self.timestamp_buffer.extend(pre_trigger_timestamps)

                # Minimal sleep to prevent CPU hogging while maintaining timing
                time.sleep(max(0.000001, sample_interval / 10))  # Adaptive sleep

            except Exception as e:
                print(f"Logic analyzer acquisition error: {e}")
                break

        print(f"Acquisition loop ended. Total samples: {sample_count}")

    def _check_trigger_condition(self, current_value, previous_value, edge, level):
        """Check if trigger condition is met"""
        if previous_value is None:
            return False

        # Convert level to digital threshold (0.5 = midpoint)
        threshold = level

        if edge == 'rising':
            return previous_value < threshold and current_value >= threshold
        elif edge == 'falling':
            return previous_value > threshold and current_value <= threshold
        elif edge == 'both':
            return (previous_value < threshold and current_value >= threshold) or \
                   (previous_value > threshold and current_value <= threshold)

        return False

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
        """Stream data to frontend at regular intervals with synchronized data transmission"""
        stream_count = 0
        last_stream_time = time.time()

        while self.acquiring and not self.stop_event.is_set():
            try:
                self.stop_event.wait(self.stream_interval)

                if not self.acquiring:
                    break

                current_time = time.time()
                stream_count += 1

                # Get current buffer sizes (they should be equal due to synchronized acquisition)
                ch1_size = len(self.ch1_buffer)
                ch2_size = len(self.ch2_buffer)
                ts_size = len(self.timestamp_buffer)

                # Ensure all buffers have the same length (synchronization check)
                min_size = min(ch1_size, ch2_size, ts_size)
                if min_size == 0:
                    continue  # No data to send

                # Prepare data for streaming with proper synchronization
                data_to_send = {
                    'timestamp': current_time,
                    'sampling_rate': self.sampling_rate,
                    'timebase': self.timebase,
                    'scale': self.amplitude_scale,
                    'channel_mode': self.channel_mode
                }

                # Send last N samples, ensuring all arrays are synchronized
                # For high sample rates, limit to prevent browser overload
                max_samples_to_send = min(5000, min_size)  # Reduced from 10000 for better performance

                # Extract synchronized data from the end of buffers
                start_idx = max(0, min_size - max_samples_to_send)

                if self.channel_mode in ['ch1', 'both']:
                    ch1_data = list(self.ch1_buffer)[start_idx:]
                    data_to_send['ch1_data'] = ch1_data
                if self.channel_mode in ['ch2', 'both']:
                    ch2_data = list(self.ch2_buffer)[start_idx:]
                    data_to_send['ch2_data'] = ch2_data

                timestamps = list(self.timestamp_buffer)[start_idx:]
                data_to_send['timestamps'] = timestamps

                # Add analysis data for PWM signals
                if len(timestamps) > 1:
                    time_span = timestamps[-1] - timestamps[0]
                    data_to_send['time_span'] = time_span
                    data_to_send['sample_count'] = len(timestamps)

                    # Calculate frequency and duty cycle if we have enough data
                    if self.channel_mode in ['ch1', 'both'] and len(ch1_data) > 10:
                        freq_ch1, duty_ch1 = self._analyze_pwm_signal(ch1_data, timestamps)
                        data_to_send['ch1_frequency'] = freq_ch1
                        data_to_send['ch1_duty_cycle'] = duty_ch1

                    if self.channel_mode in ['ch2', 'both'] and len(ch2_data) > 10:
                        freq_ch2, duty_ch2 = self._analyze_pwm_signal(ch2_data, timestamps)
                        data_to_send['ch2_frequency'] = freq_ch2
                        data_to_send['ch2_duty_cycle'] = duty_ch2

                # Send data to frontend
                self.socketio.emit('logic_analyzer_data', data_to_send)

                if stream_count % 10 == 0:  # Log every 10 streams
                    print(f"Stream {stream_count}: Sent {max_samples_to_send} samples, Buffer sizes: CH1={ch1_size}, CH2={ch2_size}, TS={ts_size}")

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
            'buffer_size': len(self.ch1_buffer),
            'trigger_enabled': self.trigger_enabled,
            'trigger_channel': self.trigger_channel,
            'trigger_edge': self.trigger_edge,
            'trigger_level': self.trigger_level,
            'pre_trigger_samples': self.pre_trigger_samples,
            'trigger_timeout': self.trigger_timeout
        }
