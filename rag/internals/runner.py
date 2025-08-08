from typing import Dict, Any
from uuid import UUID
import logging

from rag import client as rag_client
from rag.models import VectorDatabase
from workflow.internals.output_processor import create_output_data
from shared.services.embedding_service import get_embedding, rerank_documents, create_embedding_for_model, get_embedding_model_vector_size
from .pinecone import query_pinecone_serverless

logger = logging.getLogger(__name__)

async def run_rag_step(
    *,
    user_id: UUID,
    workflow_instance_uuid: UUID,
    rag_definition_uuid: UUID,
    prompt: str,
    vectordb_uuid: UUID,
    rerank: bool,
    top_k: int,
) -> Dict[str, Any]:
    """
    Executes a RAG step against the configured vector database.
    """
    logger.info(f"Running RAG step {rag_definition_uuid} on vectordb {vectordb_uuid} with top_k={top_k}, rerank={rerank}")

    if not vectordb_uuid:
        raise ValueError("Cannot execute RAG step without a vectordb_uuid.")

    # Fetch the vector DB config to determine provider and settings
    vectordb: VectorDatabase | None = await rag_client.get_vector_database(vectordb_uuid, user_id)
    if not vectordb:
        raise ValueError("Vector database not found for RAG step execution.")

    provider = (vectordb.provider or '').lower()
    settings = vectordb.settings or {}

    # Determine embedding model: prefer vector DB configured model
    embedding_model_key = settings.get("embedding_model")

    # Compute query embedding
    if embedding_model_key:
        query_embedding = create_embedding_for_model(embedding_model_key, prompt)
    else:
        # Fallback to user's current embedding model if db-configured model is not set
        query_embedding = get_embedding(prompt, user_uuid=user_id)

    results: list[Dict[str, Any]] = []

    if provider == "pinecone-serverless":
        # Execute Pinecone query
        matches = await query_pinecone_serverless(db_config=vectordb, query_embedding=query_embedding, top_k=top_k)
        # Normalize to minimal fields used downstream
        for m in matches:
            results.append({
                "id": m.get("id"),
                "score": m.get("score"),
                "metadata": m.get("metadata", {}),
            })
    elif provider == "imap_email_threads":
        # Placeholder: IMAP-based internal vector DB not implemented in this runner yet.
        # In the future, delegate to an internal index service.
        results = []
    else:
        raise ValueError(f"Unknown RAG provider '{vectordb.provider}'.")

    # Optional reranking using embedding service (Voyage-only reranker). Operates on text fields if present.
    reranked_indices: list[int] | None = None
    if rerank and results:
        # Build candidate documents from metadata if available; fallback to id
        documents: list[str] = []
        for r in results:
            meta = r.get("metadata") or {}
            # Prefer a 'text' or 'content' field if present; else stringify metadata
            doc = meta.get("text") or meta.get("content") or str(meta) or str(r.get("id"))
            documents.append(doc)
        try:
            reranked = rerank_documents(prompt, documents, top_k=min(top_k, len(documents)), user_uuid=user_id)
            # rerank_documents returns list of dicts with 'index'
            reranked_indices = [it.get("index") for it in reranked if isinstance(it, dict) and "index" in it]
        except Exception as e:
            logger.warning(f"Reranking failed, continuing with original order: {e}")

    # Prepare markdown output
    ordered_results = results
    if reranked_indices is not None and len(reranked_indices) > 0:
        ordered_results = [results[i] for i in reranked_indices if 0 <= i < len(results)]

    lines: list[str] = []
    for i, r in enumerate(ordered_results[: max(1, int(top_k))]):
        meta = r.get("metadata") or {}
        text_preview = (meta.get("text") or meta.get("content") or "")
        if isinstance(text_preview, str):
            text_preview = text_preview[:200]
        lines.append(f"[RESULT {i+1}] score={r.get('score')} id={r.get('id')}\n{text_preview}")

    markdown = "\n\n".join(lines) if lines else "No results found."

    output = await create_output_data(
        markdown_representation=markdown,
        user_id=user_id,
    )

    return {
        "output": output,
        "results": ordered_results,
        "provider": provider,
        "settings": settings,
    } 