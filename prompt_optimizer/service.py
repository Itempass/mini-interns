import logging
from typing import Dict, Any, List, Protocol, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
import asyncio
import random
from jinja2 import Template
import re
import json
import ast
from email.utils import parsedate_to_datetime
from uuid import uuid4
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

from mcp_servers.imap_mcpserver.src.imap_client.client import get_emails, get_all_labels, get_all_special_use_folders, get_complete_thread, EmailMessage, get_message_by_id, list_headers, count_uids, get_message_by_contextual_uid, list_recent_uids, export_threads_dataset_bulk
from . import database
from shared.app_settings import load_app_settings

from .models import EvaluationTemplate, EvaluationTemplateCreate, EvaluationRun, TestCaseResult, DataSourceConfig, FieldMappingConfig
from .llm_client import call_llm, LLMClientError

logger = logging.getLogger(__name__)


# --- Helper Functions ---
def _parse_llm_output(raw_output: str) -> Dict[str, Any] | str:
    """
    Tries to parse LLM output.

    1.  Checks for a markdown-fenced JSON block (```json...```) and attempts to parse its content.
    2.  If that is present and parses successfully, returns the JSON object.
    3.  In all other cases (no markdown, or markdown with non-JSON content), it attempts to parse the entire raw string.
    4.  If all parsing fails, returns the original, unmodified string, preserving all whitespace.
    """
    if not raw_output:
        return ""

    # 1. Check for markdown-fenced JSON and try to parse it
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_output, re.DOTALL)
    if match:
        content_inside_backticks = match.group(1).strip()
        try:
            return json.loads(content_inside_backticks)
        except json.JSONDecodeError:
            # It looked like a markdown block, but the content wasn't valid JSON.
            # Fall through to returning the original raw_output.
            pass

    # 2. If no valid markdown was found and parsed, try parsing the whole string
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        # 3. If all else fails, it's a plain string. Return it as is.
        return raw_output


def _apply_ground_truth_transform(dataset: List[Dict[str, Any]], field_mapping: "FieldMappingConfig") -> List[Dict[str, Any]]:
    """Applies a transformation to the ground truth field of a dataset."""
    ground_truth_field = field_mapping.ground_truth_field
    transform = field_mapping.ground_truth_transform

    if not ground_truth_field or not transform or transform == "none":
        return dataset

    logger.info(f"Applying transform '{transform}' to field '{ground_truth_field}'")
    
    transformed_dataset = []
    for item in dataset:
        new_item = item.copy()
        original_value = new_item.get(ground_truth_field)

        if original_value is not None:
            if transform == "join_comma":
                if isinstance(original_value, list):
                    new_item[ground_truth_field] = ", ".join(map(str, original_value))
                # If not a list, do nothing.
            elif transform == "first_element":
                if isinstance(original_value, list) and original_value:
                    new_item[ground_truth_field] = original_value[0]
                # If not a list or empty, do nothing.
        
        transformed_value = new_item.get(ground_truth_field)
        #_log_to_debug_file(f"APPLY_TRANSFORM (AFTER) - transformed_value: {transformed_value!r}")
        
        transformed_dataset.append(new_item)
        
    return transformed_dataset


# --- Prompt Template Loading ---
def _load_prompt_template(filename: str) -> Template:
    """Loads a Jinja2 template from the prompts directory."""
    from importlib import resources
    try:
        # Use importlib.resources to safely access package data
        template_str = resources.read_text('prompt_optimizer.prompts', filename)
        return Template(template_str)
    except FileNotFoundError:
        logger.error(f"Prompt template file not found: {filename}")
        raise


async def process_data_snapshot_background(template_uuid: UUID, user_id: UUID, data_source_config: DataSourceConfig, field_mapping_config: FieldMappingConfig):
    """
    Background task to fetch, process, and save the data snapshot for a template.
    This function is designed to be run by a background task runner (e.g., FastAPI's BackgroundTasks).
    """
    logger.info(f"Background task started: processing snapshot for template {template_uuid}")
    try:
        # 1. Fetch the full dataset
        source_id = data_source_config.tool
        config = data_source_config.params
        source = data_source_registry.get_source(source_id)
        dataset = await source.fetch_full_dataset(config, user_id)
        
        if not dataset:
            logger.warning(f"Data source returned no data for template {template_uuid}. Saving empty snapshot.")

        # 2. Apply transformations
        transformed_dataset = _apply_ground_truth_transform(dataset, field_mapping_config)

        # 3. Update the database with the data and "completed" status
        database.update_template_snapshot_data(
            uuid=template_uuid,
            cached_data=transformed_dataset,
            status="completed"
        )
        logger.info(f"Background task finished successfully for template {template_uuid}")

    except Exception as e:
        logger.error(f"Background task failed for template {template_uuid}: {e}", exc_info=True)
        # Update the database with "failed" status and the error message
        database.update_template_snapshot_data(
            uuid=template_uuid,
            cached_data=[],
            status="failed",
            error_message=str(e)
        )


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
            labels, folders = await asyncio.gather(
                get_all_labels(user_uuid=user_id),
                get_all_special_use_folders(user_uuid=user_id)
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
            email_messages = await get_emails(user_uuid=user_id, **params)
            if not email_messages:
                return {} # No sample found is a valid result
            
            source_email = email_messages[0]

            # 2. Fetch the complete thread for that email
            logger.info(f"Fetching complete thread for sample email with Message-ID: {source_email.message_id}")
            email_thread = await get_complete_thread(user_uuid=user_id, source_message=source_email)

            if not email_thread:
                logger.warning(f"Could not fetch thread for sample Message-ID: {source_email.message_id}. Returning empty sample.")
                return {}

            # 3. Flatten the thread into the desired dictionary format
            return {
                "thread_markdown": email_thread.markdown,
                "thread_subject": email_thread.subject,
                "thread_participants": email_thread.participants,
                "most_recent_user_labels": email_thread.most_recent_user_labels
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
                results = await get_emails(user_uuid=user_id, **fetch_params)
                all_matching_emails.extend(results)

            # Deduplicate the initial list of emails
            unique_emails = {msg.message_id: msg for msg in all_matching_emails}.values()
            logger.info(f"Found {len(unique_emails)} unique initial emails to process.")

            # 2. For each unique email, fetch its full thread and flatten it
            full_thread_dataset = []
            
            # Using asyncio.gather for concurrent thread fetching
            tasks = [get_complete_thread(user_uuid=user_id, source_message=email) for email in unique_emails]
            email_threads = await asyncio.gather(*tasks)

            # We no longer need to map back to the source email for labels.
            # The correct, filtered labels are now on the thread object itself.
            for thread in email_threads:
                if thread:
                    thread_data = {
                        "thread_markdown": thread.markdown,
                        "thread_subject": thread.subject,
                        "thread_participants": thread.participants,
                        "most_recent_user_labels": thread.most_recent_user_labels
                    }
                    full_thread_dataset.append(thread_data)

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
    """Public-facing function to fetch a single sample data item."""
    source = data_source_registry.get_source(source_id)
    return await source.fetch_sample(config, user_id)


async def update_template_with_snapshot(
    template: EvaluationTemplate,
    update_request: EvaluationTemplateCreate,
    user_id: UUID
) -> EvaluationTemplate:
    """
    Updates an existing evaluation template.

    If the data source configuration has changed, it sets the status to 'processing'
    and returns immediately, relying on a background task to fetch the new data.
    Otherwise, it just updates the metadata.
    """
    # Check if the data source config has actually changed.
    # We compare the incoming request's config with the stored template's config.
    if update_request.data_source_config != template.data_source_config:
        logger.info(f"Data source config changed for template {template.uuid}. Refetching data in background.")
        # Config has changed. Update metadata, set status to 'processing', and let the background task handle data.
        template.name = update_request.name
        template.description = update_request.description
        template.data_source_config = update_request.data_source_config
        template.field_mapping_config = update_request.field_mapping_config
        template.status = "processing" # This signals the background task to run
        template.cached_data = [] # Clear out the old data
        template.processing_error = None
        template.updated_at = datetime.now(timezone.utc)
    else:
        logger.info(f"Data source config unchanged for template {template.uuid}. Updating metadata only.")
        # Config is the same. Just update the name and description.
        template.name = update_request.name
        template.description = update_request.description
        template.field_mapping_config = update_request.field_mapping_config # Allow field mapping to change without refetch
        template.updated_at = datetime.now(timezone.utc)

    # Save the changes to the database
    updated_template = database.update_evaluation_template(template)
    return updated_template


# --- Evaluation Helper Functions ---

async def _evaluate_prompt(
    prompt: str,
    model: str,
    dataset: List[Dict[str, Any]],
    field_mapping: Dict[str, str],
    user_id: UUID
) -> List[TestCaseResult]:
    """Runs a prompt against a dataset using the self-contained LLM client."""
    
    async def _evaluate_single_case(item: Dict[str, Any]) -> TestCaseResult:
        input_data = item.get(field_mapping['input_field'])
        ground_truth = item.get(field_mapping['ground_truth_field'])

        if input_data is None or ground_truth is None:
            # Create a result indicating skipped so it can be filtered out later if needed
            return TestCaseResult(input_data="", ground_truth_data="", generated_output="SKIPPED", is_match=False)

        full_prompt = f"{prompt}\n\n--- DATA ---\n{input_data}"

        try:
            generated_output = await call_llm(prompt=full_prompt, model=model, user_id=user_id)

            # Use our new parser to handle JSON in markdown
            actual_value = _parse_llm_output(generated_output)

            # The ground truth from the dataset might be a string representation of a list/dict
            # e.g., "'['test emails']'"
            try:
                expected_value_parsed = ast.literal_eval(ground_truth)
            except (ValueError, SyntaxError):
                # If it's not a valid Python literal, treat it as a plain string.
                expected_value_parsed = ground_truth

            is_correct = str(actual_value) == str(expected_value_parsed)
            
            logger.info(f"--- Evaluating Test Case ---")
            logger.info(f"  - Expected Value (parsed): '{expected_value_parsed}' (type: {type(expected_value_parsed).__name__})")
            logger.info(f"  - Actual Value   (parsed): '{actual_value}' (type: {type(actual_value).__name__})")
            logger.info(f"  - Comparison (==): {is_correct}")

            return TestCaseResult(
                input_data=input_data,
                ground_truth_data=ground_truth,
                generated_output=generated_output,
                is_match=is_correct
            )
        except Exception as e:
            logger.error(f"Error running LLM call for evaluation: {e}", exc_info=True)
            return TestCaseResult(
                input_data=input_data,
                ground_truth_data=ground_truth,
                generated_output=f"ERROR: {e}",
                is_match=False
            )

    tasks = [_evaluate_single_case(item) for item in dataset]
    results = await asyncio.gather(*tasks)
    
    # Filter out any skipped cases if necessary, though gather preserves order
    return [res for res in results if res.generated_output != "SKIPPED"]


async def _generate_feedback(
    test_case: TestCaseResult,
    feedback_correct_template: Template,
    feedback_incorrect_template: Template,
    user_id: UUID
) -> Tuple[str, str]:
    """Generates a natural language feedback summary for a single test case."""
    if test_case.is_match:
        template = feedback_correct_template
        prompt = template.render(
            email_content=test_case.input_data,
            ground_truth_label=test_case.ground_truth_data
        )
    else:
        template = feedback_incorrect_template
        prompt = template.render(
            email_content=test_case.input_data,
            predicted_label=test_case.generated_output,
            ground_truth_label=test_case.ground_truth_data
        )
    
    # Use a more capable model for feedback generation
    feedback = await call_llm(prompt, model="google/gemini-2.5-flash", user_id=user_id)
    logger.info(f"Generated feedback for test case: {feedback}")
    return feedback, prompt


# --- New Evaluation and Refinement Service ---

async def run_evaluation_and_refinement(run_uuid: UUID, user_id: UUID):
    """
    The main orchestration function for running an evaluation, generating feedback,
    and refining a prompt. This is designed to be run in the background.
    It receives a run_uuid for a 'pending' run and updates it.
    """
    logger.info(f"Starting evaluation and refinement for run {run_uuid} and user {user_id}")
    run = None
    try:
        # 1. Fetch the 'pending' run object and update its status to 'running'
        run = database.get_evaluation_run(run_uuid, user_id)
        if not run:
            raise ValueError(f"Evaluation run {run_uuid} not found.")
        
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        database.update_evaluation_run(run)

        template = database.get_evaluation_template(run.template_uuid, user_id)
        if not template:
            raise ValueError(f"Evaluation template {run.template_uuid} not found.")

        # The prompt and model are now self-contained in the run
        original_prompt = run.original_prompt
        original_model = run.original_model
        
        if not template.cached_data:
            raise ValueError("Cannot run evaluation on a template with no cached data.")

        # 2. Split data into training (feedback) and validation (scoring) sets
        shuffled_data = random.sample(template.cached_data, len(template.cached_data))
        split_point = len(shuffled_data) // 2
        training_set = shuffled_data[:split_point]
        validation_set = shuffled_data[split_point:]
        
        if not validation_set:
            raise ValueError("Validation set is empty. Cannot score prompts.")

        logger.info(f"Split data: {len(training_set)} for training, {len(validation_set)} for validation.")
        
        # 3. Load Prompt Templates
        feedback_correct_template = _load_prompt_template('feedback_correct.md')
        feedback_incorrect_template = _load_prompt_template('feedback_incorrect.md')
        refine_prompt_template = _load_prompt_template('refine_prompt.md')

        # 4. Evaluate V1 Prompt (Baseline)
        logger.info(f"Running baseline evaluation for V1 prompt on validation set...")
        v1_results = await _evaluate_prompt(original_prompt, original_model, validation_set, template.field_mapping_config.model_dump(), user_id)
        v1_passed = sum(1 for r in v1_results if r.is_match)
        v1_accuracy = (v1_passed / len(v1_results)) if v1_results else 0.0

        logger.info(f"V1 Prompt Accuracy: {v1_accuracy:.2%}")

        # 5. Step 1: Generate Feedback from Training Set
        if not training_set:
            raise ValueError("Training set is empty. Cannot generate feedback.")
        
        logger.info(f"Generating feedback from V1 prompt performance on training set...")
        training_run_results = await _evaluate_prompt(original_prompt, original_model, training_set, template.field_mapping_config.model_dump(), user_id)
        
        feedback_tasks = [_generate_feedback(case, feedback_correct_template, feedback_incorrect_template, user_id) for case in training_run_results]
        feedback_results = await asyncio.gather(*feedback_tasks)

        feedback_summaries = [feedback for feedback, prompt in feedback_results]
        feedback_str = "\n".join(f"- {summary}" for summary in feedback_summaries)
        logger.info(f"Generated {len(feedback_summaries)} feedback summaries.")

        # 6. Step 2: Refine the Prompt to create V2
        logger.info(f"Refining prompt to create V2...")
        refinement_prompt = refine_prompt_template.render(
            original_prompt=original_prompt,
            feedback_summaries=feedback_str
        )
        
        # Use the most powerful model for the refinement step
        refined_prompt_v2 = await call_llm(refinement_prompt, model="google/gemini-2.5-pro", user_id=user_id)
        logger.info(f"Successfully generated V2 prompt.")

        # 7. Evaluate V2 Prompt (using the original model for a fair comparison)
        logger.info(f"Running evaluation for V2 prompt on validation set...")
        v2_results = await _evaluate_prompt(refined_prompt_v2, original_model, validation_set, template.field_mapping_config.model_dump(), user_id)
        v2_passed = sum(1 for r in v2_results if r.is_match)
        v2_accuracy = (v2_passed / len(v2_results)) if v2_results else 0.0
        logger.info(f"V2 Prompt Accuracy: {v2_accuracy:.2%}")

        # 8. Finalize and Save Results
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.summary_report = {
            "v1_accuracy": v1_accuracy,
            "v2_accuracy": v2_accuracy,
            "total_cases": len(validation_set),
            "v1_passed": v1_passed,
            "v2_passed": v2_passed,
        }
        # Store the refined prompt and the detailed results for V2
        run.detailed_results = {
            "refined_prompt_v2": refined_prompt_v2,
            "v1_results": [r.model_dump() for r in v1_results],
            "v2_results": [r.model_dump() for r in v2_results]
        }
        database.update_evaluation_run(run)
        logger.info(f"Finished and saved evaluation run {run.uuid}")

    except Exception as e:
        logger.error(f"Evaluation run failed for run {run_uuid}: {e}", exc_info=True)
        if run:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            database.update_evaluation_run(run)
        # The exception will be handled by the background task runner
        raise


async def list_threads(
    source_id: str,
    filters: Dict[str, Any],
    page: int,
    page_size: int,
    user_id: UUID
) -> Dict[str, Any]:
    """Lists lightweight thread anchors for selection, with basic pagination and filters.

    For IMAP, fetches recent messages per selected folder using get_emails with an upper bound,
    deduplicates by message_id, sorts by date desc, and slices for the requested page.
    """
    if source_id != "imap_emails":
        raise ValueError(f"Unknown data source: {source_id}")

    folder_names: List[str] = filters.get("folder_names") or ["INBOX"]
    filter_by_labels: List[str] | None = filters.get("filter_by_labels") or None

    # Upper bound the total messages fetched to keep it reasonable
    # We fetch up to page*page_size per folder (split evenly), then slice the combined list.
    # Further cap the first-page fetch to improve initial responsiveness.
    target_total = max(page, 1) * max(page_size, 1)
    per_folder_target = max(target_total // max(len(folder_names), 1), 1)
    per_folder_target = min(per_folder_target, 500)

    all_messages: List[EmailMessage] = []
    try:
        # Fetch sequentially across folders to avoid concurrent IMAP operations
        for folder in folder_names:
            try:
                # Use headers-only listing to avoid downloading bodies when listing
                header_dicts = await list_headers(
                    user_uuid=user_id,
                    folder_name=folder,
                    count=per_folder_target,
                    filter_by_labels=filter_by_labels,
                )
                # Map to a minimal EmailMessage-like shape for downstream usage
                for h in header_dicts:
                    # Create a light struct with only required fields for listing
                    em = EmailMessage(
                        uid=h.get('uid', ''),
                        message_id=h.get('message_id', ''),
                        from_=h.get('from', ''),
                        to=h.get('to', ''),
                        subject=h.get('subject', ''),
                        date=h.get('date', ''),
                        body_raw="",
                        body_markdown="",
                        body_cleaned="",
                        gmail_labels=h.get('gmail_labels', []),
                        references="",
                        in_reply_to="",
                        type="received",
                    )
                    all_messages.append(em)
            except Exception as e:
                logger.error(f"Failed to fetch emails for folder '{folder}': {e}")

        # Deduplicate by message_id
        dedup: Dict[str, EmailMessage] = {}
        for msg in all_messages:
            if msg.message_id and msg.message_id not in dedup:
                dedup[msg.message_id] = msg

        unique_messages = list(dedup.values())

        # Sort by parsed date desc
        def _parse_date_safe(d: str):
            try:
                return parsedate_to_datetime(d)
            except Exception:
                return None
        unique_messages.sort(key=lambda m: (_parse_date_safe(m.date) or 0), reverse=True)

        # Slice for the requested page
        start = (max(page, 1) - 1) * max(page_size, 1)
        end = start + max(page_size, 1)
        page_items = unique_messages[start:end]

        # Prepare lightweight items
        items = []
        for m in page_items:
            items.append({
                "uid": m.uid,
                "id": m.message_id,
                "subject": m.subject,
                "from": m.from_,
                "to": m.to,
                "date": m.date,
                "folders": m.gmail_labels,
                "labels": m.gmail_labels,
            })

        # Compute total by summing counts across folders without fetching bodies/headers
        total = 0
        for folder in folder_names:
            try:
                total += await count_uids(user_uuid=user_id, folder_name=folder, filter_by_labels=filter_by_labels)
            except Exception as e:
                logger.error(f"Failed to count UIDs for folder '{folder}': {e}")
 
        return {"items": items, "total": total}
    except Exception as e:
        logger.error(f"Error listing threads for source {source_id}: {e}", exc_info=True)
        raise


async def export_threads_dataset(
    source_id: str,
    selected_ids: List[str],
    user_id: UUID
) -> List[Dict[str, Any]]:
    """Builds the export dataset for selected identifiers using a single-connection bulk routine.

    Accepts Message-IDs or contextual UIDs; deduplicates by Gmail thread id.
    """
    if source_id != "imap_emails":
        raise ValueError(f"Unknown data source: {source_id}")

    try:
        dataset = await export_threads_dataset_bulk(user_uuid=user_id, identifiers=selected_ids)
        return dataset
    except Exception as e:
        logger.error(f"Bulk export failed: {e}", exc_info=True)
        return []


async def collect_thread_ids(
    source_id: str,
    filters: Dict[str, Any],
    limit: int,
    user_id: UUID
) -> List[str]:
    """Collect up to `limit` contextual UIDs using UID SEARCH only (no headers)."""
    if source_id != "imap_emails":
        raise ValueError(f"Unknown data source: {source_id}")

    folder_names: List[str] = filters.get("folder_names") or ["INBOX"]
    filter_by_labels: List[str] | None = filters.get("filter_by_labels") or None

    remaining = max(0, min(limit, 500))
    collected_uids: List[str] = []

    for folder in folder_names:
        if remaining <= 0:
            break
        try:
            # Ask for up to remaining from this folder; UID order approximates recency
            uids = await list_recent_uids(user_uuid=user_id, folder_name=folder, count=remaining, filter_by_labels=filter_by_labels)
            for uid in uids:
                if uid not in collected_uids:
                    collected_uids.append(uid)
                    remaining -= 1
                    if remaining <= 0:
                        break
        except Exception as e:
            logger.error(f"Failed to collect UIDs for folder '{folder}': {e}")
            continue

    return collected_uids

# --- Export Job Helpers ---

def _export_status_key(user_id: UUID, job_id: str) -> str:
    return RedisKeys.get_export_status_key(user_id, job_id)

def _export_data_key(user_id: UUID, job_id: str) -> str:
    return RedisKeys.get_export_data_key(user_id, job_id)

def _export_error_key(user_id: UUID, job_id: str) -> str:
    return RedisKeys.get_export_error_key(user_id, job_id)

def _export_progress_key(user_id: UUID, job_id: str) -> str:
    return RedisKeys.get_export_progress_key(user_id, job_id)


def create_export_job(user_id: UUID, source_id: str, selected_ids: List[str]) -> str:
    """Initialize an export job in Redis and return its job_id."""
    job_id = str(uuid4())
    rc = get_redis_client()
    rc.set(_export_status_key(user_id, job_id), "processing")
    # Store the request payload in data key temporarily to pass to background if needed
    rc.set(_export_data_key(user_id, job_id), json.dumps({
        "user_id": str(user_id),
        "source_id": source_id,
        "selected_ids": selected_ids,
    }))
    return job_id


def set_export_job_failed(user_id: UUID, job_id: str, error_message: str) -> None:
    rc = get_redis_client()
    rc.set(_export_status_key(user_id, job_id), "failed")
    rc.set(_export_error_key(user_id, job_id), error_message)


def set_export_job_completed(user_id: UUID, job_id: str, dataset: List[Dict[str, Any]]) -> None:
    rc = get_redis_client()
    rc.set(_export_status_key(user_id, job_id), "completed")
    rc.set(_export_data_key(user_id, job_id), json.dumps(dataset))


def get_export_job_status(user_id: UUID, job_id: str) -> str:
    rc = get_redis_client()
    status = rc.get(_export_status_key(user_id, job_id))
    if not status:
        return "not_found"
    if isinstance(status, bytes):
        try:
            return status.decode("utf-8")
        except Exception:
            return str(status)
    return status


def set_export_job_progress(user_id: UUID, job_id: str, total: int, completed: int) -> None:
    rc = get_redis_client()
    rc.set(_export_progress_key(user_id, job_id), json.dumps({"total": total, "completed": completed}))

def get_export_job_progress(user_id: UUID, job_id: str) -> Dict[str, int]:
    rc = get_redis_client()
    raw = rc.get(_export_progress_key(user_id, job_id))
    if not raw:
        return {"total": 0, "completed": 0}
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        total = int(data.get("total", 0))
        completed = int(data.get("completed", 0))
        return {"total": total, "completed": completed}
    except Exception:
        return {"total": 0, "completed": 0}


def get_export_job_payload(user_id: UUID, job_id: str) -> Optional[Dict[str, Any]]:
    rc = get_redis_client()
    raw = rc.get(_export_data_key(user_id, job_id))
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


def get_export_job_result(user_id: UUID, job_id: str) -> Optional[List[Dict[str, Any]]]:
    rc = get_redis_client()
    raw = rc.get(_export_data_key(user_id, job_id))
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        # If it's the initial payload, not the final dataset, return None
        if isinstance(data, dict) and "selected_ids" in data:
            return None
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


async def build_export_job(job_id: str, user_id: UUID, source_id: str, selected_ids: List[str]) -> None:
    """Background task to build the dataset and store it in Redis using a single IMAP connection with deduplication."""
    try:
        if source_id != "imap_emails":
            raise ValueError(f"Unknown data source: {source_id}")

        total = len(selected_ids)
        set_export_job_progress(user_id, job_id, total=total, completed=0)

        def _progress_cb(total_in: int, completed_in: int) -> None:
            try:
                set_export_job_progress(user_id, job_id, total=total_in, completed=completed_in)
            except Exception:
                pass

        dataset = await export_threads_dataset_bulk(user_uuid=user_id, identifiers=selected_ids, progress_callback=_progress_cb)
        # Ensure progress shows as complete for UI gating
        try:
            set_export_job_progress(user_id, job_id, total=total, completed=total)
        except Exception:
            pass
        set_export_job_completed(user_id, job_id, dataset)
    except Exception as e:
        logger.error(f"Export job {job_id} failed: {e}", exc_info=True)
        set_export_job_failed(user_id, job_id, str(e))
