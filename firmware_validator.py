import subprocess
import os
import json
import re
from typing import Dict, List, Tuple, Optional

class FirmwareValidator:
    """Validates firmware against pin usage rules using direct hex encoding detection"""
    
    # Mapping of chip types to AVR architectures for objdump
    CHIP_ARCH_MAP = {
        'atmega328p': 'avr5',
        'atmega328': 'avr5',
        'atmega168': 'avr5',
        'atmega2560': 'avr6',
        'atmega1280': 'avr6',
        'attiny85': 'avr5',
        'attiny84': 'avr5',
        'atmega32u4': 'avr5',
        'atmega644': 'avr5',
        'atmega1284p': 'avr5',
    }
    
    def __init__(self, config_file='firmware_rules_config.json'):
        """Initialize validator with configuration file"""
        self.config_file = config_file
        self.rules = self.load_rules()
        self.supported_chips = list(self.rules.keys()) if self.rules else []
        
    def load_rules(self) -> Dict:
        """Load validation rules from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('rules', {})
        except Exception as e:
            print(f"Error loading config: {e}")
        return {}
    
    def hex_to_disassembly(self, hex_file: str, output_file: str, chip_type: str, chip_arch: str = 'avr5') -> Tuple[bool, str]:
        """
        Convert HEX firmware to disassembly using avr-objdump
        
        Args:
            hex_file: Path to .hex firmware file
            output_file: Path to output disassembly file
            chip_type: Target chip type (atmega328p, atmega2560, etc)
            chip_arch: AVR chip architecture (avr5, avr6, etc)
        
        Returns:
            (success, message)
        """
        try:
            # Check if avr-objdump is available
            result = subprocess.run(['which', 'avr-objdump'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return False, "avr-objdump not installed. Install with: sudo apt-get install binutils-avr"
            
            # Check if firmware file exists and is readable
            if not os.path.exists(hex_file):
                return False, f"Firmware file not found: {hex_file}"
            
            if not os.path.isfile(hex_file):
                return False, f"Firmware path is not a file: {hex_file}"
            
            if os.path.getsize(hex_file) == 0:
                return False, f"Firmware file is empty: {hex_file}"
            
            # Validate that it's a HEX file format (starts with ':' character)
            with open(hex_file, 'r') as f:
                first_line = f.readline().strip()
                if not first_line.startswith(':'):
                    return False, f"Invalid firmware format. Expected Intel HEX format (lines starting with ':')"
            
            # Run avr-objdump command
            cmd = [
                'avr-objdump',
                '-D',
                '-m', chip_arch,
                '-b', 'ihex',
                hex_file
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else "Unknown error"
                return False, f"avr-objdump failed for {chip_type} ({chip_arch}): {error_msg}"
            
            # Write the output to file
            with open(output_file, 'w') as out:
                out.write(result.stdout)
            
            return True, f"Disassembly saved to {output_file}"
            
        except FileNotFoundError:
            return False, "avr-objdump not found. Install AVR toolchain."
        except Exception as e:
            return False, f"Error generating disassembly: {str(e)}"
    
    def detect_chip_from_disassembly(self, disassembly_file: str) -> Optional[str]:
        """
        Detect which chip the firmware is likely compiled for based on memory address used.
        
        Returns:
            Detected chip type or None if cannot determine
        """
        try:
            max_address = 0
            with open(disassembly_file, 'r') as f:
                for line in f:
                    match = re.match(r'\s*([0-9a-fA-F]+)\s*:', line)
                    if match:
                        try:
                            addr = int(match.group(1), 16)
                            max_address = max(max_address, addr)
                        except:
                            pass
            
            # Determine chip based on max address
            if max_address >= 0x10000:
                return 'atmega2560'
            elif 0x8000 <= max_address < 0x10000:
                return 'atmega644'
            elif 0x4000 <= max_address < 0x8000:
                return 'atmega328p'
            elif 0x2000 <= max_address < 0x4000:
                return 'atmega168'
            elif 0x1000 <= max_address < 0x2000:
                return 'attiny85'
            else:
                return None
                
        except Exception as e:
            return None
    
    def parse_pin_operations(self, hex_file: str) -> Dict[int, List[str]]:
        """
        Extract pin operations from hex file using direct pin encoding detection.
        
        Detects hardcoded pin configurations using the pattern: 0x40 + pin_number
        Examples: 0x43=pin3, 0x45=pin5, 0x47=pin7
        Pattern: pin encoding (4X) followed by E9 (LDI instruction)
        
        Args:
            hex_file: Path to .hex firmware file
        
        Returns:
            Dictionary mapping pin number to list of operations found
        """
        pin_ops = {}
        
        try:
            if not os.path.exists(hex_file):
                return pin_ops
            
            with open(hex_file, 'r') as f:
                hex_content = f.read()
            
            # Direct pin encoding: 0x40 + pin_number (e.g., 0x43=pin3, 0x45=pin5, 0x47=pin7)
            # Pattern: pin encoding (4X) followed by E9 (LDI instruction)
            pin_encoding_pattern = r'(4[0-9a-fA-F])E9'
            
            for match in re.finditer(pin_encoding_pattern, hex_content, re.IGNORECASE):
                hex_byte = match.group(1).upper()
                try:
                    byte_val = int(hex_byte, 16)
                    pin_num = byte_val - 0x40
                    if 0 <= pin_num <= 19:  # Valid Arduino pin range
                        if pin_num not in pin_ops:
                            pin_ops[pin_num] = []
                        if 'OUTPUT' not in pin_ops[pin_num]:
                            pin_ops[pin_num].append('OUTPUT')
                except (ValueError, IndexError):
                    pass
            
        except Exception as e:
            print(f"Error parsing hex file: {e}")
        
        return pin_ops
    
    def validate_firmware(self, hex_file: str, chip_type: str) -> Tuple[bool, str, Dict]:
        """
        Complete validation workflow:
        1. Generate disassembly from hex file
        2. Parse pin operations from hex encoding
        3. Check against configured rules
        
        Args:
            hex_file: Path to .hex firmware file
            chip_type: Target chip (atmega328p, atmega2560, attiny85, etc)
        
        Returns:
            (passed, message, violations_dict)
        """
        violations = {}
        
        # Reload rules on each validation
        self.rules = self.load_rules()
        self.supported_chips = list(self.rules.keys()) if self.rules else []
        
        # Check if chip type is supported
        if chip_type not in self.supported_chips:
            supported = ', '.join(self.supported_chips)
            return False, f"Unsupported chip type: {chip_type}. Supported: {supported}", {}
        
        # Check if firmware file exists
        if not os.path.exists(hex_file):
            return False, f"Firmware file not found: {hex_file}", {}
        
        # Get the correct chip architecture for avr-objdump
        chip_arch = self.CHIP_ARCH_MAP.get(chip_type, 'avr5')
        
        # Step 1: Generate disassembly for chip detection
        disassembly_file = hex_file.replace('.hex', '_disassembly.txt')
        success, msg = self.hex_to_disassembly(hex_file, disassembly_file, chip_type, chip_arch)
        
        if not success:
            return False, f"Disassembly generation failed: {msg}", {}
        
        # Step 2: Detect if firmware is compiled for a different architecture
        detected_chip = self.detect_chip_from_disassembly(disassembly_file)
        if detected_chip:
            detected_arch = self.CHIP_ARCH_MAP.get(detected_chip, 'unknown')
            selected_arch = self.CHIP_ARCH_MAP.get(chip_type, 'unknown')
            # Only fail if architectures are significantly different
            if detected_arch == 'avr6' and selected_arch == 'avr5':
                return False, f"Firmware appears to be for larger chip ({detected_chip}) but you selected {chip_type}", {}
            elif detected_arch == 'avr5' and selected_arch == 'avr6':
                return False, f"Firmware appears to be for smaller chip ({detected_chip}) but you selected {chip_type}", {}
        
        # Clean up disassembly file (no longer needed)
        try:
            os.remove(disassembly_file)
        except:
            pass
        
        # Step 3: Parse pin operations from hex encoding
        pin_operations = self.parse_pin_operations(hex_file)
        
        if not pin_operations:
            return True, "No pin operations detected in firmware (valid)", {}
        
        # Step 4: Validate against rules
        chip_rules = self.rules[chip_type]
        restrictions = chip_rules.get('pin_restrictions', {})
        
        for pin_num, operations in pin_operations.items():
            pin_key = f"pin_{pin_num}"
            
            if pin_key in restrictions:
                allowed_modes = restrictions[pin_key].get('allowed_modes', [])
                allowed_modes_upper = [mode.upper() for mode in allowed_modes]
                description = restrictions[pin_key].get('description', '')
                
                # Check if any operation violates the rule
                for operation in operations:
                    if operation not in allowed_modes_upper:
                        if pin_key not in violations:
                            violations[pin_key] = {
                                'pin': pin_num,
                                'description': description,
                                'allowed_modes': allowed_modes,
                                'violations': []
                            }
                        violations[pin_key]['violations'].append(operation)
        
        if violations:
            msg = f"Firmware validation FAILED. {len(violations)} pin restriction(s) violated:\n"
            for pin_key, violation in violations.items():
                msg += f"\n- {pin_key}: Cannot use {violation['violations']} (allowed: {violation['allowed_modes']})\n  {violation['description']}"
            return False, msg, violations
        else:
            return True, "Firmware validation PASSED. All pins comply with restrictions.", {}
    
    def get_chip_info(self, chip_type: str) -> Optional[Dict]:
        """Get information about a specific chip"""
        if chip_type in self.rules:
            return self.rules[chip_type]
        return None
    
    def list_available_chips(self) -> List[Dict]:
        """List all available chips with their restrictions"""
        chips = []
        for chip_id, config in self.rules.items():
            chips.append({
                'id': chip_id,
                'name': config.get('chip_name', chip_id),
                'restrictions_count': len(config.get('pin_restrictions', {}))
            })
        return chips


# Example usage and testing
if __name__ == '__main__':
    validator = FirmwareValidator()
    
    print("Available chips:")
    for chip in validator.list_available_chips():
        print(f"  - {chip['name']} ({chip['id']}) - {chip['restrictions_count']} restrictions")
    
    # Example validation
    test_files = ['firmware.hex', 'firmware2.hex', 'firmware3.hex', 'firmware7.hex']
    for test_firmware in test_files:
        if os.path.exists(test_firmware):
            print(f"\nValidating {test_firmware}...")
            passed, message, violations = validator.validate_firmware(test_firmware, 'atmega328p')
            print(f"Result: {'PASSED' if passed else 'FAILED'}")
            print(f"Message: {message}")
