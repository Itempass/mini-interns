from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from rag import client as rag_client
from rag.models import VectorDatabase
from user.models import User
from api.endpoints.auth import get_current_user
from api.types.api_models.rag import CreateVectorDatabaseRequest

router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/providers", response_model=Dict[str, Any])
async def get_available_providers_endpoint():
    """Returns the available RAG providers and their settings schema."""
    return await rag_client.get_available_providers()

@router.post("/vector-databases", response_model=VectorDatabase, status_code=status.HTTP_201_CREATED)
async def create_vector_database_endpoint(
    request: CreateVectorDatabaseRequest, user: User = Depends(get_current_user)
):
    return await rag_client.create_vector_database(request, user.uuid)

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
    uuid: UUID, db_config: VectorDatabase, user: User = Depends(get_current_user)
):
    updated_db = await rag_client.update_vector_database(uuid, db_config, user.uuid)
    if not updated_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")
    return updated_db

@router.delete("/vector-databases/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vector_database_endpoint(uuid: UUID, user: User = Depends(get_current_user)):
    success = await rag_client.delete_vector_database(uuid, user.uuid)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector database not found")
    return 