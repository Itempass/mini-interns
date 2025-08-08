from typing import Dict, Any, List, Optional
import httpx
import logging

from rag.models import VectorDatabase
from shared.services.embedding_service import get_embedding_model_vector_size

logger = logging.getLogger(__name__)

async def test_pinecone_serverless_connection(db_config: VectorDatabase) -> Dict[str, Any]:
    """
    Tests connectivity for Pinecone serverless only.
      1) GET https://api.pinecone.io/indexes to validate API key and enumerate indexes
      2) GET /indexes/{index_name} to verify existence and collect dimension, host, and spec.serverless
      3) Optionally verify user-provided cloud/region against spec.serverless
      4) If embedding_model is set, verify model vector size equals index dimension
      5) POST {host}/describe_index_stats (optionally with namespace) and confirm namespace presence
         If stats don't list namespaces, fallback to POST {host}/vectors/list with { namespace, limit: 1 }
    Returns: { ok: bool, message: str }
    """
    settings = db_config.settings or {}

    api_key = settings.get("api_key")
    index_name = settings.get("index_name")
    namespace = settings.get("namespace")
    model_key = settings.get("embedding_model")
    user_cloud = settings.get("cloud")
    user_region = settings.get("region")

    if not api_key:
        return {"ok": False, "message": "Missing required Pinecone setting: api_key is required."}

    base = "https://api.pinecone.io"
    timeout = httpx.Timeout(8.0, connect=4.0)
    notes: List[str] = []

    logger.info(
        f"[RAG/Pinecone Test SERVERLESS] provider=pinecone-serverless base=api.pinecone.io index_name={index_name} namespace={namespace} model_key={model_key} configured_cloud={user_cloud} configured_region={user_region}"
    )

    headers = {"Api-Key": api_key}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        # Step 1: List indexes to validate API key and enumerate availability
        list_resp = await client.get(f"{base}/indexes")
        logger.info(f"[RAG/Pinecone Test SERVERLESS] GET {base}/indexes -> {list_resp.status_code}")
        if list_resp.status_code != 200:
            return {"ok": False, "message": f"List indexes failed: {list_resp.status_code}: {list_resp.text[:200]}"}
        try:
            all_indexes = list_resp.json() or []
            available_names = []
            for item in all_indexes:
                if isinstance(item, dict):
                    available_names.append(item.get("name"))
            logger.info(f"[RAG/Pinecone Test SERVERLESS] Available indexes ({len(available_names)}): {available_names}")
        except Exception:
            logger.info("[RAG/Pinecone Test SERVERLESS] Could not parse list indexes response JSON.")
        notes.append("Connected to Pinecone serverless API.")

        # Step 2: Describe index if provided
        index_dimension = None
        host = None
        resp_spec_cloud = None
        resp_spec_region = None

        if index_name:
            desc = await client.get(f"{base}/indexes/{index_name}")
            logger.info(f"[RAG/Pinecone Test SERVERLESS] GET {base}/indexes/{index_name} -> {desc.status_code}")
            if desc.status_code == 404:
                return {"ok": False, "message": f"Index '{index_name}' was not found (serverless)."}
            if desc.status_code != 200:
                return {"ok": False, "message": f"Describe index failed with {desc.status_code}: {desc.text[:200]}"}

            try:
                info = desc.json()
                logger.info(f"[RAG/Pinecone Test SERVERLESS] describe_index keys: {list(info.keys())}")
                index_dimension = (
                    info.get('dimension')
                    or (info.get('database') or {}).get('dimension')
                )
                host = (
                    info.get('host')
                    or (info.get('status') or {}).get('host')
                    or (info.get('database') or {}).get('host')
                )
                spec = info.get('spec') or {}
                serverless = spec.get('serverless') or {}
                resp_spec_cloud = serverless.get('cloud')
                resp_spec_region = serverless.get('region')
                logger.info(
                    f"[RAG/Pinecone Test SERVERLESS] index_dimension={index_dimension} host={host} spec.cloud={resp_spec_cloud} spec.region={resp_spec_region}"
                )
            except Exception:
                logger.info("[RAG/Pinecone Test SERVERLESS] Could not parse describe index response JSON.")

            # Step 3: Optional region/cloud verification
            if user_cloud and resp_spec_cloud and str(user_cloud).lower() != str(resp_spec_cloud).lower():
                return {"ok": False, "message": f"Cloud mismatch: configured '{user_cloud}' but index is in '{resp_spec_cloud}'."}
            if user_region and resp_spec_region and str(user_region).lower() != str(resp_spec_region).lower():
                return {"ok": False, "message": f"Region mismatch: configured '{user_region}' but index is in '{resp_spec_region}'."}

            # Step 4: Embedding dimension validation
            if model_key and index_dimension:
                try:
                    expected_dim = get_embedding_model_vector_size(model_key)
                    logger.info(f"[RAG/Pinecone Test SERVERLESS] embedding_model={model_key} expected_dim={expected_dim}")
                    if int(expected_dim) != int(index_dimension):
                        return {
                            "ok": False,
                            "message": f"Embedding dimension mismatch: model '{model_key}' produces {expected_dim}, but index '{index_name}' is {index_dimension}."
                        }
                    notes.append(f"Embedding dimension matches index dimension ({index_dimension}).")
                except Exception as e:
                    logger.warning(f"[RAG/Pinecone Test SERVERLESS] Could not verify embedding dimension: {e}")
                    notes.append(f"Warning: Could not verify embedding dimension: {e}")

            # Step 5: Data-plane reachability + namespace presence
            if host:
                if not str(host).startswith("http://") and not str(host).startswith("https://"):
                    host = f"https://{host}"
                stats_body: Dict[str, Any] = {}
                if namespace:
                    stats_body["namespace"] = namespace
                dp_url = f"{host}/describe_index_stats"
                dp = await client.post(dp_url, json=stats_body)
                logger.info(f"[RAG/Pinecone Test SERVERLESS] POST {dp_url} body_keys={list(stats_body.keys())} -> {dp.status_code}")
                if dp.status_code != 200:
                    return {"ok": False, "message": f"Index '{index_name}' found, but data-plane call failed with {dp.status_code}: {dp.text[:200]}"}

                try:
                    stats = dp.json()
                    ns_map = stats.get("namespaces") or stats.get("namespace_summary")
                    if isinstance(ns_map, dict):
                        logger.info(f"[RAG/Pinecone Test SERVERLESS] namespaces found: {list(ns_map.keys())}")
                    if namespace:
                        if isinstance(ns_map, dict):
                            if namespace not in ns_map.keys():
                                return {"ok": False, "message": f"Namespace '{namespace}' does not exist (no stats present)."}
                            notes.append(f"Namespace '{namespace}' found.")
                        else:
                            # Fallback: try vectors/list to probe namespace existence
                            list_url = f"{host}/vectors/list"
                            payload = {"namespace": namespace, "limit": 1}
                            probe = await client.post(list_url, json=payload)
                            logger.info(f"[RAG/Pinecone Test SERVERLESS] POST {list_url} -> {probe.status_code}")
                            if probe.status_code == 200:
                                try:
                                    body = probe.json() or {}
                                    vector_list = body.get("vectors") or body.get("ids") or []
                                    if isinstance(vector_list, list) and len(vector_list) > 0:
                                        notes.append(f"Namespace '{namespace}' responded to vectors/list (at least one record present).")
                                    else:
                                        return {"ok": False, "message": f"Namespace '{namespace}' was not found or has no records. Create it by upserting data or correct the name."}
                                except Exception:
                                    return {"ok": False, "message": f"Could not confirm namespace '{namespace}' via stats or list endpoints."}
                            else:
                                return {"ok": False, "message": f"Could not confirm namespace '{namespace}': vectors/list returned {probe.status_code}."}
                except Exception:
                    logger.info("[RAG/Pinecone Test SERVERLESS] Could not parse describe_index_stats response JSON.")
                    notes.append("Warning: Could not parse index stats response.")

                return {"ok": True, "message": " ".join(notes) or "Success"}

        # If no index provided, API reachability is enough
        return {"ok": True, "message": "Successfully connected to Pinecone serverless API (index not validated)."}

# --- Query Execution ---
async def query_pinecone_serverless(
    *,
    db_config: VectorDatabase,
    query_embedding: List[float],
    top_k: int,
    namespace_override: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Executes a similarity search on a Pinecone serverless index using the data-plane /query endpoint.
    Returns a normalized list of matches: [{ id, score, metadata }]
    """
    settings = db_config.settings or {}
    api_key = settings.get("api_key")
    index_name = settings.get("index_name")
    namespace = namespace_override if namespace_override is not None else settings.get("namespace")

    if not api_key:
        raise ValueError("Missing Pinecone API key in vector database settings.")
    if not index_name:
        raise ValueError("Missing Pinecone index_name in vector database settings.")

    base = "https://api.pinecone.io"
    headers = {"Api-Key": api_key}
    timeout = httpx.Timeout(12.0, connect=5.0)

    logger.info(
        f"[RAG/Pinecone Query] index={index_name} namespace={namespace} top_k={top_k} embedding_len={len(query_embedding)} embed_head={[round(x,4) for x in (query_embedding[:3] or [])]}"
    )

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        # Describe index to obtain data-plane host
        desc = await client.get(f"{base}/indexes/{index_name}")
        logger.info(f"[RAG/Pinecone Query] describe index -> {desc.status_code}")
        if desc.status_code != 200:
            raise ValueError(f"Failed to describe index '{index_name}': {desc.status_code} {desc.text[:200]}")
        info = desc.json() or {}
        host = info.get('host') or (info.get('status') or {}).get('host') or (info.get('database') or {}).get('host')
        if not host:
            raise ValueError("Could not determine Pinecone data-plane host for index.")
        if not str(host).startswith("http://") and not str(host).startswith("https://"):
            host = f"https://{host}"
        logger.info(f"[RAG/Pinecone Query] data-plane host={host}")

        body: Dict[str, Any] = {"vector": query_embedding, "topK": int(top_k), "includeMetadata": True}
        if namespace:
            body["namespace"] = namespace

        url = f"{host}/query"
        logger.info(f"[RAG/Pinecone Query] POST {url} with topK={body['topK']} includeMetadata=True namespace={namespace}")
        resp = await client.post(url, json=body)
        logger.info(f"[RAG/Pinecone Query] response status={resp.status_code}")
        if resp.status_code != 200:
            raise ValueError(f"Pinecone query failed with {resp.status_code}: {resp.text[:200]}")

        data = resp.json() or {}
        matches = data.get("matches") or []
        logger.info(
            f"[RAG/Pinecone Query] matches={len(matches)} top_ids_scores={[(m.get('id'), round(m.get('score',0),4)) for m in (matches[:3] if isinstance(matches, list) else [])]}"
        )
        normalized: List[Dict[str, Any]] = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            normalized.append({
                "id": m.get("id"),
                "score": m.get("score"),
                "metadata": m.get("metadata") or {},
            })
        return normalized
