#!/usr/bin/env python3
"""
Correctly analyze which pins are configured as output by analyzing actual assembly
instead of static memory locations or regex patterns.

ATmega328p register addresses:
- 0x24 (0x04 I/O): DDRD (direction, bits 0-7 = pins 0-7)
- 0x25 (0x05 I/O): PORTD
- 0x26 (0x06 I/O): PIND (input)
- 0x27 (0x07 I/O): DDRC (direction, bits 0-5 = pins 8-13)
- 0x28 (0x08 I/O): PORTC
- 0x29 (0x09 I/O): PINC
- 0x2A (0x0A I/O): DDRB (direction, bits 0-5 = pins 14-19)
- 0x2B (0x0B I/O): PORTB
- 0x2C (0x0C I/O): PINB
"""

import subprocess
import re
from typing import Dict, Set, Tuple


class AVRPinAnalyzer:
    """Analyze AVR assembly to determine pin configuration"""
    
    # Register DDR addresses and their pin mappings
    DDR_REGS = {
        0x24: ('DDRD', list(range(0, 8))),      # pins 0-7
        0x27: ('DDRC', list(range(8, 14))),     # pins 8-13
        0x2A: ('DDRB', list(range(14, 20))),    # pins 14-19 (A0-A5)
    }
    
    def __init__(self, hex_file: str, chip: str = 'atmega328p'):
        self.hex_file = hex_file
        self.chip = chip
        self.ddr_operations = {}  # Track DDR register modifications
    
    def get_disassembly(self) -> str:
        """Generate disassembly from HEX file"""
        try:
            result = subprocess.run(
                ['avr-objdump', '-D', '-m', 'avr5', '-b', 'ihex', self.hex_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"avr-objdump failed: {result.stderr}")
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError("avr-objdump not found. Install with: sudo apt-get install binutils-avr")
    
    def parse_ddr_operations(self, disassembly: str) -> Dict:
        """
        Parse assembly to find DDR operations.
        
        Pattern: 
        in   rX, 0x24     (read DDRD)
        ori  rX, 0xNN     (set bits NN)
        out  0x24, rX     (write DDRD)
        
        The ori value tells us which bits (pins) are being set to output.
        """
        output_config = {
            'DDRD': 0,  # bits set to 1 = output pins
            'DDRC': 0,
            'DDRB': 0,
        }
        
        lines = disassembly.split('\n')
        
        # Track register operations
        reg_values = {}  # reg -> value
        last_ori_value = None
        last_ori_line = None
        
        for i, line in enumerate(lines):
            # Pattern: in rX, ADDR
            in_match = re.search(r'in\s+r(\d+),\s+0x([0-9a-f]+)', line)
            if in_match:
                reg_num = int(in_match.group(1))
                addr = int(in_match.group(2), 16)
                if addr in [0x24, 0x25, 0x27, 0x28, 0x2A, 0x2B]:
                    last_in_reg = reg_num
                    last_in_addr = addr
            
            # Pattern: ori rX, 0xNN (OR immediate)
            ori_match = re.search(r'ori\s+r(\d+),\s+0x([0-9a-f]+)', line)
            if ori_match:
                reg_num = int(ori_match.group(1))
                value = int(ori_match.group(2), 16)
                last_ori_value = value
                last_ori_reg = reg_num
                last_ori_line = i
            
            # Pattern: out ADDR, rX (write register)
            out_match = re.search(r'out\s+0x([0-9a-f]+),\s+r(\d+)', line)
            if out_match:
                addr = int(out_match.group(1), 16)
                reg_num = int(out_match.group(2), 16)
                
                # If this is a DDR write with a recent ori operation
                if addr in [0x24, 0x27, 0x2A]:  # DDRD, DDRC, DDRB
                    ddr_name = {0x24: 'DDRD', 0x27: 'DDRC', 0x2A: 'DDRB'}[addr]
                    
                    # Check if there was an ori just before this out
                    # The ori sets which bits should be 1 (output)
                    if last_ori_value is not None and (i - last_ori_line) <= 2:
                        output_config[ddr_name] |= last_ori_value  # Accumulate all ori values
        
        return output_config
    
    def extract_output_pins(self) -> Tuple[Dict[str, list], Dict]:
        """Extract which pins are outputs based on DDR register analysis"""
        disassembly = self.get_disassembly()
        ddr_config = self.parse_ddr_operations(disassembly)
        
        output_pins = {}
        
        for addr, (reg_name, pins) in self.DDR_REGS.items():
            ddr_value = ddr_config[reg_name]
            output_pins[reg_name] = []
            
            # Each bit set to 1 means that pin is output
            for bit_pos, pin_num in enumerate(pins):
                if ddr_value & (1 << bit_pos):
                    output_pins[reg_name].append(pin_num)
        
        return output_pins, ddr_config
    
    def get_summary(self) -> str:
        """Generate summary of pin configuration"""
        output_pins, ddr_config = self.extract_output_pins()
        
        lines = []
        lines.append("=" * 60)
        lines.append("AVR Pin Configuration Analysis")
        lines.append("=" * 60)
        lines.append(f"Chip: {self.chip}")
        lines.append(f"File: {self.hex_file}\n")
        
        lines.append("DDR Register Analysis:")
        lines.append("-" * 60)
        
        for reg_name in ['DDRD', 'DDRC', 'DDRB']:
            ddr_val = ddr_config[reg_name]
            pins = output_pins[reg_name]
            
            lines.append(f"{reg_name}: 0x{ddr_val:02X} ({ddr_val:08b}b)")
            if pins:
                lines.append(f"  → Output pins: {pins}")
            else:
                lines.append(f"  → Output pins: None (all inputs)")
        
        lines.append("\n" + "=" * 60)
        lines.append("SUMMARY - All pins configured as OUTPUT:")
        lines.append("=" * 60)
        
        all_output = []
        for pins in output_pins.values():
            all_output.extend(pins)
        
        if all_output:
            all_output.sort()
            lines.append(f"Pins: {all_output}")
            # Map to Arduino pin names
            pin_names = []
            for p in all_output:
                if p < 8:
                    pin_names.append(f"D{p}")
                elif p < 14:
                    pin_names.append(f"A{p-8}")
                else:
                    pin_names.append(f"A{p-14}")
            lines.append(f"Names: {', '.join(pin_names)}")
        else:
            lines.append("No pins configured as OUTPUT")
        
        return "\n".join(lines)


def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze AVR firmware for output pin configuration')
    parser.add_argument('hex_file', help='Firmware HEX file')
    parser.add_argument('--chip', default='atmega328p', help='Target chip')
    
    args = parser.parse_args()
    
    try:
        analyzer = AVRPinAnalyzer(args.hex_file, args.chip)
        print(analyzer.get_summary())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
