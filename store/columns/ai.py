"""
AI / Agent columns — agent_name, messages, summary, message_count, metadata.

Used by the Conversation Storable in ai/memory.py.
"""

from store.columns import REGISTRY

REGISTRY.define("agent_name", str,
    description="Name of the AI agent that owns the conversation",
    semantic_type="identifier",
    role="dimension",
    synonyms=["agent", "bot_name"],
)

REGISTRY.define("messages", list,
    description="Ordered list of conversation messages (role + content dicts)",
    role="attribute",
)

REGISTRY.define("summary", str,
    description="Auto-generated summary of the conversation",
    semantic_type="free_text",
    role="attribute",
    nullable=True,
)

REGISTRY.define("message_count", int,
    description="Number of messages in the conversation",
    role="measure",
    unit="messages",
)


# Note: 'metadata' (dict, attribute) is already defined in media.py
