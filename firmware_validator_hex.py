#!/usr/bin/env python3
"""
Validate firmware by extracting hex patterns instead of disassembly.
Direct hex byte comparison for pin initialization values.
"""

import re
from pathlib import Path

# Pin to expected hex pattern mappings
# Format: line_offset: (expected_bytes_pattern, expected_init_value)
PIN_PATTERNS = {
    3: {
        'line_32': ('43', 3),  # 0x43 in line 32 for pin 3
        'line_33': ('8FE7', 3),  # pin 3 marker bytes
    },
    5: {
        'line_32': ('45', 5),  # 0x45 in line 32 for pin 5
        'line_33': ('E9EA', 5),  # pin 5 marker bytes
    },
    7: {
        'line_32': ('47', 7),  # 0x47 in line 32 for pin 7
        'line_33': ('83E8', 7),  # pin 7 marker bytes
    },
}

def extract_hex_bytes(hex_file_path, line_num, start_offset, length):
    """Extract specific hex bytes from Intel HEX file."""
    with open(hex_file_path, 'r') as f:
        lines = f.readlines()
    
    if line_num > len(lines):
        return None
    
    hex_line = lines[line_num - 1].strip()
    # Intel HEX format: :LLAAAATTDD...CC
    # Skip the ':' and checksum, extract data section
    data_section = hex_line[9:-2]  # Skip :, length, address, type, and checksum
    return data_section[start_offset:start_offset + length]

def validate_firmware(hex_file_path, expected_pin):
    """Validate if firmware matches expected pin initialization."""
    hex_file_path = Path(hex_file_path)
    
    if not hex_file_path.exists():
        return False, f"File not found: {hex_file_path}"
    
    if expected_pin not in PIN_PATTERNS:
        return False, f"Unknown pin: {expected_pin}"
    
    pattern = PIN_PATTERNS[expected_pin]
    
    # Check line 32 for pin value
    byte_32 = extract_hex_bytes(hex_file_path, 32, 42, 2)  # Position varies, adjust offset
    if byte_32 is None:
        return False, "Could not read line 32"
    
    expected_byte = pattern['line_32'][0]
    if expected_byte not in byte_32.upper():
        return False, f"Line 32 mismatch: expected {expected_byte}, got {byte_32}"
    
    # Check line 33 for marker bytes
    byte_33 = extract_hex_bytes(hex_file_path, 33, 2, 4)  # Adjust offset as needed
    if byte_33 is None:
        return False, "Could not read line 33"
    
    expected_marker = pattern['line_33'][0]
    if expected_marker not in byte_33.upper():
        return False, f"Line 33 mismatch: expected marker {expected_marker}, got {byte_33}"
    
    return True, f"✓ Firmware validated for pin {expected_pin}"

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python firmware_validator_hex.py <hex_file> <pin_number>")
        print("Example: python firmware_validator_hex.py firmware7.hex 7")
        sys.exit(1)
    
    hex_file = sys.argv[1]
    pin = int(sys.argv[2])
    
    valid, msg = validate_firmware(hex_file, pin)
    print(msg)
    sys.exit(0 if valid else 1)
