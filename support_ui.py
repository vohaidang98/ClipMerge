import json
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import random
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from engine import Engine, VIDEO, AUDIO, read_list, write_list, select_lists

BG, PANEL, INK, MUTED, ACCENT = '#f4f6fb', '#ffffff', '#1c2940', '#78849b', '#5965e9'
SIDEBAR = '#131d31'

class MediaTable(ttk.Treeview):
    """File table exposing the selection operations used by the editor."""
    def __init__(self, parent):
        super().__init__(parent, columns=('number', 'name', 'type'), show='headings',
                         selectmode='extended', height=5, style='Media.Treeview')
        for key, label, width, stretch in [('number', '#', 48, False), ('name', 'Tên file', 220, True), ('type', 'Định dạng', 92, False)]:
            self.heading(key, text=label, anchor='w')
            self.column(key, width=width, minwidth=width if not stretch else 100, stretch=stretch, anchor='w')
        self.tag_configure('even', background='#ffffff')
        self.tag_configure('odd', background='#f8f9fd')

    def delete(self, first, last=None):
        if first == 0 and last == 'end':
            children = self.get_children()
            if children:
                super().delete(*children)
        else:
            super().delete(first)

    def insert(self, index, path):
        n = len(self.get_children())
        return super().insert('', index, values=(f'{n+1:02}', Path(path).name, Path(path).suffix[1:].upper()), tags=('even' if n % 2 == 0 else 'odd',))

    def curselection(self):
        selected = set(self.selection())
        return tuple(i for i, item in enumerate(self.get_children()) if item in selected)

    def select_set(self, first, last=None):
        children = self.get_children()
        if children:
            end = len(children)-1 if last == 'end' else first if last is None else last
            self.selection_add(children[first:end+1])

    def size(self):
        return len(self.get_children())

class NavItem(tk.Canvas):
    def __init__(self, parent, title, index, command):
        super().__init__(parent, width=196, height=46, bg=SIDEBAR, highlightthickness=0, cursor='hand2')
        self.title, self.index, self.command = title, index, command
        self.active, self.hover = False, False
        self.bind('<Button-1>', lambda e: command())
        self.bind('<Enter>', lambda e: self.paint_hover(True))
        self.bind('<Leave>', lambda e: self.paint_hover(False))
        self.paint()

    def paint_hover(self, value):
        self.hover = value
        self.paint()

    def paint(self):
        self.delete('all')
        fill = '#303a6c' if self.active else '#202c43' if self.hover else SIDEBAR
        self.create_polygon(12,2,184,2,194,12,194,34,184,44,12,44,2,34,2,12, smooth=True, fill=fill, outline='')
        color = '#ffffff' if self.active else '#a5b1c8'
        x, y = 18, 14
        if self.index == 0:
            self.create_rectangle(x,y,x+18,y+16,outline=color,width=1.5)
            self.create_polygon(x+7,y+4,x+7,y+12,x+13,y+8,fill=color)
        elif self.index == 1:
            for off in (0,7,14):
                self.create_line(x,y+off,x+3,y+off,fill=color,width=2)
                self.create_line(x+7,y+off,x+19,y+off,fill=color,width=1.5)
        elif self.index == 2:
            self.create_rectangle(x,y+5,x+14,y+18,outline=color,width=1.5)
            self.create_line(x+5,y,x+19,y,x+19,y+13,fill=color,width=1.5)
        elif self.index == 3:
            self.create_oval(x,y-1,x+18,y+17,outline=color,width=1.5)
            self.create_line(x+9,y+2,x+9,y+8,x+14,y+8,fill=color,width=1.5)
        else:
            self.create_polygon(x,y+5,x+5,y+5,x+11,y,x+11,y+17,x+5,y+12,x,y+12,outline=color,fill='',width=1.5)
            self.create_arc(x+7,y-1,x+21,y+18,start=300,extent=120,style='arc',outline=color,width=1.5)
        self.create_text(51,23,text=self.title,anchor='w',fill=color,font=('Segoe UI Semibold' if self.active else 'Segoe UI',10))

class FileList(ttk.Frame):
    def __init__(self, parent, title, media=VIDEO, sequence=False):
        super().__init__(parent, style='Card.TFrame', padding=20)
        self.paths, self.media = [], media
        self.sequence = sequence
        self.caption = tk.StringVar(value=title)
        self.title = title
        top = ttk.Frame(self, style='Card.TFrame')
        top.pack(fill='x', pady=(0, 10))
        ttk.Label(top, textvariable=self.caption, style='Card.TLabel').pack(side='left')
        label = 'Thêm video' if media == VIDEO else 'Thêm âm thanh' if media == AUDIO else 'Thêm file'
        ttk.Button(top, text=label, command=self.add).pack(side='right')
        ttk.Button(top, text='+ Thư mục', command=self.folder).pack(side='right', padx=5)
        box = ttk.Frame(self, style='Card.TFrame')
        box.pack(fill='both', expand=True)
        self.list = MediaTable(box)
        bar = ttk.Scrollbar(box, command=self.list.yview)
        bar.pack(side='right', fill='y')
        self.list.configure(yscrollcommand=bar.set)
        self.list.pack(fill='both', expand=True)
        self.empty = tk.Label(self.list, text='Chưa có file\n\nChọn file hoặc thư mục để bắt đầu', bg=PANEL, fg=MUTED, font=('Segoe UI', 11), justify='center')
        self.empty.place(relx=.5, rely=.52, anchor='center')
        self.list.bind('<Delete>', lambda e: self.remove())
        self.list.bind('<Double-1>', self.open)
        self.list.bind('<Control-a>', lambda e: self.list.select_set(0, 'end'))
        bottom = ttk.Frame(self, style='Card.TFrame')
        bottom.pack(side='bottom', fill='x', pady=(10, 0), before=box)
        for text, fn, width in [('↑', lambda: self.move(-1), 3), ('↓', lambda: self.move(1), 3), ('Trộn', self.shuffle, 6), ('Bỏ chọn', self.remove, 8), ('Xóa hết', self.clear, 8)]:
            ttk.Button(bottom, text=text, command=fn, width=width, style='Quiet.TButton').pack(side='left', padx=(0, 5))

    def refresh(self):
        self.list.delete(0, 'end')
        for i, p in enumerate(self.paths):
            self.list.insert('end', p)
        self.caption.set(f'{self.title} · {len(self.paths)}')
        if self.paths:
            self.empty.place_forget()
        else:
            self.empty.place(relx=.5, rely=.52, anchor='center')

    def add_paths(self, paths):
        try:
            additions = []
            for p in paths:
                from_txt = Path(p).suffix.lower() == '.txt'
                entries = read_list(p) if from_txt else [str(Path(p).resolve())]
                for entry in entries:
                    if not Path(entry).is_file():
                        raise ValueError(f'Không tìm thấy: {entry}')
                    if not (from_txt and self.sequence) and Path(entry).suffix.lower() not in self.media:
                        raise ValueError(f'File không được hỗ trợ trong danh sách này: {Path(entry).name}')
                    additions.append((entry, from_txt))
            # A TXT is an ordered playback sequence, including repeated clips.
            # Direct file/folder selection remains an inventory without duplicates.
            for p, from_txt in additions:
                if (from_txt and self.sequence) or p not in self.paths:
                    self.paths.append(p)
            self.refresh()
        except Exception as exc:
            messagebox.showerror('ClipMerge', str(exc))

    def add(self):
        label = 'Video' if self.media == VIDEO else 'Âm thanh' if self.media == AUDIO else 'File hỗ trợ'
        paths = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(), title=f'Thêm {label.lower()}',
            filetypes=[(label, tuple('*'+e for e in sorted(self.media))),
                       ('Danh sách TXT', '*.txt'), ('Tất cả', '*.*')])
        if paths:
            self.add_paths(paths)

    def folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.add_paths(sorted(str(p) for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in self.media))

    def remove(self):
        for i in reversed(self.list.curselection()):
            self.paths.pop(i)
        self.refresh()

    def clear(self):
        self.paths.clear()
        self.refresh()

    def shuffle(self):
        random.shuffle(self.paths)
        self.refresh()

    def move(self, step):
        selected = list(self.list.curselection())
        if not selected or min(selected)+step < 0 or max(selected)+step >= len(self.paths):
            return
        for i in (selected if step < 0 else reversed(selected)):
            self.paths[i], self.paths[i+step] = self.paths[i+step], self.paths[i]
        self.refresh()
        for i in selected:
            self.list.select_set(i+step)

    def open(self, event):
        selected = self.list.curselection()
        if selected:
            os.startfile(self.paths[selected[0]])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ClipMerge')
        self.geometry('1360x900')
        self.minsize(1220, 820)
        self.configure(bg=BG)
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'ClipMerge.ico'
        if icon.exists():
            self.iconbitmap(str(icon))
        if os.name == 'nt':
            self.after(50, self.dark_title)
        self.events = queue.Queue()
        self.busy = False
        self.engine = Engine(self.record_log, lambda n: self.events.put(('progress', n)))
        self.config_path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ClipMerge' / 'settings.json'
        self.logger = logging.getLogger('clipmerge')
        self.log_path = self.config_path.parent / 'logs' / 'clipmerge.log'
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(self.log_path, maxBytes=5_000_000, backupCount=2, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
            self.logger.info('ClipMerge 1.1.3 started')
        except OSError:
            self.log_path = None
        try:
            config = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            config = {}
        self.output = tk.StringVar(value=config.get('output', str(Path.home() / 'Videos' / 'ClipMerge')))
        self.style()
        sidebar = tk.Frame(self, bg=SIDEBAR, width=228)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill='x', padx=20, pady=(28, 38))
        logo = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'ClipMerge.png'
        if logo.exists():
            self.logo_image = tk.PhotoImage(file=str(logo))
            tk.Label(brand, image=self.logo_image, bg=SIDEBAR).pack(side='left', padx=(0, 10))
        tk.Label(brand, text='ClipMerge', fg='white', bg=SIDEBAR, font=('Segoe UI Semibold', 17)).pack(side='left')
        self.navigation = tk.Frame(sidebar, bg=SIDEBAR)
        self.navigation.pack(fill='x', padx=16)
        tk.Label(sidebar, text='v1.1.3', bg=SIDEBAR, fg='#66758f', font=('Segoe UI', 9)).pack(side='bottom', anchor='w', padx=28, pady=24)
        workspace = ttk.Frame(self, padding=(28, 0, 28, 0))
        workspace.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(workspace, padding=(0, 26, 0, 20))
        header.pack(fill='x')
        self.page_title = tk.StringVar(value='Ghép video')
        ttk.Label(header, textvariable=self.page_title, font=('Segoe UI Semibold', 24)).pack(side='left')
        self.state = tk.StringVar(value='Sẵn sàng')
        ttk.Label(header, textvariable=self.state, style='Status.TLabel', padding=(14, 7)).pack(side='right')
        self.tabs = ttk.Notebook(workspace, style='Workspace.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.pages = []
        for title in ['Ghép video', 'Tác vụ', 'Tạo danh sách', 'Thay âm thanh']:
            p = ttk.Frame(self.tabs, padding=(0, 0))
            self.tabs.add(p, text=title)
            self.pages.append(p)
        self.build_merge()
        self.build_tasks()
        self.build_selector()
        self.build_audio()
        self.build_task_creator()
        self.nav_items = []
        for i, tab in enumerate(self.tabs.tabs()):
            item = NavItem(self.navigation, self.tabs.tab(tab, 'text'), i, lambda t=tab: self.tabs.select(t))
            item.pack(fill='x', pady=4)
            self.nav_items.append(item)
        self.tabs.bind('<<NotebookTabChanged>>', self.navigate)
        self.navigate()
        footer = ttk.Frame(workspace, padding=(0, 18, 0, 20))
        footer.pack(side='bottom', fill='x', before=self.tabs)
        line = ttk.Frame(footer)
        line.pack(fill='x', pady=(0, 10))
        ttk.Label(line, text='Lưu tại', foreground=MUTED).pack(side='left', padx=(0, 12))
        ttk.Entry(line, textvariable=self.output).pack(side='left', fill='x', expand=True)
        ttk.Button(line, text='Chọn', command=self.choose_output).pack(side='left', padx=8)
        ttk.Button(line, text='Mở', command=self.open_output).pack(side='left')
        ttk.Button(line, text='Nhật ký', command=lambda: os.startfile(str(self.log_path.parent)), state='normal' if self.log_path else 'disabled').pack(side='left', padx=(8, 0))
        self.progress = ttk.Progressbar(footer, mode='determinate')
        self.progress.pack(fill='x', pady=(0, 8))
        self.logs = tk.Text(footer, height=2, bg=BG, fg=MUTED, bd=0, highlightthickness=0, font=('Segoe UI', 9), padx=0, pady=4, state='disabled')
        self.logs.pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def navigate(self, event=None):
        selected = self.tabs.index(self.tabs.select())
        self.page_title.set(self.tabs.tab(self.tabs.select(), 'text'))
        for i, item in enumerate(self.nav_items):
            item.active = i == selected
            item.paint()

    def record_log(self, message):
        logging.getLogger('clipmerge').info(message)
        self.events.put(('log', message))

    def dark_title(self):
        import ctypes
        enabled = ctypes.c_int(0)
        handle = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(enabled), 4)

    def style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=INK, font=('Segoe UI', 10), borderwidth=0)
        s.configure('TFrame', background=BG)
        s.configure('Card.TFrame', background=PANEL)
        s.configure('Card.TLabel', background=PANEL, font=('Segoe UI Semibold', 11))
        s.configure('TButton', background='#edf0fa', foreground='#45526c', padding=(14, 10), borderwidth=0, focusthickness=0)
        s.map('TButton', background=[('active', '#e0e5f7'), ('disabled', '#edf0f5')], foreground=[('disabled', '#abb3c3')])
        s.configure('Quiet.TButton', background=PANEL, foreground=MUTED, padding=(8, 7))
        s.map('Quiet.TButton', background=[('active', '#edf0fa')], foreground=[('active', ACCENT)])
        s.configure('Accent.TButton', background=ACCENT, foreground='white', font=('Segoe UI Semibold', 10))
        s.map('Accent.TButton', background=[('active', '#4853d1')])
        s.configure('Status.TLabel', background='#e5f4ee', foreground='#2c8466', font=('Segoe UI Semibold', 9))
        s.configure('TEntry', fieldbackground=PANEL, foreground=INK, insertcolor=INK, padding=9)
        s.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=INK, padding=8, arrowsize=12, arrowcolor=MUTED)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', INK)], selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', INK)])
        self.option_add('*TCombobox*Listbox.background', PANEL)
        self.option_add('*TCombobox*Listbox.foreground', INK)
        s.configure('TNotebook', background=BG)
        s.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        s.layout('Workspace.TNotebook.Tab', [])
        s.configure('Workspace.TNotebook', borderwidth=0, tabmargins=0)
        s.configure('Workspace.TNotebook', bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.layout('Workspace.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        s.configure('TNotebook.Tab', background=BG, foreground=MUTED, padding=(22, 12))
        s.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', INK)], padding=[('selected', (22, 12))])
        s.configure('TNotebook.Tab', bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.configure('TEntry', bordercolor='#dfe4ef', lightcolor='#dfe4ef', darkcolor='#dfe4ef')
        s.configure('TCombobox', bordercolor='#dfe4ef', lightcolor='#dfe4ef', darkcolor='#dfe4ef')
        s.map('TEntry', bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])
        s.configure('Media.Treeview', background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=42, borderwidth=0, font=('Segoe UI', 10))
        s.layout('Media.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        s.configure('Media.Treeview.Heading', background='#f2f4fa', foreground=MUTED, padding=(12, 10), relief='flat', font=('Segoe UI', 9))
        s.map('Media.Treeview', background=[('selected', '#e9ecff')], foreground=[('selected', '#4350c5')])
        s.configure('Vertical.TScrollbar', background='#dce2ee', troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED, arrowsize=10)
        s.configure('Horizontal.TProgressbar', bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT)
        s.configure('TCheckbutton', background=BG, foreground=INK, padding=5)
        s.map('TCheckbutton', background=[('active', BG)])
        s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#e5e9f2', thickness=4, borderwidth=0)

    def field(self, parent, label, default, values=None, width=14):
        f = ttk.Frame(parent)
        f.pack(side='left', padx=(0, 14), pady=5)
        ttk.Label(f, text=label, foreground=MUTED).pack(anchor='w', pady=(0, 5))
        v = tk.StringVar(value=default)
        widget = ttk.Combobox(f, textvariable=v, values=values, state='readonly', width=width) if values else ttk.Entry(f, textvariable=v, width=width)
        widget.pack()
        return v

    def actions(self, parent, label, command):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(12, 0))
        ttk.Button(row, text=label, style='Accent.TButton', command=command).pack(side='right')
        ttk.Button(row, text='Dừng', command=self.engine.stop).pack(side='right', padx=8)
        return row

    def reserve_controls(self, parent, expanding):
        children = parent.pack_slaves()
        for child in reversed(children[children.index(expanding)+1:]):
            child.pack_configure(side='bottom', before=expanding)

    def build_merge(self):
        p = self.pages[0]
        self.videos = FileList(p, 'Video', sequence=True)
        self.videos.pack(fill='both', expand=True)
        row = ttk.Frame(p)
        row.pack(fill='x', pady=(10, 0))
        self.encode = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text='Mã hóa lại', variable=self.encode).pack(side='left')
        self.flip, self.noise, self.normalize = tk.BooleanVar(), tk.BooleanVar(), tk.BooleanVar()
        for text, var in [('Lật ngang', self.flip), ('Nhiễu', self.noise), ('Cân bằng âm', self.normalize)]:
            ttk.Checkbutton(row, text=text, variable=var).pack(side='left', padx=10)
        row = ttk.Frame(p)
        row.pack(fill='x')
        self.size = self.field(row, 'Độ phân giải', '1920x1080', ['3840x2160', '2560x1440', '1920x1080', '1280x720', '1080x1920', '720x1280', '1080x1080', '1440x1080'])
        self.fps = self.field(row, 'FPS', '30', ['24', '25', '29.97', '30', '50', '60'], 8)
        self.encoder = self.field(row, 'Bộ mã hóa', 'CPU', ['CPU', 'NVIDIA', 'Intel', 'AMD'], 10)
        self.bitrate = self.field(row, 'Bitrate', '8M', ['2M', '4M', '8M', '12M', '20M', '40M'], 8)
        self.zoom = self.field(row, 'Zoom', '1.0', width=7)
        self.gamma = self.field(row, 'Gamma', '1.0', width=7)
        row = self.actions(p, 'Ghép video', self.merge)
        self.name = self.field(row, 'Tên file', 'video', width=20)
        self.reserve_controls(p, self.videos)

    def options(self):
        return dict(encode=self.encode.get(), size=self.size.get(), fps=self.fps.get(), encoder=self.encoder.get(), bitrate=self.bitrate.get(), zoom=self.zoom.get(), gamma=self.gamma.get(), flip=self.flip.get(), noise=self.noise.get(), normalize=self.normalize.get())

    def build_task_creator(self):
        page = ttk.Frame(self.tabs, padding=(0, 0))
        self.tabs.insert(2, page, text='Tạo tác vụ')
        groups = ttk.Notebook(page)
        groups.pack(fill='both', expand=True)
        self.groups, self.group_counts = [], []
        for i in range(4):
            frame = ttk.Frame(groups, padding=(0, 10))
            groups.add(frame, text=f'Nhóm {i+1}')
            files = FileList(frame, f'Nhóm {i+1}')
            files.pack(fill='both', expand=True)
            row = ttk.Frame(frame)
            row.pack(fill='x')
            self.group_counts.append(self.field(row, 'Số clip mỗi tác vụ', '1', width=16))
            self.groups.append(files)
            self.reserve_controls(frame, files)
        row = ttk.Frame(page)
        row.pack(fill='x')
        self.task_prefix = self.field(row, 'Tên tác vụ', 'task', width=18)
        self.task_start = self.field(row, 'Bắt đầu từ', '1', width=10)
        self.task_amount = self.field(row, 'Số tác vụ', '10', width=10)
        self.task_order = self.field(row, 'Thứ tự', 'Theo nhóm', ['Theo nhóm', 'Xen kẽ'], width=14)
        self.task_random = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text='Ngẫu nhiên', variable=self.task_random).pack(side='left', padx=12, pady=(24, 0))
        self.actions(page, 'Xuất tác vụ', self.create_tasks)
        self.reserve_controls(page, groups)

    def create_tasks(self):
        def run():
            name = self.safe_name(self.task_prefix.get())
            start, amount = int(self.task_start.get()), int(self.task_amount.get())
            if start < 1 or not 1 <= amount <= 10000:
                raise ValueError('Số thứ tự phải lớn hơn 0. Số tác vụ từ 1 đến 10000.')
            sources = []
            for files, count in zip(self.groups, self.group_counts):
                n = int(count.get())
                if n < 0:
                    raise ValueError('Số clip không được âm.')
                if files.paths and n:
                    if n > len(files.paths):
                        raise ValueError(f'{files.title}: không đủ clip.')
                    sources.append((list(files.paths), n))
            if not sources:
                raise ValueError('Thêm clip vào ít nhất một nhóm.')
            out = self.output_dir()
            dests = [out / f'{name}_{i+start:03}.txt' for i in range(amount)]
            if any(p.exists() for p in dests):
                raise ValueError('Tên tác vụ đã tồn tại.')
            plans = []
            for i, dest in enumerate(dests):
                selected = []
                for paths, n in sources:
                    selected.append(random.sample(paths, n) if self.task_random.get() else [paths[(i*n+j) % len(paths)] for j in range(n)])
                if self.task_order.get() == 'Xen kẽ':
                    clips = [group[j] for j in range(max(map(len, selected))) for group in selected if j < len(group)]
                else:
                    clips = [p for group in selected for p in group]
                if len(set(clips)) != len(clips):
                    raise ValueError('Có clip trùng giữa các nhóm. Bỏ clip trùng rồi xuất lại.')
                plans.append((dest, clips))
            for dest, clips in plans:
                write_list(dest, clips)
            self.events.put(('log', f'Đã xuất {amount} tác vụ.'))
        self.guarded(run)

    def build_tasks(self):
        p = self.pages[1]
        self.tasks = FileList(p, 'Tác vụ TXT', {'.txt'})
        # Task files are kept as files here, rather than expanded into their clips.
        def add():
            for path in filedialog.askopenfilenames(filetypes=[('Tác vụ', '*.txt')]):
                if path not in self.tasks.paths:
                    self.tasks.paths.append(path)
            self.tasks.refresh()
        def folder():
            path = filedialog.askdirectory()
            if path:
                self.tasks.paths = sorted(str(f) for f in Path(path).glob('*.txt'))
                self.tasks.refresh()
        self.tasks.add = add
        self.tasks.folder = folder
        # Update callbacks installed by FileList.
        top = self.tasks.winfo_children()[0]
        buttons = [w for w in top.winfo_children() if isinstance(w, ttk.Button)]
        buttons[0].configure(command=add)
        buttons[1].configure(command=folder)
        self.tasks.pack(fill='both', expand=True)
        row = self.actions(p, 'Chạy tất cả', lambda: self.run_tasks(False))
        ttk.Button(row, text='Chạy đã chọn', command=lambda: self.run_tasks(True)).pack(side='right', padx=5)
        ttk.Label(row, text='Dùng thiết lập tại Ghép video', foreground=MUTED).pack(side='left')
        self.reserve_controls(p, self.tasks)

    def build_selector(self):
        p = self.pages[2]
        self.source = FileList(p, 'Nguồn', VIDEO | AUDIO)
        self.source.pack(side='left', fill='both', expand=True, padx=(0, 16))
        right = ttk.Frame(p, width=390)
        right.pack(side='right', fill='both')
        for labels in [[('Số clip', '3-6', 'count'), ('Thời lượng (giây)', '60', 'target')], [('Sai số (giây)', '5', 'tolerance'), ('Số danh sách', '10', 'amount')]]:
            row = ttk.Frame(right)
            row.pack(fill='x')
            for label, value, key in labels:
                setattr(self, key, self.field(row, label, value, width=16))
        self.reuse = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text='Dùng lại giữa các danh sách', variable=self.reuse).pack(anchor='w', pady=10)
        self.selector_name = tk.StringVar(value='task')
        ttk.Entry(right, textvariable=self.selector_name).pack(fill='x', pady=(0, 8))
        self.results = tk.Listbox(right, height=6, bg=PANEL, fg=INK, bd=0, highlightthickness=0, font=('Segoe UI', 10), width=38)
        self.results.pack(fill='both', expand=True)
        self.combinations = []
        self.actions(right, 'Tạo danh sách', self.generate)
        ttk.Button(right, text='Xuất TXT', command=self.export_results).pack(fill='x', pady=(8, 0))
        self.reserve_controls(right, self.results)

    def build_audio(self):
        p = self.pages[3]
        lists = ttk.Frame(p)
        lists.pack(fill='both', expand=True)
        self.audio_videos = FileList(lists, 'Video')
        self.audio_videos.pack(side='left', fill='both', expand=True, padx=(0, 12))
        self.audios = FileList(lists, 'Âm thanh', AUDIO)
        self.audios.pack(side='left', fill='both', expand=True)
        row = self.actions(p, 'Thay âm thanh', self.replace_audio)
        self.match = self.field(row, 'Ghép theo', 'Thứ tự', ['Thứ tự', 'Tên file'], 16)
        self.reserve_controls(p, lists)

    def safe_name(self, value):
        value = value.strip()
        if not value or value in {'.', '..'} or re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith(('.', ' ')) or value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
            raise ValueError('Tên file không hợp lệ.')
        return value

    def output_dir(self):
        value = self.output.get().strip()
        if not value:
            raise ValueError('Chọn thư mục lưu.')
        p = Path(value).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def start(self, fn, action='Xử lý'):
        if self.busy:
            messagebox.showinfo('ClipMerge', 'Đang xử lý. Dừng hoặc chờ hoàn tất.')
            return
        self.busy = True
        self.engine.cancel.clear()
        self.state.set('Đang xử lý')
        self.progress['value'] = 0
        self.record_log(action)
        def worker():
            try:
                fn()
                self.logger.info('%s: hoàn tất', action)
                self.events.put(('done', 'Hoàn tất'))
            except InterruptedError:
                self.logger.info('%s: đã dừng', action)
                self.events.put(('done', 'Đã dừng'))
            except Exception as exc:
                self.logger.exception('%s: thất bại', action)
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('idle', None))
        threading.Thread(target=worker, daemon=True).start()

    def guarded(self, fn):
        try:
            fn()
        except Exception as exc:
            messagebox.showerror('ClipMerge', str(exc))

    def merge(self):
        def prepare():
            paths, options = list(self.videos.paths), self.options()
            dest = self.output_dir() / (self.safe_name(self.name.get()) + '.mp4')
            self.start(lambda: self.engine.merge(paths, dest, options), f'Ghép video · {len(paths)} clip · {dest}')
        self.guarded(prepare)

    def run_tasks(self, selected):
        def prepare():
            paths = [self.tasks.paths[i] for i in self.tasks.list.curselection()] if selected else list(self.tasks.paths)
            if not paths:
                raise ValueError('Chưa chọn tác vụ.')
            out, options = self.output_dir(), self.options()
            jobs = [(read_list(p), out / (self.safe_name(Path(p).stem) + '.mp4')) for p in paths]
            names = [str(dest).casefold() for _, dest in jobs]
            if len(names) != len(set(names)) or any(dest.exists() for _, dest in jobs):
                raise ValueError('Tên file xuất đã tồn tại.')
            def run():
                for clips, dest in jobs:
                    self.engine.log(dest.name)
                    self.engine.merge(clips, dest, options)
            self.start(run, f'Ghép {len(jobs)} tác vụ · {out}')
        self.guarded(prepare)

    def generate(self):
        def prepare():
            parts = self.count.get().split('-')
            bounds = (int(parts[0]), int(parts[-1]))
            paths = list(self.source.paths)
            target, tolerance, amount, reuse = float(self.target.get()), float(self.tolerance.get()), int(self.amount.get()), self.reuse.get()
            def run():
                result = select_lists(paths, bounds, target, tolerance, amount, reuse, cancel=self.engine.cancel, on_probe=lambda i,n: self.events.put(('progress', i/n*100)))
                self.events.put(('results', result))
                self.engine.log(f'Tìm được {len(result)}/{amount} danh sách.')
            self.start(run, 'Tạo danh sách theo thời lượng (chưa ghép video)')
        self.guarded(prepare)

    def export_results(self):
        def run():
            if not self.combinations:
                raise ValueError('Chưa có kết quả.')
            out, name = self.output_dir(), self.safe_name(self.selector_name.get())
            destinations = [out / f'{name}_{i+1:03}.txt' for i in range(len(self.combinations))]
            if any(p.exists() for p in destinations):
                raise ValueError('Tên tác vụ đã tồn tại.')
            for dest, (paths, _) in zip(destinations, self.combinations):
                write_list(dest, paths)
            self.events.put(('log', f'Đã xuất {len(destinations)} tác vụ.'))
        self.guarded(run)

    def replace_audio(self):
        def prepare():
            videos, audios = list(self.audio_videos.paths), list(self.audios.paths)
            if not videos or not audios:
                raise ValueError('Thêm video và âm thanh.')
            if self.match.get() == 'Tên file':
                mapping = {}
                for audio in audios:
                    key = Path(audio).stem.casefold()
                    if key in mapping:
                        raise ValueError('Có nhiều âm thanh trùng tên.')
                    mapping[key] = audio
                pairs = [(v, mapping.get(Path(v).stem.casefold())) for v in videos]
                if any(a is None for _, a in pairs):
                    raise ValueError('Có video chưa khớp tên âm thanh.')
            else:
                if len(videos) != len(audios):
                    raise ValueError('Số video và âm thanh phải bằng nhau.')
                pairs = list(zip(videos, audios))
            out = self.output_dir()
            jobs = [(v, a, out / (Path(v).stem + '_audio.mp4')) for v, a in pairs]
            names = [str(o).casefold() for _, _, o in jobs]
            if len(set(names)) != len(names) or any(o.exists() for _, _, o in jobs):
                raise ValueError('Tên file xuất trùng hoặc đã tồn tại.')
            def run():
                for video, audio, dest in jobs:
                    self.engine.log(Path(video).name)
                    self.engine.replace(video, audio, dest)
            self.start(run, 'Thay âm thanh')
        self.guarded(prepare)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.progress['value'] = value
                elif kind == 'results':
                    self.combinations = value
                    self.results.delete(0, 'end')
                    for i, (paths, seconds) in enumerate(value):
                        self.results.insert('end', f'{i+1:02}   {len(paths)} clip · {seconds:.1f}s')
                elif kind == 'idle':
                    self.busy = False
                else:
                    self.logs.configure(state='normal')
                    self.logs.insert('end', str(value) + '\n')
                    self.logs.see('end')
                    self.logs.configure(state='disabled')
                    if kind in ('done', 'error'):
                        self.state.set(value if kind == 'done' else 'Có lỗi')
                        if kind == 'error':
                            messagebox.showerror('ClipMerge', value)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def choose_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output.set(folder)

    def open_output(self):
        self.guarded(lambda: os.startfile(str(self.output_dir())))

    def close(self):
        if self.busy:
            messagebox.showinfo('ClipMerge', 'Dừng xử lý trước khi đóng.')
            return
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps({'output': self.output.get()}, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass
        self.destroy()

if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ClipMerge.Desktop')
    App().mainloop()
