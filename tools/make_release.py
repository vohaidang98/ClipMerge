"""Tạo file mã SHA-256 đi kèm file cài đặt để đăng lên GitHub Releases.

Chạy:
  python tools\\make_release.py <file cài đặt .exe>

Ví dụ:
  python tools\\make_release.py D:\\Code\\ClipMerge\\ClipMerge-Setup-2.1.1.exe
Kết quả: tạo ClipMerge-Setup-2.1.1.exe.sha256 cạnh file cài đặt.

Đăng bản phát hành (tag vX.Y.Z), đính kèm CẢ HAI file:
  gh release create v2.1.1 ClipMerge-Setup-2.1.1.exe ClipMerge-Setup-2.1.1.exe.sha256 --notes "..."
App sẽ tìm đúng tên ClipMerge-Setup-<phiên bản>.exe trong bản phát hành mới nhất.
"""
import hashlib
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
installer = Path(sys.argv[1])
if not installer.is_file():
    raise SystemExit(f'Không thấy file: {installer}')
digest = hashlib.sha256()
with installer.open('rb') as f:
    for chunk in iter(lambda: f.read(1 << 20), b''):
        digest.update(chunk)
target = installer.with_name(installer.name + '.sha256')
target.write_text(f'{digest.hexdigest()}  {installer.name}\n', encoding='utf-8')
print('SHA256:', digest.hexdigest())
print('Da tao:', target)
