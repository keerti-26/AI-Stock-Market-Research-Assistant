import os
import base64
from databricks.sdk import WorkspaceClient
from openai import OpenAI

_w = WorkspaceClient()

_SCOPE = os.environ.get("GROQ_SECRET_SCOPE", "groq")
_KEY = os.environ.get("GROQ_SECRET_KEY", "groq-api-key")
_BASE_URL = "https://api.groq.com/openai/v1"

DEFAULT_MODEL = "llama-3.1-70b-versatile"


def _get_api_key() -> str:
    """Fetch the Groq API key from the Databricks secret scope."""
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")

class GroqClient:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = OpenAI(
            api_key=_get_api_key(),
            base_url=_BASE_URL,
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ):
        """
        Send a conversation to Llama and get the raw completion back.
 
        messages: OpenAI-style list of {"role": ..., "content": ...} dicts
                  (plus "tool" role messages once the agent loop is running).
        tools: OpenAI-style tool schemas, e.g.
               [{"type": "function", "function": {"name": ..., "description": ...,
                 "parameters": {...JSON schema...}}}]
               Pass None for a plain, tool-free completion.
 
        Returns the full ChatCompletion object — callers check
        response.choices[0].message for either .content (final answer) or
        .tool_calls (the model wants to call a tool).
        """
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
            kwargs["parallel_tool_calls"] = False  # Prevent malformed function calls
 
        return self._client.chat.completions.create(**kwargs)

if __name__ == "__main__":
    client = GroqClient()
    resp = client.chat(messages=[{"role":"user", "content":"Are you not Llama"}])
    print(resp.choices[0].message.content)
    
