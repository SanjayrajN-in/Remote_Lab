#!/usr/bin/env python3
"""
Extract pin configuration from firmware.hex file
Parses Intel HEX and finds DDR register initialization
"""

import sys
from typing import Dict, List

class HexParser:
    """Parse Intel HEX files and extract memory contents"""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.memory = {}  # Address -> byte value
        self.parse_hex_file()
    
    def parse_hex_file(self):
        """Parse Intel HEX format file"""
        extended_linear_address = 0
        
        try:
            with open(self.filename, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line.startswith(':'):
                        continue
                    
                    # Intel HEX format: :LLAAAATTDD...CC
                    # LL = byte count (2 hex chars)
                    # AAAA = address (4 hex chars)
                    # TT = record type (2 hex chars)
                    # DD... = data
                    # CC = checksum (2 hex chars)
                    
                    byte_count = int(line[1:3], 16)
                    address = int(line[3:7], 16)
                    record_type = int(line[7:9], 16)
                    
                    if record_type == 0x00:  # Data record
                        data_start = 9
                        data_end = 9 + (byte_count * 2)
                        data_hex = line[data_start:data_end]
                        
                        # Parse data bytes
                        for i in range(byte_count):
                            byte_val = int(data_hex[i*2:i*2+2], 16)
                            addr = extended_linear_address + address + i
                            self.memory[addr] = byte_val
                    
                    elif record_type == 0x04:  # Extended linear address
                        # Next 2 bytes are upper 16 bits of address
                        upper_addr = int(line[9:13], 16)
                        extended_linear_address = upper_addr << 16
                    
                    elif record_type == 0x01:  # End of file
                        break
        
        except Exception as e:
            print(f"Error parsing {self.filename}: {e}", file=sys.stderr)
            raise
    
    def get_byte(self, addr: int) -> int:
        """Get byte value at address, return 0 if not in firmware"""
        return self.memory.get(addr, 0)
    
    def get_region(self, start_addr: int, length: int) -> bytes:
        """Get a region of memory as bytes"""
        data = bytearray()
        for i in range(length):
            data.append(self.get_byte(start_addr + i))
        return bytes(data)


class PinExtractor:
    """Extract pin configuration from firmware"""
    
    # ATmega328p memory layout
    CHIP_CONFIG = {
        'atmega328p': {
            'ddrb': 0x24,  # DDRB register address
            'ddrc': 0x27,  # DDRC register address  
            'ddrd': 0x2A,  # DDRD register address
            'portb': 0x25, # PORTB register address
            'portc': 0x28, # PORTC register address
            'portd': 0x2B, # PORTD register address
            'pinb': 0x23,  # PINB register address
            'pinc': 0x26,  # PINC register address
            'pind': 0x29,  # PIND register address
        }
    }
    
    # Pin mapping for ATmega328p
    PIN_MAP = {
        'DDRB': [(14 + i, i) for i in range(6)],  # DDRB bits 0-5 -> pins 14-19
        'DDRC': [(8 + i, i) for i in range(6)],   # DDRC bits 0-5 -> pins 8-13
        'DDRD': [(0 + i, i) for i in range(8)],   # DDRD bits 0-7 -> pins 0-7
    }
    
    def __init__(self, hex_file: str, chip: str = 'atmega328p'):
        self.hex_parser = HexParser(hex_file)
        self.chip = chip
        if chip not in self.CHIP_CONFIG:
            raise ValueError(f"Unsupported chip: {chip}")
        self.config = self.CHIP_CONFIG[chip]
    
    def extract_ddr_values(self) -> Dict[str, int]:
        """Extract DDR register values from firmware"""
        ddr_values = {}
        
        for register in ['ddrb', 'ddrc', 'ddrd']:
            addr = self.config[register]
            value = self.hex_parser.get_byte(addr)
            ddr_values[register.upper()] = value
        
        return ddr_values
    
    def extract_port_values(self) -> Dict[str, int]:
        """Extract PORT register values from firmware"""
        port_values = {}
        
        for register in ['portb', 'portc', 'portd']:
            addr = self.config[register]
            value = self.hex_parser.get_byte(addr)
            port_values[register.upper()] = value
        
        return port_values
    
    def extract_output_pins(self) -> Dict[str, List[int]]:
        """
        Extract which pins are configured as outputs
        Returns dict mapping register name to list of output pin numbers
        """
        ddr_values = self.extract_ddr_values()
        output_pins = {}
        
        for register, value in ddr_values.items():
            output_pins[register] = []
            
            if register in self.PIN_MAP:
                for pin_num, bit_pos in self.PIN_MAP[register]:
                    # Check if bit is set (1 = output, 0 = input)
                    if value & (1 << bit_pos):
                        output_pins[register].append(pin_num)
        
        return output_pins
    
    def get_summary(self) -> str:
        """Get a formatted summary of pin configuration"""
        ddr_vals = self.extract_ddr_values()
        port_vals = self.extract_port_values()
        output_pins = self.extract_output_pins()
        
        lines = []
        lines.append(f"Chip: {self.chip}")
        lines.append(f"\nDDR Register Values:")
        lines.append("-" * 50)
        
        for reg in ['DDRB', 'DDRC', 'DDRD']:
            ddr_val = ddr_vals.get(reg, 0)
            pins = output_pins.get(reg, [])
            lines.append(f"{reg}: 0x{ddr_val:02X} ({ddr_val:08b}b)")
            if pins:
                lines.append(f"  Output pins: {sorted(pins)}")
            else:
                lines.append(f"  Output pins: None (all inputs)")
        
        lines.append(f"\nPORT Register Values (output levels):")
        lines.append("-" * 50)
        for reg in ['PORTB', 'PORTC', 'PORTD']:
            port_val = port_vals.get(reg, 0)
            lines.append(f"{reg}: 0x{port_val:02X} ({port_val:08b}b)")
        
        lines.append(f"\nAll Output Pins Summary:")
        lines.append("-" * 50)
        all_output = []
        for reg, pins in output_pins.items():
            all_output.extend(pins)
        
        if all_output:
            lines.append(f"Pins configured as OUTPUT: {sorted(all_output)}")
        else:
            lines.append("No pins configured as OUTPUT")
        
        return "\n".join(lines)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract pin configuration from firmware')
    parser.add_argument('hex_file', help='Firmware HEX file')
    parser.add_argument('--chip', default='atmega328p', help='Target chip (default: atmega328p)')
    parser.add_argument('--raw', action='store_true', help='Show raw DDR/PORT register values only')
    
    args = parser.parse_args()
    
    try:
        extractor = PinExtractor(args.hex_file, args.chip)
        
        if args.raw:
            ddr_vals = extractor.extract_ddr_values()
            port_vals = extractor.extract_port_values()
            print(f"DDR Registers: {ddr_vals}")
            print(f"PORT Registers: {port_vals}")
        else:
            print(extractor.get_summary())
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
