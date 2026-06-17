#!/usr/bin/env python3
'''将会议讲解脚本 JSON 发布到 Presenter Windows 共享目录。

本脚本只拷贝当前会议目录下的 PresentationScript.json，并在目标共享目录
中创建同名会议文件夹。目标文件夹中只保留 PresentationScript.json，不发布
客户画像、演示文稿、Markdown 脚本或音频目录。
'''

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common import data_root, meeting_dir


DEFAULT_SHARE_PATH = '\\\\172.16.1.138\\SharedResources\\PresetMeetingData'
DEFAULT_USERNAME = 'digihail'
DEFAULT_PASSWORD = 'frontfree'
MEETING_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def parse_unc(path: str) -> tuple[str, str, list[str]]:
    normalized = path.replace('/', '\\').strip()
    if not normalized.startswith('\\\\'):
        raise ValueError('share path must be a UNC path')
    parts = [p for p in normalized.lstrip('\\').split('\\') if p]
    if len(parts) < 2:
        raise ValueError('share path must include server and share name')
    return parts[0], parts[1], parts[2:]


def target_path(share_path: str, meeting_id: str) -> str:
    server, share, rest = parse_unc(share_path)
    return '\\\\' + '\\'.join([server, share, *rest, meeting_id, 'PresentationScript.json'])


def quote_smb(value: str) -> str:
    double_quote = chr(34)
    return double_quote + value.replace(double_quote, '\\' + double_quote) + double_quote


def run_smbclient(server: str, share: str, username: str, password: str, commands: str) -> subprocess.CompletedProcess[str]:
    if shutil.which('smbclient') is None:
        raise RuntimeError('smbclient is not installed; install it or run this script on Windows')
    auth_file = Path(os.environ.get('TMPDIR', '/tmp')) / f'smb_auth_{os.getpid()}.conf'
    auth_file.write_text(f'username = {username}\npassword = {password}\n', encoding='utf-8')
    try:
        return subprocess.run(
            ['smbclient', f'//{server}/{share}', '-A', str(auth_file), '-m', 'SMB3', '-c', commands],
            text=True, capture_output=True, check=False,
        )
    finally:
        try:
            auth_file.unlink()
        except OSError:
            pass


def publish_linux(source: Path, share_path: str, meeting_id: str, username: str, password: str, clean: bool) -> str:
    server, share, rest = parse_unc(share_path)
    parts = rest + [meeting_id]
    current: list[str] = []
    for part in parts:
        prefix = 'cd ' + quote_smb('/'.join(current)) + '; ' if current else ''
        run_smbclient(server, share, username, password, prefix + 'mkdir ' + quote_smb(part))
        current.append(part)
    commands = ['cd ' + quote_smb(part) for part in parts]
    if clean:
        commands.append('del *')
    commands.append('put ' + quote_smb(str(source)) + ' ' + quote_smb('PresentationScript.json'))
    result = run_smbclient(server, share, username, password, '; '.join(commands))
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return target_path(share_path, meeting_id)


def publish_windows(source: Path, share_path: str, meeting_id: str, username: str, password: str, clean: bool) -> str:
    server, share, rest = parse_unc(share_path)
    share_root = '\\\\' + server + '\\' + share
    subprocess.run(['net', 'use', share_root, f'/user:{username}', password, '/persistent:no'], capture_output=True, text=True, check=False)
    dest_dir = Path(share_root)
    for part in [*rest, meeting_id]:
        dest_dir = dest_dir / part
    if clean and dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / 'PresentationScript.json'
    shutil.copy2(source, dest_file)
    return str(dest_file)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('meeting_id')
    parser.add_argument('--data-root', default=None)
    parser.add_argument('--share-path', default=DEFAULT_SHARE_PATH)
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument('--password', default=DEFAULT_PASSWORD)
    parser.add_argument('--no-clean', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not MEETING_ID_RE.match(args.meeting_id):
        print('invalid meeting_id', file=sys.stderr)
        return 2
    source = meeting_dir(data_root(args.data_root), args.meeting_id) / 'PresentationScript.json'
    if not source.exists():
        print(f'PresentationScript.json not found: {source}', file=sys.stderr)
        return 1
    destination = target_path(args.share_path, args.meeting_id)
    if args.dry_run:
        print(json.dumps({'meeting_id': args.meeting_id, 'source': str(source), 'destination': destination, 'dry_run': True}, ensure_ascii=False, indent=2))
        return 0
    try:
        if os.name == 'nt':
            destination = publish_windows(source, args.share_path, args.meeting_id, args.username, args.password, not args.no_clean)
        else:
            destination = publish_linux(source, args.share_path, args.meeting_id, args.username, args.password, not args.no_clean)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({'meeting_id': args.meeting_id, 'source': str(source), 'destination': destination, 'published': True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


