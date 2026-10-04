"""Add only verified business Pages. No input CSV or numeric Page ID is needed."""
PAGES = [
    {
        "page_url": "https://www.facebook.com/YOUR_BUSINESS_PAGE",
        "business_page": False,  # Replace the URL, then set True after verifying it.
        # "contact_selector": "#contact-card",  # Optional inspected contact-card selector.
    },
]

TIMEOUT = 15.0           # Browser operation/navigation timeout in seconds.
BROWSER_MAX_SCROLLS = 4  # Maximum scrolls while locating the contact card.
BROWSER_INTERVAL = 2.0   # Seconds between Page navigation/scroll steps.
