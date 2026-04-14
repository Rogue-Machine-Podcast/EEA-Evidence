#!/usr/bin/env python3
"""
Binary Payload XOR Mutation Extractor
-------------------------------------
Specialized forensic tool for extracting potential executable code from obfuscated
binary payloads using XOR mutation techniques.

Specifically hunts for crypto wallet targeting patterns and extraction mechanisms.

Dr. Alistair Blackwood
Spector v Severina case
"""

import os
import sys
import binascii
import itertools
import struct
from pathlib import Path

# ANSI terminal colors for forensic output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """Print formatted section header for forensic analysis output."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(80)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}")

def print_warning(text):
    """Print formatted warning message."""
    print(f"{Colors.BOLD}{Colors.RED}[!] WARNING: {text}{Colors.RESET}")

def print_info(text):
    """Print formatted info message."""
    print(f"{Colors.CYAN}[*] {text}{Colors.RESET}")

def print_success(text):
    """Print formatted success message."""
    print(f"{Colors.GREEN}[+] {text}{Colors.RESET}")

def print_suspicious(text):
    """Print formatted suspicious finding message."""
    print(f"{Colors.YELLOW}[?] SUSPICIOUS: {text}{Colors.RESET}")

# Magic bytes for common file types we might find after XOR decoding
MAGIC_BYTES = {
    b'MZ': ('DOS/PE executable', '.exe'),
    b'\x7fELF': ('ELF executable', '.elf'),
    b'PK\x03\x04': ('ZIP archive', '.zip'),
    b'\x1f\x8b\x08': ('GZIP archive', '.gz'),
    b'BZh': ('BZIP2 archive', '.bz2'),
    b'\x89PNG': ('PNG image', '.png'),
    b'\xff\xd8\xff': ('JPEG image', '.jpg'),
    b'GIF8': ('GIF image', '.gif'),
    b'%PDF': ('PDF document', '.pdf'),
    b'\xfd7zXZ': ('XZ archive', '.xz'),
    b'Rar!\x1a\x07': ('RAR archive', '.rar'),
    b'<?xml': ('XML document', '.xml'),
    b'<!DOCTYPE': ('HTML document', '.html'),
    b'<html': ('HTML document', '.html'),
    b'function': ('JavaScript', '.js'),
    b'eval(': ('JavaScript', '.js'),
    b'ethereum': ('Ethereum-related code', '.eth.js'),
    b'MetaMask': ('MetaMask-related code', '.metamask.js'),
    b'web3': ('Web3-related code', '.web3.js'),
    b'wallet': ('Crypto wallet code', '.wallet.js'),
    b'0x': ('Ethereum address', '.eth.txt'),
    b'\\\\x': ('Obfuscated JavaScript', '.obfuscated.js'),
    b'\\\\u00': ('Obfuscated JavaScript', '.obfuscated.js'),
    b'iCCP': ('ICC Profile', '.icc'),
    b'com.apple.wallpaper': ('Apple Wallpaper', '.wallpaper.bin'),
}

# Common XOR keys used in malware
COMMON_XOR_KEYS = [
    # Single-byte keys
    bytes([i]) for i in range(1, 256)
] + [
    # Common multi-byte keys
    b'x', b'XOR', b'xor', b'key', b'KEY', b'0123456789',
    b'ABCDEFGHIJKLMNOPQRSTUVWXYZ', b'abcdefghijklmnopqrstuvwxyz',
    b'MetaMask', b'Wallet', b'Ethereum', b'Bitcoin', b'Crypto',
    b'NFT', b'Token', b'Blockchain',
    b'Apple', b'Safari', b'Wallpaper', b'Extension',
    b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09', 
    b'\xff\xfe\xfd\xfc\xfb\xfa\xf9\xf8\xf7\xf6'
]

# Crypto-related patterns we're hunting for
CRYPTO_PATTERNS = [
    b'metamask', b'ethereum', b'bitcoin', b'binance', b'coinbase',
    b'wallet', b'privatekey', b'seedphrase', b'mnemonic', 
    b'recover wallet', b'recovery phrase', b'seed phrase',
    b'web3', b'chainId', b'dapp', b'token', b'NFT',
    # Ethereum address pattern
    b'0x[0-9a-fA-F]{40}',
    # MetaMask patterns
    b'injectProvider', b'request', b'eth_accounts',
    # Browser extension related
    b'extension', b'chrome.runtime', b'browser.runtime',
    # Exfiltration-related
    b'send', b'post', b'fetch', b'XMLHttpRequest',
    # Apple-specific
    b'com.apple.wallpaper', b'extension-com.apple.wallpaper'
]

def xor_data(data, key):
    """XOR the data with the provided key."""
    if not key:
        return data
        
    key_len = len(key)
    return bytes(data[i] ^ key[i % key_len] for i in range(len(data)))

def rolling_xor_data(data, start_key):
    """Apply a rolling XOR where each byte affects the next decryption key."""
    result = bytearray()
    key = start_key[0]
    
    for byte in data:
        result.append(byte ^ key)
        key = (key + byte) & 0xff
        
    return bytes(result)

def identify_file_type(data):
    """Try to identify the file type based on magic bytes."""
    if not data or len(data) < 4:
        return None, None
        
    # Check for known magic bytes
    for magic, (desc, ext) in MAGIC_BYTES.items():
        if data.startswith(magic):
            return desc, ext
            
    # Check for text files
    if all(32 <= b <= 126 or b in (9, 10, 13) for b in data[:64]):
        # Additional checks for specific text file types
        if b'{' in data[:64] and (b':' in data[:64] or b',' in data[:64]):
            return 'JSON data', '.json'
        elif b'function' in data[:100] or b'var ' in data[:100] or b'const ' in data[:100]:
            return 'JavaScript code', '.js'
        elif b'<?php' in data[:100]:
            return 'PHP code', '.php'
        elif b'#include' in data[:100] or b'int ' in data[:100] or b'void ' in data[:100]:
            return 'C/C++ code', '.c'
        elif b'import ' in data[:100] or b'def ' in data[:100] or b'class ' in data[:100]:
            return 'Python code', '.py'
        else:
            return 'Text file', '.txt'
    
    # Check for high entropy (possibly encrypted)
    entropy = calculate_entropy(data[:1024])
    if entropy > 7.5:
        return 'High entropy data (possibly encrypted)', '.bin'
        
    return 'Unknown binary data', '.bin'

def calculate_entropy(data):
    """Calculate the Shannon entropy of the data."""
    if not data:
        return 0
        
    entropy = 0
    size = len(data)
    counts = {}
    
    # Count occurrences of each byte
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1
    
    # Calculate entropy
    for count in counts.values():
        probability = count / size
        entropy -= probability * (math.log(probability, 2) if probability > 0 else 0)
        
    return entropy

def find_crypto_patterns(data):
    """Check for crypto wallet and related patterns in the data."""
    findings = []
    
    # Convert data to lowercase for case-insensitive matching
    data_lower = data.lower()
    
    for pattern in CRYPTO_PATTERNS:
        pattern_lower = pattern.lower()
        if pattern_lower in data_lower:
            pos = data_lower.find(pattern_lower)
            context_start = max(0, pos - 20)
            context_end = min(len(data), pos + len(pattern) + 20)
            context = data[context_start:context_end]
            
            # Clean up context for display
            printable_context = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in context)
            
            findings.append((pattern.decode('utf-8', errors='replace'), printable_context))
    
    return findings

def extract_interesting_strings(data):
    """Extract interesting strings from the data."""
    strings = []
    current_string = []
    
    for byte in data:
        if 32 <= byte <= 126:  # Printable ASCII
            current_string.append(chr(byte))
        else:
            if current_string and len(current_string) >= 4:
                strings.append(''.join(current_string))
            current_string = []
    
    # Don't forget the last string
    if current_string and len(current_string) >= 4:
        strings.append(''.join(current_string))
    
    # Filter for interesting strings
    interesting_strings = []
    keywords = ['wallet', 'crypto', 'meta', 'mask', 'ethereum', 'bitcoin', 'key', 'token',
                'nft', 'extension', 'safari', 'chrome', 'apple', 'password', 'secret',
                'seed', 'mnemonic', 'phrase', 'recovery', 'inject', 'http', 'fetch', 'post']
    
    for string in strings:
        if any(keyword.lower() in string.lower() for keyword in keywords):
            interesting_strings.append(string)
    
    return interesting_strings

def process_binary_file(file_path, output_dir):
    """Process a binary file with various XOR keys and extract potential hidden executables."""
    print_header(f"ANALYZING {os.path.basename(file_path)}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    file_base = os.path.splitext(os.path.basename(file_path))[0]
    
    # Read the binary data
    with open(file_path, 'rb') as f:
        data = f.read()
    
    print_info(f"File size: {len(data):,} bytes")
    
    # Try various XOR keys
    findings = []
    
    print_info(f"Testing {len(COMMON_XOR_KEYS)} XOR keys...")
    
    for key_idx, key in enumerate(COMMON_XOR_KEYS):
        # Apply XOR decoding
        decoded = xor_data(data, key)
        
        # Identify file type
        file_type, extension = identify_file_type(decoded)
        
        if file_type:
            # Check for crypto patterns
            crypto_patterns = find_crypto_patterns(decoded)
            
            if crypto_patterns or file_type in ('JavaScript code', 'JSON data'):
                # This looks promising
                key_hex = binascii.hexlify(key).decode('ascii')
                finding = {
                    'key': key,
                    'key_hex': key_hex,
                    'file_type': file_type,
                    'extension': extension,
                    'crypto_patterns': crypto_patterns,
                    'decoded_data': decoded
                }
                findings.append(finding)
                
                print_success(f"Found potential {file_type} with XOR key {key_hex}")
                for pattern, context in crypto_patterns:
                    print_suspicious(f"  - Crypto pattern: {pattern} in context: {context}")
                
                # Save the decoded file
                output_file = os.path.join(output_dir, f"{file_base}_xor_key_{key_hex}{extension}")
                with open(output_file, 'wb') as f:
                    f.write(decoded)
                print_info(f"  - Saved to {output_file}")
    
    # Try rolling XOR with common initial keys
    print_info(f"Testing rolling XOR with {len(COMMON_XOR_KEYS[:10])} initial keys...")
    
    for key in COMMON_XOR_KEYS[:10]:  # Just use the first few keys to save time
        initial_key = key[:1]  # Use just the first byte as the initial key
        
        # Apply rolling XOR decoding
        decoded = rolling_xor_data(data, initial_key)
        
        # Identify file type
        file_type, extension = identify_file_type(decoded)
        
        if file_type:
            # Check for crypto patterns
            crypto_patterns = find_crypto_patterns(decoded)
            
            if crypto_patterns or file_type in ('JavaScript code', 'JSON data'):
                # This looks promising
                key_hex = binascii.hexlify(initial_key).decode('ascii')
                finding = {
                    'key': initial_key,
                    'key_hex': key_hex,
                    'key_type': 'rolling',
                    'file_type': file_type,
                    'extension': extension,
                    'crypto_patterns': crypto_patterns,
                    'decoded_data': decoded
                }
                findings.append(finding)
                
                print_success(f"Found potential {file_type} with rolling XOR key {key_hex}")
                for pattern, context in crypto_patterns:
                    print_suspicious(f"  - Crypto pattern: {pattern} in context: {context}")
                
                # Save the decoded file
                output_file = os.path.join(output_dir, f"{file_base}_rolling_xor_key_{key_hex}{extension}")
                with open(output_file, 'wb') as f:
                    f.write(decoded)
                print_info(f"  - Saved to {output_file}")
    
    # Check for interesting strings in any of our findings
    if findings:
        for finding in findings:
            interesting_strings = extract_interesting_strings(finding['decoded_data'])
            if interesting_strings:
                print_info(f"Interesting strings found in {finding['file_type']} (XOR key: {finding['key_hex']}):")
                for i, string in enumerate(interesting_strings[:10]):
                    print_info(f"  - {string}")
                if len(interesting_strings) > 10:
                    print_info(f"  - ... and {len(interesting_strings) - 10} more")
    
    # Summary
    print_header("ANALYSIS SUMMARY")
    
    if findings:
        print_success(f"Found {len(findings)} potential hidden executables/scripts")
        print_info(f"All decoded files saved to {output_dir}")
    else:
        print_warning("No hidden executables or crypto wallet targeting code found")
    
    return findings

if __name__ == "__main__":
    import argparse
    import math  # Required for entropy calculation
    
    parser = argparse.ArgumentParser(description="Binary Payload XOR Mutation Extractor")
    parser.add_argument("input_file", help="Input binary file to analyze")
    parser.add_argument("-o", "--output-dir", help="Output directory for extracted files")
    
    args = parser.parse_args()
    
    input_file = os.path.abspath(args.input_file)
    output_dir = args.output_dir if args.output_dir else os.path.join(os.path.dirname(input_file), "extracted_payloads")
    
    if not os.path.exists(input_file):
        print_warning(f"Input file not found: {input_file}")
        sys.exit(1)
        
    process_binary_file(input_file, output_dir)
