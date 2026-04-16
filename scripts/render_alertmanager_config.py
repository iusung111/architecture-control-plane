from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_CONFIG = ROOT / 'deploy' / 'alertmanager' / 'alertmanager.src.yml'
GENERATED_CONFIG = ROOT / 'deploy' / 'alertmanager' / 'alertmanager.yml'
DEFAULT_EMAIL_TO = 'team@example.com'
DEFAULT_EMAIL_FROM = 'architecture-control-plane-alerts@example.local'
DEFAULT_SMARTHOST = 'mailpit:1025'
DEFAULT_WEBHOOK_URL = 'http://webhook-sink:8081/alertmanager'


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def main() -> None:
    config = _load_yaml(SRC_CONFIG)

    email_to = os.getenv('ALERTMANAGER_DEFAULT_EMAIL_TO', DEFAULT_EMAIL_TO).strip()
    email_from = os.getenv('ALERTMANAGER_SMTP_FROM', DEFAULT_EMAIL_FROM).strip()
    smtp_smarthost = os.getenv('ALERTMANAGER_SMTP_SMARTHOST', DEFAULT_SMARTHOST).strip()
    smtp_require_tls = _as_bool(os.getenv('ALERTMANAGER_SMTP_REQUIRE_TLS'), default=False)
    smtp_auth_username = os.getenv('ALERTMANAGER_SMTP_AUTH_USERNAME', '').strip()
    smtp_auth_password = os.getenv('ALERTMANAGER_SMTP_AUTH_PASSWORD', '').strip()
    webhook_url = os.getenv('ALERTMANAGER_WEBHOOK_URL', DEFAULT_WEBHOOK_URL).strip()

    if not email_to:
        raise SystemExit('ALERTMANAGER_DEFAULT_EMAIL_TO must not be empty')
    if not webhook_url:
        raise SystemExit('ALERTMANAGER_WEBHOOK_URL must not be empty')

    global_cfg = config.setdefault('global', {})
    global_cfg['smtp_from'] = email_from
    global_cfg['smtp_smarthost'] = smtp_smarthost
    global_cfg['smtp_require_tls'] = smtp_require_tls
    if smtp_auth_username:
        global_cfg['smtp_auth_username'] = smtp_auth_username
    else:
        global_cfg.pop('smtp_auth_username', None)
    if smtp_auth_password:
        global_cfg['smtp_auth_password'] = smtp_auth_password
    else:
        global_cfg.pop('smtp_auth_password', None)

    for receiver in config.get('receivers', []):
        if receiver.get('name') == 'webhook-sink':
            receiver['webhook_configs'][0]['url'] = webhook_url
        if receiver.get('name') == 'email-default':
            email_cfg = receiver['email_configs'][0]
            email_cfg['to'] = email_to
            email_cfg['from'] = email_from

    GENERATED_CONFIG.write_text(yaml.safe_dump(config, sort_keys=False))


if __name__ == '__main__':
    main()
