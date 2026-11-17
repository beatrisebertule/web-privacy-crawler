# Analysis

Analysis of the crawl data for Online Tracking & Privacy (NWI-IMC074) group assignment. Each analysis is a separate script and can be run on its own, or alternatively, they can be run in sequence with a script.

## Run

From any folder, after the crawls have finished.

A single analysis:

```
python analysis/xx_analysis.py
```

All of them at once:

```
python analysis/analyze.py
```

`analyze.py` runs each script as a separate process in sequence.

Script numbers match the question numbers in the assignment.

## Output

Each individual script outputs the results of the analysis in `results/` at the repo root. Depending on the script these can be in CSV, JSON and/or PNG format.