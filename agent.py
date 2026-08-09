"""
The agent: tool schemas + the tool-calling loop.
 
This is the piece that ties groq_client.py (talks to the model) and
agent_tools.py (talks to Lakebase) together.
"""
import json
from agent_tools import get_price_summary, search_news, save_research_notes
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
                    "note_text": {
                        "type": "string",
                        "description": "The note content to save.",
                    },
                },
                "required": ["ticker", "note_text"]
            },
                
        },
    },
]

# Maps tool name (as the model will call it) -> actual Python function
TOOL_FUNCTIONS = {
    "get_price_summary": get_price_summary,
    "search_news": search_news,
    "save_research_notes": save_research_notes
}

SYSTEM_PROMPT = (
    "You are a stock research assistant. You have tools to look up price data, "
    "search news semantically, and save research notes. Use tools when they'd "
    "help answer the question — don't guess at prices or news you haven't "
    "looked up. Give clear, concise answers grounded in what the tools return."
)

def run_agent(user_query:str, max_turns:int=10) ->str:
    client = GroqClient()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role":"user", "content": user_query}
    ]
    
    for _ in range(max_turns):
        response = client.chat(messages, tools=TOOLS)
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function":{
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            }
        )
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn = TOOL_FUNCTIONS.get(fn_name)
            try:
                args = json.loads(tool_call.function.arguments)
                result = fn(**args) if fn else f"Unknown tool: {fn_name}"
            except Exception as e:
                result = f"error runing function {fn_name}:{e}"

            messages.append(
                {
                    "role":"assistant",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                }
            )
        print(messages)
    return "I wasn't able to finish that within the tool-call limit — try rephrasing or breaking it into a simpler question."

if __name__ =="__main__":
    print(run_agent("What's the latest news on AI trade rotation?"))