#!/usr/bin/env python3
"""Read-only, on-demand public Pages checks. This does not renew certificates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY_BYTES = 4 * 1024 * 1024
PATHS = ('/', '/robots.txt', '/sitemap.xml', '/data/latest-24h.json')
SM = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def valid_hostname(hostname):
    return (isinstance(hostname, str) and len(hostname) <= 253 and '.' in hostname
            and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                    for label in hostname.split('.')))


def same_origin(url, hostname):
    try:
        value = urlsplit(url)
        return (value.scheme == 'https' and value.hostname == hostname
                and value.port in (None, 443) and value.username is None and value.password is None)
    except ValueError:
        return False


class UnsafeRedirect(Exception):
    pass


class SameOriginRedirect(HTTPRedirectHandler):
    def __init__(self, hostname):
        super().__init__()
        self.hostname = hostname

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not same_origin(newurl, self.hostname):
            raise UnsafeRedirect()
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url, timeout):
    """Use urllib's verified HTTPS defaults; never expose exception URLs or bodies."""
    hostname = urlsplit(url).hostname
    try:
        opener = build_opener(SameOriginRedirect(hostname))
        request = Request(url, headers={'User-Agent': 'AI-News-Radar-Pages-Health/1.0'})
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            final_url = response.geturl()
            if not same_origin(final_url, hostname):
                return {'http_status': status, 'error': 'redirect_outside_origin'}
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                return {'http_status': status, 'error': 'response_too_large'}
            return {'http_status': status, 'final_url': final_url, 'body': body}
    except UnsafeRedirect:
        return {'http_status': None, 'error': 'redirect_outside_origin'}
    except HTTPError as error:
        return {'http_status': error.code, 'error': 'http_error'}
    except URLError as error:
        return {'http_status': None, 'error': 'tls_error' if isinstance(error.reason, ssl.SSLError) else 'network_error'}
    except (ssl.SSLError, TimeoutError, OSError) as error:
        return {'http_status': None, 'error': 'tls_error' if isinstance(error, ssl.SSLError) else 'network_error'}


class SiteHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ''
        self.canonical = ''

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'title':
            self.in_title = True
        elif tag == 'link' and values.get('rel') == 'canonical':
            self.canonical = values.get('href', '')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def utc_time(value):
    if not isinstance(value, str):
        raise ValueError('missing_timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        # Pages exposes certificate expiration as a UTC calendar date.
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('timezone_required')
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def content_ok(path, body, hostname):
    try:
        text = body.decode('utf-8')
        origin = f'https://{hostname}'
        if path == '/':
            head = SiteHead()
            head.feed(text)
            return 'AI News Radar' in head.title and head.canonical == origin + '/'
        if path == '/robots.txt':
            lines = [line.strip().lower() for line in text.splitlines()]
            return 'user-agent: *' in lines and 'allow: /' in lines and f'sitemap: {origin}/sitemap.xml' in lines
        if path == '/sitemap.xml':
            root = ET.fromstring(text)
            locations = [node.text for node in root.findall(f'{SM}url/{SM}loc')]
            return root.tag == SM + 'urlset' and origin + '/' in locations and all(same_origin(url, hostname) for url in locations)
        data = json.loads(text)
        return (isinstance(data, dict) and bool(utc_time(data.get('generated_at')))
                and type(data.get('window_hours')) in (int, float) and data['window_hours'] > 0
                and isinstance(data.get('items'), list) and bool(data['items'])
                and all(isinstance(item, dict) and isinstance(item.get('title'), str) and item['title'].strip()
                        and isinstance(item.get('url'), str) and urlsplit(item['url']).scheme in ('http', 'https')
                        for item in data['items']))
    except (ValueError, TypeError, UnicodeError, ET.ParseError):
        return False


def certificate_ok(metadata, hostname, now):
    if not isinstance(metadata, dict) or metadata.get('cname') != hostname:
        return False
    certificate = metadata.get('https_certificate')
    if not isinstance(certificate, dict):
        return False
    try:
        return (certificate.get('state') == 'approved' and isinstance(certificate.get('domains'), list)
                and hostname in certificate['domains'] and utc_time(certificate.get('expires_at')) > now)
    except (ValueError, TypeError):
        return False


def check_site(hostname, pages=None, now=None, fetcher=fetch_url, timeout=10):
    if not valid_hostname(hostname) or not 0 < timeout <= 30:
        raise ValueError('invalid_input')
    now = now or datetime.now(timezone.utc)
    checks = []
    for path in PATHS:
        result = fetcher(f'https://{hostname}{path}', timeout)
        error = result.get('error')
        if not error and not same_origin(result.get('final_url', ''), hostname):
            error = 'redirect_outside_origin'
        if not error and result.get('http_status') != 200:
            error = 'http_error'
        if not error and not content_ok(path, result.get('body', b''), hostname):
            error = 'unexpected_content'
        checks.append({'path': path, 'ok': not error, 'http_status': result.get('http_status'), **({'error': error} if error else {})})
    if pages is not None:
        ok = certificate_ok(pages, hostname, now)
        checks.append({'path': 'github_pages_metadata', 'ok': ok, **({} if ok else {'error': 'pages_certificate_invalid_or_missing'})})
    ok = all(row['ok'] for row in checks)
    return {'hostname': hostname, 'checked_at': now.isoformat(), 'ok': ok,
            'status': ('checks_passed' if pages is not None else 'public_http_ok') if ok else 'failed',
            'pages_metadata_checked': pages is not None, 'checks': checks,
            'limitations': ['Public HTTPS checks validate the served routes, not a direct Cloudflare-to-origin handshake.',
                            'Supplied Pages metadata is a snapshot; refresh it with gh api before recovery verification.' if pages is not None
                            else 'Pages origin certificate metadata was not supplied; origin certificate recovery is unverified.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages-json', type=Path, help='Fresh JSON from gh api repos/LearnPrompt/ai-news-radar/pages')
    parser.add_argument('--timeout', type=float, default=10, help='Per-request socket timeout, seconds (0 < timeout <= 30)')
    args = parser.parse_args(argv)
    try:
        hostname = (ROOT / 'CNAME').read_text(encoding='utf-8').strip().lower()
        pages = None
        if args.pages_json:
            raw = args.pages_json.read_bytes()
            if len(raw) > 256 * 1024:
                raise ValueError('metadata_too_large')
            pages = json.loads(raw)
            if not isinstance(pages, dict):
                raise ValueError('metadata_must_be_object')
        report = check_site(hostname, pages=pages, timeout=args.timeout)
    except (OSError, ValueError, UnicodeError):
        print(json.dumps({'ok': False, 'status': 'input_error', 'error': 'Invalid CNAME, timeout or Pages JSON input.'}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
