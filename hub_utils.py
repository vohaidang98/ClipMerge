import ctypes
import os
import re
import shutil
from pathlib import Path
from ctypes import wintypes

def seconds(text):
    values = str(text).strip().split(':')
    if not 1 <= len(values) <= 3:
        raise ValueError('Thời gian dùng dạng giây, MM:SS hoặc HH:MM:SS.')
    total = 0.0
    for part in values:
        value = float(part)
        if value < 0:
            raise ValueError('Thời gian không được âm.')
        total = total*60 + value
    return total

def timecode(value):
    total=round(value*1000)
    return f'{total//3600000:02}:{total//60000%60:02}:{total//1000%60:02}.{total%1000:03}'

def skip_indices(text, total):
    result = set()
    for item in re.split(r'[,;\s]+', str(text).strip()):
        if not item:
            continue
        if re.fullmatch(r'\+\d+', item):
            result.update(range(min(int(item), total)))
        elif re.fullmatch(r'-\d+', item):
            result.update(range(max(0, total+int(item)), total))
        elif re.fullmatch(r'\d+-\d+', item):
            start, end = map(int, item.split('-'))
            if not 1 <= start <= end:
                raise ValueError(f'Skip không hợp lệ: {item}')
            result.update(range(start-1, min(end,total)))
        elif item.isdigit() and int(item)>0:
            if int(item)<=total:result.add(int(item)-1)
        else:
            raise ValueError(f'Skip không hợp lệ: {item}')
    return result

def filter_value(text, default, index, total):
    value, _, rules = str(text).partition('|')
    return (value.strip() or default), index not in skip_indices(rules, total)

def noise_args(text):
    text = str(text).strip() or '3'
    if text.startswith('noise='):text=text[6:]
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        return f'alls={text}:allf=t'
    fields = text.replace(',', ':')
    if re.match(r'^\d+(?:\.\d+)?:', fields):
        fields = 'alls=' + fields
    if fields in ('t', 'ut', 'u', 't+u'):
        fields='alls=3:allf='+fields
    normalized=[]
    for part in fields.split(':'):
        key,sep,value=part.partition('=')
        if re.fullmatch(r'c[0-3]',key):key+='s'
        if key.endswith('f') and re.fullmatch(r'[aptu]+',value):value='+'.join(dict.fromkeys(value))
        normalized.append(key+sep+value)
    fields=':'.join(normalized)
    # Allow noise options, never a second filter or a filter graph.
    if not re.fullmatch(r'(?:alls|allf|c[0-3][sf])=[\w.+-]+(?::(?:alls|allf|c[0-3][sf])=[\w.+-]+)*', fields):
        raise ValueError('Noise không hợp lệ. Ví dụ: 3 hoặc alls=3:allf=t+u.')
    return fields + (':allf=t' if 'allf=' not in fields else '')

def move_tasks(paths, destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    plans = []
    for path in paths:
        src = Path(path).resolve()
        dest = (root/src.name).resolve()
        if dest.parent != root or src.suffix.lower() != '.txt':
            raise ValueError('Chỉ di chuyển file Task TXT vào thư mục đã chọn.')
        if src == dest:
            continue
        if dest.exists():
            raise ValueError(f'File đã tồn tại: {dest.name}')
        plans.append((src, dest))
    for src, dest in plans:
        shutil.move(str(src), str(dest))
    return {str(src):str(dest) for src,dest in plans}

def recycle_task(path):
    path = Path(path).resolve()
    if path.suffix.lower() != '.txt' or not path.is_file():
        raise ValueError('Chỉ đưa file Task TXT vào Thùng rác.')
    if os.name != 'nt':
        raise RuntimeError('Chức năng Thùng rác cần Windows.')
    class FileOp(ctypes.Structure):
        _fields_=[('hwnd',wintypes.HWND),('wFunc',wintypes.UINT),('pFrom',wintypes.LPCWSTR),('pTo',wintypes.LPCWSTR),('fFlags',wintypes.WORD),('fAnyOperationsAborted',wintypes.BOOL),('hNameMappings',ctypes.c_void_p),('lpszProgressTitle',wintypes.LPCWSTR)]
    operation = FileOp()
    operation.wFunc = 3
    source = ctypes.create_unicode_buffer(str(path)+'\0\0')
    operation.pFrom = ctypes.cast(source, wintypes.LPCWSTR)
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if code or operation.fAnyOperationsAborted:
        raise RuntimeError(f'Không đưa được Task vào Thùng rác: {path.name} (mã {code}).')
