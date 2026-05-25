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

MAX_RETRIES = 2  # how many times to retry a failed step

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
    messages=[{"role": "user", "content": GOAL}]
)

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
print(f"Plan received — {len(steps)} steps\n")

# ── Step 2: Self-healing function ──────────────────────────────────────
def ask_llm_for_alternative(broken_selector, page_html, error):
    """When a selector fails, ask the LLM to suggest a better one."""
    print(f"  🔧 Asking LLM to heal broken selector: '{broken_selector}'")

    heal_response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="You are a CSS selector expert. Given a broken selector and page HTML, return ONLY a better CSS selector as plain text. Nothing else.",
        messages=[{
            "role": "user",
            "content": f"Broken selector: {broken_selector}\nError: {error}\nPage HTML snippet:\n{page_html[:2000]}\n\nReturn ONLY the fixed CSS selector."
        }]
    )

    new_selector = heal_response.content[0].text.strip()
    print(f"  🔧 LLM suggested: '{new_selector}'")
    return new_selector

# ── Step 3: Execute with retry + self-healing ──────────────────────────
execution_log = []
total_input_tokens  = input_tokens
total_output_tokens = output_tokens

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
            "error":           None,
            "retries":         0,
            "healed":          False
        }

        print(f"Step {i}: [{action}] {selector or value}")

        attempt = 0
        current_selector = selector

        while attempt <= MAX_RETRIES:
            try:
                if action == "navigate":
                    page.goto(value)
                    print(f"  → Navigated to {value}")

                elif action == "fill":
                    page.fill(current_selector, value)
                    print(f"  → Filled {current_selector} with '{value}'")

                elif action == "click":
                    page.click(current_selector)
                    print(f"  → Clicked {current_selector}")

                elif action == "verify":
                    if current_selector and len(current_selector) < 50:
                        page.wait_for_selector(current_selector, timeout=5000)
                        print(f"  → ✓ Verified: {expected}")
                    else:
                        page.wait_for_load_state("domcontentloaded")
                        print(f"  → ✓ Page loaded (fallback verify)")

                log_entry["status"]   = "passed"
                log_entry["retries"]  = attempt
                log_entry["selector"] = current_selector
                break  # success — exit retry loop

            except (PlaywrightTimeout, Exception) as e:
                error_msg = str(e)
                attempt += 1
                log_entry["retries"] = attempt

                if attempt <= MAX_RETRIES and current_selector:
                    print(f"  → ✗ Attempt {attempt} failed: {error_msg[:80]}")

                    # self-healing — ask LLM for a better selector
                    page_html = page.content()
                    new_selector = ask_llm_for_alternative(
                        current_selector, page_html, error_msg
                    )
                    current_selector = new_selector
                    log_entry["healed"] = True

                    total_input_tokens  += 200
                    total_output_tokens += 20
                    time.sleep(1)  # brief pause before retry
                else:
                    print(f"  → ✗ FAILED after {attempt} attempts: {error_msg[:80]}")
                    log_entry["status"] = "failed"
                    log_entry["error"]  = error_msg
                    break

        execution_log.append(log_entry)

    print("\n👀 Browser paused — press Enter to close...")
    input()
    browser.close()

# ── Step 4: Cost + report ──────────────────────────────────────────────
cost     = (total_input_tokens / 1000 * 0.00025) + (total_output_tokens / 1000 * 0.00125)
duration = round(time.time() - start_time, 2)
passed   = sum(1 for s in execution_log if s["status"] == "passed")
failed   = sum(1 for s in execution_log if s["status"] == "failed")
healed   = sum(1 for s in execution_log if s["healed"])

report = {
    "goal":          GOAL,
    "run_timestamp": datetime.now().isoformat(),
    "duration_secs": duration,
    "cost_usd":      round(cost, 6),
    "tokens": {
        "input":  total_input_tokens,
        "output": total_output_tokens
    },
    "summary": {
        "total":  len(execution_log),
        "passed": passed,
        "failed": failed,
        "healed": healed,
        "result": "PASS" if failed == 0 else "FAIL"
    },
    "steps": execution_log
}

report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(report_filename, "w") as f:
    json.dump(report, f, indent=2)

print(f"\n{'='*50}")
print(f"  RESULT  : {report['summary']['result']}")
print(f"  Total   : {len(execution_log)} steps")
print(f"  Passed  : {passed}")
print(f"  Failed  : {failed}")
print(f"  Healed  : {healed} steps self-healed")
print(f"  Cost    : ${cost:.6f}")
print(f"  Time    : {duration}s")
print(f"  Report  : {report_filename}")
print(f"{'='*50}")