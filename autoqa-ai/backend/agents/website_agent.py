import os
import json
from groq import Groq
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def analyze_website(url: str) -> dict:
    page_data = _scrape_page(url)
    test_cases = _generate_test_cases(url, page_data)
    return {
        "url": url,
        "analysis": page_data,
        "test_cases": test_cases
    }

def _scrape_page(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = page.title()
            forms = page.query_selector_all("form")
            buttons = page.query_selector_all("button, input[type='submit'], input[type='button']")
            inputs = page.query_selector_all("input, textarea, select")
            links = page.query_selector_all("a[href]")

            form_data = []
            for form in forms:
                form_inputs = form.query_selector_all("input, textarea, select")
                form_data.append({
                    "input_count": len(form_inputs),
                    "inputs": [{"type": i.get_attribute("type") or "text", "name": i.get_attribute("name") or ""} for i in form_inputs]
                })

            result = {
                "title": title,
                "url": url,
                "forms_count": len(forms),
                "buttons_count": len(buttons),
                "inputs_count": len(inputs),
                "links_count": len(links),
                "forms": form_data,
                "buttons": [b.inner_text()[:50] for b in buttons[:10]],
            }
        except Exception as e:
            result = {"title": "Error", "url": url, "error": str(e)}
        finally:
            browser.close()
    return result

PROMPT_TEMPLATE = """
You are a QA automation expert. Based on this website analysis, generate comprehensive test cases.

Website: {url}
Page Title: {title}
Forms: {forms_count} forms detected
Buttons: {buttons_count} buttons detected
Inputs: {inputs_count} input fields detected
Form Details: {forms}
Button Labels: {buttons}

Generate test cases covering:
- Functional tests
- UI/UX tests
- Edge cases
- Negative tests

Return ONLY valid JSON with:
- functional_tests: list of test case objects (id, title, steps, expected_result)
- ui_tests: list of test case objects
- edge_cases: list of test case objects
- summary: brief analysis of the website
"""

def _generate_test_cases(url: str, page_data: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        url=url,
        title=page_data.get("title", ""),
        forms_count=page_data.get("forms_count", 0),
        buttons_count=page_data.get("buttons_count", 0),
        inputs_count=page_data.get("inputs_count", 0),
        forms=json.dumps(page_data.get("forms", [])),
        buttons=json.dumps(page_data.get("buttons", []))
    )
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
