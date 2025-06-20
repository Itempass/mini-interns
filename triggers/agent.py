import logging
import json
from openai import OpenAI
from shared.app_settings import AppSettings
from agentlogger.src.client import save_conversation
from agentlogger.src.models import ConversationData, Message, Metadata
import asyncio
from fastmcp import Client
from mcp.types import Tool
from shared.config import settings  

logger = logging.getLogger(__name__)

def _format_mcp_tools_for_openai(tools: list[Tool]) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    formatted_tools = []
    for tool in tools:
        # Use inputSchema instead of parameters for mcp.types.Tool
        formatted_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        })
    return formatted_tools

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
        self.mcp_client = Client(f"http://localhost:{settings.CONTAINERPORT_MCP_IMAP}/mcp")

    def run(self, original_message):
        """Runs the complete agent cycle asynchronously to improve performance."""
        
        async def _agent_cycle():
            email_body = original_message.text or original_message.html
            if not email_body:
                return {"success": False, "message": "Email has no body content."}

            try:
                async with self.mcp_client as client:
                    # Initial setup: list tools and prepare prompts
                    mcp_tools = await client.list_tools()
                    tools = _format_mcp_tools_for_openai(mcp_tools)

                    agent_system_prompt = self.system_prompt.replace("`create_draft_reply`", "`draft_reply`")
                    full_system_prompt = f"""
You are an intelligent email assistant. Your task is to analyze an incoming email and decide if a draft reply is warranted based on the following rules:
{self.trigger_conditions}

If and only if a draft is warranted, you MUST call the `draft_reply` tool.
When generating the draft content, follow these instructions:
{agent_system_prompt}

Here is some additional context about the user you are assisting:
{self.user_context}
"""
                    messages = [
                        {"role": "system", "content": full_system_prompt},
                        {"role": "user", "content": f"Here is the email to analyze:\n\n---\n{email_body}\n---"}
                    ]

                    # Start of the Thought-Action-Observation Loop
                    for _ in range(5): # Max 5 turns to prevent infinite loops
                        # THOUGHT: Get the next action from the LLM
                        logger.info("Agent is thinking...")
                        response = await asyncio.to_thread(
                            self.client.chat.completions.create,
                            model=self.app_settings.OPENROUTER_MODEL,
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                        )
                        response_message = response.choices[0].message
                        messages.append(response_message.model_dump())

                        # If there are no tool calls, the agent has finished its work.
                        if not response_message.tool_calls:
                            logger.info("Agent decided to finish.")
                            break

                        # ACTION: Execute the requested tool calls concurrently
                        logger.info(f"Agent performing {len(response_message.tool_calls)} actions...")
                        tasks = []
                        for tool_call in response_message.tool_calls:
                            tool_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)
                            function_args["messageId"] = original_message.uid
                            tasks.append(client.call_tool(tool_name, function_args))
                        
                        tool_results = await asyncio.gather(*tasks)

                        # OBSERVATION: Append tool results to the conversation history
                        for tool_call, result in zip(response_message.tool_calls, tool_results):
                            messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": json.dumps(result),
                            })
                    
                    # After the loop, log the full conversation
                    try:
                        await save_conversation(ConversationData(
                            metadata=Metadata(conversation_id=f"agent_{original_message.uid}"),
                            messages=[Message(**m) for m in messages if m.get("content") is not None]
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to log agent conversation: {e}")

                    # Return the final message from the assistant
                    final_message = messages[-1]
                    if final_message.get("tool_calls"):
                        return {"success": False, "message": "Agent finished with a tool call, but further action is required."}
                    else:
                        return {"success": True, "message": f"Agent finished: {final_message.get('content')}"}

            except Exception as e:
                logger.error(f"An error occurred in the Email Agent: {e}", exc_info=True)
                return {"success": False, "message": f"Error in agent: {str(e)}"}

        return asyncio.run(_agent_cycle())