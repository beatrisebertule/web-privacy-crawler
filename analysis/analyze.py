#!/usr/bin/env python3
"""Run all 01_analysis.py ... 12_analysis.py files
"""
import subprocess
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parent
OUTDIR = "results"

if __name__=="__main__":
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for i in range(1, 13):
        analysis = ANALYSIS_DIR / f"{i:02d}_analysis.py"
        print("\n")
        print("=" * 45)
        print(f"          RUNNING ANALYSIS {i}")
        print("=" * 45)
        print()
        subprocess.run([sys.executable, analysis], check=True)