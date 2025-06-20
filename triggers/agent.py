import logging
import json
from openai import OpenAI
from shared.app_settings import AppSettings
from triggers.draft_handler import create_draft_reply
from agentlogger.src.client import save_conversation
from agentlogger.src.models import ConversationData, Message, Metadata
import asyncio

logger = logging.getLogger(__name__)

class EmailAgent:
    def __init__(self, app_settings: AppSettings, trigger_conditions: str, system_prompt: str, user_context: str):
        self.app_settings = app_settings
        self.trigger_conditions = trigger_conditions
        self.system_prompt = system_prompt
        self.user_context = user_context
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.app_settings.OPENROUTER_API_KEY,
        )

    def run(self, original_message):
        email_body = original_message.text or original_message.html
        if not email_body:
            return {"success": False, "message": "Email has no body content."}

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_draft_reply",
                    "description": "Creates and saves a draft email reply. Call this if a reply is warranted.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "draft_content": {
                                "type": "string",
                                "description": "The full content of the email draft, written in markdown.",
                            },
                        },
                        "required": ["draft_content"],
                    },
                },
            }
        ]

        agent_system_prompt = f"""
You are an intelligent email assistant. Your task is to analyze an incoming email and decide if a draft reply is warranted based on the following rules:
{self.trigger_conditions}

If and only if a draft is warranted, you MUST call the `create_draft_reply` tool.
When generating the draft content, follow these instructions:
{self.system_prompt}

Here is some additional context about the user you are assisting:
{self.user_context}
"""
        messages = [
            {"role": "system", "content": agent_system_prompt},
            {"role": "user", "content": f"Here is the email to analyze:\n\n---\n{email_body}\n---"}
        ]

        try:
            logger.info("Running email agent...")
            response = self.client.chat.completions.create(
                model=self.app_settings.OPENROUTER_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            
            response_message = response.choices[0].message
            messages.append(response_message)

            tool_calls = response_message.tool_calls
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call.function.name == 'create_draft_reply':
                        logger.info("Agent decided to create a draft.")
                        function_args = json.loads(tool_call.function.arguments)
                        
                        draft_result = create_draft_reply(
                            original_msg=original_message,
                            draft_content=function_args.get("draft_content")
                        )
                        
                        # Log conversation
                        try:
                            asyncio.run(save_conversation(ConversationData(
                                metadata=Metadata(conversation_id=f"agent_{original_message.uid}"),
                                messages=[Message(role=m["role"], content=str(m["content"]) if m.get("content") else json.dumps(m.get("tool_calls"))) for m in messages]
                            )))
                        except Exception as e:
                            logger.warning(f"Failed to log agent conversation: {e}")

                        return draft_result
            
            logger.info("Agent decided not to create a draft.")
            return {"success": False, "message": "Agent decided not to create a draft."}

        except Exception as e:
            logger.error(f"An error occurred in the Email Agent: {e}", exc_info=True)
            return {"success": False, "message": f"Error in agent: {str(e)}"}