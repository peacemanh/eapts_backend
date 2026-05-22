from tts import speak


def speak_and_type(page, selector, text, label):
    speak(f"Enter {label}")
    page.click(selector)
    page.wait_for_timeout(200)
    # Clear existing text first
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    for char in text:
        page.keyboard.type(char)
        page.wait_for_timeout(120)


def type_date_field(page, selector, value, narration=None):
    """Special function for date fields"""
    if narration:
        speak(narration)
    
    locator = page.locator(selector)
    locator.wait_for(state="visible", timeout=15000)
    
    # Highlight
    page.evaluate(
        """(selector) => {
            const el = document.querySelector(selector);
            if (el) el.style.outline = '4px solid purple';
        }""",
        selector,
    )
    page.wait_for_timeout(500)
    
    # Click to focus
    locator.click()
    page.wait_for_timeout(500)
    
    # Clear and type
    locator.press("Control+A")
    locator.press("Backspace")
    locator.fill(value)
    page.wait_for_timeout(300)


def highlight_and_click(page, selector, narration=None, wait_ms=1000):
    if narration:
        speak(narration)

    locator = page.locator(selector)
    locator.wait_for(state="visible", timeout=15000)
    locator.scroll_into_view_if_needed()

    page.evaluate(
        """(selector) => {
            const el = document.querySelector(selector);
            if (el) el.style.outline = '4px solid red';
        }""",
        selector,
    )

    page.wait_for_timeout(wait_ms)
    locator.click()
    page.wait_for_timeout(wait_ms)


def click_first(page, selector, narration=None):
    if narration:
        speak(narration)

    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=15000)
    locator.click()


def select_department(page, step):
    """Handle department dropdown selection"""
    row = step.get("rowIndex", 0)
    value = step.get("value", "")
    
    if "narration" in step:
        speak(step["narration"])
    
    # The department field has a different structure - it's a hidden input
    selector = f'[data-testid="field-{row}-department/ward"]'
    
    try:
        # First, find the visible dropdown element
        # The actual visible element is in the table cell
        table_row = page.locator(f'[data-testid="table-row-{row}"]')
        department_cell = table_row.locator('td').first
        
        # Click on the cell to open dropdown
        department_cell.click()
        page.wait_for_timeout(1000)
        
        # Now we need to find and click the dropdown options
        # The dropdown should appear after clicking
        # Look for MUI Select dropdown
        dropdown_selector = 'div[role="presentation"] [role="listbox"]'
        if page.locator(dropdown_selector).count() > 0:
            # Try to find the option by text
            option_selector = f'{dropdown_selector} [role="option"]:has-text("{value}")'
            page.locator(option_selector).first.click()
        else:
            # Alternative: Type the value directly
            # The department field might accept typing
            department_input = page.locator(selector)
            department_input.fill(value)
            page.wait_for_timeout(500)
            page.keyboard.press("Enter")
        
        page.wait_for_timeout(1000)
        
    except Exception as e:
        speak(f"Error selecting department: {str(e)}")
        # Fallback: try to fill the hidden input
        try:
            department_input = page.locator(selector)
            department_input.fill(value)
            page.wait_for_timeout(500)
        except:
            speak("Could not select department")


def handle_fill_row(page, step):
    """Handle filling a row with multiple fields (simpler version)"""
    row = step.get("rowIndex", 0)
    
    if "narration" in step:
        speak(step["narration"])
    
    # Wait for the row to be added
    page.wait_for_timeout(2000)
    
    # Field mapping from your debug output
    field_mapping = {
        "department": "department/ward",
        "expected_count": "number_of_expected_data_element",
        "completed_count": "number_of_data_element_completed",
        "report_received_date": "report_received_date",
        "report_due_day": "report_due_day",
        "signature": "name_and_signature",
        "remark": "remark"
    }
    
    for field, value in step["fields"].items():
        actual_field = field_mapping.get(field, field)
        selector = f'[data-testid="field-{row}-{actual_field}"]'
        
        try:
            locator = page.locator(selector)
            locator.wait_for(state="visible", timeout=10000)
            
            # Highlight
            page.evaluate(
                """(selector) => {
                    const el = document.querySelector(selector);
                    if (el) {
                        el.style.outline = '3px solid #4CAF50';
                        el.style.boxShadow = '0 0 10px rgba(76, 175, 80, 0.5)';
                    }
                }""",
                selector,
            )
            page.wait_for_timeout(500)
            
            # Special handling for department
            if field == "department":
                # Click to open dropdown
                locator.click()
                page.wait_for_timeout(1000)
                
                # Type the value
                page.keyboard.type(value)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                
            elif field == "report_received_date":
                # Date field needs special handling
                locator.click()
                page.wait_for_timeout(500)
                locator.press("Control+A")
                locator.press("Backspace")
                locator.fill(value)
                page.wait_for_timeout(500)
                
            else:
                # Normal text/numeric field
                locator.click()
                page.wait_for_timeout(300)
                locator.press("Control+A")
                locator.press("Backspace")
                locator.fill(str(value))
                page.wait_for_timeout(300)
            
        except Exception as e:
            speak(f"Warning: Could not fill field '{field}' with value '{value}': {str(e)}")


def handle_select_field(page, selector, value):
    """Handle dropdown/select fields"""
    locator = page.locator(selector)
    
    # Click to open dropdown
    locator.click()
    page.wait_for_timeout(1000)
    
    # Type the value and press enter (for MUI autocomplete)
    page.keyboard.type(value)
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")