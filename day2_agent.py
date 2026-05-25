import anthropic
import json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
client = anthropic.Anthropic()

# ── Step 1: Define your test goal ──────────────────────────────────────
GOAL = "Go to https://www.saucedemo.com and log in with username 'standard_user' and password 'secret_sauce'. Verify the products page loads."

# ── Step 2: Ask the LLM to plan the steps ──────────────────────────────
print("🤖 Asking LLM to plan the test steps...\n")

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system="""You are a QA test planner. When given a test goal, return ONLY a JSON array of steps.
Each step must have:
- "action": one of [navigate, fill, click, verify]
- "selector": the CSS selector (null for navigate and verify)
- "value": the value to use (URL for navigate, text for fill, description for verify, null for click)

Example:
[
  {"action": "navigate", "selector": null, "value": "https://example.com"},
  {"action": "fill", "selector": "#username", "value": "admin"},
  {"action": "click", "selector": "#submit", "value": null},
  {"action": "verify", "selector": ".dashboard", "value": "Dashboard loaded"}
]

Return ONLY the JSON array. No explanation. No markdown.""",
    messages=[
        {"role": "user", "content": GOAL}
    ]
)

raw = response.content[0].text
print(f"LLM plan received:\n{raw}\n")
print(f"Raw length: {len(raw)} characters")
print(f"Tokens used: input={response.usage.input_tokens}, output={response.usage.output_tokens}\n")

# ── Step 3: Parse the plan ──────────────────────────────────────────────
# ── Step 3: Parse the plan ──────────────────────────────────────────────
# Clean up markdown formatting if LLM wrapped response in ```json ... ```
clean = raw.strip()
if clean.startswith("```"):
    clean = clean.split("```")[1]  # get content between backticks
    if clean.startswith("json"):
        clean = clean[4:]          # remove the word "json"
    clean = clean.strip()

print(f"Cleaned JSON:\n{clean}\n")
steps = json.loads(clean)

# ── Step 4: Execute each step with Playwright ───────────────────────────
print("🌐 Executing steps in browser...\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    for i, step in enumerate(steps, 1):
        action  = step["action"]
        selector = step.get("selector")
        value   = step.get("value")

        print(f"Step {i}: [{action}] selector={selector} value={value}")

        if action == "navigate":
            page.goto(value)
            print(f"  → Navigated to {value}")

        elif action == "fill":
            page.fill(selector, value)
            print(f"  → Filled {selector} with '{value}'")

        elif action == "click":
            page.click(selector)
            print(f"  → Clicked {selector}")

        elif action == "verify":
            page.wait_for_selector(selector, timeout=5000)
            print(f"  → ✓ Verified: {value}")

        else:
            print(f"  → ⚠ Unknown action: {action}")

    print("\n✅ All steps completed successfully")
    print(f"Final page title: {page.title()}")
    browser.close()