import os
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from .mcp_integration import managed_mcp_session_HTTP, managed_mcp_session_STDIO, discover_and_prepare_mcp_tools
from .chat import chat_loop

# Load environment variables
load_dotenv()
PROJECT_CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
MCP_SERVER_SCRIPT = os.path.join("servers", "weather_server.py")
MCP_STREAM_SERVER_URL = "http://localhost:8123/mcp"

UseHttp = True  # Set to False to use STDIO mode

async def run_bridge_chat():
    if not PROJECT_CONNECTION_STRING:
        print("ERROR: PROJECT_CONNECTION_STRING not set. See .env.sample.")
        return

    print("Starting Azure AI Agent MCP Bridge...")
    try:
        client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(),
            conn_str=PROJECT_CONNECTION_STRING,
        )
        print("Azure AI Project Client initialized.")
    except Exception as e:
        print(f"ERROR: Failed to initialize AIProjectClient: {e}")
        return

    async with managed_mcp_session_HTTP(MCP_STREAM_SERVER_URL) if UseHttp else managed_mcp_session_STDIO(MCP_SERVER_SCRIPT) as mcp_session:
        if not mcp_session:
            print("ERROR: Could not start MCP session.")
            client.close()
            return

        tool_defs, tool_map = await discover_and_prepare_mcp_tools(mcp_session)
        if not tool_defs:
            print("Warning: No MCP tools discovered.")

        print("Creating or updating Azure AI Agent with MCP tools...")
        try:
            agent = client.agents.create_agent(
                model="gpt-4o",
                name="MCPBridgeAgent_Py_Slim",
                instructions="Use provided MCP tools when appropriate.",
                tools=tool_defs,
            )
            print(f"Agent '{agent.name}' ready (ID: {agent.id}).")
        except Exception as e:
            print(f"ERROR: Agent creation failed: {e}")
            client.close()
            return

        # Enter the chat loop
        await chat_loop(client, agent.id, tool_map)
        # Cleanup: delete the agent after chat session
        try:
            client.agents.delete_agent(agent.id)
            print(f"Deleted agent '{agent.name}' (ID: {agent.id}).")
        except Exception as e:
            print(f"Warning: Failed to delete agent '{agent.id}': {e}")

    client.close()
    print("Bridge chat session ended.")
