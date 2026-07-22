import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

response = client.responses.create(
    model=os.getenv("OPENAI_MODEL"),
    input="Say hello to Airton in English."
)

print(response.output_text)