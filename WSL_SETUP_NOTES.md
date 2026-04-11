# WSL Environment Setup Guide

## Quick Start on a new Machine

1. Ensure **WSL 2** is installed (`wsl --install -d Ubuntu`).
2. Clone this repository locally into the WSL filesystem (e.g. `~/py-flow`) to ensure rapid IO file access. Avoid cloning into the mounted `/mnt/c` Windows drive to prevent latency issues with python processing loops.
3. Use the system default Python or ensure you're on at least **Python 3.10**:
   `sudo apt update && sudo apt install python3 python3-pip python3-venv`
4. Setup virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Note for ARM64 Architectures (Snapdragon / Mac Parallels)
If your new machine is ARM-based, the py-flow codebase is already protected against WSL matrix errors (we merged the fixes via PR 2).
* `duckdb` and `deephaven` support aarch64 natively—ensure your package manager doesn't fallback to x86 translation layers! 
* Re-run `pytest` locally after install to verify `math.exp` overflow limits remain bounded correctly on your processor.

If you encounter connection drops with the dashboard, double check that your WSL networking allows outbound localhost access.
