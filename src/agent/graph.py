"""ReAct agent built with LangGraph for stock price queries.

Implements the Reasoning + Acting pattern:
  think  → decide what to do
  action → call a tool
  observe → process the tool result
  loop until the agent has a final answer
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from langchain_aws import ChatBedrock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from config import get_langfuse, get_settings
from src.agent.tools import (
    retrieve_historical_stock_price,
    retrieve_realtime_stock_price,
    search_financial_documents,
)

logger = logging.getLogger(__name__)

# ── Tools list ──────────────────────────────────────────────────────

TOOLS = [
    retrieve_realtime_stock_price,
    retrieve_historical_stock_price,
    search_financial_documents,
]

# ── System prompt ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert financial analyst AI assistant specializing in stock market analysis.

Your capabilities:
- Retrieve real-time stock prices using the retrieve_realtime_stock_price tool.
- Retrieve historical stock price data using the retrieve_historical_stock_price tool.
- Search a financial knowledge base of PDF documents using the search_financial_documents tool.

Guidelines:
1. When asked about current prices, ALWAYS use retrieve_realtime_stock_price.
2. When asked about trends or historical performance, use retrieve_historical_stock_price with appropriate date ranges.
3. When asked about company reports, earnings, or financial documents, search the knowledge base first.
4. Provide clear, concise analysis based on the data you retrieve.
5. If a tool returns an error, explain the issue to the user and suggest alternatives.
6. Always specify the ticker symbol clearly (e.g. AMZN for Amazon).
7. When analyzing trends, explain what the data means in practical terms.

Focus on Amazon (AMZN) stock unless the user specifies otherwise."""

# ── Agent state ─────────────────────────────────────────────────────


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ── Graph construction ──────────────────────────────────────────────


def _build_model() -> ChatBedrock:
    settings = get_settings()
    return ChatBedrock(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        beta_use_converse_api=True,
        model_kwargs={"temperature": 0, "max_tokens": 4096},
    ).bind_tools(TOOLS)


def _should_continue(state: AgentState) -> str:
    """Route after the agent node: call tools or finish."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _agent_node(state: AgentState) -> dict[str, Any]:
    """Invoke the LLM with the current message history."""
    model = _build_model()
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = model.invoke(messages)
    return {"messages": [response]}


def build_graph() -> StateGraph:
    """Construct and compile the ReAct agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Streaming runner ────────────────────────────────────────────────


async def run_agent_stream(
    query: str, user_id: str, trace_id: str | None = None
) -> AsyncGenerator[dict[str, str], None]:
    """Run the ReAct agent and yield streaming events.

    Args:
        query: The user's natural-language question.
        user_id: Identifier for Langfuse tracing.
        trace_id: Optional trace ID to use in Langfuse (for correlation).

    Yields:
        Dicts with keys ``type`` and ``content``:
        - type="thought"      – the agent's reasoning text
        - type="action"       – tool call name + arguments
        - type="observation"  – tool result
        - type="final_answer" – the agent's concluding response
    """
    langfuse = get_langfuse()
    trace = langfuse.trace(id=trace_id, name="stock_agent", user_id=user_id, input=query)

    # Langfuse callback handler to capture LLM calls and tool invocations
    from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

    langfuse_handler = LangfuseCallbackHandler(
        stateful_client=trace,
    )

    app = build_graph()
    input_messages = {"messages": [HumanMessage(content=query)]}
    config = {"callbacks": [langfuse_handler]}

    try:
        async for event in app.astream(input_messages, stream_mode="updates", config=config):
            for node_name, node_output in event.items():
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                yield {
                                    "type": "thought",
                                    "content": msg.content or "Deciding to use a tool...",
                                }
                                yield {
                                    "type": "action",
                                    "content": json.dumps(
                                        {"tool": tc["name"], "args": tc["args"]},
                                    ),
                                }
                        else:
                            yield {
                                "type": "final_answer",
                                "content": msg.content,
                            }

                    elif isinstance(msg, ToolMessage):
                        yield {
                            "type": "observation",
                            "content": msg.content
                            if isinstance(msg.content, str)
                            else json.dumps(msg.content),
                        }

        trace.update(output="completed")
    except Exception as e:
        logger.error("Agent error: %s", e)
        trace.update(output=f"error: {e}")
        yield {"type": "error", "content": str(e)}
    finally:
        langfuse.flush()
