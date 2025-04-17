# Azure AI Agent - MCP Bridge

This project demonstrates how to integrate tools exposed via the Model Context Protocol (MCP) into the Azure AI Agent Service using the Python SDK.

It acts as a bridge, discovering tools from a running MCP server and dynamically wrapping them as functions callable by an Azure AI Agent.

## Features

- Connects to an MCP server (currently uses stdio transport for local testing).
- Discovers available MCP tools (`list_tools`).
- Dynamically generates Python `async` wrapper functions for each MCP tool.
- Converts MCP tool input schemas to OpenAI-compatible function parameter schemas.
- Prepares tool definitions suitable for the `azure-ai-projects` SDK.
- Creates an Azure AI Agent configured with these tool definitions.
- Registers these wrappers with an `azure.ai.assistant.agent.AssistantAgent` using `FunctionTool`.
- **Handles tool execution** by polling the agent run status and manually calling the appropriate wrapper function when `requires_action`.
- Submits tool results back to the agent run.
- Includes a sample MCP weather server (`servers/weather_server.py`) for testing.
- Provides a basic interactive console loop (`main.py`) to chat with the agent.

## Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd azure-ai-mcp-bridge
    ```

2.  **Create and activate a virtual environment:**

    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # MacOS/Linux
    source .venv/bin/activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Azure AI Project:**
    - Copy the sample environment file: `cp .env.sample .env` (or `copy .env.sample .env` on Windows).
    - Edit the `.env` file and replace the placeholder value with your actual **Azure AI Project Connection String**. You can find this in the Azure AI Foundry portal under your project's overview page, or construct it using the format: `<HostName>;<AzureSubscriptionId>;<ResourceGroup>;<ProjectName>`. The `HostName` can be derived from the project's `discovery_url`.

## Running the Agent

Execute the main script (minimal entrypoint):

```bash
python main.py
```

This will orchestrate the MCP session, tool discovery, agent setup, and interactive loop via the modules in `azure_ai_mcp_bridge/`:

- `bridge.py`: handles MCP session management, tool preparation, and Azure AI Agent creation.
- `chat.py`: manages the chat loop, polling runs, executing MCP tool wrappers, and displaying responses.
- `mcp_integration.py`: contains the core logic for connecting to an MCP server, discovering tools, and generating async wrappers.

## Project Structure

```
main.py               # Minimal entrypoint delegating to bridge.run_bridge_chat()
pyproject.toml        # Project metadata and dependencies
README.md             # This documentation
azure_ai_mcp_bridge/  # Core modules
    bridge.py         # Orchestrates MCP & Azure AI Agent integration
    chat.py           # Interactive chat and run polling/tool execution
    mcp_integration.py# MCP client session and tool wrapper generation
servers/              # Example MCP server implementation (weather_server.py)
```

## Testing in VS Code

1.  Open the `azure-ai-mcp-bridge` folder in Visual Studio Code.
2.  Ensure VS Code selects the Python interpreter from your `.venv` directory (use `Ctrl+Shift+P` -> `Python: Select Interpreter`).
3.  Make sure you have created and configured your `.env` file as described in Setup step 4.
4.  Open `main.py`.
5.  Run or debug the file (F5 / Ctrl+F5). The script uses `DefaultAzureCredential` which often works seamlessly with VS Code's Azure login and `python-dotenv` for the connection string.

## How it Works

1.  `main.py` starts and loads configuration.
2.  It uses the `managed_mcp_session` context manager from `mcp_integration.py` to start the MCP server script (`weather_server.py`) and establish a `ClientSession` over stdio.
3.  `register_mcp_tools_as_azure_agent_functions` is called with the active `ClientSession`.
4.  It calls `session.list_tools()` to get MCP tool definitions.
5.  For each tool, it:
    - Creates an `async def mcp_tool_wrapper(**kwargs)` function. This wrapper, when called by the agent, will use the `ClientSession` to execute the actual MCP tool (`session.call_tool`).
    - Calls `convert_mcp_schema_to_openai_schema` to translate the MCP `inputSchema` into the format Azure AI Agent expects for function parameters.
    - Creates an `azure.ai.assistant.functions.FunctionTool` object containing both the wrapper function and its schema definition.
    - Adds the `FunctionTool` to the `agent.tools`.
6.  `main.py` enters an interactive loop:
    - User input is added as a message to a thread.
    - `project_client.agents.create_run` starts the agent processing.
    - The script **polls** `project_client.agents.get_run`.
    - If `run.status == RunStatus.REQUIRES_ACTION`:
      - It inspects `run.required_action` for tool calls.
      - For each call, it finds the matching wrapper function in the `tool_function_map`.
      - It `await`s the wrapper function (which calls the MCP server via the bridge).
      - It calls `project_client.agents.submit_tool_outputs_to_run` with the results.
    - If `run.status == RunStatus.COMPLETED`: The loop breaks.
7.  Final messages are retrieved using `project_client.agents.list_messages` and displayed.
8.  The `managed_mcp_session` context manager ensures the MCP server process is cleaned up.
