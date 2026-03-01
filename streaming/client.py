"""
streaming.client — Lightweight client for connecting to a streaming server.

Wraps the pydeephaven session — users never import pydeephaven directly.

Usage::

    from streaming import StreamingClient

    with StreamingClient() as c:
        tables = c.list_tables()
        df = c.open_table("prices_live").to_arrow().to_pandas()
        c.run_script('filtered = prices_live.where(["Symbol = `AAPL`"])')
"""

from __future__ import annotations


class StreamingClient:
    """Lightweight client for querying a remote streaming server.

    Connects via pydeephaven (no Java needed on the client machine).
    """

    def __init__(self, host: str = "localhost", port: int = 10000):
        from pydeephaven import Session

        self.host = host
        self.port = port
        self.session = Session(host=host, port=port)
        print(f"Connected to streaming server at {host}:{port}")

    def list_tables(self):
        """Return names of all tables in the server's global scope."""
        return self.session.tables

    def open_table(self, name):
        """Open a server-side table by name."""
        return self.session.open_table(name)

    def run_script(self, script: str):
        """Execute a Python script on the server. Use this to create
        custom derived tables that live server-side."""
        self.session.run_script(script)

    def bind_table(self, name: str, table):
        """Publish a client-created table to the server's global scope
        so it is visible in the web IDE and to other sessions."""
        self.session.bind_table(name=name, table=table)

    def close(self):
        """Close the session."""
        self.session.close()
        print("Session closed.")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
