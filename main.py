# main.py: Minimal entrypoint delegating to bridge
import asyncio
from azure_ai_mcp_bridge.bridge import run_bridge_chat

if __name__ == "__main__":
    asyncio.run(run_bridge_chat())
