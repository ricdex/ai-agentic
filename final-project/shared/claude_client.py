import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODELS = {
    "fast": "claude-haiku-4-5-20251001",  # triage, routing
    "standard": "claude-sonnet-4-6",       # implement, review
    "powerful": "claude-opus-4-8",         # complex retries
}


def run_agent(
    system: str,
    tools: list[dict],
    messages: list[dict],
    model: str = "standard",
    max_iterations: int = 25,
    tool_handler=None,
) -> tuple[str, list[dict]]:
    """
    ReAct loop. Runs until end_turn or task_complete tool is called.
    Returns (final_text, updated_messages).
    """
    model_id = MODELS.get(model, model)
    history = list(messages)
    final_text = ""

    for _ in range(max_iterations):
        response = client.messages.create(
            model=model_id,
            max_tokens=8096,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=tools,
            messages=history,
        )

        for block in response.content:
            if hasattr(block, "text"):
                final_text = block.text

        if response.stop_reason == "end_turn":
            history.append({"role": "assistant", "content": response.content})
            break

        if response.stop_reason == "tool_use":
            history.append({"role": "assistant", "content": response.content})
            tool_results = []
            done = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "task_complete":
                    done = True
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Marked complete.",
                    })
                    # Store the completion data for the caller
                    if tool_handler:
                        tool_handler("task_complete", block.input)
                    break

                result = tool_handler(block.name, block.input) if tool_handler else f"Tool {block.name} not implemented"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

            history.append({"role": "user", "content": tool_results})
            if done:
                break

    return final_text, history
