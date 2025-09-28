#!/usr/bin/env python3
"""
Test script to verify the dependency protection functionality
"""

import os
import sys
import tempfile

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from custom_nodes_installer import analyze_requirements, parse_requirement_line

def test_requirement_parsing():
    """Test the requirement line parsing"""
    print("Testing requirement line parsing...")
    
    test_cases = [
        "numpy>=1.21.0",
        "torch==1.13.0",
        "pillow",
        "opencv-python>=4.5.0",
        "# This is a comment",
        "",
        "transformers>=4.20.0",
        "some-custom-package==1.0.0"
    ]
    
    for line in test_cases:
        parsed = parse_requirement_line(line)
        if parsed:
            print(f"  '{line}' -> name: {parsed['name']}, constraint: '{parsed['constraint']}'")
        else:
            print(f"  '{line}' -> Skipped (comment or empty)")
    print()

def test_dependency_analysis():
    """Test the dependency analysis with a sample requirements file"""
    print("Testing dependency analysis...")
    
    # Create a temporary requirements file with mixed dependencies
    sample_requirements = """# Sample requirements file
torch>=1.13.0
numpy>=1.21.0
pillow>=8.0.0
opencv-python>=4.5.0
transformers>=4.20.0
some-custom-package==1.0.0
another-package>=2.0.0
requests>=2.25.0
# Comment line
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_requirements)
        temp_path = f.name
    
    try:
        analysis = analyze_requirements(temp_path, "test-repo")
        
        print(f"Analysis results for test-repo:")
        print(f"  Total requested: {analysis['total_requested']}")
        print(f"  Safe to install: {len(analysis['safe_to_install'])}")
        print(f"  Skipped critical: {len(analysis['skipped_critical'])}")
        print(f"  Already installed: {len(analysis['already_installed'])}")
        
        if analysis['safe_to_install']:
            print(f"  Safe packages: {', '.join(analysis['safe_to_install'])}")
        
        if analysis['skipped_critical']:
            print(f"  Skipped critical: {', '.join(analysis['skipped_critical'])}")
        
        if analysis['already_installed']:
            print(f"  Already installed: {', '.join(analysis['already_installed'])}")
            
    finally:
        os.unlink(temp_path)

def main():
    """Run all tests"""
    print("=== Dependency Protection Test Suite ===\n")
    
    test_requirement_parsing()
    test_dependency_analysis()
    
    print("\n=== Tests completed ===")
    print("The dependency protection system will:")
    print("1. Skip critical ComfyUI dependencies (torch, numpy, etc.)")
    print("2. Skip already installed packages")
    print("3. Install only new, non-critical dependencies with --no-deps flag")
    print("4. Log all actions for debugging")

if __name__ == "__main__":
    main()