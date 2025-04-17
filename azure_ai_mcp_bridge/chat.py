import asyncio
import json
from azure.ai.projects.models import (
    MessageTextContent,
    RunStatus,
    SubmitToolOutputsAction,
    ToolOutput,
)


async def chat_loop(client, agent_id, tool_map, poll_interval=1):
    thread = None
    while True:
        user = input("You: ")
        if user.lower() in ("quit", "exit"):
            print("Exiting chat session...")
            break
        if not thread:
            thread = client.agents.create_thread()

        client.agents.create_message(thread_id=thread.id, role="user", content=user)
        run = client.agents.create_run(thread_id=thread.id, agent_id=agent_id)

        # Handle tool calls and polling
        if not await _handle_run_and_tools(
            client, thread.id, run.id, tool_map, poll_interval
        ):
            print("Run failed.")
            continue

        # Fetch and print assistant response
        messages = client.agents.list_messages(
            thread_id=thread.id, order="desc", limit=1
        ).data
        if messages and messages[0].role == "assistant":
            content_texts = [
                item.text.value
                for item in messages[0].content
                if isinstance(item, MessageTextContent)
            ]
            print("Assistant:", " ".join(content_texts))


async def _handle_run_and_tools(client, thread_id, run_id, tool_map, poll_interval):
    run = client.agents.get_run(thread_id=thread_id, run_id=run_id)
    while run.status in (
        RunStatus.QUEUED,
        RunStatus.IN_PROGRESS,
        RunStatus.REQUIRES_ACTION,
    ):
        await asyncio.sleep(poll_interval)
        run = client.agents.get_run(thread_id=thread_id, run_id=run_id)

        if run.status is RunStatus.REQUIRES_ACTION:
            outputs = []
            action: SubmitToolOutputsAction = run.required_action
            for call in action.submit_tool_outputs.tool_calls:
                fn_name = call.function.name
                call_id = call.id
                try:
                    args = json.loads(call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                func = tool_map.get(fn_name, None)
                if func:
                    out = await func(**args)
                else:
                    out = f"Unknown tool: {fn_name}"
                outputs.append(ToolOutput(tool_call_id=call_id, output=str(out)))
            if outputs:
                run = client.agents.submit_tool_outputs_to_run(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=outputs,
                )
    return run.status == RunStatus.COMPLETED
