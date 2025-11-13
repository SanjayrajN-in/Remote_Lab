#!/usr/bin/env python3
"""
Firmware comparison tool using srecord utilities
Compares two HEX/BIN files and provides detailed analysis
"""

import subprocess
import os
import sys
import re
from typing import Tuple, Dict, List, Optional

class FirmwareComparer:
    """Compare firmware files using srecord tools"""
    
    def __init__(self):
        """Initialize and check for srecord tools"""
        self.tools_available = True
        self.check_tools()
    
    def check_tools(self):
        """Check if srecord tools are available"""
        required_tools = ['srec_cat', 'srec_cmp', 'srec_info']
        missing = []
        
        for tool in required_tools:
            result = subprocess.run(['which', tool], capture_output=True)
            if result.returncode != 0:
                missing.append(tool)
        
        if missing:
            print(f"Warning: Missing srecord tools: {', '.join(missing)}")
            print("Install with: sudo apt-get install srecord")
            self.tools_available = False
        
        return not missing
    
    def get_file_info(self, hex_file: str) -> Dict:
        """Get detailed info about a HEX file using srec_info"""
        if not os.path.exists(hex_file):
            raise FileNotFoundError(f"File not found: {hex_file}")
        
        try:
            result = subprocess.run(
                ['srec_info', hex_file, '-Intel'],  # -Intel format specification
                capture_output=True,
                text=True,
                timeout=10
            )
            
            info = {
                'filename': hex_file,
                'exists': True,
                'size': os.path.getsize(hex_file),
                'raw_output': result.stdout,
                'stderr': result.stderr
            }
            
            # Parse srec_info output
            for line in result.stdout.split('\n'):
                if 'Data count' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        info['data_count'] = int(match.group(1))
                elif 'Execution start address' in line:
                    match = re.search(r'0x[0-9a-fA-F]+', line)
                    if match:
                        info['entry_point'] = match.group(0)
                elif 'Lowest address' in line:
                    match = re.search(r'0x[0-9a-fA-F]+', line)
                    if match:
                        info['lowest_addr'] = match.group(0)
                elif 'Highest address' in line:
                    match = re.search(r'0x[0-9a-fA-F]+', line)
                    if match:
                        info['highest_addr'] = match.group(0)
            
            return info
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"srec_info timeout on {hex_file}")
        except Exception as e:
            raise RuntimeError(f"Error analyzing {hex_file}: {e}")
    
    def compare_files(self, file1: str, file2: str, verbose: bool = False) -> Tuple[bool, str]:
        """
        Compare two firmware files using srec_cmp
        
        Returns:
            (identical, message)
        """
        if not os.path.exists(file1):
            return False, f"File not found: {file1}"
        if not os.path.exists(file2):
            return False, f"File not found: {file2}"
        
        try:
            cmd = ['srec_cmp', file1, '-Intel', file2, '-Intel']
            if verbose:
                cmd.append('-v')
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True, f"Files are identical"
            else:
                # Parse differences from output
                output = result.stderr if result.stderr else result.stdout
                lines = output.split('\n')
                diff_summary = '\n'.join(lines[:10])  # First 10 lines
                return False, f"Files differ:\n{diff_summary}"
        
        except subprocess.TimeoutExpired:
            return False, "Comparison timeout"
        except Exception as e:
            return False, f"Comparison error: {e}"
    
    def convert_format(self, input_file: str, output_file: str, 
                      input_format: str = 'Intel', output_format: str = 'Intel') -> Tuple[bool, str]:
        """
        Convert between firmware formats using srec_cat
        Formats: Intel, Motorola, Binary, etc.
        """
        if not os.path.exists(input_file):
            return False, f"File not found: {input_file}"
        
        try:
            # srec_cat takes input and output format specifications
            cmd = [
                'srec_cat',
                input_file, f'-{input_format}',  # Input format
                '-o', output_file, f'-{output_format}'  # Output format
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and os.path.exists(output_file):
                size = os.path.getsize(output_file)
                return True, f"Converted to {output_file} ({size} bytes)"
            else:
                error = result.stderr if result.stderr else result.stdout
                return False, f"Conversion failed: {error}"
        
        except subprocess.TimeoutExpired:
            return False, "Conversion timeout"
        except Exception as e:
            return False, f"Conversion error: {e}"
    
    def extract_data_region(self, hex_file: str, start_addr: Optional[int] = None, 
                           end_addr: Optional[int] = None, output_file: Optional[str] = None) -> Tuple[bool, str]:
        """
        Extract a specific memory region from firmware file
        Uses srec_cat for precise extraction
        """
        if not os.path.exists(hex_file):
            return False, f"File not found: {hex_file}"
        
        if output_file is None:
            output_file = hex_file.replace('.hex', '_extract.hex')
        
        try:
            cmd = ['srec_cat', hex_file, '-Intel']
            
            # Add address filtering if specified
            if start_addr is not None and end_addr is not None:
                cmd.extend(['-crop', f'0x{start_addr:X}', f'0x{end_addr:X}'])
            elif start_addr is not None:
                cmd.extend(['-crop', f'0x{start_addr:X}', f'0xFFFFFFFF'])
            elif end_addr is not None:
                cmd.extend(['-crop', f'0x0', f'0x{end_addr:X}'])
            
            cmd.extend(['-o', output_file, '-Intel'])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(output_file):
                size = os.path.getsize(output_file)
                return True, f"Extracted to {output_file} ({size} bytes)"
            else:
                error = result.stderr if result.stderr else result.stdout
                return False, f"Extraction failed: {error}"
        
        except Exception as e:
            return False, f"Extraction error: {e}"
    
    def generate_memory_map(self, hex_file: str) -> Dict:
        """Generate a detailed memory map from the firmware file"""
        if not os.path.exists(hex_file):
            raise FileNotFoundError(f"File not found: {hex_file}")
        
        memory_map = {
            'file': hex_file,
            'regions': []
        }
        
        try:
            # Parse HEX file manually for detailed region analysis
            current_base = 0
            regions = []
            
            with open(hex_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.startswith(':'):
                        continue
                    
                    # Intel HEX format: :LLAAAATTDD...CC
                    # LL = byte count, AAAA = address, TT = type
                    byte_count = int(line[1:3], 16)
                    address = int(line[3:7], 16)
                    record_type = int(line[7:9], 16)
                    
                    if record_type == 0x00:  # Data record
                        regions.append({
                            'line': line_num,
                            'address': address,
                            'bytes': byte_count
                        })
                    elif record_type == 0x04:  # Extended linear address
                        current_base = int(line[9:13], 16) << 16
            
            if regions:
                memory_map['regions'] = regions
                memory_map['total_bytes'] = sum(r['bytes'] for r in regions)
                memory_map['region_count'] = len(regions)
            
            return memory_map
        
        except Exception as e:
            raise RuntimeError(f"Error parsing memory map: {e}")


def main():
    """Example usage and CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Firmware comparison and analysis tool')
    parser.add_argument('command', choices=['info', 'compare', 'convert', 'extract', 'map'],
                       help='Command to execute')
    parser.add_argument('files', nargs='+', help='Firmware file(s)')
    parser.add_argument('--output', '-o', help='Output file')
    parser.add_argument('--start', type=lambda x: int(x, 0), help='Start address')
    parser.add_argument('--end', type=lambda x: int(x, 0), help='End address')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    comparer = FirmwareComparer()
    
    if args.command == 'info':
        for file in args.files:
            try:
                info = comparer.get_file_info(file)
                print(f"\nFile: {info['filename']}")
                print(f"Size: {info['size']} bytes")
                if 'data_count' in info:
                    print(f"Data records: {info['data_count']}")
                if 'lowest_addr' in info:
                    print(f"Address range: {info['lowest_addr']} - {info['highest_addr']}")
                if args.verbose:
                    print(f"\nDetailed info:\n{info['raw_output']}")
            except Exception as e:
                print(f"Error: {e}")
    
    elif args.command == 'compare':
        if len(args.files) != 2:
            print("Compare requires exactly 2 files")
            sys.exit(1)
        identical, msg = comparer.compare_files(args.files[0], args.files[1], args.verbose)
        print(msg)
        sys.exit(0 if identical else 1)
    
    elif args.command == 'convert':
        if len(args.files) < 1:
            print("Convert requires input file")
            sys.exit(1)
        output = args.output or args.files[0].replace('.hex', '_converted.hex')
        success, msg = comparer.convert_format(args.files[0], output)
        print(msg)
        sys.exit(0 if success else 1)
    
    elif args.command == 'extract':
        if len(args.files) < 1:
            print("Extract requires input file")
            sys.exit(1)
        output = args.output or args.files[0].replace('.hex', '_extract.hex')
        success, msg = comparer.extract_data_region(args.files[0], args.start, args.end, output)
        print(msg)
        sys.exit(0 if success else 1)
    
    elif args.command == 'map':
        for file in args.files:
            try:
                mmap = comparer.generate_memory_map(file)
                print(f"\nMemory map for: {mmap['file']}")
                print(f"Total data: {mmap['total_bytes']} bytes")
                print(f"Regions: {mmap['region_count']}")
                if args.verbose and mmap['regions']:
                    print("\nRegions:")
                    for r in mmap['regions'][:10]:
                        print(f"  0x{r['address']:04X}: {r['bytes']} bytes")
            except Exception as e:
                print(f"Error: {e}")


if __name__ == '__main__':
    main()
