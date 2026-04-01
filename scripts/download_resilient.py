"""Resilient download wrapper using Popen + polling.

subprocess.run() hangs on Windows with pythonw.exe when the child crashes.
This uses Popen with explicit polling to detect child death reliably.
"""
import subprocess
import sys
import time
import os
import logging
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT / "data" / "download_resilient_log.txt"
CHILD_LOG = PROJECT / "data" / "download_child_log.txt"
PYTHON = str(PROJECT / ".venv" / "Scripts" / "python.exe")
SCRIPT = str(PROJECT / "scripts" / "download_batch.py")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, mode="a")],
)
logger = logging.getLogger(__name__)


def kill_zombie_pythons():
    """Kill ALL Python processes related to download_batch (zombies from prior runs).

    The venv python.exe is a thin launcher (~5MB) that spawns the real
    cpython interpreter (~1GB). Both must be killed.
    """
    try:
        # Use tasklist for reliable PID + memory parsing
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10,
        )
        my_pid = os.getpid()
        large_pids = []
        for line in result.stdout.strip().split("\n")[1:]:
            # Format: "python.exe","PID","Session","#","Mem K"
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 5:
                try:
                    pid = int(parts[1])
                    mem_str = parts[4].replace(',', '').replace(' K', '').strip()
                    mem_kb = int(mem_str)
                except (ValueError, IndexError):
                    continue
                # Kill any python.exe using >500MB (definitely a zombie download)
                if mem_kb > 500000 and pid != my_pid:
                    large_pids.append((pid, mem_kb))

        for pid, mem_kb in large_pids:
            logger.info(f"  Killing zombie PID {pid} ({mem_kb // 1024} MB)")
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=5)

        if large_pids:
            logger.info(f"  Killed {len(large_pids)} zombies, freed ~{sum(m for _, m in large_pids) // 1024} MB")
    except Exception as e:
        logger.warning(f"  Zombie cleanup failed: {e}")


def count_v2_files():
    v2_dir = PROJECT / "data" / "continuous_batch_v2"
    if not v2_dir.exists():
        return 0
    return len(list(v2_dir.glob("v2_*.parquet")))


def run_download_with_file_monitoring():
    """Run download and monitor file count to detect stalls.

    Instead of relying on subprocess exit detection (broken on Windows
    with venv launchers), we monitor the v2 file count. If no new files
    appear for 10 minutes, we assume the child is dead.
    """
    args = [PYTHON, SCRIPT, "--continuous-only", "--skip-merge", "--batch-size", "15"]

    f = open(CHILD_LOG, "a")
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(PROJECT),
            stdout=f,
            stderr=subprocess.STDOUT,
        )

        last_file_count = count_v2_files()
        last_progress_time = time.time()
        stall_timeout = 600  # 10 minutes with no new files = stalled

        while True:
            time.sleep(30)

            # Check if process exited
            ret = proc.poll()
            if ret is not None:
                return ret

            # Check file progress
            current_count = count_v2_files()
            if current_count > last_file_count:
                last_file_count = current_count
                last_progress_time = time.time()

            # Stall detection — kill if no new files for 10 min
            elapsed = time.time() - last_progress_time
            if elapsed > stall_timeout:
                logger.warning(f"  No new files in {elapsed:.0f}s, killing stalled process tree")
                # Kill the launcher AND any child interpreters
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/F", "/T"],
                        capture_output=True, timeout=10,
                    )
                except Exception:
                    pass
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass
                return -1
    except Exception as e:
        logger.error(f"  Monitor error: {e}")
        return -2
    finally:
        f.close()


def main():
    max_restarts = 50

    logger.info("=" * 60)
    logger.info("RESILIENT DOWNLOAD STARTED (Popen + polling)")
    logger.info(f"  Target: 168 API calls, batch-size 15")
    logger.info(f"  Current files: {count_v2_files()}")
    logger.info("=" * 60)

    for attempt in range(1, max_restarts + 1):
        files_before = count_v2_files()
        logger.info(f"\n--- ATTEMPT {attempt}/{max_restarts} ({files_before} files) ---")

        kill_zombie_pythons()
        time.sleep(3)

        exit_code = run_download_with_file_monitoring()

        files_after = count_v2_files()
        new_files = files_after - files_before

        logger.info(f"  Exit code {exit_code}, +{new_files} files ({files_after} total)")

        if exit_code == 0:
            logger.info(f"  COMPLETED SUCCESSFULLY!")
            break

        if files_after >= 168:
            logger.info(f"  All 168 files present — download complete!")
            break

        logger.info(f"  Restarting in 15 seconds...")
        time.sleep(15)
    else:
        logger.error(f"  Failed after {max_restarts} attempts")

    logger.info(f"\nFinal: {count_v2_files()} files")


if __name__ == "__main__":
    main()
