"""
Media — Unstructured Data Storage & Search
============================================
Upload, download, and search documents, images, audio, and video
with full-text search, semantic search, and bi-temporal audit trail.

Binary content stored in MinIO S3. Metadata stored as Document
Storable objects in PG with tsvector + pgvector indexed search.

Usage::

    from ai import AI
    from media import MediaStore, Document

    ai = AI(api_key="...")
    ms = MediaStore(s3_endpoint="localhost:9002", ai=ai)

    # Upload (auto-chunks + embeds when ai is set)
    doc = ms.upload("reports/q1.pdf", title="Q1 Report", tags=["research"])

    # Search — three modes
    results = ms.search("interest rate swap")           # full-text (keywords)
    results = ms.semantic_search("risk transfer")       # vector (meaning)
    results = ms.hybrid_search("credit derivatives")    # RRF fusion (best)

    # Download
    data = ms.download(doc)

    ms.close()
"""

from media.store import MediaStore
from media.models import Document

__all__ = [
    "MediaStore",
    "Document",
]
