from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from agent.tools import TOOLS


def run(query: str) -> str:
    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    agent = create_react_agent(llm, TOOLS)
    result = agent.invoke({"messages": [("human", query)]})
    return result["messages"][-1].content


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or input("Ask: ")
    print(run(query))
