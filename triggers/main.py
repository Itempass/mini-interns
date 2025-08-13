import logging
import time
import requests
import asyncio
from imap_tools import MailBox, A
from shared.app_settings import load_app_settings
from shared.redis.keys import RedisKeys
from shared.redis.redis_client import get_redis_client
from triggers.rules import passes_filter
from workflow import client as workflow_client
from workflow import trigger_client
from workflow.internals import runner
from workflow.models import InitialWorkflowData
from user.models import User
from shared.config import settings
import json
from mcp_servers.imap_mcpserver.src.imap_client import client as imap_client
from api.endpoints.auth import get_current_user
from mcp_servers.imap_mcpserver.src.imap_client.internals.connection_manager import (
    imap_connection,
    FolderNotFoundError,
    acquire_imap_slot,
)
import user.client as user_client
from shared.security.encryption import decrypt_value
from shared.services.openrouter_service import openrouter_service

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_last_uid(username: str):
    """Gets the last processed UID from Redis for a specific user."""
    redis_client = get_redis_client()
    uid = redis_client.get(RedisKeys.get_last_email_uid_key(username))
    return uid if uid else None

def set_last_uid(username: str, uid: str):
    """Sets the last processed UID in Redis for a specific user."""
    redis_client = get_redis_client()
    redis_client.set(RedisKeys.get_last_email_uid_key(username), uid)

async def main():
    """
    Main polling loop that checks for new emails and runs them against database-driven triggers for all users.
    """
    logger.info("Trigger service started.")
    
    while True:
        try:
            # Quick MCP server health check
            try:
                requests.get(f"http://localhost:{settings.CONTAINERPORT_MCP_IMAP}/mcp", timeout=2)
            except requests.exceptions.RequestException:
                logger.warning("MCP IMAP server is not reachable. Retrying in 10 seconds.")
                await asyncio.sleep(10)
                continue

            all_users = user_client.get_all_users()
            logger.info(f"Found {len(all_users)} users to check for new mail.")

            for user in all_users:
                try:
                    app_settings = load_app_settings(user_uuid=user.uuid)
                    if not all([app_settings.IMAP_SERVER, app_settings.IMAP_USERNAME, app_settings.IMAP_PASSWORD]):
                        logger.info(f"User {user.uuid} has incomplete IMAP settings. Skipping.")
                        continue
                    
                    # Use a user-specific resolved inbox name
                    resolved_inbox_name = None
                    try:
                        with imap_connection(app_settings=app_settings) as (_, resolver):
                            resolved_inbox_name = resolver.get_folder_by_attribute('\\Inbox')
                    except FolderNotFoundError:
                        logger.error(f"Could not resolve Inbox for user {user.uuid}. Skipping this user.")
                        continue
                    except Exception as e:
                        logger.error(f"Error resolving Inbox for user {user.uuid}: {e}. Skipping.", exc_info=True)
                        continue

                    logger.info(f"Checking for mail for user {user.uuid} ({app_settings.IMAP_USERNAME}) in '{resolved_inbox_name}'...")

                    # Acquire a per-user IMAP slot so we don't exceed provider limits
                    async with acquire_imap_slot(user.uuid):
                        with MailBox(app_settings.IMAP_SERVER).login(
                            app_settings.IMAP_USERNAME,
                            app_settings.IMAP_PASSWORD,
                            initial_folder=resolved_inbox_name,
                        ) as mailbox:
                            # IMPORTANT: We use the username here to handle cases where the user changes their email address.
                            last_uid = get_last_uid(app_settings.IMAP_USERNAME)
                            logger.info(f"Last processed UID for '{app_settings.IMAP_USERNAME}': {last_uid}")

                            if last_uid is None:
                                uids = mailbox.uids()
                                if uids:
                                    latest_uid_on_server = uids[-1]
                                    set_last_uid(app_settings.IMAP_USERNAME, latest_uid_on_server)
                                    logger.info(f"No previous UID found for '{app_settings.IMAP_USERNAME}'. Baseline set to {latest_uid_on_server}.")
                                else:
                                    logger.info(f"No emails in inbox for '{app_settings.IMAP_USERNAME}'.")
                                continue

                            messages = list(mailbox.fetch(A(uid=f'{int(last_uid) + 1}:*'), mark_seen=False))

                            # The UID in the response can be lower than last_uid, so we must filter.
                            filtered_messages = [msg for msg in messages if int(msg.uid) > int(last_uid)]

                            if filtered_messages:
                                logger.info(f"Found {len(filtered_messages)} new email(s) for {app_settings.IMAP_USERNAME}.")

                                my_email_address = app_settings.IMAP_USERNAME.lower()

                                for msg in filtered_messages:
                                    if msg.from_ and my_email_address in msg.from_.lower():
                                        logger.info(f"Skipping email sent by self: '{msg.subject}'")
                                        continue

                                    message_id_tuple = msg.headers.get('message-id')
                                    if not message_id_tuple:
                                        logger.warning("Skipping email with no Message-ID.")
                                        continue

                                    message_id = message_id_tuple[0].strip().strip('<>')
                                    logger.info(f"Processing message: {message_id} for user {user.uuid}")
                                    await process_message(user, msg, message_id)

                                latest_uid = filtered_messages[-1].uid
                                set_last_uid(app_settings.IMAP_USERNAME, latest_uid)
                                logger.info(f"Updated last UID for '{app_settings.IMAP_USERNAME}' to {latest_uid}")
                            else:
                                logger.info(f"No new emails for {app_settings.IMAP_USERNAME}.")
                
                except Exception as e:
                    logger.error(f"An error occurred processing user {user.uuid}: {e}", exc_info=True)
                    # Continue to the next user
                    continue

        except Exception as e:
            logger.error(f"An unexpected error occurred in main loop: {e}. Retrying in 30 seconds.", exc_info=True)

        await asyncio.sleep(30)

async def process_message(user: User, msg, message_id: str):
    """Process a single message against all database workflows for a specific user."""
    
    logger.info("--------------------")
    logger.info(f"Processing Email for User {user.uuid}: Message-ID: {message_id}, From: {msg.from_}, Subject: {msg.subject}")
    body = msg.text or msg.html
    if not body:
        logger.info("Email has no body content. Skipping processing.")
        return

    # User is now passed in, so we don't need to fetch it.
    
    # 2. Fetch all workflows for the user
    workflows = await workflow_client.list_all(user_id=user.uuid)
    if not workflows:
        logger.info(f"No workflows found for user {user.uuid}. Skipping processing.")
        return
    logger.info(f"Found {len(workflows)} workflows for user {user.uuid}. Evaluating...")

    # 3. Fetch thread context once for all triggers
    thread_context = None
    try:
        logger.info(f"Fetching message and thread context for Message-ID: {message_id}")
        email_message = await imap_client.get_message_by_id(user_uuid=user.uuid, message_id=message_id)
        if email_message:
            thread = await imap_client.get_complete_thread(user_uuid=user.uuid, source_message=email_message)
            if thread:
                thread_context = thread.markdown
                logger.info(f"Successfully fetched thread context with {len(thread.messages)} messages.")
            else: # Fallback for single message threads
                logger.warning("Could not fetch complete thread, using single message markdown.")
                thread_context = f"# Email Thread\n\n## Message 1:\n\n* **From:** {email_message.from_}\n* **To:** {email_message.to}\n* **CC:** {email_message.cc}\n* **Date:** {email_message.date}\n* **Message ID:** {email_message.message_id}\n* **Subject:** {email_message.subject}\n\n{email_message.body_markdown}\n\n---\n\n"
        else:
            logger.warning(f"Could not find message with Message-ID: {message_id}. Cannot get thread context.")
            #return

    except Exception as e:
        logger.error(f"Failed to fetch thread context for {message_id}: {e}. Using single message for trigger.", exc_info=True)
        thread_context = f"SINGLE MESSAGE (No thread context available):\n\nFrom: {msg.from_}\nTo: {msg.to}\nSubject: {msg.subject}\n\n{body}"
        #return

  

    # 4. Iterate through each workflow
    workflows_triggered = 0
    for workflow in workflows:
        logger.info(f"Evaluating workflow '{workflow.name}' ({workflow.uuid})")

        # 4a. Check if workflow is active and has a trigger
        if not workflow.is_active:
            logger.info(f"Workflow '{workflow.name}' is not active. Skipping.")
            continue
        if not workflow.trigger_uuid:
            logger.info(f"Workflow '{workflow.name}' has no trigger. Skipping.")
            continue

        # 4b. Get the trigger for the workflow
        trigger = await trigger_client.get(uuid=workflow.trigger_uuid, user_id=user.uuid)
        if not trigger:
            logger.error(f"Trigger with UUID '{workflow.trigger_uuid}' not found for workflow '{workflow.name}'. Skipping.")
            continue

        # 4c. Check simple filter rules
        if not passes_filter(msg.from_, trigger.filter_rules):
            logger.info(f"Email from '{msg.from_}' did not pass filter rules for trigger '{trigger.uuid}' of workflow '{workflow.name}'.")
            continue

        if trigger.trigger_prompt and trigger.trigger_model:
            logger.info(f"Email from '{msg.from_}' passed filter rules, now checking LLM trigger prompt for trigger '{trigger.uuid}' of workflow '{workflow.name}'.")
            
            system_prompt = f"""You are an intelligent email routing assistant. Your task is to decide if a workflow should be triggered based on the content of an email. The user has provided the following instruction:

'{trigger.trigger_prompt}'

Based on this instruction and the email thread below, should the workflow be triggered? Respond with a JSON object containing two keys:
1. "continue_processing": a boolean value (true or false).
2. "reason": a brief string explaining your decision.

For example, if the email matches the instruction:
{{"continue_processing": true, "reason": "The email is a customer inquiry as it contains pricing questions."}}

If the email does not match:
{{"continue_processing": false, "reason": "The email is personal and not related to business operations."}}
"""
            user_prompt = f"EMAIL THREAD:\n\n{thread_context}"

            try:
                response_json = await openrouter_service.get_json_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=trigger.trigger_model
                )
                if not response_json.get("continue_processing"):
                    logger.info(f"LLM decided not to trigger workflow for email from '{msg.from_}'. Reason: {response_json.get('reason', 'No reason provided.')}")
                    continue
                logger.info(f"LLM decided to trigger workflow for email from '{msg.from_}'. Reason: {response_json.get('reason', 'No reason provided.')}")
            except Exception as e:
                logger.error(f"Error processing LLM trigger prompt for workflow '{workflow.name}': {e}", exc_info=True)
                continue

        # If all checks pass, we have a match.
        logger.info(f"SUCCESS: Email matched trigger for workflow '{workflow.name}'. Kicking off instance.")
        workflows_triggered += 1

        # 5. Prepare initial data and create the workflow instance
        # The raw_data should be the pydantic model of the email.
        # The summary and markdown will be generated by the output processor.
        initial_workflow_data = InitialWorkflowData(
            markdown_representation=thread_context
        )
        logger.info(f"TRIGGER_DEBUG: Passing initial markdown data to create_instance.")

        try:
            instance = await workflow_client.create_instance(
                workflow_uuid=workflow.uuid,
                initial_markdown=initial_workflow_data.markdown_representation,
                user_id=user.uuid,
            )
            logger.info(f"Successfully created instance {instance.uuid} for workflow '{workflow.name}'")
            
            # Schedule the workflow to run in the background.
            asyncio.create_task(runner.run_workflow(instance.uuid, user.uuid))
            logger.info(f"Scheduled workflow instance {instance.uuid} for execution.")

        except Exception as e:
            logger.error(f"An error occurred while creating or running workflow instance for '{workflow.name}': {e}", exc_info=True)
    
    if workflows_triggered == 0:
        logger.info(f"No matching triggers found for email {message_id}.")
    
    logger.info("--------------------")

if __name__ == "__main__":
    asyncio.run(main()) 