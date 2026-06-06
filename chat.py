# To run this code you need to install the following dependencies:
# pip install google-genai

import os
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()


def generate():
    print(os.getenv("GEMINI_API_KEY"))
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    model="gemini-3.5-flash"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="Inception movie director name and it's release year"),
            ],
        ),
    ]
    # tools = [
    #     types.Tool(googleSearch=types.GoogleSearch(
    #     )),
    # ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="MINIMAL",
        ),
        # tools=tools,
        system_instruction=[
            types.Part.from_text(text="""You are CineMind, an AI Movie Expert."""),
        ],
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        if text := chunk.text:
            print(text, end="")

if __name__ == "__main__":
    generate()



# client = genai.Client()

# response = client.models.generate_content(
#     model="gemini-3.5-flash",
#     contents="Inception movie director name"
# )

# print(response.text)
