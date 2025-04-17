from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple

# MCP Client Library Imports
from mcp import ClientSession, StdioServerParameters
from mcp import types as mcp_types
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def managed_mcp_session(
    server_script_path: str,
) -> AsyncIterator[Optional[ClientSession]]:
    """Creates and manages an MCP client session connected to a server."""
    session: Optional[ClientSession] = None
    exit_stack = AsyncExitStack()
    try:
        print(f"[MCP Bridge] Connecting to server: {server_script_path}")
        is_python = server_script_path.endswith(".py")
        command = "python" if is_python else "node"

        server_params = StdioServerParameters(
            command=command, args=[server_script_path]
        )
        read_stream, write_stream = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        print("[MCP Bridge] MCP Session Initialized.")
        yield session
    except Exception as e:
        print(f"[MCP Bridge] ERROR: Failed to initialize MCP session: {e}")
        yield None
    finally:
        print("[MCP Bridge] Closing MCP connection...")
        await exit_stack.aclose()


def convert_mcp_schema_to_openai_function_parameters(
    mcp_schema,
) -> Dict[str, Any]:
    """Translates MCP tool schema to OpenAI-compatible function parameters."""
    if not mcp_schema or not hasattr(mcp_schema, "properties"):
        return {"type": "object", "properties": {}}

    properties = mcp_schema.properties if mcp_schema.properties else {}
    required = mcp_schema.required if mcp_schema.required else []
    converted_properties = {}

    if isinstance(properties, dict):
        for key, value in properties.items():
            if isinstance(value, dict):
                prop_details = {}
                prop_details["type"] = value.get("type", "string")
                if "description" in value:
                    prop_details["description"] = value["description"]
                converted_properties[key] = prop_details
            else:
                print(f"[MCP Bridge] Skipping invalid property format: '{key}'")
    else:
        print(f"[MCP Bridge] Invalid schema properties format: {properties}")

    openai_params = {"type": "object", "properties": converted_properties}
    if required:
        openai_params["required"] = required
    return openai_params


# Type aliases for clarity
WrapperFunction = Callable[..., Awaitable[Any]]
ToolFunctionMap = Dict[str, WrapperFunction]


async def discover_and_prepare_mcp_tools(
    mcp_session: ClientSession,
) -> Tuple[List[Dict[str, Any]], ToolFunctionMap]:
    """
    Discovers MCP tools and creates Azure AI-compatible wrappers.

    Returns:
        Tuple of (tool definitions, function map)
    """
    tool_definitions = []
    tool_function_map: ToolFunctionMap = {}

    if not mcp_session:
        print("[MCP Bridge] No active MCP session. Cannot discover tools.")
        return tool_definitions, tool_function_map

    try:
        print("[MCP Bridge] Listing MCP tools...")
        list_tools_result = await mcp_session.list_tools()
        mcp_tools: List[mcp_types.Tool] = (
            list_tools_result.tools if list_tools_result else []
        )
        print(f"[MCP Bridge] Discovered {len(mcp_tools)} MCP tools.")
    except Exception as e:
        print(f"[MCP Bridge] ERROR: Failed to list MCP tools: {e}")
        return tool_definitions, tool_function_map

    for mcp_tool in mcp_tools:
        tool_name = mcp_tool.name
        tool_description = (
            mcp_tool.description or f"Executes the MCP tool '{tool_name}'."
        )
        input_schema = getattr(mcp_tool, "inputSchema", None)

        print(f"  - Processing MCP tool: '{tool_name}'")

        # Create the async wrapper function
        def create_wrapper_func(
            current_tool_name: str, session: ClientSession
        ) -> WrapperFunction:
            async def mcp_tool_wrapper(**kwargs: Any) -> Any:
                """Dynamically generated wrapper for MCP tool."""
                print(
                    f"--->>> [Agent->MCP Bridge] Executing wrapper for MCP tool: '{current_tool_name}'"
                )
                print(f"        Arguments: {kwargs}")
                try:
                    call_result = await session.call_tool(
                        current_tool_name, arguments=kwargs
                    )
                    print(
                        f"<--- [MCP Bridge<-MCP Server] MCP tool '{current_tool_name}' raw result received."
                    )

                    # Format the result for the agent
                    result_content = "Tool executed, no text content returned."
                    if call_result and call_result.content:
                        if isinstance(call_result.content, list):
                            texts = [
                                item.text
                                for item in call_result.content
                                if isinstance(item, mcp_types.TextContent)
                            ]
                            result_content = (
                                "\n".join(texts) if texts else str(call_result.content)
                            )
                        elif isinstance(call_result.content, str):
                            result_content = call_result.content
                        else:
                            result_content = str(call_result.content)

                    print(
                        f"        Formatted result (first 200 chars): {result_content[:200]}..."
                    )
                    return result_content

                except Exception as e:
                    print(
                        f"[MCP Bridge] ERROR: Exception during MCP tool '{current_tool_name}' execution: {e}"
                    )
                    return f"Error executing tool '{current_tool_name}': {str(e)}"

            # Set a recognizable name for debugging
            mcp_tool_wrapper.__name__ = f"mcp_wrapper_{current_tool_name}"
            return mcp_tool_wrapper

        # Generate the wrapper and store it
        wrapper_function = create_wrapper_func(tool_name, mcp_session)
        tool_function_map[tool_name] = wrapper_function

        # Prepare the tool definition for the agent
        try:
            function_parameters = convert_mcp_schema_to_openai_function_parameters(
                input_schema
            )
            tool_definition = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_description,
                    "parameters": function_parameters,
                },
            }

            if isinstance(tool_definition["function"]["parameters"], dict):
                tool_definitions.append(tool_definition)
                print(f"    Prepared definition for tool '{tool_name}'.")
            else:
                print(
                    f"    ERROR: Invalid parameter schema for '{tool_name}'. Skipping tool definition."
                )

        except Exception as e:
            print(
                f"    ERROR: Failed to create definition for tool '{tool_name}': {e}. Skipping."
            )

    print(
        f"[MCP Bridge] Prepared {len(tool_definitions)} tool definitions and {len(tool_function_map)} wrapper functions."
    )
    return tool_definitions, tool_function_map
