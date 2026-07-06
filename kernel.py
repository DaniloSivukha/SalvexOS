#!/usr/bin/env python3
"""
SalvexOS 6.0 — исправлен установщик: добавлены детальные сообщения об ошибках
и сохранение введённых данных при возврате на шаг создания пользователя.
"""

import os
import sys
import json
import hashlib
import time
import datetime
import calendar
import shutil
import stat
from collections import OrderedDict

try:
    import urwid
except ImportError:
    print("Установите urwid: pip install urwid")
    sys.exit(1)

# Попытка импорта Pillow для ASCII-art
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Для просмотра изображений установите Pillow: pip install Pillow")

# ------------------------------------------------------------
# Файловая система на основе реальных файлов
# ------------------------------------------------------------
class FileSystem:
    def __init__(self, root_path):
        self.root_path = os.path.abspath(root_path)
        self.current_path = self.root_path
        self.home_path = None
        if not os.path.exists(self.root_path):
            os.makedirs(self.root_path)

    def _resolve_path(self, path):
        if not path or path == ".":
            return self.current_path
        if path.startswith("/"):
            parts = path.split("/")[1:]
            real_path = self.root_path
            for part in parts:
                if part == "" or part == ".":
                    continue
                if part == "..":
                    real_path = os.path.dirname(real_path)
                    continue
                real_path = os.path.join(real_path, part)
            return real_path
        else:
            return os.path.join(self.current_path, path)

    def mkdir(self, path, name):
        target_dir = self._resolve_path(path)
        new_dir = os.path.join(target_dir, name)
        if os.path.exists(new_dir):
            raise FileExistsError("Already exists")
        os.makedirs(new_dir, exist_ok=True)

    def touch(self, path, name, content=""):
        target_dir = self._resolve_path(path)
        new_file = os.path.join(target_dir, name)
        if os.path.exists(new_file):
            raise FileExistsError("Already exists")
        with open(new_file, "w", encoding="utf-8") as f:
            f.write(content)

    def list_dir(self, path=""):
        real_path = self._resolve_path(path)
        if not os.path.isdir(real_path):
            raise NotADirectoryError("Not a directory")
        items = []
        for item in os.listdir(real_path):
            full = os.path.join(real_path, item)
            is_dir = os.path.isdir(full)
            items.append((item, is_dir, full))
        return items

    def read_file(self, path):
        real_path = self._resolve_path(path)
        if not os.path.isfile(real_path):
            raise IsADirectoryError("Is a directory")
        with open(real_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path, content):
        real_path = self._resolve_path(path)
        if not os.path.isfile(real_path):
            raise IsADirectoryError("Is a directory")
        with open(real_path, "w", encoding="utf-8") as f:
            f.write(content)

    def remove(self, path):
        real_path = self._resolve_path(path)
        if not os.path.exists(real_path):
            raise FileNotFoundError("File not found")
        if os.path.isdir(real_path):
            if os.listdir(real_path):
                raise OSError("Directory not empty")
            os.rmdir(real_path)
        else:
            os.remove(real_path)

    def rename(self, path, new_name):
        real_path = self._resolve_path(path)
        if not os.path.exists(real_path):
            raise FileNotFoundError("File not found")
        dirname = os.path.dirname(real_path)
        new_path = os.path.join(dirname, new_name)
        if os.path.exists(new_path):
            raise FileExistsError("Name already exists")
        os.rename(real_path, new_path)

    def copy(self, src, dst):
        src_real = self._resolve_path(src)
        dst_dir_path, dst_name = os.path.split(dst) if dst else ("", "")
        if not dst_dir_path:
            dst_dir_path = "."
        dst_dir = self._resolve_path(dst_dir_path)
        if not os.path.isdir(dst_dir):
            raise NotADirectoryError("Destination not directory")
        dst_full = os.path.join(dst_dir, dst_name)
        if os.path.exists(dst_full):
            raise FileExistsError("Already exists")
        if os.path.isdir(src_real):
            shutil.copytree(src_real, dst_full)
        else:
            shutil.copy2(src_real, dst_full)

    def exists(self, path):
        real_path = self._resolve_path(path)
        return os.path.exists(real_path)

    def get_node_info(self, path):
        real_path = self._resolve_path(path)
        if not os.path.exists(real_path):
            raise FileNotFoundError("Path not found")
        st = os.stat(real_path)
        return {
            "name": os.path.basename(real_path),
            "path": real_path,
            "type": "dir" if os.path.isdir(real_path) else "file",
            "size": st.st_size if not os.path.isdir(real_path) else 0,
            "mtime": st.st_mtime,
            "mode": st.st_mode
        }

    def get_home(self, username):
        home = os.path.join(self.root_path, "home", username)
        if not os.path.exists(home):
            os.makedirs(home)
        return home

    def chdir(self, path):
        if not path:
            self.current_path = self.home_path or self.root_path
        else:
            new_path = self._resolve_path(path)
            if not os.path.isdir(new_path):
                raise NotADirectoryError("Not a directory")
            self.current_path = new_path

    def get_current_path(self):
        rel = os.path.relpath(self.current_path, self.root_path)
        if rel == ".":
            return "/"
        return "/" + rel.replace("\\", "/")

    def get_real_path(self, virtual_path):
        return self._resolve_path(virtual_path)

    def save_state(self):
        pass

# ------------------------------------------------------------
# Конфигурация и пользователи
# ------------------------------------------------------------
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

class Config:
    CONFIG_FILE = "salvexos_config.json"
    def __init__(self):
        self.data = {}
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r") as f:
                self.data = json.load(f)
            if "root_path" not in self.data:
                self.data["root_path"] = "salvexos_root"
            if "theme" not in self.data:
                self.data["theme"] = "default"
            if "installed" not in self.data:
                self.data["installed"] = False
            if "username" not in self.data:
                self.data["username"] = ""
            if "password_hash" not in self.data:
                self.data["password_hash"] = ""
            if "hostname" not in self.data:
                self.data["hostname"] = "salvexos"
        else:
            self.data = {
                "installed": False,
                "root_path": "salvexos_root",
                "username": "",
                "password_hash": "",
                "hostname": "salvexos",
                "theme": "default"
            }

    def save(self):
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_installed(self):
        return self.data.get("installed", False)

    def set_installed(self, username, password, hostname, root_path):
        self.data["installed"] = True
        self.data["username"] = username
        self.data["password_hash"] = hash_password(password)
        self.data["hostname"] = hostname
        self.data["root_path"] = root_path
        self.data["theme"] = "default"
        self.save()

    def check_password(self, password):
        return self.data.get("password_hash") == hash_password(password)

    def change_password(self, old, new):
        if self.check_password(old):
            self.data["password_hash"] = hash_password(new)
            self.save()
            return True
        return False

    def change_username(self, new_username):
        self.data["username"] = new_username
        self.save()

    def change_hostname(self, new_hostname):
        self.data["hostname"] = new_hostname
        self.save()

    def change_theme(self, theme):
        self.data["theme"] = theme
        self.save()

# ------------------------------------------------------------
# Установщик (исправлен: детальные ошибки и сохранение данных)
# ------------------------------------------------------------
class Installer:
    def __init__(self):
        self.config = Config()
        self.username = ""
        self.password = ""
        self.hostname = "salvexos"
        self.root_path = "salvexos_root"
        self.root_edit = None
        self.name_edit = None
        self.pass_edit = None
        self.pass2_edit = None
        self.host_edit = None

    def run(self):
        self.main_loop = urwid.MainLoop(self.build_welcome(), palette=self.get_palette())
        self.main_loop.run()

    def get_palette(self):
        return [
            ('body', 'black', 'light gray'),
            ('header', 'white', 'dark blue'),
            ('footer', 'white', 'dark blue'),
            ('button', 'black', 'light cyan'),
            ('button focus', 'white', 'dark cyan'),
            ('edit', 'black', 'white'),
            ('edit focus', 'white', 'dark blue'),
            ('progress', 'white', 'dark green'),
            ('label', 'light gray', 'default'),
            ('title', 'white,bold', 'default'),
        ]

    def build_welcome(self):
        text = urwid.Text(
            """
            ╔══════════════════════════════════════════╗
            ║          Добро пожаловать в             ║
            ║      ███████╗ █████╗ ██╗    ██╗        ║
            ║      ██╔════╝██╔══██╗██║    ██║        ║
            ║      ███████╗███████║██║ █╗ ██║        ║
            ║      ╚════██║██╔══██║██║███╗██║        ║
            ║      ███████║██║  ██║╚███╔███╔╝        ║
            ║      ╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝         ║
            ║                                          ║
            ║          SalvexOS 2026                  ║
            ║                                          ║
            ║   Установщик создаст файловую систему    ║
            ║   в папке на диске. Все файлы будут      ║
            ║   храниться локально.                   ║
            ║                                          ║
            ║         Нажмите "Далее" для продолжения  ║
            ╚══════════════════════════════════════════╝
            """, align='center')
        btn = urwid.Button("Далее", on_press=self.next_step)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', text),
            ('flow', btn_wrapped),
        ])
        return urwid.Filler(pile, valign='middle')

    def next_step(self, button=None):
        self.main_loop.widget = self.build_root_selection()

    def build_root_selection(self):
        txt = urwid.Text("Папка для файловой системы (будет создана):", align='center')
        edit = urwid.Edit("Путь: ", self.root_path)
        self.root_edit = edit
        btn = urwid.Button("Далее", on_press=self.next_step2)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', txt),
            ('flow', edit),
            ('flow', btn_wrapped),
        ])
        return urwid.Filler(pile, valign='middle')

    def next_step2(self, button):
        self.root_path = self.root_edit.get_edit_text()
        self.main_loop.widget = self.build_user_creation()

    def build_user_creation(self, username="", pwd="", pwd2=""):
        txt = urwid.Text("Создание пользователя", align='center')
        name_edit = urwid.Edit("Имя пользователя: ", username)
        pass_edit = urwid.Edit("Пароль: ", pwd, mask="*")
        pass2_edit = urwid.Edit("Подтверждение: ", pwd2, mask="*")
        self.name_edit = name_edit
        self.pass_edit = pass_edit
        self.pass2_edit = pass2_edit
        btn = urwid.Button("Далее", on_press=self.next_step3)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', txt),
            ('flow', name_edit),
            ('flow', pass_edit),
            ('flow', pass2_edit),
            ('flow', btn_wrapped),
        ])
        return urwid.Filler(pile, valign='middle')

    def next_step3(self, button):
        self.username = self.name_edit.get_edit_text()
        pwd = self.pass_edit.get_edit_text()
        pwd2 = self.pass2_edit.get_edit_text()
        error_msg = None
        if not self.username:
            error_msg = "Имя пользователя не может быть пустым!"
        elif pwd != pwd2:
            error_msg = "Пароли не совпадают!"
        elif len(pwd) < 4:
            error_msg = "Пароль должен быть не менее 4 символов!"
        if error_msg:
            # Показываем ошибку и возвращаемся к форме с сохранением введённых данных
            error_widget = urwid.Filler(urwid.Text(error_msg, align='center'), valign='middle')
            self.main_loop.widget = error_widget
            self.main_loop.set_alarm_in(2, lambda loop, data: setattr(loop, 'widget', self.build_user_creation(self.username, pwd, pwd2)))
            return
        self.password = pwd
        self.main_loop.widget = self.build_hostname()

    def build_hostname(self):
        txt = urwid.Text("Имя хоста:", align='center')
        edit = urwid.Edit("", self.hostname)
        self.host_edit = edit
        btn = urwid.Button("Далее", on_press=self.next_step4)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', txt),
            ('flow', edit),
            ('flow', btn_wrapped),
        ])
        return urwid.Filler(pile, valign='middle')

    def next_step4(self, button):
        self.hostname = self.host_edit.get_edit_text()
        self.main_loop.widget = self.build_progress()

    def build_progress(self):
        txt = urwid.Text("Установка... 0%", align='center')
        progress = urwid.ProgressBar('progress', 'body')
        btn = urwid.Button("Готово", on_press=self.finish_install)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', txt),
            ('weight', 1, progress),
            ('flow', btn_wrapped),
        ])
        self.start_progress(pile, txt, btn)
        return urwid.Filler(pile, valign='middle')

    def start_progress(self, pile, txt, btn):
        def update(loop, data):
            prog = data[0]
            if prog < 100:
                prog += 5
                data[0] = prog
                pile.contents[1][0].set_completion(prog)
                txt.set_text(f"Установка... {prog}%")
                loop.set_alarm_in(0.1, update, data)
            else:
                txt.set_text("Установка завершена!")
                btn.set_label("Завершить")
        self.main_loop.set_alarm_in(0.1, update, [0])

    def finish_install(self, button):
        root_path = os.path.abspath(self.root_path)
        if not os.path.exists(root_path):
            os.makedirs(root_path)
        home_dir = os.path.join(root_path, "home")
        os.makedirs(home_dir, exist_ok=True)
        user_home = os.path.join(home_dir, self.username)
        os.makedirs(user_home, exist_ok=True)
        etc_dir = os.path.join(root_path, "etc")
        os.makedirs(etc_dir, exist_ok=True)
        with open(os.path.join(etc_dir, "hostname"), "w") as f:
            f.write(self.hostname)
        with open(os.path.join(etc_dir, "issue"), "w") as f:
            f.write("SalvexOS 2026")
        bin_dir = os.path.join(root_path, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        self.config.set_installed(self.username, self.password, self.hostname, self.root_path)
        self.main_loop.widget = urwid.Text("Установка завершена! Перезапустите программу.", align='center')
        raise urwid.ExitMainLoop()

# ------------------------------------------------------------
# Вспомогательные виджеты
# ------------------------------------------------------------
class FancyButton(urwid.Button):
    def __init__(self, label, on_press=None, user_data=None):
        super().__init__(label, on_press, user_data)
        self._label = urwid.Text(label, align='center')

class FancyDialog(urwid.WidgetWrap):
    def __init__(self, text, buttons, title="Диалог", close_callback=None):
        self.close_callback = close_callback
        body = []
        body.append(('flow', urwid.Text(text, align='center')))
        body.append(('flow', urwid.Divider()))
        button_widgets = []
        for label, callback in buttons:
            def make_callback(cb):
                def wrapper(btn):
                    cb(btn)
                    if self.close_callback:
                        self.close_callback()
                return wrapper
            btn = FancyButton(label, on_press=make_callback(callback))
            button_widgets.append(urwid.AttrMap(btn, 'button', focus_map='button focus'))
        body.append(('flow', urwid.Columns(button_widgets)))
        pile = urwid.Pile(body)
        self.widget = urwid.LineBox(pile, title=title)
        super().__init__(self.widget)

class InputDialog(urwid.WidgetWrap):
    def __init__(self, prompt, callback, close_callback):
        self.edit = urwid.Edit(prompt)
        self.callback = callback
        self.close_callback = close_callback
        btn_ok = urwid.Button("OK", on_press=self.on_ok)
        btn_cancel = urwid.Button("Отмена", on_press=self.on_cancel)
        buttons = urwid.Columns([btn_ok, btn_cancel])
        pile = urwid.Pile([
            ('flow', self.edit),
            ('flow', buttons),
        ])
        pile.focus_position = 0
        self.widget = urwid.LineBox(pile, title=prompt)
        super().__init__(self.widget)

    def on_ok(self, button):
        val = self.edit.get_edit_text()
        if val:
            self.callback(val)
            if self.close_callback:
                self.close_callback()

    def on_cancel(self, button):
        if self.close_callback:
            self.close_callback()

# ------------------------------------------------------------
# Утилита ASCII-art для изображений
# ------------------------------------------------------------
def image_to_ascii(image_path, width=70, height=30):
    if not PILLOW_AVAILABLE:
        return "Установите Pillow для просмотра изображений\npip install Pillow"
    try:
        img = Image.open(image_path)
        img = img.convert("L")
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        pixels = list(img.getdata())
        chars = " .:-=+*#%@"
        w, h = img.size
        ascii_lines = []
        for y in range(h):
            line = ""
            for x in range(w):
                val = pixels[y * w + x]
                idx = int(val / 255 * (len(chars) - 1))
                line += chars[idx]
            ascii_lines.append(line)
        return "\n".join(ascii_lines)
    except Exception as e:
        return f"Ошибка загрузки изображения: {e}"

# ------------------------------------------------------------
# Приложения
# ------------------------------------------------------------

# ---- 1. Калькулятор ----
class CalculatorFrame(urwid.Frame):
    def __init__(self):
        self.display = urwid.Text("0", align='right')
        self.expression = ""
        self.buttons = [
            ['7', '8', '9', '/'],
            ['4', '5', '6', '*'],
            ['1', '2', '3', '-'],
            ['0', '.', '=', '+'],
            ['C', '←', '(', ')']
        ]
        self.grid = self.build_grid()
        display_box = urwid.LineBox(self.display, title="Вывод")
        body = urwid.Pile([
            ('weight', 1, display_box),
            ('weight', 3, self.grid),
        ])
        super().__init__(urwid.LineBox(body, title="Калькулятор"))

    def build_grid(self):
        rows = []
        for row in self.buttons:
            btns = []
            for label in row:
                btn = urwid.Button(label, on_press=self.on_button)
                btns.append(('weight', 1, urwid.AttrMap(btn, 'button', focus_map='button focus')))
            rows.append(urwid.Columns(btns))
        return urwid.Pile(rows)

    def on_button(self, button):
        label = button.get_label()
        if label == 'C':
            self.expression = ""
            self.display.set_text("0")
        elif label == '←':
            self.expression = self.expression[:-1]
            self.display.set_text(self.expression or "0")
        elif label == '=':
            try:
                result = eval(self.expression)
                self.display.set_text(str(result))
                self.expression = str(result)
            except:
                self.display.set_text("Error")
                self.expression = ""
        else:
            self.expression += label
            self.display.set_text(self.expression)

# ---- 2. Файловый менеджер ----
class FileManagerFrame(urwid.Frame):
    def __init__(self, fs, config, add_window_callback, close_window_callback):
        self.fs = fs
        self.config = config
        self.add_window = add_window_callback
        self.close_window = close_window_callback
        self.current_dir = fs.current_path
        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.header_text = urwid.Text(f"Файловый менеджер: {fs.get_current_path()}", align='center')
        actions = urwid.Columns([
            urwid.Button("Создать папку", on_press=self.create_dir),
            urwid.Button("Создать файл", on_press=self.create_file),
            urwid.Button("Переименовать", on_press=self.rename_item),
            urwid.Button("Удалить", on_press=self.delete_item),
            urwid.Button("Копировать", on_press=self.copy_item),
            urwid.Button("Вставить", on_press=self.paste_item),
        ])
        self.action_bar = urwid.AttrMap(actions, 'footer')
        super().__init__(body=self.listbox, header=self.header_text, footer=self.action_bar)
        self.refresh()
        self.clipboard = None

    def refresh(self):
        items = self.fs.list_dir(self.fs.get_current_path())
        walker = self.listbox.body
        walker.clear()
        if self.fs.get_current_path() != "/":
            btn_up = urwid.Button("<- Наверх", on_press=self.go_up)
            walker.append(urwid.AttrMap(btn_up, 'button', focus_map='button focus'))
        items.sort(key=lambda x: (not x[1], x[0].lower()))
        for name, is_dir, full_path in items:
            if is_dir:
                icon = "📁"
                size_str = ""
                mtime_str = ""
            else:
                icon = "📄"
                try:
                    st = os.stat(full_path)
                    size_str = f"{st.st_size:>8} bytes"
                    mtime_str = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                except:
                    size_str = "   ?   "
                    mtime_str = "???"
            label = f"{icon} {name:<20} {size_str:>12}  {mtime_str}"
            btn = urwid.Button(label, on_press=self.on_item, user_data=name)
            walker.append(urwid.AttrMap(btn, 'button', focus_map='button focus'))
        self.header_text.set_text(f"Файловый менеджер: {self.fs.get_current_path()}")

    def go_up(self, button):
        self.fs.chdir("..")
        self.refresh()

    def on_item(self, button, name):
        full_path = os.path.join(self.fs.current_path, name)
        if os.path.isdir(full_path):
            self.fs.chdir(name)
            self.refresh()
        else:
            ext = os.path.splitext(name)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.tiff', '.webp'):
                viewer = MediaViewerFrame(self.fs, name)
                self.add_window("Просмотр изображения", viewer, viewer)
            else:
                try:
                    editor = EditorFrame(self.fs, filepath=name, parent_dir=self.current_dir)
                    self.add_window("Редактор", editor, editor)
                except UnicodeDecodeError:
                    viewer = MediaViewerFrame(self.fs, name)
                    self.add_window("Просмотр", viewer, viewer)

    def create_dir(self, button):
        self.show_input_dialog("Имя новой папки:", lambda name: self.fs.mkdir(".", name))

    def create_file(self, button):
        self.show_input_dialog("Имя нового файла:", lambda name: self.fs.touch(".", name))

    def rename_item(self, button):
        focus = self.listbox.body.focus
        if focus:
            label = focus.base_widget.get_label()
            if label.startswith("<-"):
                return
            parts = label.split()
            if len(parts) > 1:
                name = parts[1]
                self.show_input_dialog("Новое имя:", lambda new: self.fs.rename(name, new))

    def delete_item(self, button):
        focus = self.listbox.body.focus
        if focus:
            label = focus.base_widget.get_label()
            if label.startswith("<-"):
                return
            parts = label.split()
            if len(parts) > 1:
                name = parts[1]
                def confirm(b):
                    self.fs.remove(name)
                    self.refresh()
                dialog = FancyDialog(f"Удалить {name}?", [("Да", confirm), ("Нет", lambda b: None)], close_callback=self.close_window)
                self.add_window("Подтверждение", dialog, dialog)

    def copy_item(self, button):
        focus = self.listbox.body.focus
        if focus:
            label = focus.base_widget.get_label()
            if label.startswith("<-"):
                return
            parts = label.split()
            if len(parts) > 1:
                name = parts[1]
                self.clipboard = (name, self.fs.current_path)

    def paste_item(self, button):
        if self.clipboard:
            src_name, src_dir = self.clipboard
            dst_dir = self.fs.current_path
            try:
                src_full = os.path.join(src_dir, src_name)
                dst_full = os.path.join(dst_dir, src_name)
                if os.path.isdir(src_full):
                    shutil.copytree(src_full, dst_full, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_full, dst_full)
                self.refresh()
            except Exception as e:
                self.show_error(str(e))

    def show_input_dialog(self, prompt, callback):
        dialog = InputDialog(prompt, callback, self.close_window)
        self.add_window("Ввод", dialog, dialog)

    def show_error(self, msg):
        dialog = FancyDialog(msg, [("OK", lambda b: None)], close_callback=self.close_window)
        self.add_window("Ошибка", dialog, dialog)

# ---- 3. Текстовый редактор ----
class EditorFrame(urwid.Frame):
    def __init__(self, fs, filepath=None, parent_dir=None):
        self.fs = fs
        self.filepath = filepath
        self.parent_dir = parent_dir
        self.content = ""
        if filepath and fs.exists(filepath):
            try:
                self.content = fs.read_file(filepath)
            except UnicodeDecodeError:
                raise UnicodeDecodeError("Файл не является текстовым")
        self.edit = urwid.Edit(multiline=True, edit_text=self.content)
        self.info = urwid.Text(f"Редактор: {filepath if filepath else 'новый файл'}", align='center')
        self.search_edit = urwid.Edit("Поиск: ")
        self.search_btn = urwid.Button("Найти", on_press=self.search)
        self.save_btn = urwid.Button("Сохранить", on_press=self.save)
        self.save_as_btn = urwid.Button("Сохранить как", on_press=self.save_as)
        actions = urwid.Columns([self.search_edit, self.search_btn, self.save_btn, self.save_as_btn])
        self.action_bar = urwid.AttrMap(actions, 'footer')
        self.edit_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([self.edit]))
        body = urwid.Pile([
            ('flow', self.info),
            ('weight', 8, self.edit_listbox),
        ])
        super().__init__(body=body, footer=self.action_bar)
        self.focus_part = 'body'

    def search(self, button):
        pattern = self.search_edit.get_edit_text()
        if not pattern:
            return
        text = self.edit.get_edit_text()
        pos = text.find(pattern)
        if pos != -1:
            self.edit.set_edit_pos(pos)
            self.edit.set_edit_text(text)
            self.info.set_text(f"Найдено: {pattern} в позиции {pos}")
        else:
            self.info.set_text("Не найдено")

    def save(self, button):
        if self.filepath:
            self.fs.write_file(self.filepath, self.edit.get_edit_text())
            self.info.set_text(f"Сохранено: {self.filepath}")
        else:
            self.save_as(button)

    def save_as(self, button):
        edit = urwid.Edit("Имя файла: ")
        def on_save(b):
            name = edit.get_edit_text()
            if name:
                self.filepath = name
                if not self.fs.exists(name):
                    self.fs.touch(".", name)
                self.fs.write_file(name, self.edit.get_edit_text())
                self.info.set_text(f"Сохранено: {name}")
                self.body = urwid.Pile([
                    ('flow', self.info),
                    ('weight', 8, self.edit_listbox),
                ])
        btn = urwid.Button("Сохранить", on_press=on_save)
        pile = urwid.Pile([
            ('flow', edit),
            ('flow', btn),
        ])
        pile.focus_position = 0
        dialog = urwid.LineBox(pile, title="Сохранить как")
        self.body = dialog

# ---- 4. Календарь ----
class CalendarFrame(urwid.Frame):
    def __init__(self):
        self.year = datetime.datetime.now().year
        self.month = datetime.datetime.now().month
        self.today = datetime.datetime.now().day
        self.update_calendar()
        super().__init__(self.body)

    def update_calendar(self):
        cal = calendar.monthcalendar(self.year, self.month)
        header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        rows = [header] + cal
        text_rows = []
        for row in rows:
            row_str = ""
            for day in row:
                if day == 0:
                    row_str += "   "
                else:
                    if day == self.today and self.year == datetime.datetime.now().year and self.month == datetime.datetime.now().month:
                        row_str += f"[{day:2}]"
                    else:
                        row_str += f" {day:2} "
            text_rows.append(row_str)
        cal_text = "\n".join(text_rows)
        title = f"{calendar.month_name[self.month]} {self.year}"
        prev_btn = urwid.Button("<-", on_press=self.prev_month)
        next_btn = urwid.Button("->", on_press=self.next_month)
        nav = urwid.Columns([prev_btn, next_btn])
        body = urwid.Pile([
            ('flow', urwid.Text(title, align='center')),
            ('flow', nav),
            ('flow', urwid.Text(cal_text, align='center')),
        ])
        self.body = urwid.LineBox(body, title="Календарь")

    def prev_month(self, button):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.update_calendar()

    def next_month(self, button):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.update_calendar()

# ---- 5. Просмотр изображений ----
class MediaViewerFrame(urwid.Frame):
    def __init__(self, fs, filepath, width=70, height=30):
        self.fs = fs
        self.filepath = filepath
        real_path = fs.get_real_path(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        self.is_image = ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.tiff', '.webp')
        if self.is_image and PILLOW_AVAILABLE:
            ascii_art = image_to_ascii(real_path, width=width, height=height)
            text = ascii_art
        else:
            try:
                content = fs.read_file(filepath)
                if content.strip():
                    text = content[:2000] + "..." if len(content) > 2000 else content
                else:
                    text = "[Пустой файл]"
            except UnicodeDecodeError:
                st = os.stat(real_path)
                text = f"[Бинарный файл]\nРазмер: {st.st_size} bytes\nДата изменения: {datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')}"
            except Exception as e:
                text = f"Ошибка: {e}"
        self.body = urwid.LineBox(urwid.Text(text, align='left'), title=f"Просмотр: {filepath}")
        super().__init__(self.body)

# ---- 6. Настройки ----
class SettingsFrame(urwid.Frame):
    def __init__(self, config, fs, logout_callback):
        self.config = config
        self.fs = fs
        self.logout_callback = logout_callback
        self.pages = [
            ("Общие", self.build_general),
            ("Пользователь", self.build_user),
            ("Система", self.build_system),
        ]
        self.page_idx = 0
        self.page_content = urwid.Pile([])
        nav = urwid.Columns([
            urwid.Button("< Назад", on_press=self.prev_page),
            urwid.Button("Вперед >", on_press=self.next_page),
        ])
        body = urwid.Pile([
            ('flow', urwid.Text("Настройки SalvexOS", align='center')),
            ('flow', nav),
            ('weight', 8, self.page_content),
        ])
        super().__init__(urwid.LineBox(body, title="Настройки"))
        self.update_page()

    def update_page(self):
        title, builder = self.pages[self.page_idx]
        self.page_content.contents.clear()
        widget = builder()
        self.page_content.contents.append((widget, ('weight', 1)))

    def next_page(self, button):
        if self.page_idx < len(self.pages) - 1:
            self.page_idx += 1
            self.update_page()

    def prev_page(self, button):
        if self.page_idx > 0:
            self.page_idx -= 1
            self.update_page()

    def build_general(self):
        theme = self.config.data.get("theme", "default")
        theme_edit = urwid.Edit("Тема: ", theme)
        save_btn = urwid.Button("Сохранить тему", on_press=lambda b: self.config.change_theme(theme_edit.get_edit_text()))
        return urwid.Pile([
            ('flow', theme_edit),
            ('flow', save_btn),
        ])

    def build_user(self):
        username = self.config.data.get("username", "")
        hostname = self.config.data.get("hostname", "")
        user_edit = urwid.Edit("Имя пользователя: ", username)
        host_edit = urwid.Edit("Имя хоста: ", hostname)
        old_pass = urwid.Edit("Старый пароль: ", "", mask="*")
        new_pass = urwid.Edit("Новый пароль: ", "", mask="*")
        confirm_pass = urwid.Edit("Подтверждение: ", "", mask="*")
        def save_user(b):
            new_u = user_edit.get_edit_text()
            if new_u: self.config.change_username(new_u)
            new_h = host_edit.get_edit_text()
            if new_h: self.config.change_hostname(new_h)
            old = old_pass.get_edit_text()
            new = new_pass.get_edit_text()
            conf = confirm_pass.get_edit_text()
            if old and new and new == conf:
                self.config.change_password(old, new)
        save_btn = urwid.Button("Сохранить", on_press=save_user)
        logout_btn = urwid.Button("Выйти из системы", on_press=lambda b: self.logout_callback())
        return urwid.Pile([
            ('flow', user_edit),
            ('flow', host_edit),
            ('flow', urwid.Divider()),
            ('flow', urwid.Text("Смена пароля:")),
            ('flow', old_pass),
            ('flow', new_pass),
            ('flow', confirm_pass),
            ('flow', save_btn),
            ('flow', urwid.Divider()),
            ('flow', logout_btn),
        ])

    def build_system(self):
        root_path = self.config.data.get("root_path", "salvexos_root")
        info = f"ОС: SalvexOS 2026\nЯдро: 5.0\nПользователь: {self.config.data['username']}\nХост: {self.config.data['hostname']}\nТема: {self.config.data.get('theme', 'default')}\nКорневая папка: {root_path}"
        return urwid.Filler(urwid.Text(info, align='center'), valign='middle')

# ---- 7. Терминал ----
class TerminalFrame(urwid.Frame):
    def __init__(self, fs, user, hostname):
        self.fs = fs
        self.user = user
        self.hostname = hostname
        self.history = []
        self.hist_idx = 0
        self.output = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.input = urwid.Edit(f"{user}@{hostname}:~$ ")
        self.input_widget = urwid.AttrMap(self.input, 'edit', focus_map='edit focus')
        super().__init__(body=self.output, footer=self.input_widget)
        self.focus_part = 'footer'
        self.commands = {
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "pwd": self.cmd_pwd,
            "mkdir": self.cmd_mkdir,
            "touch": self.cmd_touch,
            "rm": self.cmd_rm,
            "rmdir": self.cmd_rmdir,
            "cat": self.cmd_cat,
            "echo": self.cmd_echo,
            "clear": self.cmd_clear,
            "help": self.cmd_help,
            "exit": self.cmd_exit,
            "cp": self.cmd_cp,
            "mv": self.cmd_mv,
            "find": self.cmd_find,
            "grep": self.cmd_grep,
            "date": self.cmd_date,
            "whoami": self.cmd_whoami,
            "hostname": self.cmd_hostname,
            "info": self.cmd_info,
        }
        self.aliases = {}
        self.running = True
        self.add_output("Добро пожаловать в терминал SalvexOS! Введите help для справки.")

    def add_output(self, text):
        self.output.body.append(urwid.Text(text))

    def keypress(self, size, key):
        if self.focus_part == 'footer':
            if key == 'enter':
                cmd = self.input.get_edit_text()
                self.input.set_edit_text("")
                self.history.append(cmd)
                self.hist_idx = len(self.history)
                self.execute(cmd)
                self.focus_part = 'footer'
            elif key == 'up':
                if self.hist_idx > 0:
                    self.hist_idx -= 1
                    self.input.set_edit_text(self.history[self.hist_idx])
            elif key == 'down':
                if self.hist_idx < len(self.history) - 1:
                    self.hist_idx += 1
                    self.input.set_edit_text(self.history[self.hist_idx])
                else:
                    self.hist_idx = len(self.history)
                    self.input.set_edit_text("")
            else:
                self.input.keypress(size, key)
        else:
            super().keypress(size, key)

    def execute(self, cmd):
        if not cmd.strip():
            return
        parts = cmd.split()
        cmd_name = parts[0]
        args = parts[1:]
        if cmd_name in self.aliases:
            cmd = self.aliases[cmd_name] + " " + " ".join(args)
            parts = cmd.split()
            cmd_name = parts[0]
            args = parts[1:]
        if cmd_name in self.commands:
            self.commands[cmd_name](args)
        else:
            self.add_output(f"Команда не найдена: {cmd_name}")

    def cmd_ls(self, args):
        path = args[0] if args else "."
        try:
            items = self.fs.list_dir(path)
            self.add_output("  ".join([name for name, _, _ in items]))
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_cd(self, args):
        if not args:
            self.fs.chdir("/home/" + self.user)
            self.update_prompt()
            return
        path = args[0]
        try:
            self.fs.chdir(path)
            self.update_prompt()
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def update_prompt(self):
        path = self.fs.get_current_path()
        self.input.set_edit_text(f"{self.user}@{self.hostname}:{path}$ ")

    def cmd_pwd(self, args):
        self.add_output(self.fs.get_current_path())

    def cmd_mkdir(self, args):
        if not args:
            self.add_output("Укажите имя")
            return
        try:
            self.fs.mkdir(".", args[0])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_touch(self, args):
        if not args:
            self.add_output("Укажите имя")
            return
        try:
            self.fs.touch(".", args[0])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_rm(self, args):
        if not args:
            self.add_output("Укажите файл")
            return
        try:
            self.fs.remove(args[0])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_rmdir(self, args):
        if not args:
            self.add_output("Укажите директорию")
            return
        try:
            self.fs.remove(args[0])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_cat(self, args):
        if not args:
            self.add_output("Укажите файл")
            return
        try:
            content = self.fs.read_file(args[0])
            self.add_output(content)
        except UnicodeDecodeError:
            self.add_output("Ошибка: файл бинарный, не может быть отображён как текст")
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_echo(self, args):
        if args:
            self.add_output(" ".join(args))

    def cmd_clear(self, args):
        self.output.body.clear()

    def cmd_help(self, args):
        help_text = """
Доступные команды:
  ls [путь]          - список файлов
  cd [путь]          - сменить директорию
  pwd                - текущий путь
  mkdir <имя>        - создать папку
  touch <имя>        - создать файл
  rm <файл>          - удалить файл
  rmdir <папка>      - удалить папку
  cat <файл>         - показать содержимое
  echo <текст>       - вывести текст
  clear              - очистить экран
  cp <src> <dst>     - копировать
  mv <src> <dst>     - переместить
  find <имя>         - найти файл
  grep <стр> <файл>  - поиск в файле
  date               - текущая дата
  whoami             - имя пользователя
  hostname           - имя хоста
  info               - информация о системе
  exit               - выйти из терминала
"""
        self.add_output(help_text)

    def cmd_exit(self, args):
        self.running = False
        self.add_output("Выход из терминала")

    def cmd_cp(self, args):
        if len(args) < 2:
            self.add_output("Использование: cp <источник> <назначение>")
            return
        try:
            self.fs.copy(args[0], args[1])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_mv(self, args):
        if len(args) < 2:
            self.add_output("Использование: mv <источник> <назначение>")
            return
        try:
            self.fs.copy(args[0], args[1])
            self.fs.remove(args[0])
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_find(self, args):
        if not args:
            self.add_output("Укажите имя")
            return
        pattern = args[0]
        results = []
        root = self.fs.root_path
        for dirpath, dirnames, filenames in os.walk(root):
            for fname in filenames + dirnames:
                if pattern in fname:
                    rel = os.path.relpath(os.path.join(dirpath, fname), root)
                    results.append("/" + rel.replace("\\", "/"))
        if results:
            self.add_output("\n".join(results))
        else:
            self.add_output("Ничего не найдено")

    def cmd_grep(self, args):
        if len(args) < 2:
            self.add_output("Использование: grep <строка> <файл>")
            return
        pattern, file = args[0], args[1]
        try:
            content = self.fs.read_file(file)
            for line in content.splitlines():
                if pattern in line:
                    self.add_output(line)
        except UnicodeDecodeError:
            self.add_output("Ошибка: файл бинарный")
        except Exception as e:
            self.add_output(f"Ошибка: {e}")

    def cmd_date(self, args):
        self.add_output(datetime.datetime.now().strftime("%c"))

    def cmd_whoami(self, args):
        self.add_output(self.user)

    def cmd_hostname(self, args):
        self.add_output(self.hostname)

    def cmd_info(self, args):
        info = f"SalvexOS 2026\nПользователь: {self.user}\nХост: {self.hostname}\nФайловая система: реальная (локальная папка)"
        self.add_output(info)

# ------------------------------------------------------------
# Рабочий стол (с диалогом завершения работы)
# ------------------------------------------------------------
class Desktop:
    def __init__(self, fs, config, main_loop, logout_callback, shutdown_callback):
        self.fs = fs
        self.config = config
        self.main_loop = main_loop
        self.logout_callback = logout_callback
        self.shutdown_callback = shutdown_callback
        self.windows = []
        self.active_idx = 0
        self.taskbar = None
        self.body = urwid.Filler(urwid.Text("Рабочий стол SalvexOS", align='center'), valign='middle')
        self.frame = None
        self.build_ui()
        self.update_clock()

    def build_ui(self):
        self.menu_btn = urwid.Button("Меню", on_press=self.show_menu)
        self.term_btn = urwid.Button("Терминал", on_press=self.launch_terminal)
        self.fm_btn = urwid.Button("Файлы", on_press=self.launch_filemanager)
        self.editor_btn = urwid.Button("Редактор", on_press=self.launch_editor)
        self.calc_btn = urwid.Button("Калькулятор", on_press=self.launch_calculator)
        self.cal_btn = urwid.Button("Календарь", on_press=self.launch_calendar)
        self.settings_btn = urwid.Button("Настройки", on_press=self.launch_settings)
        self.logout_btn = urwid.Button("Выход", on_press=self.show_shutdown_dialog)
        self.home_btn = urwid.Button("На рабочий стол", on_press=self.go_home)
        self.clock_text = urwid.Text("", align='right')
        buttons_col = urwid.Columns([
            self.menu_btn,
            self.term_btn,
            self.fm_btn,
            self.editor_btn,
            self.calc_btn,
            self.cal_btn,
            self.settings_btn,
            self.logout_btn,
            self.home_btn,
            self.clock_text,
        ])
        self.taskbar = urwid.AttrMap(buttons_col, 'footer')
        self.frame = urwid.Frame(body=self.body, footer=self.taskbar)

    def update_clock(self):
        now = datetime.datetime.now()
        self.clock_text.set_text(now.strftime("%H:%M:%S  %d.%m.%Y"))
        self.main_loop.set_alarm_in(1, lambda loop, data: self.update_clock())

    def show_menu(self, button):
        menu_items = [
            ("Терминал", self.launch_terminal),
            ("Файловый менеджер", self.launch_filemanager),
            ("Редактор", self.launch_editor),
            ("Калькулятор", self.launch_calculator),
            ("Календарь", self.launch_calendar),
            ("Настройки", self.launch_settings),
            ("Рабочий стол", self.go_home),
            ("Выход", self.show_shutdown_dialog),
        ]
        buttons = []
        for label, callback in menu_items:
            btn = urwid.Button(label, on_press=callback)
            buttons.append(urwid.AttrMap(btn, 'button', focus_map='button focus'))
        content = urwid.Pile(buttons)
        menu_frame = urwid.LineBox(content, title="Меню SalvexOS")
        self.add_window("Меню", menu_frame, None)

    def show_shutdown_dialog(self, button=None):
        def shutdown(btn):
            if self.shutdown_callback:
                self.shutdown_callback()
        def cancel(btn):
            self.close_active()
        dialog = FancyDialog(
            "Вы действительно хотите завершить работу?",
            [("Завершить работу", shutdown), ("Отмена", cancel)],
            title="Завершение работы"
        )
        self.add_window("Завершение работы", dialog, dialog)

    def launch_terminal(self, button):
        term = TerminalFrame(self.fs, self.config.data["username"], self.config.data["hostname"])
        self.add_window("Терминал", term, term)

    def launch_filemanager(self, button):
        fm = FileManagerFrame(self.fs, self.config, self.add_window, self.close_active)
        self.add_window("Файловый менеджер", fm, fm)

    def launch_editor(self, button):
        editor = EditorFrame(self.fs)
        self.add_window("Редактор", editor, editor)

    def launch_calculator(self, button):
        calc = CalculatorFrame()
        self.add_window("Калькулятор", calc, calc)

    def launch_calendar(self, button):
        cal = CalendarFrame()
        self.add_window("Календарь", cal, cal)

    def launch_settings(self, button):
        settings = SettingsFrame(self.config, self.fs, self.show_shutdown_dialog)
        self.add_window("Настройки", settings, settings)

    def go_home(self, button=None):
        self.windows.clear()
        self.active_idx = 0
        self.body = urwid.Filler(urwid.Text("Рабочий стол SalvexOS", align='center'), valign='middle')
        self.frame.body = self.body

    def add_window(self, title, widget, app_object):
        frame = urwid.LineBox(widget, title=title)
        self.windows.append((title, frame, app_object))
        self.active_idx = len(self.windows) - 1
        self.update_body()

    def update_body(self):
        if self.windows:
            title, frame, app = self.windows[self.active_idx]
            self.body = frame
        else:
            self.body = urwid.Filler(urwid.Text("Рабочий стол SalvexOS", align='center'), valign='middle')
        self.frame.body = self.body

    def close_active(self):
        if self.windows:
            del self.windows[self.active_idx]
            if self.active_idx >= len(self.windows):
                self.active_idx = len(self.windows) - 1
            self.update_body()

    def get_frame(self):
        return self.frame

# ------------------------------------------------------------
# Главный класс ОС
# ------------------------------------------------------------
class SalvexOS:
    def __init__(self):
        self.config = Config()
        self.fs = None
        self.palette = [
            ('body', 'black', 'light gray'),
            ('header', 'white', 'dark blue'),
            ('footer', 'white', 'dark blue'),
            ('button', 'black', 'light cyan'),
            ('button focus', 'white', 'dark cyan'),
            ('edit', 'black', 'white'),
            ('edit focus', 'white', 'dark blue'),
            ('progress', 'white', 'dark green'),
            ('label', 'light gray', 'default'),
            ('title', 'white,bold', 'default'),
        ]

    def run(self):
        if not self.config.is_installed():
            installer = Installer()
            installer.run()
        else:
            root_path = self.config.data.get("root_path", "salvexos_root")
            self.fs = FileSystem(root_path)
            username = self.config.data["username"]
            home = self.fs.get_home(username)
            self.fs.home_path = home
            self.fs.current_path = home
            self.main_loop = urwid.MainLoop(self.build_login(), palette=self.palette)
            self.main_loop.run()

    def build_login(self):
        txt = urwid.Text("Добро пожаловать в SalvexOS", align='center')
        user_label = urwid.Text(f"Пользователь: {self.config.data['username']}")
        pass_edit = urwid.Edit("Пароль: ", "", mask="*")
        btn = urwid.Button("Войти", on_press=self.do_login)
        btn_wrapped = urwid.AttrMap(btn, 'button', focus_map='button focus')
        pile = urwid.Pile([
            ('flow', txt),
            ('flow', user_label),
            ('flow', pass_edit),
            ('flow', btn_wrapped),
        ])
        self.login_edit = pass_edit
        return urwid.Filler(pile, valign='middle')

    def do_login(self, button):
        pwd = self.login_edit.get_edit_text()
        if self.config.check_password(pwd):
            desktop = Desktop(self.fs, self.config, self.main_loop, self.logout, self.shutdown)
            self.main_loop.widget = desktop.get_frame()
        else:
            error_filler = urwid.Filler(urwid.Text("Неверный пароль. Попробуйте снова.", align='center'), valign='middle')
            self.main_loop.widget = error_filler
            self.main_loop.set_alarm_in(2, lambda loop, data: setattr(loop, 'widget', self.build_login()))

    def logout(self):
        self.main_loop.widget = self.build_login()

    def shutdown(self):
        raise urwid.ExitMainLoop()

# ------------------------------------------------------------
# Запуск
# ------------------------------------------------------------
if __name__ == "__main__":
    os_ = SalvexOS()
    os_.run()