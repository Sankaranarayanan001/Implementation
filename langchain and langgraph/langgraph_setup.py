from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import ToolMessage

from tools import tools_by_name
from langchain_setup import chain


# ---------- State ----------
class State(TypedDict):
    messages: Annotated[list, add_messages]


# ---------- Nodes ----------
def call_model(state: State) -> State:
    response = chain.invoke({"messages": state["messages"]})
    return {"messages": [response]}


def call_tool(state: State) -> State:
    last_message = state["messages"][-1]
    tool_messages = []
    for tool_call in last_message.tool_calls:
        print(f"  -> calling tool: {tool_call['name']} with args {tool_call['args']}")
        result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
    return {"messages": tool_messages}


def should_continue(state: State) -> str:
    last_message = state["messages"][-1]
    return "call_tool" if last_message.tool_calls else "end"


# ---------- Build graph ----------
graph = StateGraph(State)
graph.add_node("call_model", call_model)
graph.add_node("call_tool", call_tool)
graph.set_entry_point("call_model")
graph.add_conditional_edges("call_model", should_continue, {"call_tool": "call_tool", "end": END})
graph.add_edge("call_tool", "call_model")

# Exported compiled app, used by main.py
app = graph.compile()