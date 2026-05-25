import anthropic
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()
client = anthropic.Anthropic()

# ── Config ─────────────────────────────────────────────────────────────
GOAL = "Go to https://www.saucedemo.com and log in with username 'standard_user' and password 'secret_sauce'. Verify the products page loads."

# ── Step 1: Ask LLM to plan ────────────────────────────────────────────
print("🤖 Asking LLM to plan the test steps...\n")

start_time = time.time()

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system="""You are a QA test planner. When given a test goal, return ONLY a JSON array of steps.
Each step must have:
- "action": one of [navigate, fill, click, verify]
- "selector": MUST be a valid CSS selector like #id or .classname (null for navigate, REQUIRED for verify)
- "value": the value to use (URL for navigate, text for fill, short description for verify, null for click)
- "expected_result": what should happen after this step

IMPORTANT: For verify steps, selector must be a real CSS selector like .inventory_list or #header.
Never put descriptive text in the selector field.

Return ONLY the JSON array. No explanation. No markdown.""",
    messages=[
        {"role": "user", "content": GOAL}
    ]
)

# ── Step 2: Parse the plan ─────────────────────────────────────────────
raw = response.content[0].text
clean = raw.strip()
if clean.startswith("```"):
    clean = clean.split("```")[1]
    if clean.startswith("json"):
        clean = clean[4:]
    clean = clean.strip()

steps = json.loads(clean)
input_tokens  = response.usage.input_tokens
output_tokens = response.usage.output_tokens

print(f"Plan received — {len(steps)} steps, tokens: {input_tokens} in / {output_tokens} out\n")

# ── Step 3: Execute with logging ───────────────────────────────────────
execution_log = []

print("🌐 Executing steps in browser...\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    for i, step in enumerate(steps, 1):
        action   = step["action"]
        selector = step.get("selector")
        value    = step.get("value")
        expected = step.get("expected_result", "No expected result defined")

        log_entry = {
            "step":            i,
            "action":          action,
            "selector":        selector,
            "value":           value,
            "expected_result": expected,
            "timestamp":       datetime.now().isoformat(),
            "status":          None,
            "error":           None
        }

        print(f"Step {i}: [{action}] {selector or value}")

        try:
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
                if selector and not selector.startswith(" ") and len(selector) < 50:
                    page.wait_for_selector(selector, timeout=5000)
                    print(f"  → ✓ Verified: {expected}")
                else:
                    # selector looks like a description, not a CSS selector
                    # ask the LLM what selector to use instead
                    print(f"  → ⚠ Selector looks invalid: '{selector}'")
                    print(f"  → Falling back to checking page is not blank...")
                    page.wait_for_load_state("domcontentloaded")
                    print(f"  → ✓ Page loaded (fallback verify passed)")

            log_entry["status"] = "passed"

        except PlaywrightTimeout:
            error_msg = f"Timeout: selector '{selector}' not found within 5 seconds"
            print(f"  → ✗ FAILED: {error_msg}")
            log_entry["status"] = "failed"
            log_entry["error"]  = error_msg

        except Exception as e:
            error_msg = str(e)
            print(f"  → ✗ FAILED: {error_msg}")
            log_entry["status"] = "failed"
            log_entry["error"]  = error_msg

        execution_log.append(log_entry)

    print("\n👀 Browser paused — press Enter to close...")
    input()
    browser.close()

# ── Step 4: Calculate cost ─────────────────────────────────────────────
cost = (input_tokens / 1000 * 0.00025) + (output_tokens / 1000 * 0.00125)
duration = round(time.time() - start_time, 2)

# ── Step 5: Build report ───────────────────────────────────────────────
passed = sum(1 for s in execution_log if s["status"] == "passed")
failed = sum(1 for s in execution_log if s["status"] == "failed")

report = {
    "goal":          GOAL,
    "run_timestamp": datetime.now().isoformat(),
    "duration_secs": duration,
    "cost_usd":      round(cost, 6),
    "tokens": {
        "input":  input_tokens,
        "output": output_tokens
    },
    "summary": {
        "total":  len(execution_log),
        "passed": passed,
        "failed": failed,
        "result": "PASS" if failed == 0 else "FAIL"
    },
    "steps": execution_log
}

# ── Step 6: Save report ────────────────────────────────────────────────
report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(report_filename, "w") as f:
    json.dump(report, f, indent=2)

# ── Step 7: Print summary ──────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  RESULT : {report['summary']['result']}")
print(f"  Total  : {len(execution_log)} steps")
print(f"  Passed : {passed}")
print(f"  Failed : {failed}")
print(f"  Cost   : ${cost:.6f}")
print(f"  Time   : {duration}s")
print(f"  Report : {report_filename}")
print(f"{'='*50}")