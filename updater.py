"""Cập nhật tự động qua GitHub Releases (chỉ dùng thư viện chuẩn).

Mỗi bản phát hành trên https://github.com/vohaidang98/ClipMerge/releases cần:
  - tag dạng vX.Y.Z (ví dụ v2.1.1)
  - file cài đặt ClipMerge-Setup-X.Y.Z.exe đính kèm (asset)
  - tuỳ chọn: ClipMerge-Setup-X.Y.Z.exe.sha256 để kiểm tra toàn vẹn
    (tạo bằng: python tools\\make_release.py <file cài đặt .exe>)
Ghi chú bản phát hành (phần mô tả release) được hiện cho người dùng trước khi cập nhật.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

REPO = 'vohaidang98/ClipMerge'
API_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
USER_AGENT = 'ClipMerge-Updater'
TIMEOUT = 20


def parse_version(text):
    match = re.search(r'(\d+(?:\.\d+){0,3})', str(text))
    return tuple(int(part) for part in match.group(1).split('.')) if match else ()


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    if not a:
        return False
    size = max(len(a), len(b))
    a += (0,) * (size - len(a))
    b += (0,) * (size - len(b))
    return a > b


def _open(url, accept='application/octet-stream'):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def _find_asset(assets, name):
    for asset in assets:
        if str(asset.get('name', '')).lower() == name.lower():
            return asset
    return None


def check_latest(current):
    """Hỏi GitHub bản phát hành mới nhất.

    Trả về dict {'version', 'name', 'url', 'sha256', 'notes'} nếu có bản mới hơn,
    hoặc None nếu đang là bản mới nhất (hoặc kho chưa có bản phát hành nào).
    """
    try:
        with _open(API_URL, 'application/vnd.github+json') as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ValueError(f'GitHub trả lỗi {exc.code} khi kiểm tra cập nhật.') from exc
    except urllib.error.URLError as exc:
        raise ValueError(f'Không kết nối được GitHub:\n{exc.reason}') from exc
    if data.get('draft') or data.get('prerelease'):
        return None
    version = str(data.get('tag_name', '')).strip().lstrip('vV')
    if not parse_version(version) or not is_newer(version, current):
        return None
    assets = data.get('assets') or []
    name = f'ClipMerge-Setup-{version}.exe'
    asset = _find_asset(assets, name)
    if asset is None:
        raise ValueError(f'Bản phát hành v{version} chưa có file {name}.')
    url = str(asset.get('browser_download_url', ''))
    if not url.startswith('https://github.com/'):
        raise ValueError('Đường dẫn tải bản cập nhật không hợp lệ.')
    sha = ''
    sha_asset = _find_asset(assets, name + '.sha256')
    if sha_asset is not None:
        try:
            with _open(str(sha_asset.get('browser_download_url', ''))) as response:
                text = response.read(4096).decode('utf-8', 'replace')
        except Exception as exc:
            raise ValueError('Không tải được file mã SHA-256 của bản cập nhật.') from exc
        match = re.search(r'\b[0-9a-fA-F]{64}\b', text)
        if not match:
            raise ValueError('File .sha256 của bản cập nhật không hợp lệ.')
        sha = match.group(0).lower()
    return {'version': version, 'name': name, 'url': url, 'sha256': sha,
            'notes': str(data.get('body') or '')}


def download(info, progress=None):
    """Tải file cài đặt về máy, kiểm tra SHA-256 (nếu có), trả về đường dẫn file trên máy."""
    folder = tempfile.mkdtemp(prefix='app_update_')
    dest = os.path.join(folder, info['name'])
    digest = hashlib.sha256()
    try:
        with _open(info['url']) as src, open(dest, 'wb') as out:
            total = int(src.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done * 100 / total)
        if total and done != total:
            raise ValueError('Tải bản cập nhật không trọn vẹn, đã huỷ cập nhật.')
        if info.get('sha256') and digest.hexdigest() != info['sha256']:
            raise ValueError('File cập nhật bị lỗi (sai mã SHA-256), đã huỷ cập nhật.')
    except urllib.error.URLError as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise ValueError(f'Không tải được bản cập nhật:\n{getattr(exc, "reason", exc)}') from exc
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return dest


def install(path):
    """Chạy file cài đặt Inno Setup ở chế độ im lặng. Gọi xong thì đóng app."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS'],
                     close_fds=True, creationflags=flags)
