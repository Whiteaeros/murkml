"""Wrapper that restarts download_batch.py on crash.

The USGS dataretrieval library has cumulative resource issues that cause
silent crashes after ~20 API calls. This wrapper detects when the process
dies and restarts it, relying on the parquet caching to resume from
where it left off.
"""
import subprocess
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SCRIPT = Path(__file__).parent / "download_batch.py"
PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
MAX_RESTARTS = 30  # enough for 168 calls at ~20 calls per restart

def main():
    args = ["--continuous-only", "--skip-merge", "--batch-size", "15"]

    for restart in range(MAX_RESTARTS):
        logger.info(f"\n{'='*60}")
        logger.info(f"ATTEMPT {restart + 1}/{MAX_RESTARTS}")
        logger.info(f"{'='*60}")

        result = subprocess.run(
            [str(PYTHON), str(SCRIPT)] + args,
            capture_output=False,
            timeout=7200,  # 2 hour max per attempt
        )

        if result.returncode == 0:
            logger.info("Download completed successfully!")
            break
        else:
            logger.warning(f"Process exited with code {result.returncode}")
            logger.info("Restarting in 10 seconds (cache will skip completed calls)...")
            time.sleep(10)
    else:
        logger.error(f"Download failed after {MAX_RESTARTS} restarts")

if __name__ == "__main__":
    main()
