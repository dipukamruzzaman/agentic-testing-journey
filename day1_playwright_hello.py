from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # headless=False so you SEE it
    page = browser.new_page()

    print("Navigating to Sauce Demo...")
    page.goto("https://www.saucedemo.com")

    print("Filling login form...")
    page.fill("#user-name", "standard_user")
    page.fill("#password", "secret_sauce")
    page.click("#login-button")

    print("Checking we landed on products page...")
    page.wait_for_selector(".inventory_list")
    print("✓ Products page loaded successfully")

    print(f"Page title: {page.title()}")
    browser.close()