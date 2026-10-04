# Facebook business Page contact collector

Automated login → configured business Pages → About/Contact section → SQLite → CSV.

The bot visits only business Pages listed in `config.py`, checks for a Page marker, opens About/Contact links, and scrolls a bounded number of times to locate the contact card. It collects published email text and `mailto:` addresses from that card. It does not discover accounts from a feed or collect personal profiles, posts or comments.

## Setup

Requires Python 3.11+.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m playwright install chromium
```

If you do not already have `.env`, copy `.env.example` to `.env`. Add your credentials locally:

```dotenv
FB_LOGIN_EMAIL=your_email_or_phone
FB_LOGIN_PASSWORD='your_password'
```

Never send credentials in chat or commit `.env`. Quote/escape special characters using python-dotenv syntax. Login is attempted once per run. Browser sessions are temporary; the application does not save cookies, screenshots, traces or passwords. Do not enable browser debug logging with real credentials.

Edit `config.py`:

```python
PAGES = [
    {
        "page_url": "https://www.facebook.com/your-business",
        "business_page": True,
    },
]
```

Set `business_page=True` only after verifying the link belongs to a business Page. The placeholder is intentionally unconfirmed. A visible Page marker is also required, but it does not independently prove a business category.

## Run

```sh
.venv/bin/python -m collector
```

Options:

- `--headless`: hide the browser window.
- `--retry-failed`: retry saved failures after correcting credentials, Page configuration or layout issues.
- `--refresh`: replace saved snapshots for all configured Pages.
- `--demo`: run the synthetic offline example without loading credentials or opening a browser.

Normal output is `output/contacts.csv`. Progress is saved in `output/browser-progress.sqlite3`. Browser collection is the only live workflow; no token or numeric Page ID is needed.

## Results and resume

CSV columns:

```text
page_name,page_url,website_url,email,source_url,status,error_reason,collected_at
```

There is one row per email/source observation. Pages without an observation receive one row with an empty email and source. Empty cells represent missing values, not the literal text `null`. `website_url` remains empty and is retained for compatibility with the original CSV schema. Source URLs identify the Facebook contact page; timestamps are UTC.

CSV uses UTF-8 with BOM for Bangla/Excel, correct quoting and formula-injection protection. SQLite commits each Page atomically, removes duplicate email/source observations, and preserves multiple emails. Completed Pages are skipped on reruns. An interrupted, uncommitted Page is collected again. Refresh/retry replaces the Page snapshot; the database is not a history log. Configuration changes create a new job. Only the current list is exported, and CSV replacement is atomic.

| Status | Meaning |
| --- | --- |
| `ok` | Contact card identified and emails found |
| `no_email` | Contact card identified but no email found |
| `configuration_required` | Missing credentials or dependencies |
| `invalid_input` | Unsupported Page URL |
| `business_page_required` | Business Page confirmation missing |
| `business_page_unverified` | Visible Page marker missing |
| `login_failed` | Login did not complete or session expired |
| `login_challenge` | CAPTCHA, 2FA or security checkpoint; login is not retried |
| `access_failed` | Page unavailable, restricted or redirected unexpectedly |
| `layout_unrecognized` | About/Contact section could not be identified |
| `browser_failed` | Browser installation, navigation or UI operation failed |

An access/layout failure is never labeled `no_email`. CAPTCHA, 2FA and checkpoints are not bypassed. Resolve account issues directly with Facebook before a later run; accounts challenged on every new session may remain unsupported.

## Layout and limits

Defaults: 15-second operation timeouts, four contact-card scrolls, and two-second pauses after Page navigation and between scrolls. Adjust these in `config.py`. About/Contact links must belong to the same Page. The bot never falls back to extracting emails from the entire Page.

English/Bangla labels are supported heuristically. For an unfamiliar layout, inspect the Page and optionally add `"contact_selector": "YOUR_CSS_SELECTOR"` to that entry. It must uniquely identify only the business contact card. Never use a whole-page, feed, comment or profile selector.

**Live Facebook login and collection have not been verified.** Facebook UI changes, login dialogs and account challenges may require adjustments. Synthetic browser tests do not prove compatibility with Facebook's current UI.

## Offline demo and tests

```sh
.venv/bin/python -m collector --demo
.venv/bin/python -m pytest -q
```

The demo writes `output/demo-contacts.csv` and a separate `output/demo-business-progress.sqlite3`. Every row is labeled synthetic. It includes Bangla, multiple reserved `.example` emails, an empty result and an access failure. It makes no network requests.

Tests cover automated login using synthetic HTML, challenge handling, business Page guards, contact-card extraction, scrolling, secret-safe errors, resume, transaction rollback, duplicate removal and CSV safety. Browser tests intercept all page requests. They require installed Chromium; missing browser dependencies are reported as skipped tests.

## Files

- `config.py`: business Pages and browser limits.
- `collector/browser.py`: login and business contact-card collection.
- `collector/extraction.py`: literal email extraction.
- `collector/storage.py`: SQLite checkpoints.
- `collector/export.py`: safe CSV export.
- `collector/models.py`: result and error types.
- `collector/demo.py`: synthetic business Page example.
- `collector/__main__.py`: command-line workflow.

Dependencies: Playwright and python-dotenv. SQLite and CSV use Python's standard library. Existing output files from older versions are retained; only `browser-progress.sqlite3` is used for live resume.
