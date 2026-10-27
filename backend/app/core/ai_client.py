from huggingface_hub import InferenceClient
from app.core.config import settings

class AIClient:
    """
    Wrapper for Hugging Face Inference API to generate plain-English explanations 
    for codebase AST components.
    """
    def __init__(self):
        self.model_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
        # Pass the token explicitly from settings
        self.client = InferenceClient(model=self.model_id, token=settings.HF_TOKEN)

    def explain_code_component(self, file_path: str, code_snippet: str, metadata: dict) -> str:
        """
        Requests a concise, verified plain-English explanation of a code component using Hugging Face.
        """
        prompt = f"""You are an expert software architect analyzing a codebase. 
Provide a concise, 2-sentence plain-English explanation of the following component.

File Path: {file_path}
Metadata: {metadata}

Code Snippet:
{code_snippet}

Rules:
- Be direct and precise.
- Do not hallucinate behavior or features not present in the code."""

        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"AI summarization unavailable: {str(e)}"

ai_client = AIClient()