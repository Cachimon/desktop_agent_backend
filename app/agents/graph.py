from langgraph.graph import StateGraph, END

from app.agents.nodes import (
    plan_node,
    execute_node,
    summarize_node,
    human_interrupt_node,
    should_interrupt,
    should_replan,
)
from app.agents.state import AgentState


def build_graph(checkpointer=None) -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("plan", plan_node)
    builder.add_node("execute", execute_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("human_confirm", human_interrupt_node)

    builder.set_entry_point("plan")

    builder.add_edge("plan", "execute")

    builder.add_conditional_edges(
        "execute",
        should_interrupt,
        {True: "human_confirm", False: "summarize"},
    )

    builder.add_edge("human_confirm", "execute")

    builder.add_conditional_edges(
        "summarize",
        should_replan,
        {True: "plan", False: END},
    )

    graph = builder.compile(
        checkpointer=checkpointer, interrupt_before=["human_confirm"]
    )
    return graph
