import logging
from typing import Dict, Any, List, Protocol, Optional
from uuid import UUID
from datetime import datetime
import asyncio

from mcp_servers.imap_mcpserver.src.imap_client.client import get_emails, get_all_labels, get_all_special_use_folders, get_complete_thread, EmailMessage
from . import database
from .models import EvaluationTemplate, EvaluationTemplateCreate

logger = logging.getLogger(__name__)

# --- Data Source Abstraction ---

class DataSource(Protocol):
    """A protocol defining the interface for a data source used in evaluation templates."""

    async def get_config_schema(self, user_id: UUID) -> Dict[str, Any]:
        """Returns a JSON schema describing the configuration options for the data source."""
        ...

    async def fetch_sample(self, config: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """Fetches a single sample data item based on the provided configuration."""
        ...
        
    async def fetch_full_dataset(self, config: Dict[str, Any], user_id: UUID) -> List[Dict[str, Any]]:
        """Fetches the complete dataset based on the provided configuration."""
        ...

class IMAPDataSource:
    """Data source for fetching emails via IMAP."""

    async def get_config_schema(self, user_id: UUID) -> Dict[str, Any]:
        """
        Dynamically generates a configuration schema for IMAP.
        It fetches all available labels and folders from the user's inbox to populate the options.
        """
        logger.info(f"Fetching IMAP labels and folders for config schema for user {user_id}")
        try:
            # In a real multi-tenant app, user_id would be used to select the correct IMAP credentials.
            # For now, it's unused as we have a single system-wide IMAP connection.
            labels, folders = await asyncio.gather(
                get_all_labels(),
                get_all_special_use_folders()
            )
            logger.debug(f"Fetched {len(labels)} labels and {len(folders)} special-use folders for user {user_id}")
            
            return {
                "type": "object",
                "properties": {
                    "folder_names": {
                        "type": "array",
                        "title": "Email Folders",
                        "items": {"type": "string"},
                        "description": "The folder(s) to search for emails.",
                        "options": folders # Dynamic options for the frontend
                    },
                    "filter_by_labels": {
                        "type": "array",
                        "title": "Filter by Labels",
                        "items": {"type": "string"},
                        "description": "Only include emails that have ANY of these labels.",
                        "options": labels # Dynamic options for the frontend
                    },
                    "count": {
                        "type": "integer",
                        "title": "Number of Emails",
                        "default": 200,
                        "description": "The maximum number of recent emails to fetch. Half will be used for the test set, and half for the validation set."
                    }
                },
                "required": ["folder_names", "count"]
            }
        except Exception as e:
            logger.error(f"Failed to fetch IMAP labels/folders for user {user_id}: {e}", exc_info=True)
            # This will be caught by the API layer and returned as a 500 error.
            raise

    async def fetch_sample(self, config: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
        """
        Fetches a single email matching the config, gets its full thread context,
        and returns a flattened dictionary representation of the thread.
        """
        logger.info(f"Fetching IMAP sample for user {user_id} with config: {config}")
        
        # 1. Fetch the most recent email message matching the criteria
        folder_to_sample = (config.get("folder_names", []) + ["INBOX"])[0]
        params = {**{k: v for k, v in config.items() if k != 'folder_names'}, 'count': 1, 'folder_name': folder_to_sample}
        
        try:
            email_messages = await get_emails(**params)
            if not email_messages:
                return {} # No sample found is a valid result
            
            source_email = email_messages[0]

            # 2. Fetch the complete thread for that email
            logger.info(f"Fetching complete thread for sample email with Message-ID: {source_email.message_id}")
            email_thread = await get_complete_thread(source_email)

            if not email_thread:
                logger.warning(f"Could not fetch thread for sample Message-ID: {source_email.message_id}. Returning empty sample.")
                return {}

            # 3. Flatten the thread into the desired dictionary format
            return {
                "thread_markdown": email_thread.markdown,
                "thread_subject": email_thread.subject,
                "thread_participants": email_thread.participants,
                "source_email_labels": source_email.gmail_labels
            }

        except Exception as e:
            logger.error(f"Failed to fetch and process IMAP sample for user {user_id}: {e}", exc_info=True)
            raise

    async def fetch_full_dataset(self, config: Dict[str, Any], user_id: UUID) -> List[Dict[str, Any]]:
        """
        Fetches a set of emails based on the config, then gets the full thread 
        context for each, returning a list of flattened thread dictionaries.
        """
        logger.info(f"Fetching full IMAP dataset for user {user_id} with config: {config}")
        
        # 1. Fetch initial email messages from all specified folders
        all_matching_emails: List[EmailMessage] = []
        folder_names = config.get("folder_names", ["INBOX"])
        params_without_folders = {k: v for k, v in config.items() if k != "folder_names"}

        try:
            for folder in folder_names:
                per_folder_count = config.get("count", 200) // len(folder_names)
                fetch_params = {**params_without_folders, 'folder_name': folder, 'count': per_folder_count}
                results = await get_emails(**fetch_params)
                all_matching_emails.extend(results)

            # Deduplicate the initial list of emails
            unique_emails = {msg.message_id: msg for msg in all_matching_emails}.values()
            logger.info(f"Found {len(unique_emails)} unique initial emails to process.")

            # 2. For each unique email, fetch its full thread and flatten it
            full_thread_dataset = []
            
            # Using asyncio.gather for concurrent thread fetching
            tasks = [get_complete_thread(email) for email in unique_emails]
            email_threads = await asyncio.gather(*tasks)

            # We need to map threads back to their source email to get labels
            source_email_map = {email.message_id: email for email in unique_emails}

            for thread in email_threads:
                if thread:
                    # Find the original source email to get its labels
                    # This relies on at least one message_id in the thread matching our source map
                    source_email = None
                    for msg in thread.messages:
                        if msg.message_id in source_email_map:
                            source_email = source_email_map[msg.message_id]
                            break
                    
                    if source_email:
                        full_thread_dataset.append({
                            "thread_markdown": thread.markdown,
                            "thread_subject": thread.subject,
                            "thread_participants": thread.participants,
                            "source_email_labels": source_email.gmail_labels
                        })
                    else:
                        logger.warning(f"Could not map thread with ID {thread.thread_id} back to a source email.")

            logger.info(f"Successfully processed and flattened {len(full_thread_dataset)} email threads.")
            return full_thread_dataset
            
        except Exception as e:
            logger.error(f"Failed to fetch full IMAP dataset for user {user_id}: {e}", exc_info=True)
            raise


# --- Data Source Registry ---

class DataSourceRegistry:
    def __init__(self):
        self._sources: Dict[str, DataSource] = {}

    def register(self, source_id: str, source: DataSource):
        logger.info(f"Registering data source: {source_id}")
        self._sources[source_id] = source

    def get_source(self, source_id: str) -> DataSource:
        if source_id not in self._sources:
            logger.error(f"Attempted to access unknown data source: {source_id}")
            raise ValueError(f"Unknown data source: {source_id}")
        return self._sources[source_id]

    def list_sources(self) -> List[Dict[str, str]]:
        """Returns a list of available sources, suitable for display in the frontend."""
        # In a more complex system, the name and description could come from the source class itself.
        return [
            {"id": "imap_emails", "name": "IMAP Email Threads"}
        ]

# Initialize the registry and register our IMAP source.
data_source_registry = DataSourceRegistry()
data_source_registry.register("imap_emails", IMAPDataSource())


# --- Service Functions ---

def list_data_sources() -> List[Dict[str, str]]:
    """Returns a list of all available data sources."""
    return data_source_registry.list_sources()

async def get_data_source_config_schema(source_id: str, user_id: UUID) -> Dict[str, Any]:
    """Gets the dynamic configuration schema for a given data source."""
    source = data_source_registry.get_source(source_id)
    return await source.get_config_schema(user_id)

async def fetch_data_source_sample(source_id: str, config: Dict[str, Any], user_id: UUID) -> Dict[str, Any]:
    """Fetches a sample data item from a given data source using the provided config."""
    source = data_source_registry.get_source(source_id)
    return await source.fetch_sample(config, user_id)


async def create_template_with_snapshot(
    create_request: EvaluationTemplateCreate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Orchestrates the creation of a new EvaluationTemplate.
    1. Fetches the full dataset from the specified source to create a snapshot.
    2. Creates the full EvaluationTemplate model with the data snapshot.
    3. Saves it to the database.
    """
    logger.info(f"Creating evaluation template '{create_request.name}' for user {user_id}")

    # Step 1: Fetch the data for the static snapshot using the new abstraction.
    source_id = create_request.data_source_config.tool # Re-purposing 'tool' as the source_id
    source = data_source_registry.get_source(source_id)
    
    cached_data = await source.fetch_full_dataset(
        config=create_request.data_source_config.params,
        user_id=user_id
    )

    if not cached_data:
        logger.warning(f"Evaluation template '{create_request.name}' was created with an empty data snapshot.")

    # Step 2: Create the full EvaluationTemplate object.
    new_template = EvaluationTemplate(
        user_id=user_id,
        name=create_request.name,
        description=create_request.description,
        data_source_config=create_request.data_source_config,
        field_mapping_config=create_request.field_mapping_config,
        cached_data=cached_data
    )

    # Step 3: Save the complete template to the database.
    try:
        created_template = database.create_evaluation_template(new_template)
        logger.info(f"Successfully saved new evaluation template {created_template.uuid}")
        return created_template
    except Exception as e:
        logger.error(f"Failed to save evaluation template '{create_request.name}': {e}")
        raise

async def update_template_with_snapshot(
    template: EvaluationTemplate,
) -> EvaluationTemplate:
    """
    Orchestrates the update of an existing EvaluationTemplate.
    1. Re-fetches the full dataset to create a new snapshot if the config has changed.
    2. Updates the timestamp.
    3. Saves the updated template to the database.
    """
    logger.info(f"Updating evaluation template '{template.name}' for user {template.user_id}")

    # Step 1: Re-fetch the data for the static snapshot.
    source_id = template.data_source_config.tool
    source = data_source_registry.get_source(source_id)
    
    cached_data = await source.fetch_full_dataset(
        config=template.data_source_config.params,
        user_id=template.user_id
    )

    if not cached_data:
        logger.warning(f"Evaluation template '{template.name}' is being updated with an empty data snapshot.")

    # Update the cached data and the timestamp
    template.cached_data = cached_data
    template.updated_at = datetime.utcnow()


    # Step 2: Save the updated template to the database.
    try:
        updated_template = database.update_evaluation_template(template)
        logger.info(f"Successfully updated evaluation template {updated_template.uuid}")
        return updated_template
    except Exception as e:
        logger.error(f"Failed to update evaluation template '{template.name}': {e}")
        raise
