"""
core/process.py — Platform Utilities for Robust Process Management
==================================================================
Shared library for starting, stopping, and cleaning up server processes
across applications (dashboard, tests, data loaders).

Supports Linux-only 'purge' which clears listening ports via lsof/psutil.
"""

import logging
import os
import signal
import subprocess
import time
from typing import List, Optional, Union

import psutil

logger = logging.getLogger(__name__)

def kill_process_on_port(port: int, force: bool = True):
    """Identify and terminate any process listening on the given TCP port."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # We call the method explicitly to avoid psutil 7.x+ attribute issues
            conns = proc.connections(kind='inet')
            for conn in conns:
                if conn.laddr.port == port:
                    pid = proc.info['pid']
                    name = proc.info['name']
                    logger.info(f"  Killing process {name} (pid={pid}) on port {port}...")
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
                    proc.wait(timeout=5)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue

def kill_by_patterns(patterns: List[str], force: bool = True):
    """Terminate any process whose command line matches any of the given patterns."""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = " ".join(proc.info.get('cmdline') or [])
            if not cmdline:
                continue
            for pattern in patterns:
                if pattern in cmdline:
                    name = proc.info.get('name', 'unknown')
                    pid = proc.info['pid']
                    logger.info(f"  Terminating stale process {name} (pid={pid}) matching '{pattern}'...")
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
                    proc.wait(timeout=5)
                    break 
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            continue

class ServerManager:
    """Manages a collection of sub-servers, ensuring clean startup/shutdown."""
    
    def __init__(self):
        self._managed_servers = []

    def purge_infrastructure(self, ports: List[int], patterns: List[str]):
        """Clear the decks of any existing services on these ports or matching patterns."""
        logger.info("Purging infrastructure for fresh start...")
        for port in ports:
            kill_process_on_port(port)
        if patterns:
            kill_by_patterns(patterns)
        # Give OS time to recycle sockets
        time.sleep(1)

    def track(self, server_instance):
        """Add a server instance (with .start() and .stop() methods) to be managed."""
        self._managed_servers.append(server_instance)
        return server_instance

    async def start_all(self):
        """Start all tracked servers."""
        for srv in self._managed_servers:
            if hasattr(srv, 'start'):
                # Handle both async and sync start
                import inspect
                if inspect.iscoroutinefunction(srv.start):
                    await srv.start()
                else:
                    srv.start()

    async def stop_all(self):
        """Stop all tracked servers in reverse order (handles both async and sync)."""
        import inspect
        for srv in reversed(self._managed_servers):
            if hasattr(srv, 'stop'):
                try:
                    if inspect.iscoroutinefunction(srv.stop):
                        await srv.stop()
                    else:
                        res = srv.stop()
                        if inspect.iscoroutine(res):
                            await res
                except Exception as e:
                    logger.error(f"Error stopping server {srv}: {e}")
        self._managed_servers = []

    def stop_all_sync(self):
        """Synchronous version of stop_all for use in signal handlers or finalizers."""
        import inspect
        import asyncio
        for srv in reversed(self._managed_servers):
            if hasattr(srv, 'stop'):
                try:
                    if inspect.iscoroutinefunction(srv.stop):
                        asyncio.run(srv.stop())
                    else:
                        res = srv.stop()
                        if inspect.iscoroutine(res):
                            asyncio.run(res)
                except Exception as e:
                    logger.error(f"Error stopping server {srv} (sync): {e}")
        self._managed_servers = []

def run_with_restarts(main_func, ports_to_clean: List[int], patterns_to_clean: List[str]):
    """Wrapper to run a main function with automatic cleanup of resources on exit."""
    manager = ServerManager()
    
    def signal_handler(sig, frame):
        print("\n[ServerManager] Interrupted. Cleaning up...")
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.stop_all())
        else:
            # Fallback for sync
            for port in ports_to_clean:
                 kill_process_on_port(port)
            kill_by_patterns(patterns_to_clean)
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initial purge to capture orphaned processes from previous runs
        manager.purge_infrastructure(ports_to_clean, patterns_to_clean)
        main_func(manager)
    except Exception as e:
        print(f"[ServerManager] Critical Failure: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Final cleanup
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(manager.stop_all())
        else:
            # Sync variant
            for port in ports_to_clean:
                 kill_process_on_port(port)
            kill_by_patterns(patterns_to_clean)
