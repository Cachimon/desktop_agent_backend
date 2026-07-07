from langgraph.graph import StateGraph, END
from langgraph.types import RetryPolicy

from app.agents.nodes import (
    tool_executor_node,
    should_use_tools,
    agent_node,
    route_after_confirm,
    route_tools,
    human_confirm_node, subagent_node,
)
from app.agents.state import AgentState


def build_graph(checkpointer=None) -> StateGraph:
    builder = StateGraph(AgentState)
    builder.set_node_defaults(retry_policy=RetryPolicy(max_attempts=1))

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_executor_node)
    builder.add_node("human_confirm", human_confirm_node)
    builder.add_node("subagent_node", subagent_node)

    builder.set_entry_point("agent")

    builder.add_conditional_edges(
        "agent",
        should_use_tools,
        {"tools": "tools", "end": END, "human_confirm": "human_confirm"},
    )

    builder.add_conditional_edges(
        "tools",
        route_tools,
        {"human_confirm": "human_confirm", "agent": "agent", "subagent_node": "subagent_node"},
    )

    builder.add_edge(
        "human_confirm",
        "agent",  # 不管用户确认的结果是啥，就跑回agent
    )

    graph = builder.compile(checkpointer=checkpointer)
    # await graph.astream_events()
    return graph
