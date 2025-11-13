#!/usr/bin/env python3
"""
Production Tailwind CSS builder for Raspberry Pi
Generates optimized CSS without Node.js dependency
"""

import os
import json
import subprocess
import sys

def build_tailwind():
    """Build Tailwind CSS using standalone CLI"""
    
    # Check if tailwindcss CLI is available
    try:
        result = subprocess.run(['which', 'tailwindcss'], capture_output=True, text=True)
        if result.returncode != 0:
            print("Installing Tailwind CSS standalone CLI...")
            # For ARM-based Raspberry Pi, download standalone
            subprocess.run([
                'curl',
                '-sLO',
                'https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-arm64'
            ], check=False)
            os.chmod('tailwindcss-linux-arm64', 0o755)
            tailwindcss_cmd = './tailwindcss-linux-arm64'
        else:
            tailwindcss_cmd = 'tailwindcss'
    except Exception as e:
        print(f"Error checking for tailwindcss: {e}")
        print("Falling back to CDN-based CSS")
        return False
    
    # Build CSS
    try:
        subprocess.run([
            tailwindcss_cmd,
            '-i', 'input.css',
            '-o', 'static/styles.css',
            '--minify'
        ], check=True)
        print("✓ Tailwind CSS built successfully to static/styles.css")
        return True
    except Exception as e:
        print(f"Error building Tailwind CSS: {e}")
        return False

if __name__ == '__main__':
    build_tailwind()
