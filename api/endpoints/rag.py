from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from rag import client as rag_client
from rag.models import VectorDatabase
from user.models import User
from api.endpoints.auth import get_current_user
from api.types.api_models.rag import CreateVectorDatabaseRequest, UpdateVectorDatabaseRequest
from shared.services.embedding_service import list_embedding_model_keys, validate_embedding_api_key_for_model

router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/providers", response_model=Dict[str, Any])
async def get_available_providers_endpoint():
    """Returns the available RAG providers and their settings schema.
    Expands any setting that includes 'available_options' into a concrete list of options.
    """
    providers = await rag_client.get_available_providers()

    # Simple expansion rule: if a setting value is a dict with key 'available_options' and
    # the path equals 'shared/embedding_models.json', replace it with a list of model keys.
    for provider in providers.values():
        settings = provider.get("settings", {})
        for key, schema in list(settings.items()):
            if isinstance(schema, dict) and schema.get("select_embedding_model") is True:
                settings[key] = list_embedding_model_keys()
    return providers

@router.post("/vector-databases", response_model=VectorDatabase, status_code=status.HTTP_201_CREATED)
async def create_vector_database_endpoint(
    request: CreateVectorDatabaseRequest, user: User = Depends(get_current_user)
):
    # Validate embedding model selection if provided
    settings_payload = request.settings or {}
    selected_model = settings_payload.get("embedding_model")
    if selected_model:
        try:
            validate_embedding_api_key_for_model(selected_model)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    db_config = VectorDatabase(
        user_id=user.uuid,
        **request.model_dump()
    )
    return await rag_client.create_vector_database(db_config)

@router.get("/vector-databases/{uuid}", response_model=VectorDatabase)
async def get_vector_database_endpoint(uuid: UUID, user: User = Depends(get_current_user)):
    db = await rag_client.get_vector_database(uuid, user.uuid)
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")
    return db

@router.get("/vector-databases", response_model=List[VectorDatabase])
async def list_vector_databases_endpoint(user: User = Depends(get_current_user)):
    return await rag_client.list_vector_databases(user.uuid)

@router.put("/vector-databases/{uuid}", response_model=VectorDatabase)
async def update_vector_database_endpoint(
    uuid: UUID, request: UpdateVectorDatabaseRequest, user: User = Depends(get_current_user)
):
    existing = await rag_client.get_vector_database(uuid, user.uuid)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")

    payload = request.model_dump(exclude_unset=True)

    # Validate embedding model selection if provided in update
    settings_payload = payload.get('settings') or {}
    selected_model = settings_payload.get('embedding_model')
    if selected_model:
        try:
            validate_embedding_api_key_for_model(selected_model)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    merged = VectorDatabase(
        uuid=existing.uuid,
        user_id=existing.user_id,
        name=payload.get('name', existing.name),
        type=payload.get('type', existing.type),
        provider=payload.get('provider', existing.provider),
        settings=payload.get('settings', existing.settings),
        status=payload.get('status', existing.status),
        error_message=payload.get('error_message', existing.error_message),
        created_at=existing.created_at,
        updated_at=existing.updated_at,
    )

    updated_db = await rag_client.update_vector_database(uuid, merged, user.uuid)
    if not updated_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")
    return updated_db

@router.delete("/vector-databases/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vector_database_endpoint(uuid: UUID, user: User = Depends(get_current_user)):
    success = await rag_client.delete_vector_database(uuid, user.uuid)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")
    return 