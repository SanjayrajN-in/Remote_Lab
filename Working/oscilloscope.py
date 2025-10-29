import time
import threading
import math
import random



try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False

# Global instances
_oscilloscope_manager = None

def init_oscilloscope_manager(socketio):
    """Initialize the global oscilloscope manager instance"""
    global _oscilloscope_manager
    if _oscilloscope_manager is None:
        _oscilloscope_manager = OscilloscopeManager(socketio)
    return _oscilloscope_manager

def get_oscilloscope_manager():
    """Get the global oscilloscope manager instance"""
    return _oscilloscope_manager

class OscilloscopeManager:
    """Manages oscilloscope connections and operations"""

    def __init__(self, socketio):
        self.socketio = socketio
        self.connected = False
        self.acquiring = False
        self.pyvisa_available = PYVISA_AVAILABLE
        self.resource_string = None
        self.instrument = None
        self.trigger_level = 0.0
        self.timebase = 0.001  # 1ms default
        self.vertical_scale = 1.0
        self.channel = 1
        self.acquisition_thread = None

    def connect(self, resource_string):
        """Connect to an oscilloscope using VISA resource string"""
        try:
            if not self.pyvisa_available:
                return False, "PyVISA not available"

            rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(resource_string)
            self.resource_string = resource_string
            self.connected = True

            # Basic setup
            self.instrument.timeout = 5000
            self.instrument.write("*CLS")  # Clear status
            self.instrument.write("*RST")  # Reset instrument

            return True, f"Connected to {resource_string}"
        except Exception as e:
            self.connected = False
            return False, f"Connection failed: {str(e)}"

    def disconnect(self):
        """Disconnect from the oscilloscope"""
        try:
            if self.acquiring:
                self.stop_acquisition()

            if self.instrument:
                self.instrument.close()
                self.instrument = None

            self.connected = False
            self.resource_string = None
            return True, "Disconnected successfully"
        except Exception as e:
            return False, f"Disconnect failed: {str(e)}"

    def get_device_info(self):
        """Get information about the connected device"""
        if not self.connected or not self.instrument:
            return {
                "model": "Not connected",
                "manufacturer": "N/A",
                "serial": "N/A",
                "firmware": "N/A"
            }

        try:
            model = self.instrument.query("*IDN?")
            return {
                "model": model.strip(),
                "manufacturer": "N/A",
                "serial": "N/A",
                "firmware": "N/A"
            }
        except Exception as e:
            return {
                "model": f"Error: {str(e)}",
                "manufacturer": "N/A",
                "serial": "N/A",
                "firmware": "N/A"
            }

    def start_acquisition(self, channel=1):
        """Start oscilloscope acquisition"""
        if not self.connected:
            return False, "Not connected to oscilloscope"

        try:
            self.channel = channel
            self.acquiring = True

            # Start acquisition thread
            self.acquisition_thread = threading.Thread(target=self._acquisition_loop)
            self.acquisition_thread.daemon = True
            self.acquisition_thread.start()

            return True, f"Acquisition started on channel {channel}"
        except Exception as e:
            self.acquiring = False
            return False, f"Failed to start acquisition: {str(e)}"

    def stop_acquisition(self):
        """Stop oscilloscope acquisition"""
        try:
            self.acquiring = False

            if self.acquisition_thread and self.acquisition_thread.is_alive():
                self.acquisition_thread.join(timeout=1.0)

            return True, "Acquisition stopped"
        except Exception as e:
            return False, f"Failed to stop acquisition: {str(e)}"

    def set_trigger_level(self, level, channel=1):
        """Set trigger level"""
        try:
            self.trigger_level = level
            if self.connected and self.instrument:
                # This would be instrument-specific commands
                pass
            return True
        except Exception as e:
            return False

    def set_timebase(self, timebase):
        """Set timebase (seconds per division)"""
        try:
            self.timebase = timebase
            if self.connected and self.instrument:
                # This would be instrument-specific commands
                pass
            return True
        except Exception as e:
            return False

    def set_vertical_scale(self, scale, channel=1):
        """Set vertical scale (volts per division)"""
        try:
            self.vertical_scale = scale
            if self.connected and self.instrument:
                # This would be instrument-specific commands
                pass
            return True
        except Exception as e:
            return False

    def _acquisition_loop(self):
        """Main acquisition loop - runs in separate thread"""
        while self.acquiring and self.connected:
            try:
                # This is a placeholder - real implementation would read from instrument
                time.sleep(0.1)  # Simulate acquisition delay

                # Emit demo data for now
                demo_data = self._generate_demo_waveform()
                self.socketio.emit('oscilloscope_data', {
                    'channel': self.channel,
                    'data': demo_data,
                    'timebase': self.timebase,
                    'scale': self.vertical_scale
                })

            except Exception as e:
                print(f"Oscilloscope acquisition error: {e}")
                break

    def _generate_demo_waveform(self):
        """Generate demo waveform data"""
        points = 1000
        data = []

        for i in range(points):
            t = i / points * 10 * self.timebase  # 10 divisions worth of data
            # Generate a sine wave
            value = math.sin(2 * math.pi * 1 * t) * self.vertical_scale
            data.append(value)

        return data
