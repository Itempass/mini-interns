



workflow step (in workflow/)
- here we should be able to set prompt, reranker true/false, results (int)
- 


rag client (in rag/)
- execute_rag (prompt, reranker, results, vectordb_id)
- get_available_rag_servers
- get_rag_server_options
- create_new_rag_server

endpoints (in api/)
- get_available_rag_servers
- get_new_rag_server_options
- create_new_rag_server

mysql table
- status
- uuid
- user_id
- created_at
- updated_at
- settings
- error_message
- type (internal/external)