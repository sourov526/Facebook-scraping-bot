"""Synthetic fixtures only. No real Facebook account or connection is used."""
import pytest
from collector.browser import BrowserFacebook, validate_entry, check_access, same_page
from collector.models import CollectionError

ENTRY = {'page_url': 'https://www.facebook.com/synthetic-business', 'business_page': True}


@pytest.mark.parametrize('entry', [
    {'page_url': ENTRY['page_url']},
    {'page_url': 'https://www.facebook.com/groups/123', 'business_page': True},
    {'page_url': 'https://evil.example/business', 'business_page': True},
    {'page_url': 'http://facebook.com/business', 'business_page': True},
    {'page_url': 'https://facebook.com/people/someone', 'business_page': True},
])
def test_browser_rejects_unconfirmed_or_unsupported(entry):
    with pytest.raises(CollectionError):
        validate_entry(entry)


def test_page_links_stay_on_same_page():
    assert same_page(ENTRY['page_url'], ENTRY['page_url'] + '/about')
    assert not same_page(ENTRY['page_url'], 'https://www.facebook.com/other/about')
    assert not same_page(ENTRY['page_url'], 'https://evil.example/synthetic-business/about')
    assert same_page('https://facebook.com/profile.php?id=123', 'https://facebook.com/profile.php?id=123&sk=about')
    assert not same_page('https://facebook.com/profile.php?id=123', 'https://facebook.com/profile.php?id=456')


@pytest.mark.parametrize('url,text,status', [
    ('https://www.facebook.com/checkpoint/', '', 'login_challenge'),
    ('https://www.facebook.com/', 'Enter authentication code', 'login_challenge'),
    ('https://www.facebook.com/login/', '', 'login_failed'),
    ('https://evil.example/', '', 'access_failed'),
])
def test_access_failures_are_not_no_email(url, text, status):
    with pytest.raises(CollectionError) as exc:
        check_access(url, text)
    assert exc.value.status == status


def test_missing_credentials_and_fatal_login_not_retried(monkeypatch):
    bot = BrowserFacebook(None, None)
    for _ in range(2):
        with pytest.raises(CollectionError) as exc:
            bot.collect(ENTRY)
        assert exc.value.status == 'configuration_required'
    assert bot.fatal
    bot.close()


@pytest.fixture
def synthetic_browser():
    api = pytest.importorskip('playwright.sync_api')
    runtime = api.sync_playwright().start()
    try:
        browser = runtime.chromium.launch(headless=True)
    except api.Error as exc:
        runtime.stop()
        if "Executable doesn't exist" in str(exc):
            pytest.skip('Install Playwright Chromium to run synthetic browser tests')
        raise
    bot = BrowserFacebook('synthetic@example.test', 'SYNTHETIC-SECRET', headless=True, interval=0, timeout=1500)
    # Use actual browser DOM/clicks; intercept EVERY network request offline.
    context = browser.new_context()
    calls = []
    state = {'email': True, 'marker': True, 'challenge': False, 'unknown': False, 'hidden': False}
    def route(request):
        url = request.request.url
        calls.append(url)
        if '/login/' in url:
            html = '''<form action="/welcome"><input name="email"><input name="pass" type="password">
              <button name="login">Log in</button></form>'''
        elif '/welcome' in url:
            if state['challenge']:
                html = '<p>Enter authentication code</p>'
            else:
                context.add_cookies([{'name': 'c_user', 'value': 'SYNTHETIC', 'url': 'https://www.facebook.com'}])
                html = '<p>Welcome</p>'
        elif '/about' in url:
            address = '<p>hello@business.example</p><a href="mailto:sales%40business.example?subject=ignore@other.example">Email</a>' if state['email'] else '<p>Phone: 000-000</p>'
            if state['unknown']:
                html = '<main>Unknown UI</main>'
            else:
                hidden = 'style="display:none"' if state['hidden'] else ''
                html = f'''<main><section id="contact" {hidden}><h2>Contact info</h2>{address}
                    <p style="display:none">hidden@other.example</p></section>
                    <article>commenter@other.example</article></main>'''
                if state['hidden']:
                    html += '''<div style="height:3000px">Scroll fixture</div><script>
                    window.addEventListener('wheel', () => document.querySelector('#contact').style.display='block');</script>'''
        else:
            marker = '<p>Page transparency</p>' if state['marker'] else ''
            html = f'<main><h1>SYNTHETIC Business</h1>{marker}<a href="/synthetic-business/about">About</a></main>'
        request.fulfill(status=200, content_type='text/html', body=html)
    context.route('**/*', route)
    bot.runtime, bot.browser, bot.context = runtime, browser, context
    bot.page = context.new_page()
    bot.page.set_default_timeout(1500)
    bot.error_type = api.Error
    yield bot, state, calls
    bot.close()


def test_browser_collects_contact_only(synthetic_browser):
    bot, state, calls = synthetic_browser
    result = bot.collect(ENTRY)
    assert result.page_name == 'SYNTHETIC Business'
    assert result.status == 'ok'
    assert result.observations == {
        ('hello@business.example', ENTRY['page_url'] + '/about'),
        ('sales@business.example', ENTRY['page_url'] + '/about'),
    }
    assert all('www.facebook.com' in url for url in calls)


def test_browser_recognized_empty_contact(synthetic_browser):
    bot, state, _ = synthetic_browser
    state['email'] = False
    assert bot.collect(ENTRY).status == 'no_email'


def test_browser_personal_profile_not_collected(synthetic_browser):
    bot, state, calls = synthetic_browser
    state['marker'] = False
    with pytest.raises(CollectionError) as exc:
        bot.collect(ENTRY)
    assert exc.value.status == 'business_page_unverified'
    assert not any('/about' in url for url in calls)


def test_browser_unknown_layout_is_failure(synthetic_browser):
    bot, state, _ = synthetic_browser
    state['unknown'] = True
    bot.scrolls = 0
    with pytest.raises(CollectionError) as exc:
        bot.collect(ENTRY)
    assert exc.value.status == 'layout_unrecognized'


def test_browser_scrolls_to_contact(synthetic_browser):
    bot, state, _ = synthetic_browser
    state['hidden'] = True
    bot.interval = 0.1
    assert bot.collect(ENTRY).status == 'ok'


def start_with_fixture_browser(bot, monkeypatch):
    from types import SimpleNamespace
    import playwright.sync_api as api
    runtime, browser, context = bot.runtime, bot.browser, bot.context
    monkeypatch.setattr(api, 'sync_playwright', lambda: SimpleNamespace(start=lambda: runtime))
    monkeypatch.setattr(runtime.chromium, 'launch', lambda **kwargs: browser)
    monkeypatch.setattr(browser, 'new_context', lambda **kwargs: context)
    bot.page = None


def test_synthetic_automated_login(synthetic_browser, monkeypatch):
    bot, _, calls = synthetic_browser
    start_with_fixture_browser(bot, monkeypatch)
    result = bot.collect(ENTRY)
    assert result.status == 'ok'
    assert any('/welcome' in url for url in calls)
    assert bot.password is None


def test_synthetic_login_challenge_stops_further_requests(synthetic_browser, monkeypatch):
    bot, state, calls = synthetic_browser
    state['challenge'] = True
    start_with_fixture_browser(bot, monkeypatch)
    with pytest.raises(CollectionError) as exc:
        bot.collect(ENTRY)
    assert exc.value.status == 'login_challenge'
    count = len(calls)
    with pytest.raises(CollectionError):
        bot.collect(ENTRY)
    assert len(calls) == count
    assert not any('/synthetic-business' in url for url in calls)


def test_browser_exception_does_not_expose_password(synthetic_browser, monkeypatch):
    import playwright.sync_api as api
    bot, _, _ = synthetic_browser
    start_with_fixture_browser(bot, monkeypatch)
    def fail(**kwargs):
        raise api.Error('fill("SYNTHETIC-SECRET") failed')
    monkeypatch.setattr(bot.runtime.chromium, 'launch', fail)
    with pytest.raises(CollectionError) as exc:
        bot.collect(ENTRY)
    assert 'SYNTHETIC-SECRET' not in str(exc.value)
    assert exc.value.status == 'browser_failed'
