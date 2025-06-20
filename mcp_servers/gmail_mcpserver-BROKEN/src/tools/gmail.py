"""
Refactored Gmail API tools for MCP server, using GmailService.
"""

import os
import base64
import asyncio
import logging
from typing import List, Optional, Literal, Union, Dict, Any
import re

from email_reply_parser import EmailReplyParser

from ..mcp_builder import mcp_builder
from fastmcp import Context
from ..session_manager import get_user_context_from_context, get_cached_or_fresh_token
from ..services.pinecone_service import PineconeService
from ..services.summarization_service import SummarizationService
from ..services.tone_service import ToneService
from ..services.gmail_service import GmailService
from ..services.agentlogger_service import AgentLoggerService

# Set up logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _extract_body_from_payload(payload: Dict[str, Any]) -> str:
    """Robustly extracts the text/plain body from a message payload."""
    if payload.get('body', {}).get('data'):
        try:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            return ""
    elif payload.get('parts'):
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                try:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                except (ValueError, UnicodeDecodeError):
                    continue
            elif part.get('parts'):
                body = _extract_body_from_payload(part)
                if body:
                    return body
    return ""

async def _get_conversation_context(
    gmail_service: GmailService, 
    access_token: str,
    thread_id: str, 
    target_email_id: str
) -> Optional[Dict[str, Any]]:
    """
    Fetches the conversational context for a target email within a thread using GmailService.
    """
    try:
        thread = await gmail_service.get_thread(access_token, thread_id)
        messages = thread.get('messages', [])

        target_message = next((msg for msg in messages if msg['id'] == target_email_id), None)
        if not target_message:
            return None
        
        target_index = messages.index(target_message)

        def process_msg(msg):
            body = _extract_body_from_payload(msg.get('payload', {}))
            return {
                "id": msg.get('id'),
                "body": EmailReplyParser.parse_reply(body),
                "is_sent": 'SENT' in msg.get('labelIds', [])
            }

        processed_target = process_msg(target_message)

        if processed_target["is_sent"]:
            if target_index > 0:
                previous_message = process_msg(messages[target_index - 1])
                return {
                    "type": "sent_reply",
                    "conversation": {
                        "message_replied_to": previous_message["body"],
                        "our_reply": processed_target["body"]
                    }
                }
            else:
                return {
                    "type": "sent_initial",
                    "conversation": { "our_email": processed_target["body"] }
                }
        else:
            our_reply = None
            if target_index < len(messages) - 1:
                next_message = process_msg(messages[target_index + 1])
                if next_message["is_sent"]:
                    our_reply = next_message["body"]
            
            return {
                "type": "received_email",
                "conversation": {
                    "received_email": processed_target["body"],
                    "our_reply": our_reply
                }
            }
            
    except Exception as e:
        logger.error(f"💥 Error in _get_conversation_context for thread {thread_id}: {e}", exc_info=True)
        return None

# --- Tool Implementations ---

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def list_inbox_emails(maxResults: Optional[int] = 10, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """Lists the user's inbox emails (excluding drafts) with basic details."""
    logger.info(f"🔧 TOOL CALL: list_inbox_emails")
    logger.debug(f"📥 TOOL PARAMS [list_inbox_emails]: maxResults={maxResults}")
    
    user_context = await get_user_context_from_context(ctx)
    token = await get_cached_or_fresh_token(user_context)
    gmail_service = GmailService()
    
    messages = await gmail_service.list_messages(token, max_results=maxResults, query='in:inbox -in:draft')
    
    if not messages:
        logger.debug(f"📤 TOOL RESPONSE [list_inbox_emails]: No messages found")
        logger.info(f"✅ TOOL COMPLETED: list_inbox_emails")
        return []

    results = []
    for i, msg_summary in enumerate(messages):
        try:
            detail = await gmail_service.get_message(token, msg_summary['id'], format='metadata')
            
            headers = detail.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            from_ = next((h['value'] for h in headers if h['name'] == 'From'), '')
            to = next((h['value'] for h in headers if h['name'] == 'To'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            label_ids = detail.get('labelIds', [])
            is_sent = 'SENT' in label_ids
            email_type = 'sent' if is_sent else 'received'
            
            result_item = {
                'id': msg_summary['id'],
                'threadId': msg_summary['threadId'],
                'subject': subject, 'from': from_, 'to': to, 'date': date,
                'labelIds': label_ids, 'type': email_type,
                'snippet': detail.get('snippet', '')
            }
            results.append(result_item)
            logger.debug(f"📧 [list_inbox_emails] Message {i+1}/{len(messages)}: {email_type} - {subject[:50]}...")
            
        except Exception as e:
            logger.warning(f"⚠️  Error getting details for message {msg_summary['id']}: {str(e)}")
            results.append({
                'id': msg_summary['id'], 'threadId': msg_summary['threadId'],
                'subject': '[Error - details unavailable]', 'from': '[Error - details unavailable]',
                'to': '[Error - details unavailable]', 'date': '[Error - details unavailable]',
                'labelIds': [], 'type': 'unknown', 'snippet': '[Error - details unavailable]'
            })
    
    logger.debug(f"📤 TOOL RESPONSE [list_inbox_emails]: Found {len(results)} inbox messages")
    logger.info(f"✅ TOOL COMPLETED: list_inbox_emails")
    return results

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def get_email(messageId: str, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> Dict[str, Any]:
    """Retrieves a specific email by its ID along with the entire conversation thread."""
    logger.info(f"🔧 TOOL CALL: get_email")
    logger.debug(f"📥 TOOL PARAMS [get_email]: messageId={messageId}")
    
    user_context = await get_user_context_from_context(ctx)
    token = await get_cached_or_fresh_token(user_context)
    gmail_service = GmailService()
    
    target_message = await gmail_service.get_message(token, messageId)
    thread_id = target_message.get('threadId')
    logger.debug(f"🧵 [get_email] Target message threadId: {thread_id}")
    
    thread_response = await gmail_service.get_thread(token, thread_id)
    
    def process_message(msg):
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        from_ = next((h['value'] for h in headers if h['name'] == 'From'), '')
        to = next((h['value'] for h in headers if h['name'] == 'To'), '')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
        cc = next((h['value'] for h in headers if h['name'] == 'Cc'), '')
        bcc = next((h['value'] for h in headers if h['name'] == 'Bcc'), '')
        body = EmailReplyParser.parse_reply(_extract_body_from_payload(msg.get('payload', {})))
        label_ids = msg.get('labelIds', [])
        is_sent = 'SENT' in label_ids
        msg_type = 'sent' if is_sent else 'received'
        
        return {
            'id': msg.get('id'), 'labelIds': label_ids, 'snippet': msg.get('snippet', ''),
            'subject': subject, 'from': from_, 'to': to, 'date': date,
            'cc': cc if cc else None, 'bcc': bcc if bcc else None, 'body': body,
            'type': msg_type, 'isTargetMessage': msg.get('id') == messageId
        }

    messages = thread_response.get('messages', [])
    processed_messages = [process_message(msg) for msg in messages]
    
    try:
        processed_messages.sort(key=lambda x: messages.index(next(m for m in messages if m['id'] == x['id'])))
    except:
        logger.warning("⚠️  Could not sort messages chronologically")

    structured_response = {
        'threadId': thread_id, 'messageCount': len(processed_messages),
        'targetMessageId': messageId, 'messages': processed_messages
    }
    
    logger.debug(f"📤 TOOL RESPONSE [get_email]: Retrieved thread {thread_id} with {len(processed_messages)} messages")
    logger.info(f"✅ TOOL COMPLETED: get_email")
    return structured_response

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def search_emails_with_gmail_query(query: str, maxResults: int = 10, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """Searches for emails matching a query, using the Gmail syntax."""
    logger.info(f"🔧 TOOL CALL: search_emails_with_gmail_query")
    logger.debug(f"📥 TOOL PARAMS [search_emails_with_gmail_query]: query='{query}', maxResults={maxResults}")
    
    user_context = await get_user_context_from_context(ctx)
    token = await get_cached_or_fresh_token(user_context)
    gmail_service = GmailService()
    
    messages = await gmail_service.list_messages(token, max_results=maxResults, query=query)
    logger.debug(f"🔍 [search_emails_with_gmail_query] Search returned {len(messages)} message IDs")
    
    if not messages:
        logger.debug(f"📤 TOOL RESPONSE [search_emails_with_gmail_query]: No messages found")
        logger.info(f"✅ TOOL COMPLETED: search_emails_with_gmail_query")
        return []

    results = []
    for i, msg in enumerate(messages):
        try:
            detail = await gmail_service.get_message(token, msg['id'], format='full')
            headers = detail.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            from_ = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            body = _extract_body_from_payload(detail.get('payload', {}))
            results.append({'id': msg['id'], 'subject': subject, 'from': from_, 'date': date, 'body': body})
            logger.debug(f"📧 [search_emails_with_gmail_query] Message {i+1}/{len(messages)}: {subject[:50]}...")
        except Exception as e:
            logger.warning(f"⚠️  Error getting details for message {msg['id']}: {str(e)}")
            results.append({'id': msg['id'], 'subject': '[Error - details unavailable]', 'from': '[Error - details unavailable]', 'date': '[Error - details unavailable]', 'body': '[Error - details unavailable]'})

    logger.debug(f"📤 TOOL RESPONSE [search_emails_with_gmail_query]: Found {len(results)} matching emails")
    return results

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def draft_reply(messageId: str, body: str, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> Union[Dict[str, Any], str]:
    """Creates a draft email in response to an existing email. IMPORTANT: Make sure to use the get_available_languages_for_tone_of_voice and get_tone_of_voice tool to get the user's tone of voice before drafting the reply."""
    if used_tools_history is None or ('get_tone_of_voice' not in used_tools_history or 'get_available_languages_for_tone_of_voice' not in used_tools_history):
        return "Both get_available_languages_for_tone_of_voice and get_tone_of_voice must be used first"

    logger.info(f"🔧 TOOL CALL: draft_reply. Tool history: {used_tools_history}")
    logger.debug(f"📥 TOOL PARAMS [draft_reply]: messageId={messageId}, body='{body[:100]}...', cc={cc}, bcc={bcc}")
    
    user_context = await get_user_context_from_context(ctx)
    token = await get_cached_or_fresh_token(user_context)
    gmail_service = GmailService()
    
    original_email = await gmail_service.get_message(token, messageId, format='full')
    thread_id = original_email.get('threadId')
    headers = original_email.get('payload', {}).get('headers', [])
    
    original_from = next((h['value'] for h in headers if h['name'] == 'From'), '')
    original_subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
    original_message_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), '')
    original_references = next((h['value'] for h in headers if h['name'] == 'References'), '')
    
    logger.debug(f"🧵 THREAD INFO: Original threadId={thread_id}, messageId={original_message_id}")
    
    email_match = re.search(r'<([^>]+)>', original_from)
    reply_to_email = email_match.group(1) if email_match else original_from.strip()
    
    reply_subject = original_subject
    if not reply_subject.lower().startswith('re:'):
        reply_subject = f"Re: {reply_subject}"
    logger.debug(f"📧 SUBJECT THREADING: Original='{original_subject}' -> Reply='{reply_subject}'")
    
    cc_field = f"Cc: {', '.join(cc)}\n" if cc else ""
    bcc_field = f"Bcc: {', '.join(bcc)}\n" if bcc else ""
    in_reply_to_field = f"In-Reply-To: {original_message_id}\n" if original_message_id else ""
    
    references_list = []
    if original_references:
        references_list.extend(original_references.split())
    if original_message_id and original_message_id not in references_list:
        references_list.append(original_message_id)
    references_field = f"References: {' '.join(references_list)}\n" if references_list else ""
    
    original_text = _extract_body_from_payload(original_email.get('payload', {}))
    original_body_text = f"\n\n---\nOriginal message:\n{original_text}" if original_text else ""
    
    raw_message = (
        f"To: {reply_to_email}\n{cc_field}{bcc_field}"
        f"Subject: {reply_subject}\n{in_reply_to_field}{references_field}\n"
        f"{body}{original_body_text}"
    )
    
    encoded_message = base64.urlsafe_b64encode(raw_message.encode('utf-8')).decode('utf-8')
    message_data = {'raw': encoded_message}
    if thread_id:
        message_data['threadId'] = thread_id
        logger.debug(f"🧵 ADDING threadId to draft reply: {thread_id}")
    
    response = await gmail_service.create_draft(token, message_data)

    try:
        agent_logger_service = AgentLoggerService()
        await agent_logger_service.log_draft(
            incoming_email_id=messageId,
            generated_draft=body,
            account_email=user_context.account_email
        )
    except Exception as e:
        logger.error(
            f"💥 Error calling AgentLoggerService for message {messageId}: {e}", exc_info=True
        )
    
    logger.debug(f"📤 TOOL RESPONSE [draft_reply]: Created reply draft {response.get('id', 'unknown')} for message {messageId}")
    logger.info(f"✅ TOOL COMPLETED: draft_reply")
    return response

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def semantic_search_emails(query: str, top_k: Optional[int] = 10, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """Performs a semantic search on emails and returns conversational context."""
    logger.info(f"🔧 TOOL CALL: semantic_search_emails")
    logger.debug(f"📥 TOOL PARAMS [semantic_search_emails]: top_k={top_k}, query='{query}'")

    try:
        user_context = await get_user_context_from_context(ctx)
        token = await get_cached_or_fresh_token(user_context)
        gmail_service = GmailService()
        
        pinecone_service = PineconeService()
        search_results = pinecone_service.query_user_emails(
            user_email=user_context.account_email, query=query, top_k=top_k
        )
        if not search_results:
            logger.debug("📤 TOOL RESPONSE [semantic_search_emails]: No results from vector search.")
            return []
            
        threads_to_fetch = list(set(r.get('thread_id') for r in search_results if r.get('thread_id')))
        batched_threads = await gmail_service.batch_get_threads(token, threads_to_fetch)
        threads_by_id = {thread['id']: thread for thread in batched_threads}
        
        final_results = []
        for r in search_results:
            thread_id = r.get('thread_id')
            email_id = r.get('email_id')
            
            if thread_id in threads_by_id:
                thread = threads_by_id[thread_id]
                messages = thread.get('messages', [])
                target_message = next((msg for msg in messages if msg['id'] == email_id), None)
                if not target_message: continue
                
                target_index = messages.index(target_message)
                def process_msg(msg):
                    body = _extract_body_from_payload(msg.get('payload', {}))
                    return { "body": EmailReplyParser.parse_reply(body), "is_sent": 'SENT' in msg.get('labelIds', []) }

                processed_target = process_msg(target_message)
                context = None
                
                if processed_target["is_sent"]:
                    if target_index > 0:
                        previous_message = process_msg(messages[target_index - 1])
                        context = {
                            "type": "sent_reply",
                            "conversation": {
                                "message_replied_to": previous_message["body"],
                                "our_reply": processed_target["body"]
                            }
                        }
                    else:
                        context = {"type": "sent_initial", "conversation": {"our_email": processed_target["body"]}}
                else:
                    our_reply = None
                    if target_index < len(messages) - 1:
                        next_message = process_msg(messages[target_index + 1])
                        if next_message["is_sent"]: our_reply = next_message["body"]
                    context = {"type": "received_email", "conversation": {"received_email": processed_target["body"], "our_reply": our_reply}}
                
                if context:
                    final_results.append({
                        'score': r.get('score'), 'email_id': email_id,
                        'thread_id': thread_id, **context
                    })

        logger.debug(f"📤 TOOL RESPONSE [semantic_search_emails]: Found {len(final_results)} results with context.")
        logger.info(f"✅ TOOL COMPLETED: semantic_search_emails")
        return final_results

    except Exception as e:
        logger.error(f"💥 TOOL FAILED [semantic_search_emails]: {e}", exc_info=True)
        raise Exception(f"An error occurred during semantic search: {e}")

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def find_similar_emails(messageId: str, top_k: Optional[int] = 5, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """Finds emails with similar content to a given email and returns their conversational context."""
    logger.info(f"🔧 TOOL CALL: find_similar_emails")
    logger.debug(f"📥 TOOL PARAMS [find_similar_emails]: messageId='{messageId}', top_k={top_k}")

    try:
        user_context = await get_user_context_from_context(ctx)
        token = await get_cached_or_fresh_token(user_context)
        gmail_service = GmailService()

        target_email = await gmail_service.get_message(token, messageId, format='full')
        email_body = _extract_body_from_payload(target_email.get('payload', {}))
        if not email_body:
            logger.warning(f"⚠️  [find_similar_emails] Could not extract body from email {messageId}.")
            return []

        summarization_service = SummarizationService()
        email_summary = summarization_service.summarize_email_body(email_body)
        logger.debug(f"📄 [find_similar_emails] Generated summary: '{email_summary[:100]}...'")

        pinecone_service = PineconeService()
        search_results = pinecone_service.query_user_emails(
            user_email=user_context.account_email, query=email_summary, top_k=top_k + 1
        )
        
        final_results = []
        tasks = []
        original_search_results = []
        for r in search_results:
            if r.get('email_id') != messageId:
                tasks.append(_get_conversation_context(gmail_service, token, r.get('thread_id'), r.get('email_id')))
                original_search_results.append(r)
        
        contexts = await asyncio.gather(*tasks)
        
        for i, context in enumerate(contexts):
            if context:
                r = original_search_results[i]
                final_results.append({
                    'score': r.get('score'), 'email_id': r.get('email_id'),
                    'thread_id': r.get('thread_id'), **context
                })
        
        final_results = final_results[:top_k]

        logger.debug(f"📤 TOOL RESPONSE [find_similar_emails]: Found {len(final_results)} similar emails.")
        logger.info(f"✅ TOOL COMPLETED: find_similar_emails")
        return final_results

    except Exception as e:
        logger.error(f"💥 TOOL FAILED [find_similar_emails]: {e}", exc_info=True)
        raise Exception(f"An error occurred while finding similar emails: {e}")

# --- Non-Gmail tools ---
@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def get_available_languages_for_tone_of_voice(used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> Dict[str, Any]:
    """Gets a list of all available language profiles for the user's account's tone of voice."""
    logger.info(f"🔧 TOOL CALL: get_available_languages_for_tone_of_voice")
    user_context = await get_user_context_from_context(ctx)
    tone_service = ToneService()
    available_languages = tone_service.get_available_languages(user_context.account_email)
    if not available_languages:
        return {"message": "No tone of voice profiles have been configured for this account."}
    return {"available_languages": available_languages}

@mcp_builder.tool(exclude_args=["ctx", "used_tools_history"])
async def get_tone_of_voice(language: str, used_tools_history: Optional[List[str]] = None, ctx: Context = None) -> Union[Dict[str, Any], str]:
    """Gets the user's tone of voice description for a given language profile."""
    if used_tools_history is None or 'get_available_languages_for_tone_of_voice' not in used_tools_history:
        return "The `get_available_languages_for_tone_of_voice` tool must be used before getting a specific tone."
    logger.info(f"🔧 TOOL CALL: get_tone_of_voice")
    user_context = await get_user_context_from_context(ctx)
    tone_service = ToneService()
    tone_description = tone_service.get_tone(user_context.account_email, language)
    if tone_description is None:
        return f"No tone profile found for language: {language}"
    return tone_description 