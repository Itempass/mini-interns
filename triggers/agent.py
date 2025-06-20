import logging
import json
from openai import OpenAI
from shared.app_settings import AppSettings
from agentlogger.src.client import save_conversation
from agentlogger.src.models import ConversationData, Message, Metadata
import asyncio
from fastmcp import Client
from mcp.types import Tool, TextContent
from shared.config import settings  

logger = logging.getLogger(__name__)



def _format_mcp_tools_for_openai(tools: list[Tool]) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    logger.info(f"Formatting {len(tools)} MCP tools for OpenAI:")
    for tool in tools:
        logger.info(f"  - Tool: {tool.name} - {tool.description}")
    
    formatted_tools = []
    for tool in tools:
        # Use inputSchema instead of parameters for mcp.types.Tool
        formatted_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        formatted_tools.append(formatted_tool)
        logger.debug(f"Formatted tool: {json.dumps(formatted_tool, indent=2)}")
    
    logger.info(f"Successfully formatted {len(formatted_tools)} tools for OpenAI")
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
        logger.info(f"EmailAgent initialized with MCP client at: http://localhost:{settings.CONTAINERPORT_MCP_IMAP}/mcp")

    def run(self, original_message):
        """Runs the complete agent cycle asynchronously to improve performance."""
        
        async def _agent_cycle():
            email_body = original_message.text or original_message.html
            if not email_body:
                logger.warning("Email has no body content")
                return {"success": False, "message": "Email has no body content."}

            logger.info(f"Processing email UID: {original_message.uid}")
            logger.info(f"Email body length: {len(email_body)} characters")
            logger.debug(f"Email body content: {email_body[:200]}...")

            try:
                async with self.mcp_client as client:
                    # Initial setup: list tools and prepare prompts
                    logger.info("Listing tools from MCP server...")
                    mcp_tools = await client.list_tools()
                    logger.info(f"Retrieved {len(mcp_tools)} tools from MCP server")
                    
                    if not mcp_tools:
                        logger.warning("No tools retrieved from MCP server!")
                        return {"success": False, "message": "No tools available from MCP server"}
                    
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
                    logger.info("System prompt prepared")
                    logger.debug(f"Full system prompt: {full_system_prompt}")
                    
                    messages = [
                        {"role": "system", "content": full_system_prompt},
                        {"role": "user", "content": f"Here is the email to analyze:\n\n---\n{email_body}\n---"}
                    ]
                    logger.info(f"Initial messages prepared with {len(messages)} messages")

                    # Start of the Thought-Action-Observation Loop
                    for turn in range(5): # Max 5 turns to prevent infinite loops
                        logger.info(f"Starting agent turn {turn + 1}/5")
                        
                        # THOUGHT: Get the next action from the LLM
                        logger.info("Agent is thinking...")
                        logger.debug(f"Sending to OpenAI: {len(messages)} messages, {len(tools)} tools")
                        
                        response = await asyncio.to_thread(
                            self.client.chat.completions.create,
                            model=self.app_settings.OPENROUTER_MODEL,
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                        )
                        response_message = response.choices[0].message
                        
                        logger.info(f"OpenAI response received:")
                        logger.info(f"  - Content: {response_message.content}")
                        logger.info(f"  - Tool calls: {len(response_message.tool_calls) if response_message.tool_calls else 0}")
                        
                        if response_message.tool_calls:
                            for i, tool_call in enumerate(response_message.tool_calls):
                                logger.info(f"  - Tool call {i+1}: {tool_call.function.name}")
                                logger.debug(f"    Arguments: {tool_call.function.arguments}")
                        
                        messages.append(response_message.model_dump())

                        # If there are no tool calls, the agent has finished its work.
                        if not response_message.tool_calls:
                            logger.info("Agent decided to finish without tool calls")
                            logger.info(f"Final agent message: {response_message.content}")
                            break

                        # ACTION: Execute the requested tool calls concurrently
                        logger.info(f"Agent performing {len(response_message.tool_calls)} actions...")
                        tasks = []
                        for tool_call in response_message.tool_calls:
                            tool_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)
                            function_args["messageId"] = original_message.uid
                            logger.info(f"Executing tool: {tool_name} with messageId: {original_message.uid}")
                            logger.debug(f"Tool arguments: {function_args}")
                            tasks.append(client.call_tool(tool_name, function_args))
                        
                        tool_results = await asyncio.gather(*tasks)
                        logger.info(f"Tool execution completed, got {len(tool_results)} results")

                        # OBSERVATION: Append tool results to the conversation history
                        for tool_call, result in zip(response_message.tool_calls, tool_results):
                            logger.info(f"Tool {tool_call.function.name} result: {result}")
                            # Extract text from TextContent objects
                            result_text = "\n".join(item.text for item in result)
                            messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": result_text,
                            })
                    
                    logger.info("Agent cycle completed, logging conversation...")
                    
                    # After the loop, log the full conversation
                    try:
                        await save_conversation(ConversationData(
                            metadata=Metadata(conversation_id=f"agent_{original_message.uid}"),
                            messages=[Message(**m) for m in messages if m.get("content") is not None]
                        ))
                        logger.info("Conversation logged successfully")
                    except Exception as e:
                        logger.warning(f"Failed to log agent conversation: {e}")

                    # Return the final message from the assistant
                    final_message = messages[-1]
                    logger.info(f"Final message type: {final_message.get('role')}")
                    logger.info(f"Final message has tool_calls: {bool(final_message.get('tool_calls'))}")
                    
                    if final_message.get("tool_calls"):
                        logger.warning("Agent finished with a tool call, but further action is required")
                        return {"success": False, "message": "Agent finished with a tool call, but further action is required."}
                    else:
                        logger.info(f"Agent completed successfully: {final_message.get('content')}")
                        return {"success": True, "message": f"Agent finished: {final_message.get('content')}"}

            except Exception as e:
                logger.error(f"An error occurred in the Email Agent: {e}", exc_info=True)
                return {"success": False, "message": f"Error in agent: {str(e)}"}

        return asyncio.run(_agent_cycle())