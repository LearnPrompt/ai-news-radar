import json
import subprocess
from unittest.mock import patch

from scripts.update_news import (
    clean_agentmail_public_url,
    fetch_agentmail_digest_via_cli,
    maybe_fetch_agentmail_digest,
)


def listed(messages):
    return subprocess.CompletedProcess([], 0, json.dumps({'ok': True, 'data': {'data': messages}}), '')


def test_domain_filter_runs_before_any_body_reads():
    messages = [
        {'message_id': 'allowed', 'from': {'email': 'news@example.com'}, 'subject': 'Allowed'},
        {'message_id': 'excluded', 'from': {'email': 'private@other.example'}, 'subject': 'Excluded'},
    ]
    with patch('subprocess.run', return_value=listed(messages)), patch(
        'scripts.update_news.read_agentmail_public_url_via_cli', return_value='https://example.com/issue'
    ) as read:
        result = fetch_agentmail_digest_via_cli(generated_at='2026-09-09T00:00:00Z',
            after='2026-09-08T00:00:00Z', allowed_sender_domains=['example.com'], resolve_public_urls=True)
    read.assert_called_once_with('allowed', cli_path='agently-cli')
    assert result['total_messages'] == 1
    assert 'Excluded' not in json.dumps(result)


def test_body_timeout_preserves_metadata_without_publishing_a_link():
    messages = [{'message_id': 'one', 'from': {'email': 'news@example.com'}, 'subject': 'A newsletter'}]
    with patch('subprocess.run', side_effect=[listed(messages), subprocess.TimeoutExpired('agently-cli', 45)]):
        result = fetch_agentmail_digest_via_cli(generated_at='2026-09-09T00:00:00Z',
            after='2026-09-08T00:00:00Z', resolve_public_urls=True)
    assert result['total_messages'] == 1
    assert 'public_url' not in result['items'][0]


def test_credentials_and_ambiguous_tracking_links_are_not_published():
    assert clean_agentmail_public_url('https://reader:secret@example.com/issue') == ''
    assert clean_agentmail_public_url('https://tracking.example.com/private-token') == ''
    assert clean_agentmail_public_url('https://agent.qq.com:443/?message_id=private') == ''


def test_disabled_mail_never_invokes_cli():
    with patch.dict('os.environ', {}, clear=True), patch('subprocess.run') as run:
        payload, status = maybe_fetch_agentmail_digest(None, '2026-09-09T00:00:00Z', '2026-09-08T00:00:00Z', 24)
    assert payload is None
    assert status['enabled'] is False
    run.assert_not_called()
