#!/usr/bin/env python3
"""Run all 01_analysis.py ... 12_analysis.py files
"""
import subprocess
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parent

for i in range(1, 13):
    analysis = ANALYSIS_DIR / f"{i:02d}_analysis.py"
    print("Running analysis", i)
    subprocess.run([sys.executable, analysis], check=True)