import json
import math
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path
from contextlib import contextmanager, ExitStack
from hub_utils import skip_indices, filter_value, noise_args, timecode

VIDEO = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.ts', '.m4v', '.flv', '.wmv', '.mpg', '.mpeg', '.m2ts', '.mts', '.3gp', '.vob', '.mxf', '.ogv'}
AUDIO = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.opus'}
HIDDEN = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}

def tool(name):
    import sys
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    bundled = base / 'bin' / (name + '.exe')
    found = str(bundled) if bundled.exists() else shutil.which(name)
    if not found:
        raise RuntimeError(f'Không tìm thấy {name}. Đặt {name}.exe trong thư mục bin hoặc thêm vào PATH.')
    return found

def probe(path):
    result = subprocess.run([tool('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-show_data_hash', 'sha256', '-of', 'json', str(path)], capture_output=True, encoding='utf-8', errors='replace', timeout=60, **HIDDEN)
    if result.returncode:
        raise RuntimeError(f'{Path(path).name}: {result.stderr.strip()}')
    return json.loads(result.stdout)

def duration(path):
    return float(probe(path)['format']['duration'])

def video_stream(info):
    return next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'
                 and not s.get('disposition', {}).get('attached_pic')), None)

def clip_duration(info):
    # The container may include music that extends beyond the last video frame.
    video = video_stream(info)
    for value in ((video or {}).get('duration'), info.get('format', {}).get('duration')):
        try:
            seconds = float(value)
            if math.isfinite(seconds) and seconds > 0:
                return seconds
        except (TypeError, ValueError):
            pass
    raise ValueError('Không đọc được thời lượng video.')

def copy_compatible(infos):
    for info in infos:
        video = video_stream(info) or {}
        audio = next((s for s in info['streams'] if s.get('codec_type') == 'audio'), {})
        if video.get('codec_name') not in {'h264', 'hevc', 'mpeg4', 'av1', 'vp9'}:
            return False
        if audio and audio.get('codec_name') not in {'aac', 'mp3'}:
            return False
        if audio:
            try:
                if abs(float(audio['duration']) - clip_duration(info)) > .1:
                    return False
            except (KeyError, TypeError, ValueError):
                return False
    def signature(info):
        # Concat requires matching stream layout, codec headers and time bases.
        layout = tuple((s.get('codec_type'), s.get('codec_name')) for s in info['streams'])
        video = video_stream(info) or {}
        audio = next((s for s in info['streams'] if s.get('codec_type') == 'audio'), {})
        vkeys = ('codec_name', 'profile', 'level', 'width', 'height', 'pix_fmt',
                 'sample_aspect_ratio', 'r_frame_rate', 'time_base', 'field_order',
                 'color_range', 'color_space', 'color_transfer', 'color_primaries', 'extradata_hash')
        akeys = ('codec_name', 'sample_rate', 'channels', 'channel_layout', 'time_base', 'extradata_hash')
        rotation = tuple(s.get('rotation', 0) for s in video.get('side_data_list', []) if 'rotation' in s)
        return layout, tuple(video.get(k) for k in vkeys), tuple(audio.get(k) for k in akeys), rotation
    first = signature(infos[0])
    return all(signature(info) == first for info in infos[1:])

def concat_line(path):
    return "file '" + str(Path(path).resolve()).replace('\\', '/').replace("'", "'\\''") + "'"

def read_list(path):
    result = []
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('file '):
            line = line[5:].strip()
            if line.startswith("'") and line.endswith("'"):
                line = line[1:-1].replace("'\\''", "'")
        else:
            line = line.strip('"')
        p = Path(line)
        if not p.is_absolute():
            p = Path(path).parent / p
        if not p.is_file():
            raise ValueError(f'Không tìm thấy: {p}')
        result.append(str(p.resolve()))
    if not result:
        raise ValueError('Danh sách trống.')
    logger = logging.getLogger('clipmerge')
    logger.info('Đọc TXT: %s · %s lượt clip', Path(path).resolve(), len(result))
    for index, item in enumerate(result, 1):
        logger.info('  TXT %s: %s', index, item)
    return result

def write_list(path, paths):
    Path(path).write_text('\n'.join(concat_line(p) for p in paths) + '\n', encoding='utf-8')

def select_lists(paths, count_range, target, tolerance, amount, reuse=False, tries=10000, cancel=None, on_probe=None):
    low, high = count_range
    if low < 1 or high < low or high > len(paths) or target <= 0 or tolerance < 0 or amount < 1:
        raise ValueError('Kiểm tra số clip, thời lượng và số danh sách.')
    durations = {}
    for i, p in enumerate(paths):
        if cancel and cancel.is_set():
            raise InterruptedError('Đã dừng.')
        durations[p] = duration(p)
        if on_probe:
            on_probe(i + 1, len(paths))
    results, seen, used = [], set(), set()
    for _ in range(tries):
        if cancel and cancel.is_set():
            raise InterruptedError('Đã dừng.')
        available = [p for p in paths if reuse or p not in used]
        if len(available) < low:
            break
        chosen = random.sample(available, random.randint(low, min(high, len(available))))
        key = tuple(sorted(chosen))
        if key not in seen and abs(sum(durations[p] for p in chosen) - target) <= tolerance:
            results.append((chosen, sum(durations[p] for p in chosen)))
            seen.add(key)
            used.update(chosen)
            if len(results) >= amount:
                break
    return results

class Engine:
    def __init__(self, log=lambda x: None, progress=lambda x: None, status=lambda *x: None):
        self.log, self.progress = log, progress
        self.cancel = threading.Event()
        self.process = None
        self.status = status
        self.context = None
        self.temp_history = []
        self.last_output = []

    @contextmanager
    def workspace(self, parent, cleanup=True):
        parent = Path(parent).resolve()
        temp = Path(tempfile.mkdtemp(prefix='.clipmerge-', dir=parent)).resolve()
        (temp/'.clipmerge-owner').write_text('ClipMerge', encoding='utf-8')
        self.temp_history.append(str(temp))
        try:
            yield temp
        finally:
            if cleanup:
                if temp.parent != parent or not temp.name.startswith('.clipmerge-'):
                    raise RuntimeError('Thư mục Temp không hợp lệ.')
                shutil.rmtree(temp)
            else:
                self.log(f'Giữ Temp: {temp}')

    def stop(self):
        self.cancel.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run(self, args, total=0, progress_range=(0, 99), strict_decode=False):
        if self.cancel.is_set():
            raise InterruptedError('Đã dừng.')
        command = [tool('ffmpeg'), '-hide_banner', '-nostdin', '-n', '-progress', 'pipe:1', '-nostats']
        if strict_decode:
            command += ['-xerror']
        command += args
        logging.getLogger('clipmerge').info('FFmpeg: %s', subprocess.list2cmdline(command))
        errors = []
        important_errors = []
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', **HIDDEN)
        if self.cancel.is_set():
            self.process.terminate()
        for line in self.process.stdout:
            line = line.strip()
            if line.startswith('out_time_us=') and total:
                try:
                    fraction = max(0, min(1, float(line.split('=')[1]) / 1000000 / total))
                    lo, hi = progress_range
                    self.progress(lo + (hi-lo) * fraction)
                except ValueError:
                    pass
            elif line and not re.match(r'^(?:frame|fps|stream_\d+_\d+_q|bitrate|total_size|out_time_us|out_time_ms|out_time|dup_frames|drop_frames|speed|progress)=', line):
                errors.append(line)
                errors = errors[-30:]
                if re.search(r'error|corrupt|invalid|failed|truncat|partial file|no frame|cannot', line, re.I):
                    important_errors.append(line)
                    important_errors = important_errors[-30:]
        self.process.wait()
        code = self.process.returncode
        self.process.stdout.close()
        self.process = None
        self.last_output = errors
        if self.cancel.is_set():
            raise InterruptedError('Đã dừng.')
        if code:
            details = important_errors or errors
            logging.getLogger('clipmerge').error('FFmpeg exit %s:\n%s', code, '\n'.join(details))
            raise RuntimeError(f'FFmpeg lỗi (mã {code}):\n' + ('\n'.join(details[-12:]) or 'Không có thông tin chi tiết.'))

    def merge(self, paths, output, options):
        output = Path(output)
        if output.exists():
            raise ValueError(f'File đã tồn tại: {output.name}')
        if not paths:
            raise ValueError('Chưa có video.')
        sources = [str(Path(p).resolve()) for p in paths]
        original_sources = list(sources)
        infos, lengths = [], []
        self.progress(0)
        for number, p in enumerate(sources, 1):
            self.status('check', number, len(sources))
            if self.cancel.is_set():
                raise InterruptedError('Đã dừng.')
            self.log(f'Kiểm tra: {Path(p).name}')
            if not Path(p).is_file():
                raise ValueError(f'Không tìm thấy: {p}')
            info = probe(p)
            if video_stream(info) is None:
                raise ValueError(f'File không có luồng video: {Path(p).name}')
            infos.append(info)
            lengths.append(clip_duration(info))
        total = sum(lengths)
        ranges = options.get('_preview_ranges')
        encode = bool(options.get('encode') or ranges or options.get('mute'))
        auto_encode = not encode and not copy_compatible(infos)
        if auto_encode:
            self.log('Clip khác thông số hoặc âm thanh: tự chuẩn hóa trước khi ghép.')
            encode = True
        config = dict(options)
        if auto_encode:
            # Keep visual effects off when the user requested a straight join.
            config.update(zoom='1', gamma='1', flip=False, noise=False, normalize=False)
        first_video = video_stream(infos[0])
        config.setdefault('size', f"{first_video['width'] // 2 * 2}x{first_video['height'] // 2 * 2}")
        try:
            default_fps = float(Fraction(first_video.get('avg_frame_rate', '0/1')))
        except (ValueError, ZeroDivisionError):
            default_fps = 30
        config.setdefault('fps', str(default_fps or 30))
        for key, value in dict(encoder='CPU', bitrate='8M', zoom='1', gamma='1').items():
            config.setdefault(key, value)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Stage beside destination; publish only a complete result.
        timeline_path = output.with_name(output.stem+'_timeline.txt')
        if options.get('timeline') and timeline_path.exists():
            raise ValueError(f'File đã tồn tại: {timeline_path.name}')
        with self.workspace(output.parent, options.get('cleanup', True)) as tmp, ExitStack() as contexts:
            inputs = list(sources)
            if options.get('copy_sources'):
                cache = Path(contexts.enter_context(tempfile.TemporaryDirectory(prefix='clipmerge-cache-')))
                for i,p in enumerate(sources):
                    self.status('cache', i+1, len(sources))
                    cached = cache/(f'{i:05}'+Path(p).suffix)
                    with open(p,'rb') as source, open(cached,'xb') as target:
                        while True:
                            if self.cancel.is_set():raise InterruptedError('Đã dừng.')
                            block=source.read(8*1024*1024)
                            if not block:break
                            target.write(block)
                    inputs[i]=str(cached)
            if encode:
                normalized = []
                normalized_infos = []
                w, h = map(int, config['size'].split('x'))
                fps = float(config['fps'])
                if not (0 < fps <= 240 and w > 0 and h > 0 and w % 2 == 0 and h % 2 == 0):
                    raise ValueError('FPS, zoom hoặc gamma không hợp lệ.')
                encoder = {'CPU': 'libx264', 'NVIDIA': 'h264_nvenc', 'Intel': 'h264_qsv', 'AMD': 'h264_amf'}[config['encoder']]
                elapsed = 0
                for i, p in enumerate(sources):
                    self.status('encode', i+1, len(sources))
                    self.log(f'{i + 1}/{len(sources)} · {Path(p).name}')
                    info = infos[i]
                    video = video_stream(info)
                    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
                    source_index = config.get('_source_indices', list(range(len(sources))))[i]
                    filter_total = config.get('_filter_total', len(sources))
                    skip_all = source_index in skip_indices(config.get('skip', ''), filter_total)
                    zoom_text, do_zoom = filter_value(config['zoom'], '1', source_index, filter_total)
                    gamma_text, do_gamma = filter_value(config['gamma'], '1', source_index, filter_total)
                    zoom = float(zoom_text.rstrip('%'))
                    if zoom > 3: zoom /= 100
                    gamma = float(gamma_text)
                    if not (1 <= zoom <= 3 and .1 <= gamma <= 10):
                        raise ValueError('Zoom hoặc Gamma không hợp lệ.')
                    mode = config.get('scale', 'Letterbox')
                    if mode == 'Stretch':
                        spatial = [f'scale={w}:{h}', 'setsar=1']
                    elif mode == 'Crop':
                        spatial = [f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2:reset_sar=1', f'crop={w}:{h}']
                    else:
                        spatial = [f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1', f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2']
                    filters = ['setpts=PTS-STARTPTS'] + spatial + ['setsar=1', f'fps={fps}']
                    if zoom != 1 and do_zoom and not skip_all:
                        filters += [f'scale=trunc(iw*{zoom}/2)*2:trunc(ih*{zoom}/2)*2', f'crop={w}:{h}']
                    if config.get('flip') and not skip_all and source_index not in skip_indices(config.get('flip_skip', ''), filter_total):
                        filters.append('hflip')
                    if gamma != 1 and do_gamma and not skip_all:
                        filters.append(f'eq=gamma={gamma}')
                    if config.get('noise') and not skip_all:
                        noise, do_noise = filter_value(config.get('noise_value', '8,allf=t+u'), '3', source_index, filter_total)
                        if do_noise: filters.append('noise='+noise_args(noise))
                    dest = tmp / f'{i:05}.mp4'
                    args = (['-ss', str(ranges[i][0])] if ranges else [])
                    if config.get('hwaccel'):args += ['-hwaccel',config['hwaccel']]
                    args += ['-i', inputs[i]]
                    muted = config.get('mute', False)
                    if not audio and not muted:
                        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                    args += ['-map', f"0:{video['index']}", '-vf', ','.join(filters), '-c:v', encoder, '-b:v', config['bitrate'], '-pix_fmt', 'yuv420p', '-map_metadata', '-1']
                    if not muted:
                        args += ['-map', f"0:{audio['index']}" if audio else '1:a:0', '-c:a', 'aac', '-b:a', config.get('abitrate', '192k'), '-ar', str(config.get('asample', '48000')), '-ac', '2']
                    else:
                        args += ['-an']
                    af = ['aresample=async=1:first_pts=0']
                    if config.get('normalize') and not muted:
                        if config.get('normalize_mode') == 'peak' and audio:
                            self.status('audio', i+1, len(sources))
                            meter=f"aresample={config.get('asample','48000')},aformat=channel_layouts=stereo,volumedetect"
                            self.run(['-i', inputs[i], '-map', f"0:{audio['index']}", '-vn', '-af', meter, '-f', 'null', '-'], lengths[i], (90*elapsed/total, 90*elapsed/total), strict_decode=True)
                            match = re.search(r'max_volume:\s*([-\d.]+)\s*dB', '\n'.join(self.last_output))
                            target = float(config.get('target_db', -1))
                            if not -60 <= target <= 0: raise ValueError('Target dBFS phải từ -60 đến 0.')
                            gain = max(-60, min(30, target-float(match.group(1)))) if match else 0
                            af.insert(0, f'volume={gain}dB')
                            self.status('encode', i+1, len(sources))
                        else:
                            af.insert(0, 'loudnorm=I=-16:TP=-1.5:LRA=11')
                    af.append('apad')
                    # Duration metadata can underestimate MPEG/TS footage. Let the
                    # decoded video reach EOF; padded audio cannot end it early.
                    if not muted: args += ['-af', ','.join(af), '-shortest']
                    if ranges: args += ['-t', str(ranges[i][1])]
                    args += [str(dest)]
                    try:
                        self.run(args, lengths[i], (90*elapsed/total, 90*(elapsed+lengths[i])/total), strict_decode=True)
                    except RuntimeError as exc:
                        raise RuntimeError(f'Không đọc hết clip {i+1}/{len(sources)}: {p}\n{exc}') from exc
                    elapsed += lengths[i]
                    normalized.append(str(dest))
                    encoded_info = probe(dest)
                    # Validate each clip against its source, before replacing the
                    # source metadata with the shorter normalized file's metadata.
                    source_duration = video.get('duration')
                    if not ranges and source_duration not in (None, 'N/A'):
                        expected_duration = float(source_duration)
                        actual_duration = clip_duration(encoded_info)
                        if actual_duration + max(.15, 2/fps) < expected_duration:
                            raise RuntimeError(f'Clip bị thiếu nội dung sau xử lý: {p}\nNguồn: {expected_duration:.2f}s; đọc được: {actual_duration:.2f}s. Chưa lưu kết quả ghép.')
                    logging.getLogger('clipmerge').info('Clip %s/%s complete: %s; source=%ss, encoded=%ss', i+1, len(sources), p, lengths[i], clip_duration(encoded_info))
                    normalized_infos.append(encoded_info)
                sources = normalized
                infos = normalized_infos
            else:
                sources = inputs
            manifest = tmp / 'concat.txt'
            write_list(manifest, sources)
            dest = tmp / 'result.mp4'
            self.log('Đang ghép…')
            self.status('join', len(sources), len(sources))
            self.run(['-f', 'concat', '-safe', '0', '-i', str(manifest), '-map', '0:V:0', '-map', '0:a:0?', '-c', 'copy', '-movflags', '+faststart', str(dest)], total, (90 if encode else 0, 99))
            result = probe(dest)
            self.status('validate', len(sources), len(sources))
            result_video = video_stream(result)
            if result_video is None:
                raise RuntimeError('Kết quả không có video. Chưa lưu file xuất.')
            expected = sum(clip_duration(info) for info in infos)
            if abs(clip_duration(result) - expected) > max(.2, len(sources) * .1):
                raise RuntimeError('Thời lượng kết quả không khớp tổng các clip. Chưa lưu file xuất.')
            if any(s['codec_type'] == 'audio' for info in infos for s in info['streams']) and not any(s['codec_type'] == 'audio' for s in result['streams']):
                raise RuntimeError('Kết quả bị thiếu âm thanh. Chưa lưu file xuất.')
            counts = [video_stream(info).get('nb_frames') for info in infos]
            if all(str(n).isdigit() for n in counts) and str(result_video.get('nb_frames')).isdigit():
                if sum(map(int, counts)) != int(result_video['nb_frames']):
                    raise RuntimeError('Kết quả bị thiếu khung hình. Chưa lưu file xuất.')
            if self.cancel.is_set():
                raise InterruptedError('Đã dừng.')
            if output.exists():
                raise ValueError(f'File đã tồn tại: {output.name}')
            os.rename(dest, output)
            if options.get('timeline'):
                elapsed = 0
                lines = [f'# Timeline (total {timecode(clip_duration(result))})']
                for n,(source,info) in enumerate(zip(original_sources,infos),1):
                    span = clip_duration(info)
                    lines.append(f'{n:03} | {timecode(elapsed)} - {timecode(elapsed+span)} | {Path(source).name}')
                    elapsed += span
                timeline_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        self.progress(100)
        self.log(f'Đã ghép {len(sources)} clip · {clip_duration(result):.1f}s · {output.name}')
        self.status('complete', len(sources), len(sources))

    def replace(self, video, audio, output):
        output = Path(output)
        if output.exists():
            raise ValueError(f'File đã tồn tại: {output.name}')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.clipmerge-', dir=output.parent) as tmp:
            staged = Path(tmp) / 'result.mp4'
            self.run(['-i', video, '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-af', 'apad', '-t', str(duration(video)), '-map_metadata', '0', '-movflags', '+faststart', str(staged)], duration(video))
            if self.cancel.is_set():
                raise InterruptedError('Đã dừng.')
            if output.exists():
                raise ValueError(f'File đã tồn tại: {output.name}')
            os.rename(staged, output)
        self.progress(100)
