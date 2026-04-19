# Antigravity Context: Guidelines for ARM64 WSL Environments

Agent assistants (Antigravity instances) instantiated on this localized machine must deeply respect the following environmental constraints native to WSL ARM platforms, as deduced by prior documentation and trial-and-error.

## 1. The "Flight Recorder" Protocol (Log-Before-Action)
Due to occasional VS Code connection dropping under intense `pgserver` load or emulation CPU pressure, you **must persist your state intent** before risky long-running shell loops or aggressive refactoring tests.
**Rule:** When undertaking a task, log a brief single-line Markdown note containing your current task objective into:
`/home/dunstanm/py-flow/.agent_activity.log`
*(Upon unexpected disconnection or session restart, your very first action should be to read this file and resume where left off.)*

## 2. Emulated Overheads vs Native Code
A key instability on WSL ARM concerns database provisioning.
* `questdb` and `deephaven-server` are `aarch64` native and performant. Keep relying on them for streaming logic tests.
* `pgserver` must be handled through a shim namespace substitution pointing to `pixeltable_pgserver` natively. If there is a `uuid-ossp.control` not found or permission error, this implies the shim has failed to export its actual package path `__file__`. Never try to substitute with x86 pgserver emulation via pip uninstalling the native shim unless natively debugging Docker emulator boundaries! 

## 3. Conftest `conftest.py` Blocking Limits
If attempting to execute localized unit or mock tests (i.e. `pytest -k test_store_simple`), the `conftest.py` may fail out aggressively by attempting to execute `Deephaven` server contexts that are currently turned off.
**Isolating Fix Pattern**: Instead of modifying the tests or forcing dependencies, wrap your test execution by temporarily hiding the config:
```bash
mv tests/conftest.py tests/conftest.py.bak
python3 -m pytest tests/test_simple.py
mv tests/conftest.py.bak tests/conftest.py
```

## 4. Workaround for Run Command Workspace Trust Issues
If the `run_command` tool flags security exceptions regarding "Workspace restricted / no access", and the user cannot elevate trustworthiness naturally, immediately halt further blind commands and request the User execute manually supplied Bash code blocks instead. Do not loop fail state.
