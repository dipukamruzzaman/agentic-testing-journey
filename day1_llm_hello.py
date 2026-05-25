import anthropic
from dotenv import load_dotenv

load_dotenv()


response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system="You are a QA test planner. When given a test goal, break it into clear step-by-step actions a browser automation tool can execute.",
    messages=[
        {
            "role": "user",
            "content": "Goal: Go to https://www.saucedemo.com and log in with username 'standard_user' and password 'secret_sauce'. Verify the products page loads."
        }
    ]
)

print(response.content[0].text)
print(f"\n--- Token usage: input={response.usage.input_tokens}, output={response.usage.output_tokens} ---")