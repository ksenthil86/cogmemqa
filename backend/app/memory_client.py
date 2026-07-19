"""
Conversation memory for the chat API, backed by neo4j-agent-memory.

MemoryService wraps a single lifespan-managed MemoryClient (which owns its
own async Neo4j driver) and is best-effort by design: every public method
swallows failures and returns neutral values so chat keeps working when
memory is down or disabled (MEMORY_ENABLED=false).

Spike-verified integration notes (library v0.5.0, bolt backend):
- Gemini has no native adapter; provider strings route through LiteLLM,
  which reads GEMINI_API_KEY. text-embedding-004 is retired upstream;
  gemini-embedding-001 (3072 dims) works. Dimensions must be explicit and
  are locked into the vector indexes on first connect().
- Entity extraction runs synchronously inside add_message() and links
  (Message)-[:MENTIONS]->(Entity). Extracted *preferences* are dropped by
  the library, so we capture each ExtractionResult via a delegating
  extractor wrapper and persist preferences with long_term.add_preference.
- get_context() returns a formatted prompt string in v0.5.0.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("cogmem.memory")

_LLM_MODEL = "gemini/gemini-flash-latest"
_EMBEDDING_MODEL = "gemini/gemini-embedding-001"
_EMBEDDING_DIMENSIONS = 3072
_CONTEXT_MAX_ITEMS = 10
_CONVERSATION_LIMIT = 20


class _CapturingExtractor:
    """Delegates to the real extractor and keeps the last ExtractionResult.

    Needed because ShortTermMemory persists entities/relations from the
    result but silently discards preferences — the capture lets the service
    persist them (and report badge counts) after add_message returns.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last_result: Any = None

    async def extract(self, text: str, **kwargs: Any) -> Any:
        result = await self._inner.extract(text, **kwargs)
        self.last_result = result
        return result


def memory_enabled() -> bool:
    return os.environ.get("MEMORY_ENABLED", "true").strip().lower() not in (
        "false", "0", "no", "off",
    )


def _build_client() -> tuple[Any, _CapturingExtractor]:
    """Construct an unconnected MemoryClient with a capturing LLM extractor."""
    from neo4j_agent_memory import MemoryClient, MemorySettings
    from neo4j_agent_memory.config.settings import ExtractionConfig, ExtractorType
    from neo4j_agent_memory.extraction.factory import create_extractor
    from neo4j_agent_memory.llm import from_provider

    extraction = ExtractionConfig(
        extractor_type=ExtractorType.LLM,
        llm_model=_LLM_MODEL,
        extract_preferences=True,
        enable_spacy=False,
        enable_gliner=False,
    )
    settings = MemorySettings(
        neo4j={
            "uri": os.environ["NEO4J_URI"],
            "username": os.environ["NEO4J_USER"],
            "password": os.environ["NEO4J_PASSWORD"],
        },
        llm=_LLM_MODEL,
        embedding=from_provider(
            _EMBEDDING_MODEL, kind="embedding", dimensions=_EMBEDDING_DIMENSIONS
        ),
        extraction=extraction,
    )
    capture = _CapturingExtractor(create_extractor(extraction, settings.schema_config))
    return MemoryClient(settings, extractor=capture), capture


class MemoryService:
    """Best-effort conversation memory facade used by the chat endpoint."""

    def __init__(self) -> None:
        self.active: bool = False
        self._client: Any = None
        self._capture: _CapturingExtractor | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not memory_enabled():
            logger.info("memory disabled via MEMORY_ENABLED")
            return
        if os.environ.get("MEMORY_API_KEY"):
            logger.warning(
                "MEMORY_API_KEY is set, which would switch neo4j-agent-memory "
                "to the hosted NAMS backend — memory disabled; unset it to use bolt."
            )
            return
        try:
            self._client, self._capture = _build_client()
            await self._client.connect()
            self.active = True
            logger.info("memory client connected (bolt, %s)", _EMBEDDING_MODEL)
        except Exception:
            logger.exception("memory client failed to start; chat continues without memory")
            self._client = None
            self.active = False

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.exception("memory client close failed")
        self._client = None
        self.active = False

    async def get_chat_context(
        self, session_id: str, query: str
    ) -> tuple[str | None, list[dict]]:
        """
        Return (memory_block, recent_turns) for the agent prompt.

        memory_block carries long-term knowledge only (entities, facts,
        preferences); recent conversation turns come from get_conversation
        so they are not duplicated inside the block. Both are fetched
        BEFORE the current message is stored.
        """
        if not self.active:
            return None, []
        memory_block: str | None = None
        turns: list[dict] = []
        try:
            block = await self._client.get_context(
                query,
                session_id=session_id,
                include_short_term=False,
                include_long_term=True,
                include_reasoning=False,  # never read CoGMEM ReasoningTrace nodes
                max_items=_CONTEXT_MAX_ITEMS,
            )
            memory_block = block.strip() or None
        except Exception:
            logger.exception("get_context failed")
        try:
            conv = await self._client.short_term.get_conversation(
                session_id, limit=_CONVERSATION_LIMIT
            )
            for msg in conv.messages:
                role = getattr(msg.role, "value", str(msg.role))
                turns.append({
                    "role": "model" if role == "assistant" else "user",
                    "text": msg.content,
                })
        except Exception:
            logger.exception("get_conversation failed")
        return memory_block, turns

    async def record_user_message(self, session_id: str, text: str) -> dict:
        """
        Store the user turn; extraction runs inline. Returns badge counts
        {"entities": n, "preferences": n} (zeros on any failure).
        """
        if not self.active:
            return {"entities": 0, "preferences": 0}
        try:
            # Lock so a concurrent chat can't interleave capture reads.
            async with self._lock:
                self._capture.last_result = None
                await self._client.short_term.add_message(
                    session_id=session_id, role="user", content=text
                )
                result = self._capture.last_result
            if result is None:
                return {"entities": 0, "preferences": 0}

            entity_count = len(result.filter_invalid_entities().entities)
            preference_count = 0
            for pref in result.preferences:
                try:
                    await self._client.long_term.add_preference(
                        pref.category,
                        pref.preference,
                        context=pref.context,
                        confidence=pref.confidence,
                    )
                    preference_count += 1
                except Exception:
                    logger.exception("add_preference failed for %r", pref.preference)
            return {"entities": entity_count, "preferences": preference_count}
        except Exception:
            logger.exception("record_user_message failed")
            return {"entities": 0, "preferences": 0}

    async def record_model_message(self, session_id: str, text: str) -> None:
        """Store the assistant turn. Extraction is skipped (agent output is
        derived from the graph; extracting it back would create noise)."""
        if not self.active or not text:
            return
        try:
            await self._client.short_term.add_message(
                session_id=session_id,
                role="assistant",
                content=text,
                extraction_mode="skip",
            )
        except Exception:
            logger.exception("record_model_message failed")
