import os
from classic_ui import App, VERSION, filedialog, messagebox

if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ClipMerge.Desktop')
    App().mainloop()
