"""Business Page browser collection and a separate synthetic offline demo."""
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
import config
from . import demo
from .browser import BrowserFacebook
from .models import Result, CollectionError
from .storage import Storage, key
from .export import export_csv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Collect published contact emails from configured Facebook business Pages")
    parser.add_argument("--headless", action="store_true", help="Hide the browser window")
    parser.add_argument("--demo", action="store_true", help="Synthetic offline data; separate database/CSV")
    parser.add_argument("--retry-failed", action="store_true", help="Retry saved failures")
    parser.add_argument("--refresh", action="store_true", help="Recollect all configured business Pages")
    args = parser.parse_args()
    entries = demo.ENTRIES if args.demo else config.PAGES
    keys = [key(entry) for entry in entries]
    prefix = "demo-" if args.demo else ""
    # Keep the existing browser database so earlier browser progress still resumes.
    database = "demo-business-progress.sqlite3" if args.demo else "browser-progress.sqlite3"
    storage = Storage(ROOT / "output" / database)
    output = ROOT / "output" / f"{prefix}contacts.csv"
    browser = None
    try:
        if not args.demo:
            load_dotenv(ROOT / ".env")
            browser = BrowserFacebook(os.getenv("FB_LOGIN_EMAIL"), os.getenv("FB_LOGIN_PASSWORD"),
                headless=args.headless, timeout=int(config.TIMEOUT * 1000),
                scrolls=config.BROWSER_MAX_SCROLLS, interval=config.BROWSER_INTERVAL)
        for index, (entry, job_key) in enumerate(zip(entries, keys), 1):
            if not args.refresh and storage.done(job_key, args.retry_failed):
                print(f"Page {index}: resumed (saved result)")
                continue
            try:
                result = demo.collect(entry) if args.demo else browser.collect(entry)
            except CollectionError as exc:
                result = Result(page_url=entry.get("page_url", ""), status=exc.status, error_reason=exc.reason)
            storage.save(job_key, result)
            print(f"Page {index}: {result.status} ({len(result.observations)} observations)")
    except KeyboardInterrupt:
        print("Interrupted; saved Pages will be resumed.")
    finally:
        try:
            export_csv(storage, keys, output)
        finally:
            storage.close()
            if browser:
                browser.close()
    print(f"{'SYNTHETIC OFFLINE DEMO: ' if args.demo else ''}CSV saved to {output}")


if __name__ == "__main__":
    main()
