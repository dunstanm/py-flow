import asyncio
import os
import sys
import threading
import time
import signal
import logging

from marketdata.admin import MarketDataServer
from streaming.admin import StreamingServer
from core.process import ServerManager, kill_process_on_port

# Setup logging to see process lifecycle events
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Launcher")

def main():
    print("=" * 60)
    print("  SWAP CURVE ANALYTICS DASHBOARD — ROBUST LAUNCHER")
    print("  Dual-Engine Fitting: py-flow vs QuantLib")
    print("=" * 60)

    # 1. Initialize ServerManager for holistic lifecycle tracking
    manager = ServerManager()

    # Define ports we need to clear to ensure we pick up fresh code
    DASHBOARD_PORT = 8050
    MARKET_DATA_PORT = 8000
    STREAMING_PORT = 10000

    print("→ Purging stale infra to ensure fresh code is picked up...")
    manager.purge_infrastructure(
        ports=[MARKET_DATA_PORT, STREAMING_PORT, DASHBOARD_PORT],
        patterns=["uvicorn", "deephaven", "marketdata.server"]
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # 2. Track and Start Market Data Server (port 8000)
        md = MarketDataServer(port=MARKET_DATA_PORT)
        manager.track(md)
        print("→ Starting MarketDataServer (Live OIS Feed)...")
        loop.run_until_complete(md.start())
        
        # 3. Track and Start Streaming Server (Deephaven)
        print("→ Starting StreamingServer (Deephaven Engine)...")
        try:
            ss = StreamingServer(port=STREAMING_PORT)
            manager.track(ss)
            ss.start()
            # Activate ticking tables now that Deephaven is running
            from streaming import activate
            activate()
        except Exception as e:
            print(f"  ⚠ StreamingServer skipped/failed: {e}")

        # 4. Launch the Panel App (Dashboard)
        from dashboard.apps.swap_curve import create_app
        print(f"→ Launching Dashboard on http://localhost:{DASHBOARD_PORT}")
        print("  (Close terminal or use Ctrl+C to shutdown all services)\n")
        
        app = create_app()
        # serve() blocks until the process is terminated
        try:
            # We don't track 'app' directly as serve() is blocking.
            # Instead, we rely on the try-finally block for cleanup.
            server = app.serve(port=DASHBOARD_PORT, show=False)
            
            # Keep monitoring if serve() somehow returns early
            while True:
                time.sleep(1)
        except Exception as e:
            print(f"❌ Dashboard server failed: {e}")

    except KeyboardInterrupt:
        print("\nInterrupt received. Initiating shutdown sequence...")
    finally:
        print("💡 Shutting down all background services...")
        if loop.is_running():
            loop.run_until_complete(manager.stop_all())
        else:
            # Fallback for sync shutdown
            manager.stop_all_sync()
        print("✓ Cleanup complete. Goodbye.")

if __name__ == "__main__":
    main()
