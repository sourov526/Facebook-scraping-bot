"""Synthetic business Pages only. No accounts or contact details are real."""
from .models import Result
from .extraction import extract_text

ENTRIES = [
    {"page_url": f"https://www.facebook.com/SYNTHETIC_BUSINESS_{i}", "business_page": True}
    for i in range(1, 4)
]


def collect(entry):
    number = entry["page_url"].rsplit("_", 1)[1]
    result = Result(page_url=entry["page_url"], page_name="SYNTHETIC DEMO — নমুনা দোকান " + number)
    result.error_reason = "SYNTHETIC OFFLINE DATA; no network requests"
    if number == "1":
        result.observations = {
            (email, result.page_url + "/about")
            for email in extract_text("hello@business.example sales@business.example")
        }
        result.status = "ok"
    elif number == "3":
        result.status = "access_failed"
        result.error_reason += "; simulated unavailable business Page"
    return result
