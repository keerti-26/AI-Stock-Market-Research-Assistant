"""
The agent: tool schemas + the tool-calling loop.
 
This is the piece that ties groq_client.py (talks to the model) and
agent_tools.py (talks to Lakebase) together.
"""
import json
from agent_tools import get_price_summary, search_news, save_research_notes, compare_tickers, manage_watchlist
from groq_client import GroqClient

# ---- Tool schemas: tell Llama what functions exist and how to call them ----
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_price_summary",
            "description": (
                "Get the most recent price snapshot for a stock ticker, "
                "including close price, day range, % change, and volume."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. AAPL",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": (
                "Semantically search recent news articles for a company or topic. "
                "Use this for questions about news, sentiment, events, or context "
                "that isn't just a raw price lookup — e.g. 'what's happening with "
                "AAPL lately' or 'companies exposed to rising interest rates'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in Natural language",
                    },
                    "ticker":{
                        "type":"string",
                        "description":"Optional: restrict results to this ticker only"
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function":{
            "name" : "save_research_notes",
            "description": (
                "Saves users research notes  for a ticker to reference later."
                "Use this when user explicitly asks to save, log or record a note or analysis"
            ),
            "parameters":{
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol the note is about.",
                    },
                    "notes_text": {
                        "type": "string",
                        "description": "The note content to save.",
                    },
                },
                "required": ["ticker", "notes_text"]
            },
                
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_watchlist",
            "description": (
                "Add or remove a ticker from the user's watchlist. Use this "
                "when the user explicitly asks to add/track or remove/drop "
                "a ticker from their watchlist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove"],
                        "description": "Whether to add or remove the ticker.",
                    },
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. AAPL",
                    },
                },
                "required": ["action", "ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_tickers",
            "description": (
                "Compare price and fundamentals across 2 or more tickers "
                "side by side. Use this when the user asks to compare, "
                "contrast, or see multiple tickers together rather than "
                "asking about just one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of 2+ ticker symbols to compare, e.g. ['AAPL', 'MSFT']",
                    },
                },
                "required": ["tickers"],
            },
        },
    },
]

# Maps tool name (as the model will call it) -> actual Python function
TOOL_FUNCTIONS = {
    "get_price_summary": get_price_summary,
    "search_news": search_news,
    "save_research_notes": save_research_notes,
    "manage_watchlist": manage_watchlist,
    "compare_tickers": compare_tickers,
}

SYSTEM_PROMPT = (
    "You are a stock research assistant. You have tools to look up price data, "
    "search news semantically, and save research notes. Use tools when they'd "
    "help answer the question — don't guess at prices or news you haven't "
    "looked up. Give clear, concise answers grounded in what the tools return."
)

def run_agent(user_query:str, max_turns:int=10) ->str:
    """
    Runs the full tool-calling loop for a single user message and returns
    the agent's final text answer. max_turns caps how many times the model
    can call tools before we force a stop, to avoid an infinite loop if
    something's misbehaving.
    """
    client = GroqClient()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]
 
    for _ in range(max_turns):
        try:
            response = client.chat(messages=messages, tools=TOOLS)
        except Exception as e:
            error_text = str(e)
 
            # First: this failure mode is often intermittent — just retry once.
            try:
                response = client.chat(messages=messages, tools=TOOLS)
            except Exception as e2:
                error_text = str(e2)
                # Retry also failed — try to recover the tool call Llama
                # actually intended, from the malformed generation text.
                recovered = _extract_malformed_tool_call(error_text)
                if recovered is None:
                    return (
                        "I had trouble processing that question due to a "
                        "model formatting issue — could you try rephrasing it?"
                    )
 
                fn_name, args = recovered
                fn = TOOL_FUNCTIONS.get(fn_name)
                try:
                    result = fn(**args) if fn else f"Unknown tool: {fn_name}"
                except Exception as tool_err:
                    result = f"Error running {fn_name}: {tool_err}"
 
                # Feed the recovered result back as plain context and ask
                # for a text-only answer (no tools) to avoid repeating the
                # same malformed-call failure on the next turn.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"(The {fn_name} tool was run and returned: {result})\n\n"
                            "Using that information, answer my original question."
                        ),
                    }
                )
                try:
                    followup = client.chat(messages=messages)
                    return followup.choices[0].message.content
                except Exception:
                    return str(result)
 
        message = response.choices[0].message
 
        if not message.tool_calls:
            # No tool call requested — this is the final answer.
            return message.content
 
        # The model wants to call one or more tools. Append its request to
        # the conversation, then run each tool and append the results.
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        )
 
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn = TOOL_FUNCTIONS.get(fn_name)
 
            try:
                args = json.loads(tool_call.function.arguments)
                result = fn(**args) if fn else f"Unknown tool: {fn_name}"
            except Exception as e:
                # Tool errors get fed back to the model as the tool result,
                # not raised — lets the model explain the failure to the
                # user instead of crashing the whole conversation.
                result = f"Error running {fn_name}: {e}"
 
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )
 
    return "I wasn't able to finish that within the tool-call limit — try rephrasing or breaking it into a simpler question."
 

if __name__ =="__main__":
    print(run_agent("What's the latest news on AI trade rotation?"))