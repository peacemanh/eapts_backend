# debug_selectors.py
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from tts import speak

load_dotenv(override=True)

APP_URL = os.getenv("APP_URL")

def debug_selectors():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate through the same steps
        page.goto(APP_URL + "/login")
        
        # Login
        page.locator('[data-testid="login-username"]').fill("solomon")
        page.locator('[data-testid="login-password"]').fill("Peaceone!1")
        page.locator('[data-testid="login-submit"]').click()
        page.wait_for_load_state("networkidle")
        
        # Select location
        page.locator('[data-testid="location-item-8"]').click()
        page.locator('[data-testid="complete-login-button"]').click()
        
        # Open PMT log books
        page.locator('[data-testid="pmt-log-books-module"]').click()
        
        # Open first logbook
        page.locator('div[data-testid^="logbook-"]').first.click()
        page.wait_for_load_state("networkidle")
        
        # Click add row
        page.locator('[data-testid="add-row-button"]').click()
        page.wait_for_timeout(2000)
        
        # DEBUG: Find all elements with data-testid
        print("\n=== DEBUG: All elements with data-testid ===")
        all_testids = page.evaluate("""
            () => {
                const elements = document.querySelectorAll('[data-testid]');
                const result = [];
                elements.forEach(el => {
                    result.push({
                        testid: el.getAttribute('data-testid'),
                        tag: el.tagName,
                        id: el.id,
                        className: el.className,
                        text: el.textContent?.substring(0, 100) || '',
                        html: el.outerHTML.substring(0, 200)
                    });
                });
                return result;
            }
        """)
        
        for item in all_testids:
            print(f"\ndata-testid: {item['testid']}")
            print(f"Tag: {item['tag']}")
            print(f"Text: {item['text']}")
            print(f"HTML snippet: {item['html']}")
        
        # Take a screenshot
        page.screenshot(path="debug_page.png")
        print("\nScreenshot saved as debug_page.png")
        
        browser.close()

if __name__ == "__main__":
    debug_selectors()