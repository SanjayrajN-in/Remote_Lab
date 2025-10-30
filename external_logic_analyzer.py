import serial
import time
import threading
import serial.tools.list_ports

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("pyserial not available - external logic analyzer will not function")

class ExternalLogicAnalyzer:
    """Handles external USB logic analyzer operations"""

    def __init__(self):
        self.serial = None
        self.serial_available = SERIAL_AVAILABLE
        self.connected = False

    def find_usb_serial_ports(self):
        """Find available USB serial ports"""
        if not self.serial_available:
            return []

        usb_ports = []
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                # Look for USB serial devices (common patterns)
                if any(keyword in port.device for keyword in ['ttyUSB', 'ttyACM', 'tty.usbserial']):
                    usb_ports.append(port.device)
                # Also check VID/PID for common USB serial adapters
                elif port.vid is not None and port.pid is not None:
                    # Common USB serial VID/PIDs
                    usb_ports.append(port.device)
        except Exception as e:
            print(f"Error scanning serial ports: {e}")

        # Additionally check for common USB serial port names that might not be listed
        common_ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1']
        import os
        for port in common_ports:
            if os.path.exists(port) and port not in usb_ports:
                usb_ports.append(port)

        return usb_ports

    def initialize(self, port=None, baudrate=115200):
        """Initialize external logic analyzer connection"""
        if not self.serial_available:
            return False, "pyserial not available"

        # If no port specified, auto-detect USB serial ports
        if port is None:
            usb_ports = self.find_usb_serial_ports()
            if not usb_ports:
                return False, "No USB serial ports found. Please connect your external logic analyzer."

            # Try each detected port until one works
            accessible_ports = []
            for detected_port in usb_ports:
                try:
                    print(f"Trying to open USB serial port: {detected_port}")
                    test_serial = serial.Serial(detected_port, baudrate, timeout=1)
                    test_serial.close()  # Close immediately if successful
                    accessible_ports.append(detected_port)
                    print(f"Successfully tested USB serial port: {detected_port}")
                except Exception as e:
                    print(f"Port {detected_port} not accessible: {e}")
                    continue

            if not accessible_ports:
                return False, "No accessible USB serial ports found. Please check your external logic analyzer connection."

            # Use the first accessible port
            port = accessible_ports[0]

        try:
            self.serial = serial.Serial(port, baudrate, timeout=1)
            self.connected = True
            print(f"External logic analyzer initialized on {port}")
            return True, f"External logic analyzer initialized on {port}"
        except Exception as e:
            self.serial = None
            self.connected = False
            print(f"External logic analyzer initialization failed: {str(e)}")
            return False, f"External logic analyzer initialization failed: {str(e)}"

    def cleanup(self):
        """Clean up external logic analyzer resources"""
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
            self.serial = None
            self.connected = False
        except Exception as e:
            print(f"Error cleaning up external LA: {e}")

    def read_channels(self):
        """Read channel data from external logic analyzer

        Expected format: "ch1,ch2,ch3,ch4\\n" where each is 0 or 1
        Returns: (ch1_diff, ch2_diff) where:
        - ch1_diff = ch1 - ch2 (LA channels 1&2 for plot CH1)
        - ch2_diff = ch3 - ch4 (LA channels 3&4 for plot CH2)
        """
        if not self.connected or not self.serial:
            return None, None

        try:
            line = self.serial.readline().decode('utf-8').strip()
            if line:
                parts = line.split(',')
                if len(parts) == 4:
                    la_ch1 = int(parts[0])  # LA channel 1
                    la_ch2 = int(parts[1])  # LA channel 2
                    la_ch3 = int(parts[2])  # LA channel 3
                    la_ch4 = int(parts[3])  # LA channel 4

                    # Map to plot channels as per task:
                    # ch1 and ch2 of LA are for ch1 of plot
                    # ch3 and ch4 of LA are for ch2 of plot
                    # ch1 and ch3 capture +ve pulse, ch2 and ch4 capture -ve pulse
                    ch1_diff = la_ch1 - la_ch2  # +ve - -ve for plot CH1
                    ch2_diff = la_ch3 - la_ch4  # +ve - -ve for plot CH2

                    return ch1_diff, ch2_diff
                else:
                    # Invalid data format
                    return None, None
            else:
                # No data available
                return None, None
        except Exception as e:
            print(f"External LA read error: {e}")
            return None, None

    def is_available(self):
        """Check if external logic analyzer is available"""
        return self.serial_available

    def is_connected(self):
        """Check if external logic analyzer is connected"""
        return self.connected

    def get_status(self):
        """Get status of external logic analyzer"""
        return {
            'available': self.serial_available,
            'connected': self.connected
        }
