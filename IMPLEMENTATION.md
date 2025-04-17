# Implementation Details: Azure AI Agent - MCP Bridge

This document explains the inner workings of the MCP Bridge for Azure AI Agents. If you're looking to understand how it works under the hood or extend it for your own use cases, you're in the right place.

## Architecture Overview

The bridge isn't a single component but rather a system of cooperating parts that connect two different worlds:

```
  Azure AI Agent Service      |       Model Context Protocol
  ----------------------------|----------------------------
  Function Definitions        |       MCP Tool Schemas
  Function Calls              |       MCP Tool Calls
  Azure AI Agent              |       MCP Server
```

## Core Components

### 1. MCP Integration (`mcp_integration.py`)

This module handles all communication with the MCP server:

- **`managed_mcp_session`**: Creates and manages a connection to an MCP server using stdio
- **`discover_and_prepare_mcp_tools`**: Discovers available tools from the server
- **`convert_mcp_schema_to_openai_function_parameters`**: Translates MCP schemas to OpenAI-compatible formats

The most important part is the dynamic wrapper generator:

```python
# This creates wrapper functions that:
# 1. Get called by the Azure AI Agent
# 2. Forward parameters to the MCP tool
# 3. Format the result for Azure AI

def create_wrapper_func(current_tool_name: str, session: ClientSession) -> WrapperFunction:
    async def mcp_tool_wrapper(**kwargs: Any) -> Any:
        """Dynamically generated wrapper for MCP tool."""
        # Call the MCP tool
        call_result = await session.call_tool(current_tool_name, arguments=kwargs)

        # Format the result for the agent
        result_content = "Tool executed, no text content returned."
        if call_result and call_result.content:
            # Process different content types...

        return result_content
```

### 2. Bridge Orchestration (`bridge.py`)

This module coordinates the overall process:

- Initializes the Azure AI Project Client with credentials
- Connects to the MCP server via `managed_mcp_session`
- Discovers tools and creates wrappers via `discover_and_prepare_mcp_tools`
- Creates or updates an Azure AI Agent with the tool definitions
- Launches the interactive chat session

### 3. Chat and Execution (`chat.py`)

This module handles the chat loop and tool execution:

- **`chat_loop`**: Manages the interactive console
- **`_handle_run_and_tools`**: Monitors run status and executes tools when requested

A critical piece is the tool execution workflow:

```python
# When Azure AI wants to call a tool:
for call in action.submit_tool_outputs.tool_calls:
    fn_name = call.function.name  # Which tool to call
    call_id = call.id             # ID for tracking the call
    args = json.loads(call.function.arguments)  # Parameters for the tool

    # This is where we find and call the MCP wrapper function
    func = tool_map.get(fn_name, None)
    if func:
        out = await func(**args)  # Call the wrapper function

    # Send the result back to Azure AI
    outputs.append(ToolOutput(tool_call_id=call_id, output=str(out)))
```

## The "Bridge" Explained

The term "bridge" refers to how this system connects two different worlds:

1. **On the Azure AI side**:

   - Tools are defined as functions with parameters
   - The agent decides when to call these functions
   - Function inputs and outputs use the OpenAI format

2. **On the MCP side**:
   - Tools are defined with schemas
   - Tools are called with specific arguments
   - Results are returned in MCP format

The bridge dynamically translates between these worlds:

```
Agent calls "get_forecast" → Bridge wrapper receives call → Wrapper calls MCP tool →
MCP server executes → Returns result → Wrapper formats result → Agent receives result
```

What makes this powerful is that it's completely dynamic - you don't have to manually code each function. The bridge inspects the MCP server's tools at runtime and creates all the necessary connections.

## Data Flow Example

Here's what happens when you ask about the weather:

1. **User**: "What's the weather in New York?"
2. **Azure AI Agent**:
   - Analyzes the request
   - Decides to use the `get_forecast` tool
   - Sends a function call request with parameters: `{"latitude": 40.7128, "longitude": -74.006}`
3. **Bridge**:
   - Receives the function call
   - Finds the correct wrapper function from `tool_map`
   - Calls the wrapper with the provided parameters
4. **MCP Wrapper**:
   - Formats the call for the MCP server
   - Makes the call via the MCP session
   - Receives the raw result
   - Formats the result into text for the agent
5. **Azure AI Agent**:
   - Receives the formatted result
   - Uses it to construct a response
6. **User**: Sees the response about New York's weather

## Extension Points

If you want to extend this bridge, here are the key points:

1. **Support for Different MCP Servers**:

   - Modify `managed_mcp_session` in `mcp_integration.py` to support other MCP transports
   - For HTTP-based MCP servers, you'd implement the new Streamable HTTP protocol

2. **Enhanced Tool Definitions**:

   - Improve `convert_mcp_schema_to_openai_function_parameters` to handle more complex schemas

3. **Result Processing**:

   - Update the result processing in the wrapper functions to handle different content types

4. **Multiple MCP Servers**:
   - Modify `bridge.py` to connect to multiple MCP servers and aggregate their tools

## Limitations and Future Work

Current limitations:

- Only supports stdio transport (not HTTP)
- Only connects to one MCP server at a time
- Basic error handling
- No streaming support for long-running tools

Future improvements could include:

- Supporting HTTP-based MCP servers with the new Streamable HTTP protocol
- Improved error handling and retry mechanisms
- Support for connecting to multiple MCP servers simultaneously
- Streaming results for long-running operations
- Better handling of various content types (images, audio, etc.)
