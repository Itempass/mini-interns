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
    def __init__(self, app_settings: AppSettings, trigger_conditions: str, system_prompt: str, user_context: str, agent_steps: str, agent_instructions: str):
        self.app_settings = app_settings
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        self.trigger_conditions = trigger_conditions.replace("<<CURRENT_DATE>> YYYY-MM-DD", current_date)
        self.system_prompt = system_prompt.replace("<<CURRENT_DATE>> YYYY-MM-DD", current_date)
        self.user_context = user_context.replace("<<CURRENT_DATE>> YYYY-MM-DD", current_date)
        self.agent_steps = agent_steps.replace("<<CURRENT_DATE>> YYYY-MM-DD", current_date)
        self.agent_instructions = agent_instructions.replace("<<CURRENT_DATE>> YYYY-MM-DD", current_date)
        s
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.app_settings.OPENROUTER_API_KEY,
        )
        self.mcp_client = None  # Will be initialized dynamically
        logger.info("EmailAgent initialized without a pre-configured MCP client.")

    def run(self, original_message, contextual_uid: str):
        """Runs the complete agent cycle asynchronously to improve performance."""
        
        async def _agent_cycle():
            email_body = original_message.text or original_message.html
            if not email_body:
                logger.warning("Email has no body content")
                return {"success": False, "message": "Email has no body content."}

            logger.info(f"Processing email UID: {original_message.uid} (Contextual: {contextual_uid})")
            logger.info(f"Email body length: {len(email_body)} characters")
            logger.debug(f"Email body content: {email_body[:200]}...")

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
                            mcp_server_url = selected_server.get("url")
                            logger.info(f"Selected MCP server: {selected_server.get('name')} at {mcp_server_url}")
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
                    mcp_tools = await client.list_tools()
                    logger.info(f"Retrieved {len(mcp_tools)} tools from MCP server")
                    
                    if not mcp_tools:
                        logger.warning("No tools retrieved from MCP server!")
                        return {"success": False, "message": "No tools available from MCP server"}
                    
                    tools = _format_mcp_tools_for_openai(mcp_tools)

                    system_prompt = f"""
                        You are an agent that should follow the user instructions and execute tasks, using the tools provided to you.

                        The user will provide you with instructions on what to do. Follow these dilligently. 
                    """

                    agent_steps_prompt = f"""
                        These are the steps you must follow:
                        {self.agent_steps}
                    """

                    input_prompt = f"""
                        Here is the email to analyze:
                        UID: {original_message.uid}
                        From: {original_message.from_}
                        To: {original_message.to}
                        Date: {original_message.date_str}
                        Subject: {original_message.subject}
                        Body:
                        {email_body}
                    """

              
                    
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": self.agent_instructions},
                        #{"role": "user", "content": agent_steps_prompt},
                        {"role": "user", "content": input_prompt}
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
                            logger.info(f"Executing tool: {tool_name} with arguments: {function_args}")
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
                            metadata=Metadata(conversation_id=f"agent_{contextual_uid}"),
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