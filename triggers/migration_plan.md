# Plan for Migrating `triggers` to an Agent-Based Approach

This document outlines the plan to migrate the current trigger system from a hardcoded LLM workflow to a more flexible, agent-based architecture. The key principle is to simplify the logic while preserving all existing functionality.

## 1. Current Architecture

The current system in the `/triggers` directory works as follows:

-   `main.py`: Polls an IMAP server for new emails.
-   `rules.py`: Filters incoming emails based on sender rules.
-   `llm_workflow.py`: Contains a hardcoded, two-step LLM chain:
    1.  **Trigger Check**: An LLM call determines if a draft reply should be created based on prompts stored in Redis.
    2.  **Draft Generation**: If the trigger condition is met, a second LLM call generates the content for the draft reply.
-   `draft_handler.py`: A utility that takes the generated content and creates a draft in the user's email account via IMAP.

The user has referred to the two LLM calls in `llm_workflow.py` as two separate, hardcoded flows.

## 2. Proposed Agent Architecture

We will replace the rigid, two-step workflow with a single, intelligent agent. This agent will be responsible for the entire decision-making process, from analyzing the email to generating a response.

The core idea is to use a modern, tool-calling LLM that can decide for itself whether an action (like drafting a reply) is necessary.

### Key Changes:

-   **New `triggers/agent.py`**: This file will house the new `EmailAgent` class.
-   **Deletion of `triggers/llm_workflow.py`**: The logic in this file will be consolidated into the new agent, making it obsolete.
-   **Modification of `triggers/main.py`**: The main loop will be simplified to instantiate and run the `EmailAgent` for each new email.

## 3. Implementation Steps

### Step 1: Create `triggers/agent.py`

This new file will define the `EmailAgent`.

```python
# triggers/agent.py (conceptual)

from openai import OpenAI
from triggers.draft_handler import create_draft_reply
# ... other imports

class EmailAgent:
    def __init__(self, settings, prompts):
        self.client = OpenAI(...)
        self.prompts = prompts
        self.settings = settings

    def run(self, original_message):
        # 1. Define the tool(s) available to the agent.
        #    The function signature is important for the LLM to understand.
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_draft_reply",
                    "description": "Creates and saves a draft email reply.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "draft_content": {
                                "type": "string",
                                "description": "The full content of the email draft.",
                            },
                        },
                        "required": ["draft_content"],
                    },
                },
            }
        ]

        # 2. Construct the system prompt.
        #    This combines the trigger conditions and drafting instructions.
        system_prompt = f"""
        You are an intelligent email assistant. Your task is to analyze an incoming email and decide if a draft reply is warranted based on the following rules:
        {self.prompts.trigger_conditions}

        If and only if a draft is warranted, you must call the `create_draft_reply` tool.
        When generating the draft content, follow these instructions:
        {self.prompts.system_prompt}

        Here is some additional context about the user you are assisting:
        {self.prompts.user_context}
        """

        # 3. Make a single call to the LLM.
        response = self.client.chat.completions.create(
            model=self.settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the email to analyze:\n\n{original_message.text}"}
            ],
            tools=tools,
            tool_choice="auto",
        )

        # 4. Process the LLM's response.
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            for tool_call in tool_calls:
                if tool_call.function.name == "create_draft_reply":
                    # The LLM decided to create a draft.
                    args = json.loads(tool_call.function.arguments)
                    return create_draft_reply(
                        original_msg=original_message,
                        draft_content=args["draft_content"]
                    )
        
        # The LLM decided not to create a draft.
        return {"success": False, "message": "Agent decided not to create a draft."}
```

### Step 2: Refactor `triggers/main.py`

The `process_message` function will be simplified to use the new agent.

```python
# triggers/main.py (conceptual change)

# from triggers.llm_workflow import run_workflow # REMOVE
# from triggers.draft_handler import create_draft_reply # REMOVE
from triggers.agent import EmailAgent # ADD

def process_message(msg):
    # ... (existing code for logging, filtering, etc.) ...

    if body:
        # ... (check for DRAFT_CREATION_ENABLED) ...
        
        # Get prompts from Redis (this might be moved into the agent)
        # ...

        # Instantiate and run the agent
        agent = EmailAgent(settings=app_settings, prompts=...)
        agent_result = agent.run(msg)

        if agent_result["success"]:
            logger.info("Draft created successfully by agent!")
            logger.info(agent_result["message"])
        else:
            logger.error(f"Agent did not create draft: {agent_result['message']}")
```

### Step 3: Delete `triggers/llm_workflow.py`

Once the agent is implemented and integrated, `llm_workflow.py` is no longer needed and should be deleted to avoid confusion.

## 4. Benefits of this Approach

-   **Simplicity**: The logic is consolidated into a single class. The control flow in `main.py` becomes more straightforward.
-   **Flexibility**: An agent-based approach is inherently more extensible. We can add new tools or more complex reasoning to the agent in the future without major refactoring.
-   **Maintainability**: Having one component (`EmailAgent`) responsible for all LLM interactions makes the system easier to debug and maintain.
-   **Efficiency**: We potentially reduce the number of LLM calls from two to one, as the agent can decide and generate in a single pass.