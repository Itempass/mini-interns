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
import httpx
from datetime import datetime
from shared.redis.redis_client import get_redis_client
from shared.redis.keys import RedisKeys

logger = logging.getLogger(__name__)



def _format_mcp_tools_for_openai(tools: list[Tool], server_name: str) -> list[dict]:
    """Formats a list of MCP Tools into the format expected by OpenAI."""
    logger.info(f"Formatting {len(tools)} MCP tools for OpenAI using server name '{server_name}':")
    
    formatted_tools = []
    for tool in tools:
        full_tool_name = f"{server_name}-{tool.name}"
        # Use inputSchema instead of parameters for mcp.types.Tool
        formatted_tool = {
            "type": "function",
            "function": {
                "name": full_tool_name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        formatted_tools.append(formatted_tool)
        logger.debug(f"Formatted tool with full name: {json.dumps(formatted_tool, indent=2)}")
    
    logger.info(f"Successfully formatted {len(formatted_tools)} tools for OpenAI")
    return formatted_tools

class EmailAgent:
    def __init__(self, app_settings: AppSettings, trigger_conditions: str, agent_instructions: str):
        self.app_settings = app_settings
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        self.trigger_conditions = trigger_conditions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")

        self.agent_instructions = agent_instructions.replace("<<CURRENT_DATE>>", f"{current_date} (format YYYY-MM-DD)")
        
        redis_client = get_redis_client()
        agent_tools_json = redis_client.get(RedisKeys.AGENT_TOOLS)
        agent_tools = json.loads(agent_tools_json) if agent_tools_json else {}
        
        self.agent_tools = agent_tools
        required_tools_with_order = [
            (tool_id, details['order'])
            for tool_id, details in agent_tools.items()
            if details.get('required')
        ]
        required_tools_with_order.sort(key=lambda x: x[1])
        self.required_tools_sequence = [tool_id for tool_id, order in required_tools_with_order]
        logger.info(f"Required tool sequence loaded: {self.required_tools_sequence}")
        logger.info(f"Full agent tool settings from Redis: {self.agent_tools}")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.app_settings.OPENROUTER_API_KEY,
        )
        self.mcp_client = None  # Will be initialized dynamically
        logger.info("EmailAgent initialized without a pre-configured MCP client.")

    def _get_next_required_tool(self, completed_required_tools: set) -> str:
        """Returns the next required tool that hasn't been completed yet, or None if all are done."""
        for tool_id in self.required_tools_sequence:
            if tool_id not in completed_required_tools:
                return tool_id
        return None

    async def run(self, original_message, contextual_uid: str, thread_context: str = None):
        """Runs the complete agent cycle asynchronously to improve performance."""
        
        email_body = original_message.text or original_message.html
        if not email_body:
            logger.warning("Email has no body content")
            return {"success": False, "message": "Email has no body content."}

        logger.info(f"Processing email UID: {original_message.uid} (Contextual: {contextual_uid})")
        logger.info(f"Email body length: {len(email_body)} characters")
        logger.debug(f"Email body content: {email_body[:200]}...")
        
        if thread_context:
            logger.info(f"Thread context provided with {len(thread_context)} characters")
        else:
            logger.warning("No thread context provided, using single message")

        try:
            # Dynamically discover and select an MCP server
            mcp_server_url = None
            try:
                # The API is running on port 5001 inside the container
                api_url = f"http://localhost:{settings.CONTAINERPORT_API}/mcp/servers"
                logger.info(f"Discovering MCP servers from API at {api_url}...")
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(api_url)
                    response.raise_for_status()
                    servers = response.json()
                    if servers:
                        # For now, just use the first available server.
                        # This can be expanded with more sophisticated selection logic.
                        selected_server = servers[0]
                        server_name = selected_server.get("name")
                        mcp_server_url = selected_server.get("url")
                        logger.info(f"Selected MCP server: {server_name} at {mcp_server_url}")
                    else:
                        logger.error("No MCP servers discovered. Cannot proceed.")
                        return {"success": False, "message": "No MCP servers available."}
            except Exception as e:
                logger.error(f"Failed to discover MCP servers: {e}", exc_info=True)
                return {"success": False, "message": f"Failed to discover MCP servers: {e}"}

            if not mcp_server_url:
                logger.error("MCP server URL not found after discovery. Cannot proceed.")
                return {"success": False, "message": "MCP server URL not found."}

            self.mcp_client = Client(mcp_server_url)

            async with self.mcp_client as client:
                # Initial setup: list tools and prepare prompts
                logger.info(f"Listing tools from MCP server at {mcp_server_url}...")
                all_mcp_tools = await client.list_tools()
                logger.info(f"Retrieved {len(all_mcp_tools)} tools from MCP server, now filtering based on settings...")
                logger.debug(f"Available tool names from MCP server: {[tool.name for tool in all_mcp_tools]}")

                enabled_tool_ids = {tool_id for tool_id, details in self.agent_tools.items() if details.get('enabled')}
                logger.debug(f"Enabled tool IDs from settings: {enabled_tool_ids}")
                mcp_tools = [tool for tool in all_mcp_tools if f"{server_name}-{tool.name}" in enabled_tool_ids]
                logger.info(f"Filtered to {len(mcp_tools)} enabled tools.")
                
                if not mcp_tools:
                    logger.warning("No enabled tools available for the agent!")
                    return {"success": False, "message": "No enabled tools available"}
                
                tools = _format_mcp_tools_for_openai(mcp_tools, server_name=server_name)

                system_prompt = f"""
                    You are an agent that should follow the user instructions and execute tasks, using the tools provided to you.

                    The user will provide you with instructions on what to do. Follow these dilligently. 

                    You have multiple tools available to you. You MUST use the required tools, and you MUST use them in this order: {', '.join(self.required_tools_sequence)}.
                    You can use the non-required tools at your discretion.
                """

                # NEW: Use thread context instead of single message details
                if thread_context:
                    input_prompt = f"""
                        Here is the email thread to analyze:
                        
                        TRIGGERING MESSAGE UID: {contextual_uid}
                        
                        FULL THREAD CONTEXT:
                        {thread_context}
                        
                        Please focus your analysis on the triggering message while considering the full conversation context. The triggering message is clearly marked in the thread above.
                    """
                else:
                    # Fallback to single message format
                    input_prompt = f"""
                        Here is the email to analyze (single message - no thread context available):
                        UID: {contextual_uid}
                        From: {original_message.from_}
                        To: {original_message.to}
                        Date: {original_message.date_str}
                        Subject: {original_message.subject}
                        Body:
                        {email_body}
                    """

          
                
                messages = [
                    {"role": "system", "content": self.agent_instructions},
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_prompt},
                    {"role": "system", "content": f"First, think about the user's instructions, the tools available to you, and the steps you need to take. Then, execute. You MUST use the required tools, and you MUST use them in this order initially: {', '.join(self.required_tools_sequence)}. However, you can call any previously completed required tool again if needed. You can use the non-required tools at your discretion at any time."}
                ]
                logger.info(f"Initial messages prepared with {len(messages)} messages")

                completed_required_tools = set()

                # Start of the Thought-Action-Observation Loop
                for turn in range(7): # Max 7 turns to prevent infinite loops
                    next_required_tool = self._get_next_required_tool(completed_required_tools)
                    logger.info(f"Starting agent turn {turn + 1}/7. Completed required tools: {completed_required_tools}. Next required: {next_required_tool}")
                    
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

                    if not response_message.tool_calls:
                        if required_tool_index < len(self.required_tools_sequence):
                            next_required_tool = self.required_tools_sequence[required_tool_index]
                            nudge_message = f"You cannot finish yet. You must call the '{next_required_tool}' tool next. The required tool order is: {', '.join(self.required_tools_sequence)}."
                            messages.append({"role": "system", "content": nudge_message})
                            logger.info(f"Nudging agent: {nudge_message}")
                            continue
                        else:
                            logger.info("Agent decided to finish, and all required tools are done.")
                            break

                    if response_message.tool_calls:
                        called_tool_ids = {tc.function.name for tc in response_message.tool_calls}
                        
                        # Check if we need to enforce tool order
                        if next_required_tool and next_required_tool not in called_tool_ids:
                            # Check if agent is trying to call future required tools that haven't been reached yet
                            future_required_tools = set()
                            found_next = False
                            for tool_id in self.required_tools_sequence:
                                if tool_id == next_required_tool:
                                    found_next = True
                                elif found_next:
                                    future_required_tools.add(tool_id)
                            
                            called_future_tools = called_tool_ids.intersection(future_required_tools)
                            
                            if called_future_tools:
                                logger.warning(f"Agent tried to call future required tools {called_future_tools} before completing {next_required_tool}. Intervening.")
                                tool_error_message = f"Error: Tool call denied. You cannot call {', '.join(called_future_tools)} until you have called '{next_required_tool}' first. The required tool order is: {', '.join(self.required_tools_sequence)}. You have completed: {', '.join(completed_required_tools) if completed_required_tools else 'none'}."
                                
                                for tool_call in response_message.tool_calls:
                                    messages.append({
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": tool_call.function.name,
                                        "content": tool_error_message,
                                    })
                                continue
                            else:
                                # Agent is calling completed required tools or non-required tools - allow it
                                logger.info(f"Agent called {called_tool_ids} without calling next required tool '{next_required_tool}'. This is allowed (re-calls or non-required tools).")
                        else:
                            logger.info(f"Agent called required tool '{next_required_tool}' as expected, or no required tools pending.")

                        logger.info(f"Agent performing {len(response_message.tool_calls)} actions...")
                        tasks = []
                        for tool_call in response_message.tool_calls:
                            full_tool_name = tool_call.function.name
                            short_tool_name = full_tool_name.replace(f"{server_name}-", "", 1)
                            function_args = json.loads(tool_call.function.arguments)
                            logger.info(f"Executing tool: {full_tool_name} (short: {short_tool_name}) with arguments: {function_args}")
                            tasks.append(client.call_tool(short_tool_name, function_args))
                        
                        tool_results = await asyncio.gather(*tasks)
                        logger.info(f"Tool execution completed, got {len(tool_results)} results")

                        for tool_call, result in zip(response_message.tool_calls, tool_results):
                            logger.info(f"Tool {tool_call.function.name} result: {result}")
                            result_text = "\n".join(item.text for item in result)
                            messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": tool_call.function.name,
                                "content": result_text,
                            })

                        # Update completed required tools tracking
                        if next_required_tool and next_required_tool in called_tool_ids:
                            completed_required_tools.add(next_required_tool)
                            logger.info(f"Required tool '{next_required_tool}' was successfully called and marked as completed.")
                        
                        # Also track any other required tools that might have been called (re-calls)
                        for tool_id in called_tool_ids:
                            if tool_id in self.required_tools_sequence:
                                completed_required_tools.add(tool_id)
                                logger.debug(f"Required tool '{tool_id}' marked as completed (re-call or parallel call).")
                
                logger.info("Agent cycle completed, logging conversation...")
                
                # After the loop, log the full conversation
                try:
                    await save_conversation(ConversationData(
                        metadata=Metadata(
                            conversation_id=f"agent_{contextual_uid}",
                            readable_workflow_name="Email Agent",
                            readable_instance_context=f"{original_message.from_} - {original_message.subject}"
                        ),
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