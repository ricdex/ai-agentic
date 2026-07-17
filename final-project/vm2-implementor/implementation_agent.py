import logging
from shared.claude_client import run_agent
from sandbox import Sandbox

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the repository",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative path from repo root"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or update a file (full content replacement)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string", "description": "Complete file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in source files using grep",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "file_pattern": {"type": "string", "description": "Glob like *.py, *.ts"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the test suite. Always call this before task_complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Optional: specific test file or dir"}
            },
        },
    },
    {
        "name": "task_complete",
        "description": "Signal that implementation is done AND tests pass",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was changed and why"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "files_changed"],
        },
    },
]

SYSTEM = """You are an expert software engineer implementing fixes for GitHub issues in an automated factory.

Workflow:
1. List files to understand the project structure
2. Search and read the relevant code
3. Implement the minimal fix — avoid touching unrelated code
4. Add or update tests if the issue requires it
5. Run tests — if they fail, debug and fix until they pass
6. Call task_complete only when ALL tests pass

Rules:
- Minimal changes: fix only what the issue describes
- Never hardcode credentials or magic values without constants
- If tests fail, read the error, fix, and try again (you have multiple chances)
- Write idiomatic, clean code"""


def implement(
    issue_title: str,
    issue_body: str,
    spec: str,
    sandbox: Sandbox,
    use_powerful: bool = False,
) -> dict:
    model = "powerful" if use_powerful else "standard"
    task_result: dict = {}

    def tool_handler(name: str, inputs: dict) -> str:
        if name == "read_file":
            return sandbox.read_file(inputs["path"])
        if name == "write_file":
            return sandbox.write_file(inputs["path"], inputs["content"])
        if name == "search_code":
            return sandbox.search_code(inputs["pattern"], inputs.get("file_pattern", "*.py"))
        if name == "list_files":
            return sandbox.list_files(inputs.get("directory", "."))
        if name == "run_tests":
            passed, output = sandbox.run_tests(inputs.get("test_path", ""))
            status = "PASSED ✓" if passed else "FAILED ✗"
            return f"Tests {status}\n\n{output}"
        if name == "task_complete":
            task_result["summary"] = inputs.get("summary", "")
            task_result["files_changed"] = inputs.get("files_changed", [])
            return "Completion registered."
        return f"Unknown tool: {name}"

    spec_section = f"\n\n**Spec aprovado:**\n{spec}" if spec else ""
    messages = [{
        "role": "user",
        "content": (
            f"## Issue\n**{issue_title}**\n\n{issue_body}{spec_section}\n\n"
            f"Start by listing the files in the root directory."
        ),
    }]

    logger.info(f"Running implementation agent (model={model})")
    run_agent(
        system=SYSTEM,
        tools=TOOLS,
        messages=messages,
        model=model,
        tool_handler=tool_handler,
    )

    # Confirm tests pass after agent finishes
    tests_passed, test_output = sandbox.run_tests()
    return {
        "success": tests_passed,
        "summary": task_result.get("summary", "Implementation complete"),
        "files_changed": task_result.get("files_changed", []),
        "test_output": test_output,
    }
