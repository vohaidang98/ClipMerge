import json
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import random
import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from support_ui import App as BaseApp, FileList as BaseFileList
from engine import Engine, VIDEO, AUDIO, read_list, write_list, probe, clip_duration, select_lists
from hub_utils import seconds, move_tasks, recycle_task
import threading
import licensing
import updater

VERSION='2.1.0'
ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
BLUE='#3599cc';DARK='#2e4053';RED='#e85c48';ORANGE='#f0a313';GREEN='#1db8a2';GRAY='#91a2a4'

class ClipList(BaseFileList):
    def __init__(self,parent,title,media=VIDEO,sequence=False,toolbar=True,audio_controls=False):
        ttk.Frame.__init__(self,parent,padding=3)
        self.paths=[];self.media=media;self.sequence=sequence;self.title=title
        self.caption=tk.StringVar(value=title+' (0)')
        head=ttk.Frame(self);head.pack(fill='x',pady=(0,3))
        ttk.Label(head,textvariable=self.caption).pack(side='left')
        ttk.Button(head,text='+',width=3,command=self.add).pack(side='right')
        ttk.Button(head,text='…',width=3,command=self.folder).pack(side='right',padx=2)
        if toolbar:
            bar=ttk.Frame(self);bar.pack(side='bottom',fill='x',pady=3)
            if audio_controls:
                owner=self.winfo_toplevel();kind='Audio' if media==AUDIO else 'Video'
                for label,fn,color in [(f'Thêm {kind}...',self.add,GRAY),(f'Xóa {kind} đã chọn',self.remove,ORANGE),(f'Clear {kind}',self.clear,RED)]:owner.button(bar,label,fn,color,side='left',fill='x',expand=True,padx=1)
            else:
                for label,fn in [('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),('Bỏ chọn',self.remove),('Clear',self.clear)]:ttk.Button(bar,text=label,command=fn,width=7).pack(side='left',padx=1)
        box=ttk.Frame(self);box.pack(fill='both',expand=True)
        self.list=tk.Listbox(box,height=5,selectmode='extended',exportselection=False,font=('Segoe UI',9),bd=1,relief='solid',highlightthickness=0)
        y=ttk.Scrollbar(box,command=self.list.yview);y.pack(side='right',fill='y')
        x=ttk.Scrollbar(box,orient='horizontal',command=self.list.xview);x.pack(side='bottom',fill='x')
        self.list.configure(yscrollcommand=y.set,xscrollcommand=x.set);self.list.pack(fill='both',expand=True)
        self.list.bind('<Double-1>',lambda e:self.add() if not self.paths else self.open(e))
        self.list.bind('<Delete>',lambda e:self.remove());self.list.bind('<Control-a>',lambda e:self.list.select_set(0,'end'))
        self.list.bind('<Control-Up>',lambda e:self.move(-1));self.list.bind('<Control-Down>',lambda e:self.move(1))
        self.list.bind('<Button-1>',lambda e:setattr(self.winfo_toplevel(),'active_list',self),add='+')
        menu=tk.Menu(self,tearoff=False)
        for label,fn in [('Thêm file...',self.add),('Thêm thư mục...',self.folder),('Mở file',lambda:self.open(None)),('Bỏ chọn',self.remove),('Đảo ngẫu nhiên',self.shuffle)]:menu.add_command(label=label,command=fn)
        self.list.bind('<Button-3>',lambda e:menu.tk_popup(e.x_root,e.y_root))
        self.winfo_toplevel().enable_drop(self.list,self.add_paths)

    def shuffle(self):
        before=self.paths[:]
        if len(before)<2 or all(p==before[0] for p in before):return
        random.shuffle(self.paths)
        # A random permutation can equal its input; every click must change it.
        if self.paths==before:self.paths[:]=before[1:]+before[:1]
        self.refresh()

    def refresh(self):
        self.list.delete(0,'end')
        for p in self.paths:self.list.insert('end',Path(p).name)
        self.caption.set(f'{self.title} ({len(self.paths)})')

class App(BaseApp):
    def __init__(self):
        tk.Tk.__init__(self)
        self.title(f'ClipMerge — v{VERSION}');self.geometry(f'{min(940,self.winfo_screenwidth()-60)}x{min(800,self.winfo_screenheight()-100)}');self.minsize(790,660)
        if (ASSETS/'ClipMerge.ico').exists():self.iconbitmap(str(ASSETS/'ClipMerge.ico'))
        self.events=queue.Queue();self.busy=False;self.active_list=None
        self.task_paths=[];self.task_counts={};self.task_states={};self.last_move=None;self.used_selector=set()
        self.config_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ClipMerge/settings.json'
        try:self.saved=json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.saved={}
        self.logger=logging.getLogger('clipmerge');self.logger.setLevel(logging.INFO)
        self.log_path=self.config_path.parent/'logs/clipmerge.log'
        try:
            self.log_path.parent.mkdir(parents=True,exist_ok=True)
            handler=RotatingFileHandler(self.log_path,maxBytes=5_000_000,backupCount=2,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));self.logger.addHandler(handler)
        except OSError:self.log_path=None
        self.logger.info('ClipMerge %s started',VERSION)
        self.engine=Engine(self.record_log,lambda n:self.events.put(('progress',n)),lambda stage,i,n:self.events.put(('phase',(self.engine.context,stage,i,n))))
        self.state=tk.StringVar(value='Sẵn sàng');self.output=tk.StringVar(value=self.saved.get('output',str(Path.home()/'Videos/ClipMerge')))
        self.dnd_available=False
        try:self.tk.call('lappend','auto_path',str(ASSETS/'tkdnd'));self.tk.call('package','require','tkdnd');self.dnd_available=True
        except tk.TclError:self.logger.warning('TkDND unavailable',exc_info=True)
        self.style();self.make_variables();self.make_menu()
        footer=ttk.Frame(self,padding=(6,3));footer.pack(side='bottom',fill='x')
        self.progress=ttk.Progressbar(footer);self.progress.pack(fill='x',pady=2)
        ttk.Label(footer,textvariable=self.state).pack(anchor='w')
        self.log_frame=ttk.Frame(footer)
        self.logs=tk.Text(self.log_frame,height=3,font=('Consolas',9),state='disabled',bd=1,relief='solid',highlightthickness=0);self.logs.pack(fill='x')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=5,pady=2)
        self.pages=[]
        for name in ['MERGE HUB','TASK BUILDER','MERGE LITE','AUDIO REPLACE','VIDEO SELECTOR']:
            p=ttk.Frame(self.tabs,padding=5);self.tabs.add(p,text=name);self.pages.append(p)
        self.build_hub();self.build_builder();self.build_lite();self.build_audio();self.build_selector()
        self.restore_controls()
        self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
        self.updating=False;self.refresh_license();self.after(3000,lambda:self.check_update(False))
        if not licensing.is_activated():self.withdraw();self.after(100,lambda:self.ask_activation(required=True))

    def style(self,dark=False):
        s=ttk.Style(self);s.theme_use('clam');bg='#232b36' if dark else '#fff';fg='#edf1f6' if dark else '#252b35'
        self.configure(bg=bg);s.configure('.',font=('Segoe UI',9),background=bg,foreground=fg)
        for name in ['TFrame','TLabel','TCheckbutton','TLabelframe','TLabelframe.Label']:s.configure(name,background=bg)
        s.configure('TButton',padding=(4,3),background='#edf1f4',foreground='#2c3e50',borderwidth=1)
        s.map('TButton',background=[('active','#d9e8f3')]);s.map('TCheckbutton',background=[('active',bg)])
        s.configure('TNotebook',background=bg,borderwidth=0);s.configure('TNotebook.Tab',padding=(8,5))
        s.map('TNotebook.Tab',background=[('selected',bg)])
        field='#303b49' if dark else '#fff'
        for name in ['TEntry','TCombobox']:s.configure(name,fieldbackground=field,foreground=fg,padding=3)
        s.map('TCombobox',fieldbackground=[('readonly',field)],foreground=[('readonly',fg)])
        s.configure('Treeview',rowheight=24,background=field,fieldbackground=field,foreground=fg)
        s.map('Treeview',background=[('selected','#dbeaf6')],foreground=[('selected','#1c334b')]);s.configure('Treeview.Heading',padding=4)
        s.configure('Horizontal.TProgressbar',background=BLUE,troughcolor='#e9edf1',thickness=4)

    def button(self,p,text,command,color=DARK,**pack):
        w=tk.Button(p,text=text,command=command,bg=color,fg='white',activebackground=color,activeforeground='white',font=('Segoe UI',9),relief='flat',bd=0,highlightthickness=0,pady=2)
        w.pack(**pack);return w

    def make_variables(self):
        defaults=dict(encode=True,gpu=False,gpu_mode='cuda',cleanup=True,at_task=False,mute=False,subfolder=False,timeline=False,delete_task=False,normalize=False,size='1920x1080',fps='30',bitrate='4M',ratio='16/9',preset='1080p (16:9)',scale='Letterbox',abitrate='192k',asample='48000',preview_start='00:00',preview_length='10',zoom_on=False,zoom='113',flip=False,flip_skip='',gamma_on=False,gamma='1.2',noise_on=False,noise='3',skip='',target_db='-1.0')
        self.vars={};saved=self.saved.get('hub',{})
        for key,default in defaults.items():self.vars[key]=tk.BooleanVar(value=saved.get(key,default)) if isinstance(default,bool) else tk.StringVar(value=str(saved.get(key,default)))
        self.visible_tabs={i:tk.BooleanVar(value=self.saved.get('visible_tabs',{}).get(str(i),True)) for i in (2,3,4)}

    def make_menu(self):
        menu=tk.Menu(self);self.configure(menu=menu)
        f=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Tệp',menu=f)
        for label,fn in [('Thêm Task TXT...',self.add_task_files),('Thêm thư mục Task...',self.add_task_folder),('Thêm video vào danh sách đang chọn...',lambda:self.active_list.add() if self.active_list else self.lite_lists[0].add()),('Chọn thư mục lưu...',self.choose_output),('Nhật ký',self.open_logs),('Thoát',self.close)]:f.add_command(label=label,command=fn)
        h=tk.Menu(menu,tearoff=False);menu.add_cascade(label='MERGE HUB',menu=h)
        for label,fn in [('Ghép tất cả',lambda:self.run_tasks(False)),('Ghép Task đã chọn',lambda:self.run_tasks(True)),('Preview',self.preview),('Chọn tất cả',self.select_all_tasks),('Dừng ghép',self.engine.stop)]:h.add_command(label=label,command=fn)
        b=tk.Menu(menu,tearoff=False);menu.add_cascade(label='TASK BUILDER',menu=b);b.add_command(label='Mở Task Builder',command=lambda:self.tabs.select(1));b.add_command(label='Xuất TXT',command=self.create_tasks)
        d=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Hiển thị',menu=d);d.add_command(label='Hiện / ẩn nhật ký',command=self.toggle_log);d.add_command(label='Rút gọn / Mở rộng',command=self.toggle_controls)
        for index,title in [(2,'MERGE LITE'),(3,'AUDIO REPLACE'),(4,'VIDEO SELECTOR')]:d.add_checkbutton(label=title,variable=self.visible_tabs[index],command=lambda i=index:self.toggle_tab(i))
        t=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Giao diện',menu=t);t.add_command(label='Sáng',command=lambda:self.style(False));t.add_command(label='Tối',command=lambda:self.style(True))
        a=tk.Menu(menu,tearoff=False);menu.add_cascade(label='Trợ giúp',menu=a)
        a.add_command(label='Cách dùng',command=lambda:messagebox.showinfo('ClipMerge','MERGE HUB: nhận TXT, ghép tất cả hoặc Task đã chọn.\nTASK BUILDER: 4 nhóm V0–V3; Random riêng từng nhóm; Mixed xen kẽ V2/V3.\nMERGE LITE: mỗi cột có clip sẽ xuất thành một video.\nAUDIO REPLACE: ghép theo tên hoặc thứ tự.\nVIDEO SELECTOR: tìm tổ hợp clip theo số lượng/thời lượng.\n\nDấu + thêm file; dấu … chọn thư mục. Có thể kéo thả file/thư mục.\nStart/Length chỉ dành cho Preview trên dòng thời gian Task.\nZoom: 113 hoặc 113 | +1,3,-3.\nSkip: +n bỏ n clip đầu; -n bỏ n clip cuối; 3 bỏ clip thứ 3.\nChuột phải Target để đổi dBFS.\nXóa Task đưa TXT vào Thùng rác, không xóa video.'))
        a.add_command(label=f'ClipMerge {VERSION}',command=lambda:messagebox.showinfo('ClipMerge',f'ClipMerge {VERSION}\nFFmpeg GPLv3\n{self.log_path}'))
        a.add_command(label='Kiểm tra cập nhật...',command=lambda:self.check_update(True))
        a.add_command(label='Kích hoạt...',command=self.ask_activation)

    def enable_drop(self,w,callback):
        if not self.dnd_available:return
        self.tk.call('tkdnd::drop_target','register',str(w),'DND_Files')
        def drop(data):
            paths=[]
            for value in self.tk.splitlist(data):
                p=Path(value)
                if p.is_dir():paths.extend(str(f) for f in sorted(p.iterdir()) if f.is_file())
                else:paths.append(value)
            callback(paths);return 'copy'
        self.tk.call('bind',str(w),'<<Drop:DND_Files>>',self.register(drop)+' %D')

    def check(self,p,key,text,row,col):ttk.Checkbutton(p,text=text,variable=self.vars[key]).grid(row=row,column=col,sticky='w',padx=4,pady=1)

    def field_grid(self,p,label,key,row,col,values=None,callback=None):
        f=ttk.Frame(p);f.grid(row=row,column=col,sticky='ew',padx=3,pady=4)
        if label:ttk.Label(f,text=label).pack(side='left',padx=(0,4))
        w=ttk.Combobox(f,textvariable=self.vars[key],values=values,width=9) if values else ttk.Entry(f,textvariable=self.vars[key],width=9)
        w.pack(side='left',fill='x',expand=True)
        if callback:w.bind('<<ComboboxSelected>>',callback)
        return w

    def build_hub(self):
        p=self.pages[0];self.controls=ttk.Frame(p);self.controls.pack(fill='x')
        row=ttk.Frame(self.controls);row.pack(fill='x')
        left=ttk.LabelFrame(row,text='Tùy chọn Ghép chậm',padding=4);left.pack(side='left',fill='both',expand=True,padx=(0,5))
        right=ttk.LabelFrame(row,text='Tùy chọn khác',padding=4);right.pack(side='left',fill='both',expand=True)
        for r,key,label in [(0,'encode','Ghép chậm (Re-encode)'),(1,'gpu','Dùng GPU'),(2,'cleanup','Tự động dọn Temp')]:self.check(left,key,label,r,0)
        ttk.Label(left,text='GPU Mode:').grid(row=1,column=1,padx=3)
        ttk.Combobox(left,textvariable=self.vars['gpu_mode'],values=['cuda','nvdec','qsv','dxva2','CPU + NVIDIA','CPU + AMD','CPU + Intel','normal'],state='readonly',width=13).grid(row=1,column=2,padx=3)
        for r,c,key,label in [(0,0,'at_task','Xuất tại Thư Mục Task'),(0,1,'mute','Tắt Âm thanh'),(1,0,'subfolder','Tạo Thư mục con'),(1,1,'timeline','Xuất Timeline'),(2,0,'delete_task','Tự động xóa Task(.txt)'),(2,1,'normalize','Normalize Audio')]:self.check(right,key,label,r,c)
        self.target_label=ttk.Label(right,text='→ '+self.vars['target_db'].get()+' dBFS',foreground='#888');self.target_label.grid(row=2,column=2,sticky='w');self.target_label.bind('<Button-3>',lambda e:self.change_target())
        cfg=ttk.LabelFrame(self.controls,text='Cấu hình Ghép chậm',padding=4);cfg.pack(fill='x',pady=5)
        for c in range(5):cfg.columnconfigure(c,weight=1)
        for c,(label,key,vals) in enumerate([('WxH:','size',['1920x1080','1280x720','3840x2160','1080x1920','1080x1080']),('FPS:','fps',['24','25','29.97','30','50','60']),('V_bitrate:','bitrate',['2M','4M','8M','12M'])]):self.field_grid(cfg,label,key,0,c,vals)
        self.field_grid(cfg,'Preset:','ratio',0,3,['16/9','9/16','1/1','4/3'],self.preset_change)
        self.field_grid(cfg,'','preset',0,4,['4K','2K','1080p','720p','480p'],self.preset_change)
        for c,(label,key,vals) in enumerate([('Scale:','scale',['Letterbox','Crop','Stretch']),('A_bitrate:','abitrate',['96k','128k','192k','256k','320k']),('A_sample:','asample',['22050','44100','48000']),('Start:','preview_start',None),('Length:','preview_length',None)]):self.field_grid(cfg,label,key,1,c,vals)
        for c,flag,key,label in [(0,'zoom_on','zoom','Zoom'),(1,'flip','flip_skip','H_flip'),(2,'gamma_on','gamma','Gamma'),(3,'noise_on','noise','Noise')]:
            f=ttk.Frame(cfg);f.grid(row=2,column=c,sticky='ew',padx=2,pady=4);ttk.Checkbutton(f,text=label,variable=self.vars[flag]).pack(side='left');ttk.Entry(f,textvariable=self.vars[key],width=8).pack(side='left',fill='x',expand=True)
        self.field_grid(cfg,'Skip:','skip',2,4)
        self.hub_bottom=ttk.Frame(p);self.hub_bottom.pack(side='bottom',fill='x',pady=4)
        self.count_label=tk.StringVar();ttk.Label(self.hub_bottom,textvariable=self.count_label).pack(anchor='w');ttk.Label(self.hub_bottom,textvariable=self.output).pack(anchor='w')
        self.task_area=ttk.LabelFrame(p,text='Tasklist (.txt)',padding=5);self.task_area.pack(fill='both',expand=True)
        actions=ttk.Frame(self.task_area);actions.pack(side='right',fill='y',padx=(8,0))
        treebox=ttk.Frame(self.task_area);treebox.pack(fill='both',expand=True)
        self.task_tree=ttk.Treeview(treebox,columns=('name','count','status'),show='headings',height=6,selectmode='extended')
        for key,label,width in [('name','Task',330),('count','Clip',40),('status','Trạng thái',130)]:self.task_tree.heading(key,text=label);self.task_tree.column(key,width=width,minwidth=35,stretch=key!='count')
        y=ttk.Scrollbar(treebox,command=self.task_tree.yview);y.pack(side='right',fill='y');self.task_tree.configure(yscrollcommand=y.set);self.task_tree.pack(fill='both',expand=True)
        self.task_tree.bind('<Double-1>',lambda e:self.add_task_files());self.task_tree.bind('<Delete>',lambda e:self.remove_tasks());self.task_tree.bind('<Control-a>',lambda e:self.select_all_tasks());self.task_tree.bind('<<TreeviewSelect>>',lambda e:self.update_task_count())
        self.enable_drop(self.task_tree,self.add_task_paths)
        specs=[('<<< Ghép >>>',lambda:self.run_tasks(False),DARK),('__Ghép Tasklist__',lambda:self.run_tasks(True),DARK),('Chọn thư mục lưu',self.choose_output,BLUE),('Mở thư mục lưu',self.open_output,BLUE),('preview',self.preview,GREEN),('Làm trống Tasklist',self.clear_tasks,ORANGE),('Loại trừ khỏi Tasklist',self.remove_tasks,ORANGE),('Dừng ghép',self.engine.stop,RED),('Di chuyển Tasks tới...',lambda:self.move_selected(True),GRAY),('Di chuyển Tasks',lambda:self.move_selected(False),GRAY),('*** Xóa Tasks ***',self.delete_selected,GRAY),('Dọn thư mục Temp',self.clean_temp,GRAY),('Rút gọn',self.toggle_controls,DARK)]
        for label,fn,color in specs:self.button(actions,label,fn,color,fill='x',pady=0).configure(pady=0)
        self.refresh_tasks()

    def preset_change(self,event=None):
        height=next((n for text,n in [('4K',2160),('2K',1440),('1080',1080),('720',720),('480',480)] if text in self.vars['preset'].get()),1080)
        ratio=self.vars['ratio'].get();w,h={'16/9':(round(height*16/9/2)*2,height),'9/16':(height,round(height*16/9/2)*2),'1/1':(height,height),'4/3':(round(height*4/3/2)*2,height)}.get(ratio,(1920,1080));self.vars['size'].set(f'{w}x{h}')

    def change_target(self):
        value=simpledialog.askfloat('Normalize Audio','Target dBFS (-60 đến 0):',initialvalue=float(self.vars['target_db'].get()),minvalue=-60,maxvalue=0,parent=self)
        if value is not None:self.vars['target_db'].set(f'{value:.1f}');self.target_label.configure(text=f'→ Target: {value:.1f} dBFS')

    def options(self,lite=False):
        v={k:x.get() for k,x in self.vars.items()}
        if lite:v.update({k:x.get() for k,x in self.lite_vars.items()})
        gpu={'cuda':'NVIDIA','nvdec':'NVIDIA','qsv':'Intel','dxva2':'AMD','CPU + NVIDIA':'NVIDIA','CPU + AMD':'AMD','CPU + Intel':'Intel','normal':'CPU'}
        result=dict(encode=v['encode'],encoder=gpu.get(v['gpu_mode'],'CPU') if v['gpu'] else 'CPU',cleanup=v['cleanup'],size=v['size'],fps=v['fps'],bitrate=v['bitrate'],scale=v['scale'],abitrate=v['abitrate'],asample=v['asample'],zoom=v['zoom'] if v['zoom_on'] else '1',flip=v['flip'],flip_skip=v['flip_skip'],gamma=v['gamma'] if v['gamma_on'] else '1',noise=v['noise_on'],noise_value=v['noise'],skip=v['skip'],mute=v['mute'],normalize=v['normalize'],normalize_mode='peak',target_db=v['target_db'],timeline=v['timeline'])
        if v['gpu'] and v['gpu_mode'] in ('cuda','nvdec','qsv','dxva2'):result['hwaccel']={'cuda':'cuda','nvdec':'cuda','qsv':'qsv','dxva2':'dxva2'}[v['gpu_mode']]
        if lite:result.update(zoom='1',flip=False,gamma='1',noise=False,normalize=False,mute=False,timeline=False,skip='',copy_sources=self.lite_copy.get())
        elif any(v[k] for k in ['zoom_on','flip','gamma_on','noise_on','normalize']):result['encode']=True
        return result

    def idle_required(self):
        if self.busy:raise ValueError('Đang xử lý. Dừng hoặc chờ hoàn tất trước khi thay đổi Tasklist.')

    def add_task_files(self):self.add_task_paths(filedialog.askopenfilenames(parent=self,title='Thêm Task TXT',filetypes=[('Task TXT','*.txt')]))
    def add_task_folder(self):
        folder=filedialog.askdirectory(parent=self)
        if folder:self.add_task_paths([str(p) for p in sorted(Path(folder).glob('*.txt'))])

    def add_task_paths(self,paths):
        def run():
            self.idle_required();pending=[]
            for value in paths:
                p=Path(value);entries=sorted(p.glob('*.txt')) if p.is_dir() else [p]
                for item in entries:
                    if item.suffix.lower()!='.txt':raise ValueError('MERGE HUB nhận TXT. Thêm video trực tiếp tại MERGE LITE.')
                    key=str(item.resolve());pending.append((key,len(read_list(key))))
            for key,count in pending:
                if key not in self.task_paths:self.task_paths.append(key)
                self.task_counts[key]=count;self.task_states[key]='Chờ ghép'
            self.refresh_tasks()
        self.guarded(run)

    def refresh_tasks(self):
        children=self.task_tree.get_children()
        if children:self.task_tree.delete(*children)
        for i,path in enumerate(self.task_paths):self.task_tree.insert('','end',iid=str(i),values=(Path(path).name,self.task_counts.get(path,'?'),self.task_states.get(path,'Chờ ghép')))
        if not self.task_paths:self.task_tree.insert('','end',iid='hint',values=('<< Nhấp đúp hoặc kéo thả file .txt vào đây >>','',''))
        self.update_task_count()

    def update_task_count(self):self.count_label.set(f'Số Task: {len([i for i in self.task_tree.selection() if i!="hint"])} / {len(self.task_paths)}')
    def select_all_tasks(self):self.task_tree.selection_set([i for i in self.task_tree.get_children() if i!='hint'])
    def selected_paths(self):return [self.task_paths[int(i)] for i in self.task_tree.selection() if i!='hint']
    def clear_tasks(self):
        def run():self.idle_required();self.task_paths.clear();self.refresh_tasks()
        self.guarded(run)
    def remove_tasks(self):
        def run():
            self.idle_required();selected=set(self.selected_paths());self.task_paths=[p for p in self.task_paths if p not in selected];self.refresh_tasks()
        self.guarded(run)

    def move_selected(self,choose):
        def run():
            self.idle_required();paths=self.selected_paths()
            if not paths:raise ValueError('Chọn Task cần di chuyển.')
            target=filedialog.askdirectory(parent=self) if choose or not self.last_move else self.last_move
            if not target:return
            result=move_tasks(paths,target);self.last_move=target
            for old,new in result.items():self.task_paths[self.task_paths.index(old)]=new;self.task_counts[new]=self.task_counts.pop(old)
            self.refresh_tasks()
        self.guarded(run)

    def delete_selected(self):
        def run():
            self.idle_required();paths=self.selected_paths()
            if paths and messagebox.askyesno('Xóa Task',f'Đưa {len(paths)} file TXT đã chọn vào Thùng rác?',parent=self):
                for p in paths:recycle_task(p);self.task_paths.remove(p)
                self.refresh_tasks()
        self.guarded(run)

    def run_tasks(self,selected=False):
        def prepare():
            self.idle_required();paths=self.selected_paths() if selected else list(self.task_paths)
            if not paths:raise ValueError('Thêm hoặc chọn Task TXT trước khi ghép.')
            opts=self.options();jobs=[]
            for path in paths:
                clips=read_list(path);folder=Path(path).parent if self.vars['at_task'].get() else self.output_dir()
                if self.vars['subfolder'].get():folder=folder/Path(path).stem
                dest=folder/(Path(path).stem+'.mp4')
                if dest.exists():raise ValueError(f'File đã tồn tại: {dest}')
                jobs.append((path,clips,dest))
            names=[str(d).casefold() for _,_,d in jobs]
            if len(names)!=len(set(names)):raise ValueError('Các Task trùng tên file xuất.')
            delete=self.vars['delete_task'].get()
            if delete and not messagebox.askyesno('Tự động xóa Task','Đưa TXT vào Thùng rác sau khi ghép thành công?',parent=self):return
            def worker():
                for n,(path,clips,dest) in enumerate(jobs,1):
                    self.engine.context=path;self.events.put(('task_status',(path,f'Task {n}/{len(jobs)}')))
                    try:self.engine.merge(clips,dest,opts)
                    except Exception:self.events.put(('task_status',(path,'Đã dừng' if self.engine.cancel.is_set() else 'Lỗi')));raise
                    if delete:recycle_task(path)
                    self.events.put(('task_status',(path,'Hoàn tất')))
            self.start(worker,f'Ghép {len(jobs)} Task')
        self.guarded(prepare)

    def preview(self):
        def prepare():
            self.idle_required();selected=self.selected_paths();path=selected[0] if selected else self.task_paths[0] if self.task_paths else None
            if not path:raise ValueError('Chọn một Task để preview.')
            paths=read_list(path);start=seconds(self.vars['preview_start'].get());length=seconds(self.vars['preview_length'].get())
            if length<=0:raise ValueError('Length phải lớn hơn 0.')
            opts=self.options();opts.update(encode=True,timeline=False,cleanup=True)
            def worker():
                self.engine.context='Preview · '+Path(path).name;chosen=[];ranges=[];indices=[];offset=0
                for i,p in enumerate(paths):
                    if self.engine.cancel.is_set():raise InterruptedError('Đã dừng.')
                    d=clip_duration(probe(p));lo=max(start,offset);hi=min(start+length,offset+d)
                    if hi>lo:chosen.append(p);ranges.append((lo-offset,hi-lo));indices.append(i)
                    offset+=d
                    if offset>=start+length:break
                if not chosen:raise ValueError('Start nằm ngoài thời lượng Task.')
                opts.update(_preview_ranges=ranges,_source_indices=indices,_filter_total=len(paths))
                folder=self.config_path.parent/'previews';folder.mkdir(parents=True,exist_ok=True)
                dest=Path(tempfile.mkdtemp(prefix='preview-',dir=folder))/'preview.mp4'
                self.engine.merge(chosen,dest,opts);self.events.put(('open',str(dest)))
            self.start(worker,f'Preview · {Path(path).name}')
        self.guarded(prepare)

    def clean_temp(self):
        def run():
            self.idle_required();paths=[]
            for value in self.engine.temp_history:
                p=Path(value).resolve()
                if p.exists() and p.name.startswith('.clipmerge-') and (p/'.clipmerge-owner').is_file() and (p/'.clipmerge-owner').read_text()=='ClipMerge':paths.append(p)
            if not paths:messagebox.showinfo('Temp','Không có Temp được giữ lại trong phiên này.');return
            if messagebox.askyesno('Dọn Temp',f'Xóa {len(paths)} thư mục Temp ClipMerge của phiên này?',parent=self):
                for p in paths:shutil.rmtree(p)
        self.guarded(run)

    def shuffle_lists(self,lists):
        for group in lists:group.shuffle()

    def build_builder(self):
        p=self.pages[1]
        out=ttk.LabelFrame(p,text='Tùy chọn xuất Task',padding=5);out.pack(side='bottom',fill='x',pady=6)
        self.task_prefix=tk.StringVar();self.task_start=tk.StringVar(value='1');self.task_amount=tk.StringVar(value='1')
        for label,var,width in [('Tên Task:',self.task_prefix,20),('Số bắt đầu:',self.task_start,6),('Số lượng:',self.task_amount,6)]:ttk.Label(out,text=label).pack(side='left',padx=4);ttk.Entry(out,textvariable=var,width=width).pack(side='left',padx=3)
        self.button(out,'Xuất TXT',self.create_tasks,side='right',padx=4)
        actions=ttk.LabelFrame(p,text='Điều khiển danh sách',padding=5);actions.pack(side='bottom',fill='x',pady=5)
        self.button(actions,'Xóa tất cả',lambda:[g.clear() for g in self.groups],ORANGE,side='left',padx=3)
        self.button(actions,'Xóa items chọn',lambda:[g.remove() for g in self.groups],ORANGE,side='left',padx=3)
        self.button(actions,'Đảo ngẫu nhiên',lambda:self.shuffle_lists(self.groups),GRAY,side='left',padx=3)
        self.mixed=tk.BooleanVar();ttk.Checkbutton(actions,text='Mixed V2 + V3',variable=self.mixed).pack(side='right',padx=4)
        columns=ttk.Frame(p);columns.pack(fill='both',expand=True)
        self.groups=[];self.group_counts=[];self.group_random=[]
        for i in range(4):
            col=ttk.Frame(columns);col.pack(side='left',fill='both',expand=True,padx=2)
            controls=ttk.Frame(col);controls.pack(side='bottom',fill='x',pady=4)
            row=ttk.Frame(controls);row.pack(fill='x');ttk.Label(row,text='Số lượng:').pack(side='left')
            flag=tk.BooleanVar(value=i>=2);self.group_random.append(flag);ttk.Checkbutton(row,text='Random',variable=flag).pack(side='right')
            count=tk.StringVar(value='0');self.group_counts.append(count);ttk.Spinbox(controls,from_=0,to=9999,textvariable=count,width=7).pack(fill='x',pady=4)
            files=ClipList(col,f'V{i}',toolbar=False);files.pack(fill='both',expand=True);self.groups.append(files)
            self.button(controls,'Clear',files.clear,RED,fill='x')

    def create_tasks(self):
        def run():
            self.idle_required();name=self.safe_name(self.task_prefix.get());start=int(self.task_start.get());amount=int(self.task_amount.get())
            if start<1 or not 1<=amount<=10000:raise ValueError('Chỉ số và số Task không hợp lệ.')
            groups=[]
            for i,(files,count,flag) in enumerate(zip(self.groups,self.group_counts,self.group_random)):
                n=int(count.get())
                if n<0 or n>len(files.paths):raise ValueError(f'V{i} không đủ clip.')
                if n:groups.append((i,list(files.paths),n,flag.get()))
            if not groups:raise ValueError('Chọn số lượng clip cần lấy ở từng nhóm.')
            out=self.output_dir();plans=[]
            for task in range(amount):
                picked={}
                for i,paths,n,shuffle in groups:picked[i]=random.sample(paths,n) if shuffle else [paths[(task*n+j)%len(paths)] for j in range(n)]
                if self.mixed.get() and 2 in picked and 3 in picked:
                    a,b=picked[2],picked.pop(3);picked[2]=[g[j] for j in range(max(len(a),len(b))) for g in (a,b) if j<len(g)]
                clips=[p for i in sorted(picked) for p in picked[i]];dest=out/f'{name}_{task+start:03}.txt'
                if dest.exists():raise ValueError(f'File đã tồn tại: {dest.name}')
                plans.append((dest,clips))
            for dest,clips in plans:write_list(dest,clips)
            self.record_log(f'Đã xuất {len(plans)} Task TXT · {out}')
        self.guarded(run)

    def build_lite(self):
        p=self.pages[2];bottom=ttk.Frame(p);bottom.pack(side='bottom',fill='x',pady=6)
        actions=ttk.LabelFrame(bottom,text='Thao tác',padding=5);actions.pack(side='right',fill='y',padx=(6,0))
        cfg=ttk.LabelFrame(bottom,text='Tùy chọn',padding=5);cfg.pack(fill='both',expand=True)
        self.lite_vars={k:(tk.BooleanVar(value=self.vars[k].get()) if isinstance(self.vars[k],tk.BooleanVar) else tk.StringVar(value=self.vars[k].get())) for k in ['encode','gpu','gpu_mode','size','bitrate','fps','asample','abitrate','scale']}
        for key,value in dict(size='1280x720',bitrate='2M',fps='29.97',asample='44100',abitrate='128k',scale='Default').items():self.lite_vars[key].set(value)
        self.lite_copy=tk.BooleanVar();row=ttk.Frame(cfg);row.pack(fill='x')
        ttk.Checkbutton(row,text='Ghép chậm (Re-encode)',variable=self.lite_vars['encode']).pack(side='left');ttk.Checkbutton(row,text='Sao chép tạm (SSD)',variable=self.lite_copy).pack(side='right')
        row=ttk.Frame(cfg);row.pack(fill='x',pady=4);ttk.Checkbutton(row,text='Dùng GPU',variable=self.lite_vars['gpu']).pack(side='left')
        ttk.Combobox(row,textvariable=self.lite_vars['gpu_mode'],values=['cuda','nvdec','qsv','dxva2','CPU + AMD','CPU + NVIDIA','CPU + Intel','normal'],width=12,state='readonly').pack(side='left',padx=4)
        ttk.Label(row,text='Preset:').pack(side='left',padx=4)
        self.lite_ratio=tk.StringVar(value='16/9');self.lite_preset=tk.StringVar(value='Tùy chỉnh')
        for variable,values in [(self.lite_ratio,['16/9','9/16','1/1','4/3']),(self.lite_preset,['Tùy chỉnh','4K','2K','1080p','720p','480p'])]:
            combo=ttk.Combobox(row,textvariable=variable,values=values,width=10,state='readonly');combo.pack(side='left',padx=3);combo.bind('<<ComboboxSelected>>',self.lite_preset_change)
        for specs in [[('W x H:','size',['1280x720','1920x1080','1080x1920','1080x1080']),('V_bitrate:','bitrate',['2M','4M','8M']),('FPS:','fps',['24','25','29.97','30','60'])],[('A_sample:','asample',['44100','48000']),('A_bitrate:','abitrate',['128k','192k','256k']),('Scale:','scale',['Default','Letterbox','Crop','Stretch'])]]:
            row=ttk.Frame(cfg);row.pack(fill='x',pady=3)
            for label,key,values in specs:ttk.Label(row,text=label).pack(side='left',padx=3);ttk.Combobox(row,textvariable=self.lite_vars[key],values=values,width=10).pack(side='left',padx=2)
        row=ttk.Frame(cfg);row.pack(fill='x',pady=6);ttk.Label(row,text='Tên:').pack(side='left');self.lite_name=tk.StringVar(value='Output');ttk.Entry(row,textvariable=self.lite_name,width=20).pack(side='left',padx=5)
        ttk.Label(row,text='Bắt đầu #:').pack(side='left');self.lite_start=tk.StringVar(value='1');ttk.Spinbox(row,from_=1,to=99999,textvariable=self.lite_start,width=6).pack(side='left',padx=5)
        for text,fn,color in [('Chọn thư mục lưu',self.choose_output,BLUE),('Xóa tất cả',lambda:[g.clear() for g in self.lite_lists],ORANGE),('Xóa đã chọn',lambda:[g.remove() for g in self.lite_lists],ORANGE),('Đảo ngẫu nhiên',lambda:self.shuffle_lists(self.lite_lists),GRAY),('Ghép video',self.merge_lite,DARK),('Dừng ghép',self.engine.stop,RED)]:self.button(actions,text,fn,color,fill='x',pady=3)
        ttk.Label(p,textvariable=self.output).pack(side='bottom',anchor='w')
        columns=ttk.Frame(p);columns.pack(fill='both',expand=True);self.lite_lists=[]
        for i in range(4):g=ClipList(columns,f'V{i}',sequence=True,toolbar=False);g.pack(side='left',fill='both',expand=True,padx=2);self.lite_lists.append(g)

    def merge_lite(self):
        def prepare():
            self.idle_required();name=self.safe_name(self.lite_name.get());start=int(self.lite_start.get());folder=self.output_dir();jobs=[]
            if start<1:raise ValueError('Chỉ số bắt đầu phải lớn hơn 0.')
            for group in self.lite_lists:
                if group.paths:
                    dest=folder/f'{name}_{start+len(jobs):03}.mp4'
                    if dest.exists():raise ValueError(f'File đã tồn tại: {dest.name}')
                    jobs.append((list(group.paths),dest))
            if not jobs:raise ValueError('Thêm clip vào ít nhất một danh sách.')
            opts=self.options(lite=True)
            def worker():
                for paths,dest in jobs:self.engine.context=str(dest);self.engine.merge(paths,dest,opts)
            self.start(worker,f'MERGE LITE · {len(jobs)} video')
        self.guarded(prepare)

    def lite_preset_change(self,event=None):
        if self.lite_preset.get()=='Tùy chỉnh':return
        height={'4K':2160,'2K':1440,'1080p':1080,'720p':720,'480p':480}[self.lite_preset.get()]
        w,h={'16/9':(round(height*16/9/2)*2,height),'9/16':(height,round(height*16/9/2)*2),'1/1':(height,height),'4/3':(round(height*4/3/2)*2,height)}[self.lite_ratio.get()]
        self.lite_vars['size'].set(f'{w}x{h}')

    def build_audio(self):
        p=self.pages[3];ttk.Label(p,textvariable=self.output).pack(anchor='w',pady=3)
        actions=ttk.LabelFrame(p,text='Tùy chọn ghép',padding=5);actions.pack(side='bottom',fill='x',pady=5)
        self.match=tk.StringVar(value='Tên file');row=ttk.Frame(actions);row.pack(fill='x',pady=3)
        ttk.Radiobutton(row,text='Match theo Tên',variable=self.match,value='Tên file').pack(side='left',padx=5);ttk.Radiobutton(row,text='Ghép theo Thứ tự',variable=self.match,value='Thứ tự').pack(side='left',padx=12)
        self.button(row,'Chọn thư mục lưu',self.choose_output,BLUE,side='right')
        self.button(actions,'Bắt đầu ghép Audio',self.replace_audio,DARK,fill='x',pady=4)
        row=ttk.Frame(p);row.pack(fill='both',expand=True)
        self.audio_videos=ClipList(row,'Video',audio_controls=True);self.audio_videos.pack(side='left',fill='both',expand=True,padx=(0,3))
        self.audios=ClipList(row,'Audio',AUDIO,audio_controls=True);self.audios.pack(side='left',fill='both',expand=True,padx=(3,0))

    def build_selector(self):
        p=self.pages[4];top=ttk.Frame(p);top.pack(fill='x')
        inputs=ttk.LabelFrame(top,text='Thông số lựa chọn',padding=4);inputs.pack(side='left',fill='both')
        options=ttk.LabelFrame(top,text='Tùy chọn & Hành động',padding=5);options.pack(side='left',fill='both',expand=True,padx=(5,0))
        self.selector_vars={k:tk.StringVar(value=v) for k,v in dict(count='',target='',tolerance='',amount='',tries='5000',duration_unit='phút',tolerance_unit='phút',format="file 'path'").items()}
        for r,(label,key) in enumerate([('SL Video:','count'),('Thời lượng:','target'),('Sai số:','tolerance'),('SL Danh sách:','amount'),('Lần thử tối đa:','tries')]):
            ttk.Label(inputs,text=label).grid(row=r,column=0,sticky='w',padx=3,pady=3);ttk.Entry(inputs,textvariable=self.selector_vars[key],width=12).grid(row=r,column=1,padx=3,pady=3)
            if key in ('target','tolerance'):
                unit='duration_unit' if key=='target' else 'tolerance_unit';ttk.Combobox(inputs,textvariable=self.selector_vars[unit],values=['giây','phút','giờ'],width=6,state='readonly').grid(row=r,column=2,padx=3)
        row=ttk.Frame(options);row.pack(fill='x');ttk.Label(row,text='Định dạng xuất:').pack(side='left')
        for value in ['"path"',"file 'path'"]:ttk.Radiobutton(row,text=value,variable=self.selector_vars['format'],value=value).pack(side='left',padx=4)
        self.exclude_used=tk.BooleanVar();self.reuse=tk.BooleanVar();self.export_as_tasks=tk.BooleanVar()
        row=ttk.Frame(options);row.pack(fill='x',pady=4)
        ttk.Checkbutton(row,text='Không dùng lại',variable=self.exclude_used,command=lambda:self.reuse.set(False) if self.exclude_used.get() else None).pack(side='left');ttk.Checkbutton(row,text='Có dùng lại',variable=self.reuse,command=lambda:self.exclude_used.set(False) if self.reuse.get() else None).pack(side='left',padx=8);ttk.Checkbutton(row,text='Xuất thành Task',variable=self.export_as_tasks).pack(side='right')
        row=ttk.Frame(options);row.pack(fill='x')
        self.button(row,'Xóa tất cả',lambda:self.source.clear(),ORANGE,side='left',fill='x',expand=True,padx=2);self.button(row,'Xóa đã chọn',lambda:self.source.remove(),ORANGE,side='left',fill='x',expand=True,padx=2);self.button(row,'Xuất TXT',self.export_selector,BLUE,side='left',fill='x',expand=True,padx=2)
        row=ttk.Frame(options);row.pack(fill='x',pady=4)
        self.button(row,'Làm trống Nội dung',self.clear_results,RED,side='left',fill='x',expand=True,padx=2);self.button(row,'Đặt lại video đã dùng',self.used_selector.clear,GRAY,side='left',fill='x',expand=True,padx=2)
        self.button(options,'<<< Tạo >>>',self.generate_selector,DARK,fill='x',pady=4)
        row=ttk.Frame(p);row.pack(fill='both',expand=True,pady=5)
        self.source=ClipList(row,'Danh sách Video',VIDEO|AUDIO);self.source.pack(side='left',fill='both',expand=True,padx=(0,4))
        result=ttk.Frame(row);result.pack(side='left',fill='both',expand=True);ttk.Label(result,text='Kết quả:').pack(anchor='w')
        self.results=tk.Listbox(result,font=('Segoe UI',9),height=5,width=45,exportselection=False);self.results.pack(fill='both',expand=True);self.combinations=[]

    def clear_results(self):self.combinations=[];self.results.delete(0,'end')

    def generate_selector(self):
        def prepare():
            self.idle_required();v={k:x.get() for k,x in self.selector_vars.items()};parts=v['count'].split('-');bounds=(int(parts[0]),int(parts[-1]))
            scale={'giây':1,'phút':60,'giờ':3600};target=float(v['target'])*scale[v['duration_unit']];tolerance=float(v['tolerance'])*scale[v['tolerance_unit']];amount=int(v['amount']);tries=int(v['tries'])
            if not 5000<=tries<=50000:raise ValueError('Lần thử tối đa từ 5000 đến 50000.')
            paths=list(dict.fromkeys(p for p in self.source.paths if not self.exclude_used.get() or p not in self.used_selector));reuse=self.reuse.get()
            def worker():
                result=select_lists(paths,bounds,target,tolerance,amount,reuse,tries,cancel=self.engine.cancel,on_probe=lambda i,n:self.events.put(('progress',100*i/n)))
                self.events.put(('results',result));self.record_log(f'Tìm được {len(result)}/{amount} danh sách. Chưa ghép video.')
            self.start(worker,'VIDEO SELECTOR')
        self.guarded(prepare)

    def export_selector(self):
        def run():
            if not self.combinations:raise ValueError('Chưa có kết quả.')
            if self.export_as_tasks.get():
                name=simpledialog.askstring('Tên Task','Tên Task:',initialvalue='task',parent=self)
                if not name:return
                name=self.safe_name(name);folder=self.output_dir();plans=[(folder/f'{name}_{i+1:03}.txt',paths) for i,(paths,d) in enumerate(self.combinations)]
            else:
                value=filedialog.asksaveasfilename(parent=self,defaultextension='.txt',initialfile='video_list.txt',filetypes=[('TXT','*.txt')])
                if not value:return
                # Save every result with a header; read_list ignores these comments.
                plans=[(Path(value),None)]
            if any(p.exists() for p,_ in plans):raise ValueError('File xuất đã tồn tại.')
            def lines(paths):return ["file '"+p.replace('\\','/').replace("'","'\\''")+"'" if self.selector_vars['format'].get()=="file 'path'" else '"'+p+'"' for p in paths]
            for dest,paths in plans:
                text='\n'.join(lines(paths)) if paths is not None else '\n'.join(f'# Danh sách {i+1} · {d:.3f}s\n'+'\n'.join(lines(paths)) for i,(paths,d) in enumerate(self.combinations))
                dest.write_text(text+'\n',encoding='utf-8')
            self.record_log(f'Đã xuất {len(plans)} TXT')
        self.guarded(run)

    def toggle_controls(self):
        if self.controls.winfo_manager():self.controls.pack_forget()
        else:self.controls.pack(fill='x',before=self.task_area)

    def toggle_tab(self,index):self.tabs.tab(self.pages[index],state='normal' if self.visible_tabs[index].get() else 'hidden')

    def restore_controls(self):
        for key,value in self.saved.get('lite',{}).items():
            if key in self.lite_vars:self.lite_vars[key].set(value)
        for key,variable in [('lite_copy',self.lite_copy),('lite_name',self.lite_name),('lite_start',self.lite_start),('lite_ratio',self.lite_ratio),('lite_preset',self.lite_preset)]:
            if key in self.saved:variable.set(self.saved[key])
        b=self.saved.get('builder',{})
        for key,var in [('name',self.task_prefix),('start',self.task_start),('amount',self.task_amount),('mixed',self.mixed)]:
            if key in b:var.set(b[key])
        for variables,key in [(self.group_counts,'counts'),(self.group_random,'random')]:
            for var,value in zip(variables,b.get(key,[])):var.set(value)
        for key,value in self.saved.get('selector',{}).items():
            if key in self.selector_vars:self.selector_vars[key].set(value)
        for index in self.visible_tabs:self.toggle_tab(index)
    def toggle_log(self):
        if self.log_frame.winfo_manager():self.log_frame.pack_forget()
        else:self.log_frame.pack(fill='x')
    def open_logs(self):
        if self.log_path:self.guarded(lambda:os.startfile(str(self.log_path.parent)))

    def refresh_license(self):
        self.title(f'ClipMerge — v{VERSION} · '+('Đã kích hoạt' if licensing.is_activated() else 'Bản cơ bản'))

    def ask_activation(self,required=False):
        win=tk.Toplevel(self);win.title('Kích hoạt ClipMerge');win.resizable(False,False)
        if not required:win.transient(self)
        def cancel():
            win.destroy()
            if required:self.destroy()
        win.protocol('WM_DELETE_WINDOW',cancel)
        frame=ttk.Frame(win,padding=22);frame.pack()
        ttk.Label(frame,text='Nhập mã kích hoạt để sử dụng ClipMerge.').pack(anchor='w')
        code=tk.StringVar();entry=ttk.Entry(frame,textvariable=code,show='*',width=34);entry.pack(pady=(12,4))
        message=tk.StringVar();ttk.Label(frame,textvariable=message,foreground='#c0392b').pack(anchor='w')
        def submit(event=None):
            if licensing.activate(code.get()):
                win.destroy();self.refresh_license()
                if required:self.deiconify()
                messagebox.showinfo('ClipMerge','Kích hoạt thành công.',parent=self)
            else:code.set('');message.set('Mã không đúng. Hãy thử lại.')
        buttons=ttk.Frame(frame);buttons.pack(anchor='e',pady=(12,0))
        ttk.Button(buttons,text='Thoát' if required else 'Hủy',command=cancel).pack(side='right');ttk.Button(buttons,text='Kích hoạt',command=submit).pack(side='right',padx=8)
        entry.bind('<Return>',submit);entry.focus_set();win.grab_set()

    def check_update(self,manual):
        if self.updating:return
        if not licensing.is_activated():
            if manual:messagebox.showinfo('ClipMerge','Chỉ bản đã kích hoạt mới cập nhật được. Vào Trợ giúp > Kích hoạt và nhập mã.',parent=self)
            return
        if self.busy:
            if manual:messagebox.showinfo('ClipMerge','Đang xử lý. Hãy đợi xong rồi cập nhật.',parent=self)
            return
        folder=updater.get_folder('ClipMerge')
        if not folder:
            if not manual:return
            folder=filedialog.askdirectory(title='Chọn thư mục cập nhật (trên mạng LAN)',parent=self)
            if not folder:return
            updater.set_folder('ClipMerge',folder)
        self.updating=True
        def work():
            try:self.events.put(('update',(updater.check_latest(folder,VERSION),manual)))
            except Exception as exc:self.events.put(('update_error',(str(exc),manual)))
        threading.Thread(target=work,daemon=True).start()

    def offer_update(self,info,manual):
        if not info:
            self.updating=False
            if manual:messagebox.showinfo('ClipMerge',f'Bạn đang dùng bản mới nhất ({VERSION}).',parent=self)
            return
        text=f'Có bản mới {info["version"]} (đang dùng {VERSION}).\n\n{info["notes"].strip()[:600]}\n\nCập nhật ngay?'
        if self.busy or not messagebox.askyesno('ClipMerge',text,parent=self):
            self.updating=False;return
        self.state.set(f'Đang tải bản {info["version"]}...')
        def work():
            try:self.events.put(('install',updater.download(info,lambda p:self.events.put(('progress',p)))))
            except Exception as exc:self.events.put(('update_error',(str(exc),True)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.progress['value']=value
                elif kind=='update':self.offer_update(*value)
                elif kind=='update_error':
                    self.updating=False
                    if value[1]:
                        self.state.set('Cập nhật thất bại');messagebox.showerror('ClipMerge',f'Không cập nhật được:\n{value[0]}',parent=self)
                        if messagebox.askyesno('ClipMerge','Chọn lại thư mục cập nhật?',parent=self):
                            updater.set_folder('ClipMerge','');self.after(100,lambda:self.check_update(True))
                elif kind=='install':updater.install(value);self.destroy();return
                elif kind=='phase':
                    path,stage,i,n=value;label={'check':'Kiểm tra','audio':'Đo âm thanh','encode':'Mã hóa','join':'Nối cuối','validate':'Kiểm tra kết quả','complete':'Hoàn tất'}.get(stage,stage);text=f'{label} {i}/{n}' if stage in ('check','audio','encode') else label
                    self.state.set((Path(path).name+' · ' if path else '')+text);self.set_task_status(path,text)
                elif kind=='task_status':self.set_task_status(*value)
                elif kind=='open':self.guarded(lambda v=value:os.startfile(v))
                elif kind=='results':
                    self.combinations=value;self.results.delete(0,'end')
                    for i,(paths,d) in enumerate(value):
                        self.results.insert('end',f'Danh sách {i+1} · {d:.1f}s')
                        for path in paths:self.results.insert('end','  '+Path(path).name);self.used_selector.add(path)
                elif kind=='idle':self.busy=False;self.engine.context=None
                else:
                    self.logs.configure(state='normal');self.logs.insert('end',str(value)+'\n');self.logs.see('end');self.logs.configure(state='disabled')
                    if kind in ('done','error'):
                        self.state.set(value if kind=='done' else 'Có lỗi')
                        if kind=='error':messagebox.showerror('ClipMerge',value,parent=self)
        except queue.Empty:pass
        self.after(100,self.poll)

    def set_task_status(self,path,text):
        if path in self.task_paths:self.task_states[path]=text;self.task_tree.set(str(self.task_paths.index(path)),'status',text)

    def close(self):
        if self.busy:messagebox.showinfo('ClipMerge','Dừng xử lý trước khi đóng.',parent=self);return
        try:
            data={'output':self.output.get(),'hub':{k:v.get() for k,v in self.vars.items()},'lite':{k:v.get() for k,v in self.lite_vars.items()},'builder':dict(name=self.task_prefix.get(),start=self.task_start.get(),amount=self.task_amount.get(),mixed=self.mixed.get(),counts=[v.get() for v in self.group_counts],random=[v.get() for v in self.group_random]),'selector':{k:v.get() for k,v in self.selector_vars.items()},'visible_tabs':{str(k):v.get() for k,v in self.visible_tabs.items()}}
            for key,var in [('lite_copy',self.lite_copy),('lite_name',self.lite_name),('lite_start',self.lite_start),('lite_ratio',self.lite_ratio),('lite_preset',self.lite_preset)]:data[key]=var.get()
            self.config_path.parent.mkdir(parents=True,exist_ok=True);self.config_path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        except OSError:pass
        self.destroy()
