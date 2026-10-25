"""Public-site verification must fail on 526 and stale Pages certificates."""
from datetime import datetime, timezone
from io import BytesIO
import json
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_pages_health as health

HOST = 'news.learnprompt.pro'
NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


@pytest.fixture
def payloads():
    return {
        '/': b'<html><head><title>AI News Radar</title><link rel="canonical" href="https://news.learnprompt.pro/"></head><body>AI News Radar</body></html>',
        '/robots.txt': b'User-agent: *\nAllow: /\nSitemap: https://news.learnprompt.pro/sitemap.xml\n',
        '/sitemap.xml': b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://news.learnprompt.pro/</loc></url></urlset>',
        '/data/latest-24h.json': json.dumps({'generated_at': '2026-10-25T00:00:00Z', 'window_hours': 24, 'items': [{'title': 'AI news', 'url': 'https://example.org/news'}]}).encode(),
    }


def probe(payloads, pages=None):
    def fetch(url, timeout):
        path = health.urlsplit(url).path
        return {'http_status': 200, 'body': payloads[path], 'final_url': url}
    return health.check_site(HOST, pages=pages, now=NOW, fetcher=fetch)


def pages():
    return {'cname': HOST, 'https_certificate': {'state': 'approved', 'expires_at': '2026-11-25', 'domains': [HOST]}}


def test_public_checks_do_not_claim_origin_certificate_verified(payloads):
    report = probe(payloads)
    assert report['ok']
    assert report['status'] == 'public_http_ok'
    assert report['pages_metadata_checked'] is False
    assert report['limitations']


def test_public_and_pages_checks_pass(payloads):
    report = probe(payloads, pages())
    assert report['ok']
    assert report['pages_metadata_checked'] is True
    assert len(report['checks']) == 5


@pytest.mark.parametrize('change', [
    lambda p: p['https_certificate'].update(state='bad_authz'),
    lambda p: p['https_certificate'].update(expires_at='2026-10-12'),
    lambda p: p['https_certificate'].pop('expires_at'),
    lambda p: p.pop('https_certificate'),
    lambda p: p.update(cname='www.learnprompt.pro'),
    lambda p: p['https_certificate'].update(domains=['www.learnprompt.pro']),
])
def test_bad_or_incomplete_certificate_is_not_recovery(payloads, change):
    metadata = pages()
    change(metadata)
    assert not probe(payloads, metadata)['ok']


@pytest.mark.parametrize('path,body', [
    ('/', b'<html><title>Cloudflare error</title></html>'),
    ('/robots.txt', b'<html>error code 526</html>'),
    ('/sitemap.xml', b'<html>not a sitemap</html>'),
    ('/data/latest-24h.json', b'{}'),
    ('/data/latest-24h.json', b'{"generated_at":"today","window_hours":24,"items":[]}'),
])
def test_http_200_error_bodies_fail(payloads, path, body):
    payloads[path] = body
    assert not probe(payloads)['ok']


def test_http_526_is_preserved():
    def fetch(url, timeout):
        return {'http_status': 526, 'error': 'http_error'}
    report = health.check_site(HOST, now=NOW, fetcher=fetch)
    assert not report['ok']
    assert all(row['http_status'] == 526 for row in report['checks'])


def test_final_cross_host_cannot_clear_failure(payloads):
    def fetch(url, timeout):
        return {'http_status': 200, 'body': payloads['/'], 'final_url': 'https://www.learnprompt.pro/'}
    report = health.check_site(HOST, now=NOW, fetcher=fetch)
    assert not report['ok']
    assert all(row['error'] == 'redirect_outside_origin' for row in report['checks'])


def test_redirect_handler_rejects_cross_host_and_http():
    redirect = health.SameOriginRedirect(HOST)
    for target in ['https://www.learnprompt.pro/', 'http://news.learnprompt.pro/', 'https://news.learnprompt.pro:444/', 'https://user:password@news.learnprompt.pro/']:
        with pytest.raises(health.UnsafeRedirect):
            redirect.redirect_request(None, None, 302, '', {}, target)


@pytest.mark.parametrize('failure,expected', [
    (HTTPError('https://secret:password@news.learnprompt.pro/', 526, 'bad', {}, BytesIO(b'failure')), 'http_error'),
    (URLError('https://secret:password@private.example/'), 'network_error'),
])
def test_network_errors_are_classified_without_exception_secrets(monkeypatch, failure, expected):
    class Opener:
        def open(self, *args, **kwargs):
            raise failure
    monkeypatch.setattr(health, 'build_opener', lambda *args: Opener())
    result = health.fetch_url('https://news.learnprompt.pro/', 1)
    assert result['error'] == expected
    assert 'password' not in json.dumps(result)
    if expected == 'http_error':
        assert result['http_status'] == 526


def test_response_size_is_bounded(monkeypatch):
    class Response(BytesIO):
        status = 200
        def geturl(self):
            return 'https://news.learnprompt.pro/'
    class Opener:
        def open(self, *args, **kwargs):
            return Response(b'a' * (health.MAX_BODY_BYTES + 1))
    monkeypatch.setattr(health, 'build_opener', lambda *args: Opener())
    assert health.fetch_url('https://news.learnprompt.pro/', 1)['error'] == 'response_too_large'


@pytest.mark.parametrize('hostname', ['https://news.learnprompt.pro/', 'a@b', 'a/b', '', 'news.learnprompt.pro:443'])
def test_invalid_hostname_is_input_error(hostname):
    with pytest.raises(ValueError):
        health.check_site(hostname, now=NOW)


def test_current_repository_payloads_match_verification_contract():
    payloads = {path: (health.ROOT / ('index.html' if path == '/' else path.lstrip('/'))).read_bytes()
                for path in health.PATHS}
    assert probe(payloads, pages())['ok']


@pytest.mark.parametrize('raw', [b'not json', b'[]', b'null'])
def test_cli_rejects_bad_pages_input_before_network(tmp_path, capsys, monkeypatch, raw):
    metadata = tmp_path / 'pages.json'
    metadata.write_bytes(raw)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid input must not reach network')
    monkeypatch.setattr(health, 'check_site', forbidden)
    assert health.main(['--pages-json', str(metadata)]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'input_error'


def test_cli_failure_exit_and_json(capsys, monkeypatch):
    monkeypatch.setattr(health, 'check_site', lambda *args, **kwargs: {'ok': False, 'status': 'failed'})
    assert health.main([]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'failed'


def test_cli_public_success_exit_and_json(capsys, monkeypatch):
    monkeypatch.setattr(health, 'check_site', lambda *args, **kwargs: {'ok': True, 'status': 'public_http_ok'})
    assert health.main([]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'public_http_ok'
