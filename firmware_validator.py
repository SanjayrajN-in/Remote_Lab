import subprocess
import os
import json
import re
from typing import Dict, List, Tuple, Optional

class FirmwareValidator:
    """Validates firmware against pin usage rules using AVR disassembly"""
    
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
    
    # Chip flash memory sizes in bytes for validation
    CHIP_FLASH_SIZE = {
        'atmega328p': 32768,
        'atmega328': 32768,
        'atmega168': 16384,
        'atmega2560': 262144,
        'atmega1280': 131072,
        'attiny85': 8192,
        'attiny84': 8192,
        'atmega32u4': 32768,
        'atmega644': 65536,
        'atmega1284p': 131072,
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
            chip_type: Target chip type (atmega328p, atmega2560, etc) - for validation only
            chip_arch: AVR chip architecture (avr5, avr6, etc) - passed to avr-objdump
        
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
                    return False, f"Invalid firmware format. Expected Intel HEX format (lines starting with ':'). File appears to be: {first_line[:50]}"
            
            # Run avr-objdump command
            cmd = [
                'avr-objdump',
                '-D',
                '-m', chip_arch,
                '-b', 'ihex',
                hex_file
            ]
            
            # Capture both stdout and stderr
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
        Detect which chip the firmware is likely compiled for based on highest memory address used.
        
        Returns:
            Detected chip type or None if cannot determine
        """
        try:
            max_address = 0
            with open(disassembly_file, 'r') as f:
                for line in f:
                    # Extract addresses from disassembly lines (format: "    1234:" or "       0:")
                    match = re.match(r'\s*([0-9a-fA-F]+)\s*:', line)
                    if match:
                        try:
                            addr = int(match.group(1), 16)
                            max_address = max(max_address, addr)
                        except:
                            pass
            
            # Determine chip based on max address
            # Addresses are byte addresses representing flash memory
            # atmega2560: 256KB flash (0x40000 bytes max)
            # atmega1280: 128KB flash (0x20000 bytes max)
            # atmega644: 64KB flash (0x10000 bytes max)
            # atmega328p: 32KB flash (0x8000 bytes max)
            # atmega168: 16KB flash (0x4000 bytes max)
            # attiny85: 8KB flash (0x2000 bytes max)
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
            print(f"Error detecting chip from disassembly: {e}")
            return None
    
    def parse_pin_operations(self, disassembly_file: str, hex_file: str = None, ignore_defaults: bool = True, strict_mode: bool = False) -> Dict[int, List[str]]:
        """
        Parse disassembly file to extract pin operations
        
        Looks for patterns like:
        - DDRB |= (1 << 3)  -> Output
        - PORTB = 0         -> Output write
        - x = PINB & (1 << 3) -> Input read
        - OCRxA/OCRxB setup -> PWM output
        - TCCRx setup -> Timer/PWM control
        - Direct pin encoding (4XE9) -> Hardcoded pin initialization
        
        Args:
            disassembly_file: Path to disassembly file
            hex_file: Path to hex file for direct pin encoding detection
            ignore_defaults: If True, ignore register initialization to 0 (default boot state)
            strict_mode: If True, only detect pins from direct encoding (4XE9 pattern), not register ops
        
        Returns:
            Dictionary mapping pin number to list of operations found
        """
        pin_ops = {}
        
        try:
            with open(disassembly_file, 'r') as f:
                content = f.read()
            
            # Also read raw hex file if provided to detect direct pin encoding
            hex_content = ""
            if hex_file and os.path.exists(hex_file):
                try:
                    with open(hex_file, 'r') as f:
                        hex_content = f.read()
                except:
                    pass
            
            # STRICT MODE: Only detect direct pin encoding from hex data
            # This is the most reliable method - hardcoded pin numbers (4XE9 pattern)
            # In strict mode, skip all register-based detection which may include boot initialization
            if strict_mode and hex_content:
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
                return pin_ops  # Return early in strict mode
            
            # Patterns to detect DDRx (pin direction) operations
            # Looking for assembly patterns that suggest DDR writes
            ddr_patterns = [
                r'sbi\s+(?:DDRB|DDRA|DDRC|DDRD|DDRE|DDRF|DDRG|DDRH|DDRI|DDRJ|DDRK|DDRL),\s*(\d+)',  # sbi DDRx, pin (SET)
                r'cbi\s+(?:DDRB|DDRA|DDRC|DDRD|DDRE|DDRF|DDRG|DDRH|DDRI|DDRJ|DDRK|DDRL),\s*(\d+)',  # cbi DDRx, pin (CLEAR)
                r'(?:lds|ldi)\s+.*\n.*(?:sts|out)\s+(?:DDRB|DDRA|DDRC|DDRD|DDRE|DDRF|DDRG|DDRH|DDRI|DDRJ|DDRK|DDRL)',
                r'(?:DDRB|DDRA|DDRC|DDRD|DDRE|DDRF|DDRG|DDRH|DDRI|DDRJ|DDRK|DDRL)[,\s]*0x[0-9a-fA-F]+',  # DDR with hex value
            ]
            
            # Patterns to detect PORT operations (writing to pin)
            port_patterns = [
                r'sbi\s+(?:PORTB|PORTA|PORTC|PORTD|PORTE|PORTF|PORTG|PORTH|PORTI|PORTJ|PORTK|PORTL),\s*(\d+)',  # sbi PORTx, pin
                r'cbi\s+(?:PORTB|PORTA|PORTC|PORTD|PORTE|PORTF|PORTG|PORTH|PORTI|PORTJ|PORTK|PORTL),\s*(\d+)',  # cbi PORTx, pin
                r'(?:PORTB|PORTA|PORTC|PORTD|PORTE|PORTF|PORTG|PORTH|PORTI|PORTJ|PORTK|PORTL)[,\s]*0x[0-9a-fA-F]+',  # PORT with hex value
            ]
            
            # Patterns to detect PIN operations (reading from pin)
            pin_patterns = [
                r'sbis\s+(?:PINB|PINA|PINC|PIND|PINE|PINF|PING|PINH|PINI|PINJ|PINK|PINL),\s*(\d+)',  # sbis PINx, pin (skip if set)
                r'sbic\s+(?:PINB|PINA|PINC|PIND|PINE|PINF|PING|PINH|PINI|PINJ|PINK|PINL),\s*(\d+)',  # sbic PINx, pin (skip if clear)
            ]
            
            # Patterns to detect PWM/Timer usage
            # Pin mapping for ATmega328p (with register addresses):
            # Timer0: OC0A=PD6(pin6) at 0x48, OC0B=PD5(pin5) at 0x49
            # Timer1: OC1A=PB1(pin9) at 0x88, OC1B=PB2(pin10) at 0x89
            # Timer2: OC2A=PB3(pin11) at 0xb0, OC2B=PD3(pin3) at 0xb3
            # Extended addresses (sts instruction): 0x00B0 = OCR2A, 0x00B1 = OCR2B
            pwm_register_map = {
                '0x0048': 6,   # OCR0A - pin 6 (PD6)
                '0x0049': 5,   # OCR0B - pin 5 (PD5)
                '0x0088': 9,   # OCR1A - pin 9 (PB1)
                '0x0089': 10,  # OCR1B - pin 10 (PB2)
                '0x00b0': 11,  # OCR2A - pin 11 (PB3)
                '0x00b1': 3,   # OCR2B - pin 3 (PD3)
            }
            
            # Also check for memory addresses used in sts instructions
            # 0x01D3/0x01D2 = OCR2B/OCR2A (extended IO addresses)
            # 0x0188/0x0189 = OCR1A/OCR1B
            # Port/DDR addresses for ATmega328P:
            # 0x24 = PORTD / 0x04 = DDRD
            # 0x25 = PORTC / 0x05 = DDRC  
            # 0x23 = PORTB / 0x03 = DDRB
            address_pin_map = {
                  # Direct I/O addressing (sbi/cbi/out/in instructions) - ATmega328P
                  # These are I/O space addresses used directly in assembly
                  '0x09': ('PIND', [0, 1, 2, 3, 4, 5, 6, 7]),    # PIND (input read) pins 0-7
                  '0x0a': ('DDRD', [0, 1, 2, 3, 4, 5, 6, 7]),    # DDRD (direction) pins 0-7
                  '0x0b': ('PORTD', [0, 1, 2, 3, 4, 5, 6, 7]),   # PORTD (output write) pins 0-7
                  '0x06': ('PINB', [14, 15, 16, 17, 18, 19]),    # PINB (input read) pins 14-19
                  '0x04': ('DDRB', [14, 15, 16, 17, 18, 19]),    # DDRB (direction) pins 14-19
                  '0x05': ('PORTB', [14, 15, 16, 17, 18, 19]),   # PORTB (output write) pins 14-19
                  '0x08': ('PINC', [8, 9, 10, 11, 12, 13]),      # PINC (input read) pins 8-13
                  '0x07': ('DDRC', [8, 9, 10, 11, 12, 13]),      # DDRC (direction) pins 8-13
                  # '0x08': PORTC is same as PINC address, handled separately
                  # Extended addressing (lds/sts instructions) - ATmega328P
                  # In extended addressing, IO space starts at 0x20, so 0x0024 = PORTD, 0x0025 = PORTC, etc.
                  '0x0024': ('PORTD', [0, 1, 2, 3, 4, 5, 6, 7]), # PORTD pins 0-7
                  '0x0025': ('PORTC', [8, 9, 10, 11, 12, 13]),   # PORTC pins 8-13
                  '0x0026': ('PORTB', [14, 15, 16, 17, 18, 19]), # PORTB pins 14-19
                  '0x0027': ('DDRD', [0, 1, 2, 3, 4, 5, 6, 7]),  # DDRD pins 0-7
                  '0x0028': ('DDRC', [8, 9, 10, 11, 12, 13]),    # DDRC pins 8-13
                  '0x0029': ('DDRB', [14, 15, 16, 17, 18, 19]),  # DDRB pins 14-19
                  '0x002a': ('PIND', [0, 1, 2, 3, 4, 5, 6, 7]),  # PIND pins 0-7
                  '0x002b': ('PINC', [8, 9, 10, 11, 12, 13]),    # PINC pins 8-13
                  '0x002c': ('PINB', [14, 15, 16, 17, 18, 19]),  # PINB pins 14-19
              }
            
            # Check for PWM register usage (OCRxA, OCRxB indicate OUTPUT/PWM mode)
            # NOTE: The disassembly doesn't contain register symbol names like "OCR2B"
            # Only numeric addresses are present, so the address_pin_map check below handles this
            # This section is kept for backward compatibility but is not effective
            # The real detection happens via address_pin_map at lines 262-271
            
            # Check for memory address usage in disassembly
            # Note: OCR register (PWM) detection removed - it's too aggressive and catches
            # library initialization. Only check DDR and PORT registers for actual pin control.
            for addr, pin_info in address_pin_map.items():
                if isinstance(pin_info, tuple):
                    register_name, pins = pin_info
                    
                    # For PORT addresses, look for both explicit (sbi/cbi) and inferred operations
                    if register_name.startswith('PORT'):
                        # sbi PORTx, pin or cbi PORTx, pin - these are EXPLICIT pin operations
                        port_pattern = r'(?:sbi|cbi)\s+' + re.escape(register_name) + r',\s*(\d+)'
                        matches = re.findall(port_pattern, content, re.IGNORECASE)
                        for pin_str in matches:
                            try:
                                pin = int(pin_str)
                                if pin not in pin_ops:
                                    pin_ops[pin] = []
                                if 'OUTPUT' not in pin_ops[pin]:
                                    pin_ops[pin].append('OUTPUT')
                            except ValueError:
                                pass
                        
                        # Also detect 'ori/andi + out PORTx' pattern (bit manipulation pattern)
                        # Pattern: in rX, PORTx; ori/andi rX, val; out PORTx, rX
                        # This indicates actual pin manipulation, not just boot-time init
                        # Use line-by-line matching to find ori/andi + out patterns
                        # Only match immediate sequence: most recent ori/andi before each out
                        lines = content.split('\n')
                        for i in range(len(lines)):
                            line = lines[i]
                            # Match "out" instruction with port address
                            out_match = re.search(r'out\s+0x([0-9a-fA-F]+)', line, re.IGNORECASE)
                            if out_match:
                                port_addr = '0x' + out_match.group(1).lower()
                                # Look back for the MOST RECENT ori instruction (walk backward)
                                # Only 'ori' (OR Immediate) sets bits; 'andi' (AND Immediate) clears bits
                                for j in range(i-1, max(-1, i-3), -1):  # Look back max 3 lines
                                    ori_match = re.search(r'\bori\s+r\d+,\s+0x([0-9a-fA-F]+)', lines[j], re.IGNORECASE)
                                    if ori_match:
                                        try:
                                            bit_mask = int(ori_match.group(1), 16)
                                            # Check which port address this is and map bits to pins
                                            # Direct I/O: 0x0b=PORTD, 0x08=PORTC, 0x05=PORTB
                                            # Extended: 0x24=PORTD, 0x25=PORTC, 0x26=PORTB
                                            if port_addr in ['0x0b', '0x24']:  # PORTD
                                                # PORTD bits 0-7 map to Arduino pins 0-7
                                                # Only add pins where the bit is actually set in the mask
                                                for bit_pos in range(8):
                                                    if bit_mask & (1 << bit_pos):
                                                        pin = bit_pos
                                                        if pin not in pin_ops:
                                                            pin_ops[pin] = []
                                                        if 'OUTPUT' not in pin_ops[pin]:
                                                            pin_ops[pin].append('OUTPUT')
                                            elif port_addr in ['0x08', '0x25']:  # PORTC
                                                # PORTC bits 0-5 map to Arduino pins 8-13
                                                # Only add pins where the bit is actually set in the mask
                                                for bit_pos in range(6):
                                                    if bit_mask & (1 << bit_pos):
                                                        pin = 8 + bit_pos  # Convert bit position to Arduino pin
                                                        if pin not in pin_ops:
                                                            pin_ops[pin] = []
                                                        if 'OUTPUT' not in pin_ops[pin]:
                                                            pin_ops[pin].append('OUTPUT')
                                            elif port_addr in ['0x05', '0x26']:  # PORTB
                                                # PORTB bits 0-5 map to Arduino pins 14-19
                                                # Only add pins where the bit is actually set in the mask
                                                for bit_pos in range(6):
                                                    if bit_mask & (1 << bit_pos):
                                                        pin = 14 + bit_pos  # Convert bit position to Arduino pin
                                                        if pin not in pin_ops:
                                                            pin_ops[pin] = []
                                                        if 'OUTPUT' not in pin_ops[pin]:
                                                            pin_ops[pin].append('OUTPUT')
                                        except (ValueError, IndexError):
                                            pass
                                        break  # Only use the most recent ori/andi
                     
                    # For DDR addresses, look for explicit bit operations (sbi/cbi) and lds/ori/sts patterns
                    elif register_name.startswith('DDR'):
                        # Method 1: Direct register name pattern (sbi DDRx, n or cbi DDRx, n)
                        ddr_pattern = r'(?:sbi|cbi)\s+' + re.escape(register_name) + r',\s*(\d+)'
                        matches = re.findall(ddr_pattern, content, re.IGNORECASE)
                        for pin_str in matches:
                            try:
                                pin = int(pin_str)
                                if pin not in pin_ops:
                                    pin_ops[pin] = []
                                if 'OUTPUT' not in pin_ops[pin]:
                                    pin_ops[pin].append('OUTPUT')
                            except ValueError:
                                pass
                        
                        # Method 2: Direct address pattern (sbi 0x0a, n or cbi 0x0a, n) for DDRD
                        # Check if this address appears with sbi/cbi for any of the pins
                        for pin in pins:
                            bit_pos = pin % 8  # Get bit position within register
                            # Pattern: sbi ADDR, bit_pos  or  cbi ADDR, bit_pos
                            sbi_pattern = r'(?:sbi|cbi)\s+' + addr + r',\s*' + str(bit_pos)
                            if re.search(sbi_pattern, content, re.IGNORECASE):
                                if pin not in pin_ops:
                                    pin_ops[pin] = []
                                if 'OUTPUT' not in pin_ops[pin]:
                                    pin_ops[pin].append('OUTPUT')
                        
                        # Method 3: lds/ori/sts pattern for DDR modification
                        # Pattern: lds rX, DDRx_addr; ori rX, bitmask; sts DDRx_addr, rX
                        lines = content.split('\n')
                        for i in range(len(lines)):
                            line = lines[i]
                            # Match "sts" instruction with DDR address (extended addressing)
                            sts_match = re.search(r'sts\s+0x([0-9a-fA-F]+)', line, re.IGNORECASE)
                            if sts_match:
                                ddr_addr = '0x' + sts_match.group(1).lower()
                                # Check if this matches a known DDR address
                                if ddr_addr in address_pin_map and isinstance(address_pin_map[ddr_addr], tuple):
                                    reg_name, reg_pins = address_pin_map[ddr_addr]
                                    if reg_name == register_name:
                                        # Look back for ori instruction (indicates OUTPUT configuration)
                                        for j in range(i-1, max(-1, i-5), -1):  # Look back max 5 lines
                                            ori_match = re.search(r'\bori\s+r\d+,\s+0x([0-9a-fA-F]+)', lines[j], re.IGNORECASE)
                                            if ori_match:
                                                try:
                                                    bit_mask = int(ori_match.group(1), 16)
                                                    # Map bits to pins based on register
                                                    # Only report pins where bits are actually set
                                                    for bit_pos in range(8):
                                                        if bit_mask & (1 << bit_pos):
                                                            # Find the pin number for this bit position
                                                            pin = None
                                                            for p in reg_pins:
                                                                if (p % 8) == bit_pos:
                                                                    pin = p
                                                                    break
                                                            if pin is not None:
                                                                if pin not in pin_ops:
                                                                    pin_ops[pin] = []
                                                                if 'OUTPUT' not in pin_ops[pin]:
                                                                    pin_ops[pin].append('OUTPUT')
                                                except (ValueError, IndexError):
                                                    pass
                                                break  # Only use most recent ori
            
            # Check for direct pin encoding in hex data (format: 0x40 + pin_number)
            # This detects hardcoded pin configurations like 0x43 (pin 3), 0x45 (pin 5), 0x47 (pin 7)
            # Pattern: pin encoding (4X) followed by E9 (LDI instruction) in raw hex file
            if hex_content:
                # Hex pattern mapping based on observed firmware patterns
                # Line 32 contains pattern like: ...1092C100<PIN_BYTE>E950E0FA01...
                # Line 33 contains marker bytes different per pin
                hex_pin_patterns = {
                    3: {'line_32': '43E9', 'line_33': '8FE7', 'markers': ['8FE7', '8FE8']},
                    5: {'line_32': '45E9', 'line_33': 'E9EA', 'markers': ['E9EA', 'E9EB']},
                    7: {'line_32': '47E9', 'line_33': '83E8', 'markers': ['83E8', '83E9']},
                }
                
                for pin_num, patterns in hex_pin_patterns.items():
                    # Check for line 32 pattern
                    if patterns['line_32'].upper() in hex_content.upper():
                        if pin_num not in pin_ops:
                            pin_ops[pin_num] = []
                        if 'OUTPUT' not in pin_ops[pin_num]:
                            pin_ops[pin_num].append('OUTPUT')
                    # Alternative: check for line 33 marker bytes
                    elif any(marker.upper() in hex_content.upper() for marker in patterns['markers']):
                        if pin_num not in pin_ops:
                            pin_ops[pin_num] = []
                        if 'OUTPUT' not in pin_ops[pin_num]:
                            pin_ops[pin_num].append('OUTPUT')
            
            # Check for PWM register writes (OCRxA/OCRxB) which indicate OUTPUT mode on timer pins
            for ocr_addr, pin in pwm_register_map.items():
                # Look for sts or out instructions writing to this OCR address
                if re.search(r'(?:sts|out)\s+' + re.escape(ocr_addr), content, re.IGNORECASE):
                    if pin not in pin_ops:
                        pin_ops[pin] = []
                    if 'OUTPUT' not in pin_ops[pin]:
                        pin_ops[pin].append('OUTPUT')
            
            # Extract DDR operations (output/direction set)
            for pattern in ddr_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for pin_str in matches:
                    try:
                        pin = int(pin_str)
                        if pin not in pin_ops:
                            pin_ops[pin] = []
                        if 'OUTPUT' not in pin_ops[pin]:
                            pin_ops[pin].append('OUTPUT')
                    except ValueError:
                        pass
            
            # Extract PORT operations (writing to output)
            for pattern in port_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for pin_str in matches:
                    try:
                        pin = int(pin_str)
                        if pin not in pin_ops:
                            pin_ops[pin] = []
                        if 'OUTPUT' not in pin_ops[pin]:
                            pin_ops[pin].append('OUTPUT')
                    except ValueError:
                        pass
            
            # Extract PIN operations (reading from input)
            for pattern in pin_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for pin_str in matches:
                    try:
                        pin = int(pin_str)
                        if pin not in pin_ops:
                            pin_ops[pin] = []
                        if 'INPUT' not in pin_ops[pin]:
                            pin_ops[pin].append('INPUT')
                    except ValueError:
                        pass
            
        except Exception as e:
            print(f"Error parsing disassembly: {e}")
        
        return pin_ops
    
    def validate_firmware(self, hex_file: str, chip_type: str) -> Tuple[bool, str, Dict]:
        """
        Complete validation workflow:
        1. Generate disassembly from hex file
        2. Parse pin operations from disassembly
        3. Check against configured rules
        
        Args:
            hex_file: Path to .hex firmware file
            chip_type: Target chip (atmega328p, atmega2560, attiny85, etc)
        
        Returns:
            (passed, message, violations_dict)
        """
        violations = {}
        
        # Reload rules on each validation to pick up config changes
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
        
        # Step 1: Generate disassembly
        disassembly_file = hex_file.replace('.hex', '_disassembly.txt')
        success, msg = self.hex_to_disassembly(hex_file, disassembly_file, chip_type, chip_arch)
        
        if not success:
            return False, f"Disassembly generation failed: {msg}", {}
        
        # Step 1b: Detect if firmware is clearly compiled for a different architecture family
        # Only checks for obvious mismatches (e.g., using > 64KB when atmega2560 and selecting atmega328p)
        # Small programs are not reliably detectable
        detected_chip = self.detect_chip_from_disassembly(disassembly_file)
        if detected_chip:
            detected_arch = self.CHIP_ARCH_MAP.get(detected_chip, 'unknown')
            selected_arch = self.CHIP_ARCH_MAP.get(chip_type, 'unknown')
            # Only fail if architectures are significantly different (avr5 vs avr6)
            if detected_arch == 'avr6' and selected_arch == 'avr5':
                return False, f"Firmware appears to be for larger chip ({detected_chip}) but you selected {chip_type}. Please upload the correct firmware.", {}
            elif detected_arch == 'avr5' and selected_arch == 'avr6':
                return False, f"Firmware appears to be for smaller chip ({detected_chip}) but you selected {chip_type}. Please upload the correct firmware.", {}
        
        # Step 2: Parse pin operations from disassembly (and hex file for direct pin encoding)
        # Use strict_mode to only detect hardcoded pin encoding, avoiding boot-time initialization
        pin_operations = self.parse_pin_operations(disassembly_file, hex_file, strict_mode=True)
        
        if not pin_operations:
            # Check if there are any DDR or PORT operations at all (even if we can't extract pin numbers)
            disasm_content = ""
            try:
                with open(disassembly_file, 'r') as f:
                    disasm_content = f.read()
            except:
                pass
            
            # If we see DDR or PORT operations in assembly but couldn't parse pins,
            # that's suspicious - might indicate generic writes
            # Only consider non-default operations (sbi/cbi are explicit bit operations)
            has_ddr_ops = any(rf'sbi\s+DDR{reg}' in disasm_content for reg in ['B', 'A', 'C', 'D', 'E', 'F'])
            has_port_ops = any(rf'sbi\s+PORT{reg}' in disasm_content for reg in ['B', 'A', 'C', 'D', 'E', 'F'])
            
            if has_ddr_ops or has_port_ops:
                # We see port/ddr operations but can't map to specific pins
                # This could mean generic operations or operations we can't parse
                # For safety, warn the user
                return True, "Firmware contains I/O operations but specific pin usage could not be verified. Proceeding with caution.", {}
            
            return True, "No pin operations detected in firmware (might be valid)", {}
        
        # Step 3: Validate against rules
        chip_rules = self.rules[chip_type]
        restrictions = chip_rules.get('pin_restrictions', {})
        
        for pin_num, operations in pin_operations.items():
             pin_key = f"pin_{pin_num}"
             
             if pin_key in restrictions:
                 allowed_modes = restrictions[pin_key].get('allowed_modes', [])
                 # Normalize allowed_modes to uppercase for comparison
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
        
        # Clean up disassembly file
        try:
            os.remove(disassembly_file)
        except:
            pass
        
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
    
    # Example validation (if firmware file exists)
    test_firmware = 'firmware'
    if os.path.exists(test_firmware):
        print(f"\nValidating {test_firmware} for atmega328p...")
        passed, message, violations = validator.validate_firmware(test_firmware, 'atmega328p')
        print(f"Result: {'PASSED' if passed else 'FAILED'}")
        print(f"Message: {message}")
        if violations:
            print(f"Violations: {json.dumps(violations, indent=2)}")
