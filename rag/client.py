from uuid import UUID
from typing import List, Optional, Dict, Any
import json
import os
import httpx
import logging
from .models import VectorDatabase
from .internals import database as db
from shared.services.embedding_service import get_embedding_model_vector_size

logger = logging.getLogger(__name__)

RAG_AVAILABLE_PATH = os.path.join(os.path.dirname(__file__), 'available.json')

async def get_available_providers() -> Dict[str, Any]:
    """Reads and returns the available RAG providers from the JSON file."""
    try:
        with open(RAG_AVAILABLE_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

async def create_vector_database(db_config: VectorDatabase) -> VectorDatabase:
    """Creates a new vector database configuration."""
    return await db._create_vector_database_in_db(db_config)

async def get_vector_database(uuid: UUID, user_id: UUID) -> Optional[VectorDatabase]:
    """Retrieves a specific vector database configuration."""
    return await db._get_vector_database_from_db(uuid, user_id)

async def list_vector_databases(user_id: UUID) -> List[VectorDatabase]:
    """Lists all vector database configurations for a user."""
    return await db._list_vector_databases_from_db(user_id)

async def update_vector_database(uuid: UUID, db_config: VectorDatabase, user_id: UUID) -> Optional[VectorDatabase]:
    """Updates an existing vector database configuration."""
    return await db._update_vector_database_in_db(uuid, db_config, user_id)

async def delete_vector_database(uuid: UUID, user_id: UUID) -> bool:
    """Deletes a vector database configuration."""
    return await db._delete_vector_database_from_db(uuid, user_id)

# --- Phase 2: RAG Execution Integration ---
async def execute_step(
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
    Executes a RAG step. This is a thin facade that will call an internal runner
    which handles provider-specific logic.
    """
    from .internals import runner as rag_runner  # Local import to avoid cycles if any
    return await rag_runner.run_rag_step(
        user_id=user_id,
        workflow_instance_uuid=workflow_instance_uuid,
        rag_definition_uuid=rag_definition_uuid,
        prompt=prompt,
        vectordb_uuid=vectordb_uuid,
        rerank=rerank,
        top_k=top_k,
    )

# --- Connectivity Tests ---
async def test_vector_database_connection(db_config: VectorDatabase) -> Dict[str, Any]:
    """
    Tests connectivity for a configured vector database.
    Serverless Pinecone only:
      1) List indexes via api.pinecone.io to validate API key and visibility
      2) Describe target index via GET /indexes/{index_name}
      3) Verify optional region/cloud settings against index spec.serverless
      4) If an embedding_model is set in settings, verify its vector size equals the index dimension
      5) Call data-plane host from the describe payload and POST /describe_index_stats
         (optionally with namespace) to ensure data-plane reachability and confirm namespace presence
    Internal providers: success (no external connectivity required)
    Returns: { ok: bool, message: str }
    """
    try:
        if db_config.type == "internal":
            return {"ok": True, "message": "Internal provider does not require external connectivity."}

        provider = (db_config.provider or "").lower()
        settings = db_config.settings or {}

        if provider == "pinecone":
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
                f"[RAG/Pinecone Test SERVERLESS] provider=pinecone base=api.pinecone.io index_name={index_name} namespace={namespace} model_key={model_key} configured_cloud={user_cloud} configured_region={user_region}"
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
                        # serverless host should be present at top-level 'host' or in status
                        host = (
                            info.get('host')
                            or (info.get('status') or {}).get('host')
                            or (info.get('database') or {}).get('host')
                        )
                        # optional spec.serverless region/cloud verification
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
                                            # If empty, treat as non-existent/empty namespace; we choose strict validation and fail
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

        # Default: Unknown external provider
        return {"ok": False, "message": f"Unknown provider '{db_config.provider}'. Cannot test connectivity."}
    except Exception as e:
        logger.error(f"[RAG/Pinecone Test SERVERLESS] Unexpected error: {e}", exc_info=True)
        return {"ok": False, "message": f"Unexpected error during connectivity test: {e}"}
