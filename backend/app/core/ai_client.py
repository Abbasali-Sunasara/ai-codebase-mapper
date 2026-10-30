from openai import APITimeoutError, OpenAI, RateLimitError

from app.core.config import settings


class AIClient:
    """Use Groq to explain metadata extracted deterministically from code."""

    def __init__(self) -> None:
        self.model_id = settings.groq_model
        self.client = (
            OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=20.0,
                max_retries=0,
            )
            if settings.groq_api_key
            else None
        )

    def explain_code_component(self, file_path: str, code_snippet: str, metadata: dict) -> str:
        if self.client is None:
            return "AI summarization unavailable: GROQ_API_KEY is not configured."
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a software architect. Give exactly two concise sentences in plain English. "
                            "Explain only behavior supported by the provided AST metadata and source; do not invent features."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"File: {file_path}\n"
                            f"AST metadata: {metadata}\n\n"
                            f"Source snippet:\n{code_snippet}"
                        ),
                    },
                ],
                max_tokens=160,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            if not content:
                return "AI summarization unavailable: Groq returned an empty response."
            return content.strip()
        except RateLimitError:
            return "AI summarization unavailable: Groq rate limit reached; try again later."
        except APITimeoutError:
            return "AI summarization unavailable: Groq request timed out."
        except Exception as error:
            return f"AI summarization unavailable: Groq request failed ({error})."


ai_client = AIClient()
