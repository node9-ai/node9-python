"""
LangChain integration — secure any Tool by decorating its _run method.

Install:
  pip install node9 langchain langchain-openai

Run the Node9 daemon first:
  npx @node9/proxy daemon
"""

from node9 import protect, ActionDeniedException
from langchain.tools import BaseTool
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# --- Wrap any LangChain tool by decorating _run ---

class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = "Write content to a file on disk."

    @protect("write_file")
    def _run(self, path: str, content: str) -> str:
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"


class RunShellTool(BaseTool):
    name: str = "bash"
    description: str = "Run a shell command and return its output."

    @protect("bash")
    def _run(self, command: str) -> str:
        import subprocess
        return subprocess.check_output(command, shell=True, text=True)


class DeleteFileTool(BaseTool):
    name: str = "delete_file"
    description: str = "Permanently delete a file."

    @protect("delete_file")
    def _run(self, path: str) -> str:
        import os
        os.remove(path)
        return f"Deleted {path}"


# --- Build the agent ---

def build_agent() -> AgentExecutor:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    tools = [WriteFileTool(), RunShellTool(), DeleteFileTool()]

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful AI assistant. Use tools when needed."),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


if __name__ == "__main__":
    agent = build_agent()
    try:
        result = agent.invoke({"input": "Write a summary of today's tasks to /tmp/tasks.txt"})
        print(result["output"])
    except ActionDeniedException as e:
        print(f"Node9 blocked the action: {e}")
