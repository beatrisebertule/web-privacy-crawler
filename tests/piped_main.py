"""
Runs an analysis script's `main` in a fresh Python with stdout piped.

Stdout encoding is forced to cp1252, the Windows default for piped output, so the tests behave the
same on every OS.
"""

# Standard library imports
import os
import subprocess
import sys
from pathlib import Path

ANALYSIS_DIRECTORY = Path(__file__).resolve().parent.parent / "analysis"

DRIVER = """
import importlib
import sys
from pathlib import Path

sys.path.insert(0, {analysis!r})
script = importlib.import_module({module!r})
script.CRAWL_DIRECTORY = Path({crawl!r})
script.RESULTS_DIRECTORY = Path({results!r})
script.SITE_LIST_PATH = Path({site_list!r})
script.main()
"""


def run_main_piped(
    module: str,
    crawl_directory: Path,
    results_directory: Path,
    site_list_path: Path,
) -> subprocess.CompletedProcess[bytes]:
    """
    Run `main` of an analysis script on the given folders.

    :param module: script name without `.py`, such as "11_analysis"
    :param crawl_directory: folder of `.har` files
    :param results_directory: where the CSV goes
    :param site_list_path: site list CSV
    :return: Finished process with stdout and stderr as bytes.
    """
    code = DRIVER.format(
        analysis=str(ANALYSIS_DIRECTORY),
        module=module,
        crawl=str(crawl_directory),
        results=str(results_directory),
        site_list=str(site_list_path),
    )
    environment = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    environment.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=environment,
        timeout=120,
    )
