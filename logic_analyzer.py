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
    print("lgpio not available - GPIO logic analyzer will not function")



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
    """Manages logic analyzer operations using Raspberry Pi GPIO or external USB device"""

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
        self.sampling_rate = 100000  # 100 kHz sampling
        self.buffer_size = 10000     # Buffer for 0.1 seconds of data
        self.stream_interval = 0.05  # Send data every 50ms

        # Simple data buffers - just the differential values
        self.ch1_diff_buffer = deque(maxlen=self.buffer_size)
        self.ch2_diff_buffer = deque(maxlen=self.buffer_size)
        self.timestamp_buffer = deque(maxlen=self.buffer_size)

        # Control parameters
        self.channel_mode = 'both'  # 'ch1', 'ch2', 'both'
        self.timebase = 0.001      # 1ms/div default
        self.amplitude_scale = 1.0

        # Frequency analysis parameters
        self.frequency_buffer_size = 5000  # Samples to use for frequency analysis

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
            if self.chip:
                lgpio.gpiochip_close(self.chip)
                self.chip = None
        except Exception as e:
            print(f"Error cleaning up GPIO: {e}")

    def initialize_hardware(self):
        """Initialize hardware"""
        return self.initialize_gpio()

    def cleanup_hardware(self):
        """Clean up hardware"""
        self.cleanup_gpio()

    def start_acquisition(self):
        """Start logic analyzer acquisition"""
        if not self.lgpio_available:
            return False, "lgpio not available"

        if self.acquiring:
            return False, "Already acquiring"

        try:
            # Initialize hardware
            success, message = self.initialize_hardware()
            if not success:
                return False, message

            # Reset buffers and stop event
            self.ch1_diff_buffer.clear()
            self.ch2_diff_buffer.clear()
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

            # Clean up hardware
            self.cleanup_hardware()

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
        """Acquisition loop for internal GPIO logic analyzer"""
        sample_interval = 1.0 / self.sampling_rate
        last_sample_time = time.time()
        sample_count = 0

        while self.acquiring and not self.stop_event.is_set():
            try:
                current_time = time.time()

                # Maintain sampling rate
                if current_time - last_sample_time >= sample_interval:
                    # Read GPIO pins (0 or 1)
                    ch1_pos = lgpio.gpio_read(self.chip, self.PIN_CH1_POS)
                    ch1_neg = lgpio.gpio_read(self.chip, self.PIN_CH1_NEG)
                    ch2_pos = lgpio.gpio_read(self.chip, self.PIN_CH2_POS)
                    ch2_neg = lgpio.gpio_read(self.chip, self.PIN_CH2_NEG)

                    # Compute differences: pos - neg gives +1, 0, or -1
                    ch1_diff = ch1_pos - ch1_neg
                    ch2_diff = ch2_pos - ch2_neg

                    # Store the differential values
                    self.ch1_diff_buffer.append(ch1_diff)
                    self.ch2_diff_buffer.append(ch2_diff)
                    self.timestamp_buffer.append(current_time)

                    sample_count += 1

                    # Print status occasionally
                    if sample_count % 5000 == 0:
                        print(f"Sample {sample_count}: CH1={ch1_diff}, CH2={ch2_diff}")

                    last_sample_time = current_time

                # Small sleep to prevent CPU hogging
                time.sleep(0.0001)

            except Exception as e:
                print(f"Logic analyzer acquisition error: {e}")
                break

        print(f"Acquisition loop ended. Total samples: {sample_count}")

    def _analyze_signal_frequency(self, data, timestamps):
        """Analyze signal to calculate frequency and duty cycle for any periodic signal"""
        if len(data) < 20 or len(timestamps) < 20:
            return 0.0, 0.0

        try:
            # Convert to numpy arrays for efficient processing
            signal = np.array(data, dtype=float)
            times = np.array(timestamps, dtype=float)

            # For differential signals, consider +1 as high, -1 as low, 0 as neutral
            # Convert to binary signal for frequency analysis (high/low transitions)
            binary_signal = np.where(signal > 0.5, 1.0, 0.0)  # +1 becomes 1, others become 0

            # Find transitions (edges) where signal changes
            diff_signal = np.diff(binary_signal)
            edge_indices = np.where(np.abs(diff_signal) > 0.5)[0] + 1  # Find where signal changes

            if len(edge_indices) < 4:  # Need at least 2 full cycles (4 edges minimum)
                return 0.0, 0.0

            # Get edge timestamps
            edge_times = times[edge_indices]

            # Calculate periods between consecutive rising edges (more stable for frequency)
            rising_edges = []
            for i in range(1, len(edge_indices)):
                prev_idx = edge_indices[i-1]
                curr_idx = edge_indices[i]
                # Check if this is a rising edge (0 to 1 transition)
                if binary_signal[prev_idx] < 0.5 and binary_signal[curr_idx] > 0.5:
                    rising_edges.append(times[curr_idx])

            if len(rising_edges) < 2:
                # Fallback: use all edges if no clear rising edges
                periods = np.diff(edge_times)
            else:
                periods = np.diff(np.array(rising_edges))

            if len(periods) < 2:
                return 0.0, 0.0

            # Filter out unrealistic periods based on sampling rate and expected frequency range
            sampling_interval = np.mean(np.diff(times)) if len(times) > 1 else 0.00001
            min_period = sampling_interval * 2  # At least 2 samples per period
            max_period = 1.0  # Maximum 1 second period (1 Hz minimum)

            # For stepper motors and similar signals, allow lower frequencies
            if np.mean(periods) > 0.01:  # If average period > 10ms, likely stepper motor
                max_period = 1.0  # Allow down to 1 Hz
            else:
                max_period = 0.1  # For higher frequencies, limit to 10 Hz max period

            valid_periods = periods[(periods >= min_period) & (periods <= max_period)]

            if len(valid_periods) < 2:
                return 0.0, 0.0

            # Use median instead of mean for better robustness against outliers
            median_period = np.median(valid_periods)
            frequency = 1.0 / median_period if median_period > 0 else 0.0

            # Calculate duty cycle more accurately
            # For the signal segments between edges
            high_time = 0.0
            total_time = times[-1] - times[0]

            if total_time > 0:
                # Count time spent in high state
                for i in range(len(binary_signal) - 1):
                    if binary_signal[i] > 0.5:  # High state
                        segment_time = times[i + 1] - times[i]
                        high_time += segment_time

                duty_cycle = (high_time / total_time) * 100.0
            else:
                duty_cycle = 0.0

            return frequency, duty_cycle

        except Exception as e:
            print(f"Error analyzing signal: {e}")
            return 0.0, 0.0

    def _streaming_loop(self):
        """Stream differential data to frontend"""
        stream_count = 0

        while self.acquiring and not self.stop_event.is_set():
            try:
                self.stop_event.wait(self.stream_interval)

                if not self.acquiring:
                    break

                current_time = time.time()
                stream_count += 1

                # Send live streaming data
                buffer_size = len(self.ch1_diff_buffer)
                if buffer_size == 0:
                    continue

                # Send last frequency_buffer_size samples for accurate frequency analysis
                max_samples = min(self.frequency_buffer_size, buffer_size)
                start_idx = max(0, buffer_size - max_samples)

                # Get data slices
                ch1_data = list(self.ch1_diff_buffer)[start_idx:]
                ch2_data = list(self.ch2_diff_buffer)[start_idx:]
                timestamps = list(self.timestamp_buffer)[start_idx:]

                # Calculate frequency for each channel using the full buffer for accuracy
                ch1_freq, ch1_duty = self._analyze_signal_frequency(ch1_data, timestamps)
                ch2_freq, ch2_duty = self._analyze_signal_frequency(ch2_data, timestamps)

                # Prepare data for frontend - send last 2000 samples for display
                display_samples = min(2000, buffer_size)
                display_start_idx = max(0, buffer_size - display_samples)
                display_ch1_data = list(self.ch1_diff_buffer)[display_start_idx:]
                display_ch2_data = list(self.ch2_diff_buffer)[display_start_idx:]
                display_timestamps = list(self.timestamp_buffer)[display_start_idx:]

                data_to_send = {
                    'timestamp': current_time,
                    'sampling_rate': self.sampling_rate,
                    'timebase': self.timebase,
                    'scale': self.amplitude_scale,
                    'channel_mode': self.channel_mode,
                    'ch1_data': display_ch1_data,
                    'ch2_data': display_ch2_data,
                    'timestamps': display_timestamps,
                    'ch1_frequency': ch1_freq,
                    'ch1_duty_cycle': ch1_duty,
                    'ch2_frequency': ch2_freq,
                    'ch2_duty_cycle': ch2_duty
                }

                # Send data to frontend
                self.socketio.emit('logic_analyzer_data', data_to_send)

                if stream_count % 10 == 0:
                    print(f"Stream {stream_count}: Sent {display_samples} samples, CH1: {ch1_freq:.1f}Hz ({ch1_duty:.1f}%), CH2: {ch2_freq:.1f}Hz ({ch2_duty:.1f}%)")

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
            'buffer_size': len(self.ch1_diff_buffer)
        }
