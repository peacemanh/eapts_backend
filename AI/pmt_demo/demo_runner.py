import os
import json
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from tts import speak
from actions import (
    speak_and_type,
    highlight_and_click,
    click_first,
    handle_fill_row,
    select_department,
    type_date_field
)

load_dotenv(override=True)

APP_URL = os.getenv("APP_URL")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", 500))


def run_training(training_name: str):
    with open("trainings.json") as f:
        trainings = json.load(f)

    training = trainings[training_name]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO
        )
        page = browser.new_page()

        speak(training.get("intro", ""))

        for step in training["steps"]:
            action = step["action"]

            if action == "goto":
                page.goto(APP_URL + step["url"])

            elif action == "type":
                # Check if value comes from env or directly
                if "env" in step:
                    value = os.getenv(step["env"])
                elif "value" in step:
                    value = step["value"]
                else:
                    speak(f"Error: No value source for type action")
                    continue
                    
                speak_and_type(
                    page,
                    step["selector"],
                    value,
                    step.get("label", "field")
                )

            elif action == "type_date":
                # Handle date fields
                value = step.get("value", "")
                type_date_field(
                    page,
                    step["selector"],
                    value,
                    step.get("narration")
                )

            elif action == "click":
                highlight_and_click(
                    page,
                    step["selector"],
                    step.get("narration")
                )

            elif action == "click_first":
                click_first(
                    page,
                    step["selector"],
                    step.get("narration")
                )

            elif action == "wait_network_idle":
                page.wait_for_load_state("networkidle")
                
            elif action == "fill_row":
                handle_fill_row(page, step)
                
            elif action == "select_department":
                select_department(page, step)
                
            elif action == "wait":
                timeout = step.get("timeout", 1000)
                if "narration" in step:
                    speak(step["narration"])
                time.sleep(timeout / 1000)
                
            else:
                speak(f"Unknown action: {action}")

        speak(training.get("outro", ""))
        page.wait_for_timeout(3000)
        browser.close()


if __name__ == "__main__":
    run_training("pmt_logbook_training")