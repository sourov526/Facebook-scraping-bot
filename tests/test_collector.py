import csv
import pytest
from collector.extraction import extract_text
from collector.models import Result
from collector.storage import Storage
from collector.export import export_csv, safe_cell


def test_literal_email_extraction():
    assert extract_text("hello@EXAMPLE.com hello@EXAMPLE.com name [at] example.com") == {"hello@example.com"}


def test_sqlite_resume_dedup_and_csv(tmp_path):
    store = Storage(tmp_path / 'db.sqlite3')
    r = Result(page_url='https://facebook.com/1', page_name='=HYPERLINK("bad"), বাংলা\nদোকান',
               observations={('a@example.com', 'https://example.com'), ('a@example.com', 'https://example.com/contact')}, status='ok')
    store.save('one', r)
    store.save('one', r)
    store.save('two', Result(page_url='https://facebook.com/2', status='access_failed'))
    assert store.done('one', True) and not store.done('two', True)
    store.close()
    store = Storage(tmp_path / 'db.sqlite3')
    assert store.done('two')
    output = tmp_path / 'contacts.csv'
    export_csv(store, ['one', 'one', 'two'], output)
    assert output.read_bytes().startswith(b'\xef\xbb\xbf')
    with output.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and rows[0]['page_name'].startswith("'=HYPERLINK")
    assert 'বাংলা\nদোকান' in rows[0]['page_name']
    assert rows[2]['email'] == '' and rows[2]['status'] == 'access_failed'
    store.close()


@pytest.mark.parametrize('cell', ['=1+2', '+cmd', '-1', '@SUM(A1)', ' \t=1', '\ntext'])
def test_formula_protection(cell):
    assert safe_cell(cell).startswith("'")


def test_checkpoint_transaction_rolls_back(tmp_path):
    store = Storage(tmp_path / 'db.sqlite3')
    original = Result(page_url='https://facebook.com/1', page_name='original', status='ok')
    store.save('one', original)
    broken = Result(page_url='https://facebook.com/1', page_name='replacement')
    broken.observations = {('email@example.com', None)}
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.save('one', broken)
    assert list(store.rows(['one']))[0][0] == 'original'
    store.close()


def test_demo_cli_never_requests_network(tmp_path, monkeypatch):
    from collector import __main__ as cli
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['collector', '--demo'])
    def reject(*args, **kwargs):
        raise AssertionError('offline demo attempted network access')
    monkeypatch.setattr(cli.BrowserFacebook, '__init__', reject)
    cli.main()
    output = tmp_path / 'output' / 'demo-contacts.csv'
    first = output.read_bytes()
    cli.main()
    assert output.read_bytes() == first
    with output.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert all('SYNTHETIC' in row['error_reason'] for row in rows)


def test_default_cli_uses_business_browser_and_resumes(tmp_path, monkeypatch):
    from collector import __main__ as cli
    entry = {'page_url': 'https://www.facebook.com/synthetic-business', 'business_page': True}
    calls = []
    class Browser:
        def __init__(self, *args, **kwargs):
            pass
        def collect(self, item):
            calls.append(item)
            return Result(page_url=item['page_url'], page_name='Synthetic Business', status='no_email')
        def close(self):
            pass
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli.config, 'PAGES', [entry])
    monkeypatch.setattr(cli, 'BrowserFacebook', Browser)
    monkeypatch.setattr('sys.argv', ['collector'])
    cli.main()
    cli.main()
    assert calls == [entry]
    assert (tmp_path / 'output' / 'browser-progress.sqlite3').exists()
    with (tmp_path / 'output' / 'contacts.csv').open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['status'] == 'no_email' and row['email'] == ''
    monkeypatch.setattr('sys.argv', ['collector', '--refresh'])
    cli.main()
    assert len(calls) == 2


def test_cli_records_login_failure_without_exposing_credentials(tmp_path, monkeypatch):
    from collector import __main__ as cli
    from collector.models import CollectionError
    class Browser:
        def __init__(self, *args, **kwargs):
            pass
        def collect(self, entry):
            raise CollectionError('login_failed', 'login_not_completed')
        def close(self):
            pass
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli.config, 'PAGES', [{'page_url': 'https://www.facebook.com/synthetic-business', 'business_page': True}])
    monkeypatch.setattr(cli, 'BrowserFacebook', Browser)
    monkeypatch.setattr('sys.argv', ['collector'])
    cli.main()
    with (tmp_path / 'output' / 'contacts.csv').open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['status'] == 'login_failed' and row['email'] == ''
