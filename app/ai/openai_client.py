import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


class OpenAIClient:
    def __init__(self) -> None:
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY não encontrada no arquivo .env."
            )

        self.model = os.getenv(
            "OPENAI_MODEL",
            "gpt-4.1-mini",
        )

        self.client = OpenAI(api_key=api_key)

    def generate_response(
        self,
        messages: list[dict[str, Any]],
        instructions: str,
    ) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=messages,
        )

        text = response.output_text.strip()

        if not text:
            raise RuntimeError(
                "A OpenAI retornou uma resposta vazia."
            )

        return text