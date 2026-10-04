"""Bounded browser collection of explicitly configured business Pages.

No profile discovery, feed extraction, challenge solving, session persistence,
or password retries. UI selectors require live verification for your locale.
"""
import re
import time
from urllib.parse import urlsplit, urljoin, parse_qs
from .models import CollectionError, Result
from .extraction import extract_text

ABOUT = re.compile(r"^(About|সম্পর্কে|বিস্তারিত)$", re.I)
CONTACT = re.compile(r"^(Contact info|Contact information|Contact and basic info|যোগাযোগের তথ্য|যোগাযোগ এবং সাধারণ তথ্য)$", re.I)
PAGE_MARKERS = re.compile(r"Page transparency|পেজের স্বচ্ছতা|Page\s*[·•]", re.I)
CHALLENGE = re.compile(r"captcha|two.factor|authentication code|confirm your identity|security check|দুই.?ধাপ|নিরাপত্তা যাচাই", re.I)


def validate_entry(entry):
    try:
        p = urlsplit(entry['page_url'])
        if (p.scheme != 'https' or p.hostname not in {'www.facebook.com', 'facebook.com'}
                or p.username or p.password or p.port not in {None, 443}
                or not p.path.strip('/') or '\\' in entry['page_url']
                or any(ord(c) < 33 for c in entry['page_url'])):
            raise ValueError()
        if p.path.strip('/').split('/')[0] in {'groups', 'friends', 'people', 'search', 'watch', 'reel', 'reels', 'login'}:
            raise ValueError()
    except (KeyError, ValueError):
        raise CollectionError('invalid_input', 'expected_https_business_page_url') from None
    if entry.get('business_page') is not True:
        raise CollectionError('business_page_required', 'Confirm business_page=True only for a business Page in config.py')
    return entry['page_url']



def same_page(source, target):
    """Only follow About/Contact links belonging to the configured Page."""
    a, b = urlsplit(source), urlsplit(target)
    if b.scheme != 'https' or b.hostname not in {'www.facebook.com', 'facebook.com'}:
        return False
    def identity(p):
        path = p.path.strip('/').split('/')[0]
        return parse_qs(p.query).get('id', [''])[0] if path == 'profile.php' else path
    return bool(identity(a)) and identity(a) == identity(b)


def check_access(url, text):
    p = urlsplit(url)
    if p.hostname not in {'facebook.com', 'www.facebook.com'} or p.scheme != 'https':
        raise CollectionError('access_failed', 'unexpected_browser_destination')
    if any(part in p.path.lower() for part in ('checkpoint', 'challenge', 'two_step', 'captcha')) or CHALLENGE.search(text):
        raise CollectionError('login_challenge', 'CAPTCHA_2FA_or_security_check_requires_manual_resolution')
    if p.path.startswith('/login'):
        raise CollectionError('login_failed', 'login_not_completed_or_session_expired')
    if re.search(r"content (?:isn't|is not) available|temporarily blocked|you.re temporarily blocked", text, re.I):
        raise CollectionError('access_failed', 'page_unavailable_or_account_restricted')


# DOM text only from a bounded Contact section; never scrape a feed or comments.
# innerText/visibility excludes hidden DOM text. mailto query strings are ignored.
CONTACT_DATA = r"""element => {
    const visible = e => !!(e.getClientRects().length) &&
        getComputedStyle(e).visibility !== 'hidden';
    const blocked = e => e.closest('article,[role="article"],[role="feed"]');
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const chunks = [];
    while (walker.nextNode()) {
        const p = walker.currentNode.parentElement;
        if (p && visible(p) && !blocked(p) && !p.closest('script,style,template,noscript'))
            chunks.push(walker.currentNode.textContent);
    }
    const mailto = [...element.querySelectorAll('a[href^="mailto:"]')]
        .filter(e => visible(e) && !blocked(e)).map(e => e.getAttribute('href'));
    return {text: chunks.join(' '), mailto};
}"""


class BrowserFacebook:
    def __init__(self, username, password, headless=False, timeout=15000, scrolls=4, interval=2):
        self.username, self.password = username, password
        self.headless, self.timeout = headless, timeout
        self.scrolls, self.interval = scrolls, interval
        self.runtime = self.browser = self.context = self.page = None
        self.fatal = None
        self.error_type = ()

    def close(self):
        # No cookies, credentials, screenshots, videos or traces written to disk.
        try:
            if self.browser:
                self.browser.close()
        finally:
            if self.runtime:
                self.runtime.stop()
        self.password = None

    def _start(self):
        if not self.username or not self.password:
            raise CollectionError('configuration_required', 'Set FB_LOGIN_EMAIL and FB_LOGIN_PASSWORD locally in .env')
        try:
            from playwright.sync_api import sync_playwright, Error
        except ImportError:
            raise CollectionError('configuration_required', 'Install project dependencies and Playwright Chromium; see README') from None
        self.error_type = Error
        try:
            self.runtime = sync_playwright().start()
            self.browser = self.runtime.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context(locale='en-US', accept_downloads=False)
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            self.page.set_default_navigation_timeout(self.timeout)
            self.page.goto('https://www.facebook.com/login/', wait_until='domcontentloaded')
            # Validate the credential destination before filling or submitting.
            p = urlsplit(self.page.url)
            if p.scheme != 'https' or p.hostname != 'www.facebook.com':
                raise CollectionError('login_failed', 'unexpected_login_destination')
            if CHALLENGE.search(self.page.locator('body').inner_text()):
                raise CollectionError('login_challenge', 'login_security_check')
            self.page.locator('input[name="email"]').fill(self.username)
            self.page.locator('input[name="pass"]').fill(self.password)
            self.page.locator('button[name="login"]').click()
            # Wait a bounded period for the authenticated cookie, never infer
            # successful login solely from disappearance of the password form.
            for _ in range(20):
                check_access_after_login = self.page.locator('body').inner_text()
                if CHALLENGE.search(check_access_after_login) or any(
                    s in urlsplit(self.page.url).path for s in ('checkpoint', 'two_step', 'challenge')):
                    raise CollectionError('login_challenge', 'CAPTCHA_2FA_or_security_check_requires_manual_resolution')
                if any(c['name'] == 'c_user' for c in self.context.cookies('https://www.facebook.com')):
                    check_access(self.page.url, check_access_after_login)
                    self.password = None
                    return
                self.page.wait_for_timeout(500)
            raise CollectionError('login_failed', 'credentials_rejected_or_login_UI_requires_attention')
        except self.error_type:
            # Playwright exceptions can include fill() arguments. Never propagate them.
            raise CollectionError('browser_failed', 'browser_installation_login_UI_or_timeout; see README') from None

    def _access(self):
        text = self.page.locator('body').inner_text()
        check_access(self.page.url, text)
        if self.page.locator('input[name="pass"]:visible').count():
            raise CollectionError('login_failed', 'session_expired_or_login_required')
        return text

    def _click_section(self, pattern):
        links = self.page.get_by_role('link', name=pattern)
        for i in range(min(links.count(), 10)):
            link = links.nth(i)
            if not link.is_visible():
                continue
            target = urljoin(self.page.url, link.get_attribute('href') or '')
            if not same_page(self.page_identity, target):
                continue
            link.click()
            self.page.wait_for_timeout(1000)
            self._access()
            if not same_page(self.page_identity, self.page.url):
                raise CollectionError("access_failed", "contact_link_redirected_to_another_page")
            return True
        return False

    def _contact_section(self, entry):
        # Explicit selectors allow an inspected layout to be supported without
        # ever falling back to collecting the entire Page or feed.
        if entry.get('contact_selector'):
            section = self.page.locator(entry['contact_selector'])
            if section.count() == 1 and section.is_visible():
                return section
            raise CollectionError('layout_unrecognized', 'configured_contact_selector_not_unique_or_visible')
        labels = self.page.get_by_text(CONTACT, exact=True)
        for i in range(min(labels.count(), 10)):
            label = labels.nth(i)
            if not label.is_visible():
                continue
            # A contact card normally encloses its heading and several lines.
            # Reject large/ambiguous containers and any feed-bearing ancestor.
            for level in range(1, 5):
                section = label.locator('/'.join(['..'] * level))
                text = section.inner_text()
                if (len(text.splitlines()) >= 2 and len(text) <= 6000
                        and not section.locator('article,[role="article"],[role="feed"]').count()
                        and section.get_by_text(CONTACT, exact=True).count() == 1):
                    return section
        raise CollectionError('layout_unrecognized', 'visible_contact_section_not_identified; configure contact_selector after inspection')

    def collect(self, entry):
        url = validate_entry(entry)
        if self.fatal:
            raise CollectionError(*self.fatal)
        try:
            if self.page is None:
                self._start()
            self.page.goto(url, wait_until='domcontentloaded')
            time.sleep(self.interval)
            text = self._access()
            self.page_identity = self.page.url
            if not PAGE_MARKERS.search(text):
                raise CollectionError('business_page_unverified', 'No Page marker found; personal profiles are not collected')
            main = self.page.get_by_role('main')
            names = main.get_by_role('heading', level=1)
            if not names.count():
                raise CollectionError('layout_unrecognized', 'page_name_heading_missing')
            result = Result(page_url=url, page_name=names.first.inner_text())
            if not self._click_section(ABOUT):
                raise CollectionError('layout_unrecognized', 'About_link_missing')
            self._click_section(CONTACT)
            section = None
            for attempt in range(self.scrolls + 1):
                self._access()
                try:
                    section = self._contact_section(entry)
                    break
                except CollectionError:
                    if attempt == self.scrolls:
                        raise
                    self.page.mouse.wheel(0, 650)
                    time.sleep(self.interval)
            data = section.evaluate(CONTACT_DATA)
            emails = extract_text(data['text'])
            from urllib.parse import unquote
            for href in data['mailto']:
                emails |= extract_text(unquote(href[7:].split('?', 1)[0]))
            source = self.page.url
            result.observations = {(email, source) for email in emails}
            result.status = 'ok' if emails else 'no_email'
            return result
        except CollectionError as exc:
            if exc.status in {'login_failed', 'login_challenge', 'configuration_required', 'browser_failed'}:
                self.fatal = exc.status, exc.reason
            raise
        except self.error_type:
            raise CollectionError('browser_failed', 'navigation_or_UI_timeout') from None
