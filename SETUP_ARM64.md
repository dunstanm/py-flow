# Fresh Linux ARM Laptop Setup Plan for py-flow

This document outlines the setup plan for a new ARM64 laptop (e.g., Snapdragon X Elite, Surface Pro 11) to safely and successfully run the `py-flow` platform within WSL.

## 1. WSL (Ubuntu) Installation
1. Start an Administrator Windows command prompt and install Ubuntu WSL: 
   ```bash
   wsl --install -d Ubuntu
   ```
2. Verify you are running WSL 2: `wsl --list --verbose`
3. Open your Ubuntu terminal to proceed with Linux system setup.

## 2. Docker & x86 Emulation (Critical for ARM64)
While we aim for native `aarch64` wheels where possible, some legacy dependencies or database binaries may fall back to x86. You must prepare a `binfmt_misc` layer.
1. **Install Docker Engine** natively in WSL Ubuntu (or use Docker Desktop with WSL integration enabled). 
2. Register the emulator handlers using QEMU:
   ```bash
   sudo docker run --privileged --rm tonistiigi/binfmt --install all
   ```
3. Test that x86-64 docker emulation is working:
   ```bash
   sudo docker run --platform linux/amd64 alpine uname -m
   ```
   *(Expected output: `x86_64`)*

## 3. Core Toolchain: CMake, Python, and uv
1. **C++ Build Chains & Python**: You will likely need to compile wheels for non-native dependencies. Note: The project currently requires Python 3.10/3.11 compatibility.
   ```bash
   sudo apt update && sudo apt install -y build-essential cmake git python3 python3-pip python3-venv python3-dev libssl-dev
   ```
2. **Install `uv` (Fast Python Package Manager)**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   *(Be sure to reload your bashrc: `source ~/.bashrc`)*

## 4. py-flow Repository Checkout
1. Clone the project onto the native Linux filesystem:
   ```bash
   cd ~
   git clone <repo-url> py-flow
   cd py-flow
   ```
2. Checkout the specific `dev-setup-handover` branch created for the new machine:
   ```bash
   git fetch origin
   git checkout dev-setup-handover
   ```

## 5. Virtual Environment & Dependencies
1. Create your managed environment using `uv` and activate it:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
2. **ARM64 DB Compatibility (pgserver)**: The default `pgserver` package does not cleanly deploy an aarch64 binary. Install the pixeltable native shim:
   ```bash
   uv pip install pixeltable-pgserver
   ```
3. **Install Workspace Extras**:
   Install the project along with every module subsystem needed for testing and frontend:
   ```bash
   uv pip install -e ".[server,marketdata,timeseries,lakehouse,media,ai,datacube,client,dev]"
   ```

## 6. Environment Keys & Kickoff
Create a local `.env` file copying any team variables. Note that a mock API key might be necessary to unblock `pytest`.
```bash
echo "GEMINI_API_KEY=dummy_key_for_local_testing" > .env
```
Ensure VS Code `.vscode/settings.json` points to this `.env` file. You are now prepared to run `pytest` and `python scripts/...` locally.
