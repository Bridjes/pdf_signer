import io
import sys
import fitz
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageEnhance, ImageFilter
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from .signature_crop_window import SignatureCropWindow


class PDFSignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Signature Professional")
        self.root.geometry("1280x850")
        
        # Убираем иконку перышка
        try:
            self.root.iconbitmap('')
        except:
            pass
        
        # Данные
        self.pdf_path = None
        self.signature_path = None
        self.pdf_images = []
        self.current_page = 0
        self.signature_img = None
        self.signature_photo = None
        
        # Позиция и размер подписи (в пикселях экрана для редактируемой подписи)
        self.sig_x = 100
        self.sig_y = 100
        self.sig_width = 150
        self.sig_height = 50
        self.scale_factor = 1.0
        self.zoom_level = 100
        
        # Список размещенных подписей (храним относительные координаты 0.0-1.0)
        self.placed_signatures = []
        
        # Флаг активной подписи
        self.active_signature = False
        
        # Перетаскивание
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Параметры скролла
        self.allow_auto_page_switch = False
        self.scroll_effort = 0
        self.effort_threshold = 3
        self.last_scroll_pos = 0.0
        
        self.setup_styles()
        self.create_menu()
        self.create_main_area()
        self.create_bottom_bar()

    def setup_styles(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except:
            pass
        self.style.configure("Bottom.TFrame", background="#f0f0f0")
        self.style.configure("Bottom.TLabel", background="#f0f0f0", font=("Segoe UI", 9))
        self.style.configure("Right.TFrame", background="#f5f5f5")

    def create_menu(self):
        self.menubar = tk.Menu(self.root)
        
        # Вкладка Файл
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Открыть PDF...", command=self.load_pdf, accelerator="Ctrl+O")
        file_menu.add_command(label="Сохранить как...", command=self.save_signed_pdf, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Закрыть файл", command=self.close_pdf, accelerator="Ctrl+W")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit, accelerator="Alt+F4")
        self.menubar.add_cascade(label="Файл", menu=file_menu)
        
        # Вкладка Вставить
        insert_menu = tk.Menu(self.menubar, tearoff=0)
        insert_menu.add_command(label="Создать подпись из фото...", command=self.create_signature)
        insert_menu.add_command(label="Загрузить готовую PNG...", command=self.load_signature, accelerator="Ctrl+L")
        self.menubar.add_cascade(label="Вставить", menu=insert_menu)
        
        # Вкладка Справка
        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self.show_about)
        self.menubar.add_cascade(label="Справка", menu=help_menu)
        
        self.root.config(menu=self.menubar)
        
        # Горячие клавиши
        self.root.bind("<Control-o>", lambda e: self.load_pdf())
        self.root.bind("<Control-s>", lambda e: self.save_signed_pdf())
        self.root.bind("<Control-w>", lambda e: self.close_pdf())
        self.root.bind("<Control-l>", lambda e: self.load_signature())
        self.root.bind("<Control-Return>", lambda e: self.place_signature())

    def create_main_area(self):
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Правая панель инструментов
        self.right_panel = ttk.Frame(self.main_container, style="Right.TFrame", width=250)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        self.right_panel.pack_propagate(False)
        
        # Контейнер для инструментов подписи
        self.signature_tools_frame = ttk.LabelFrame(self.right_panel, text=" Инструменты подписи ", padding="10")
        
        # Размер подписи
        ttk.Label(self.signature_tools_frame, text="Размер подписи:", 
                 font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(5, 5))
        self.size_scale = ttk.Scale(self.signature_tools_frame, from_=50, to=500, 
                                    command=self.resize_signature, orient=tk.HORIZONTAL)
        self.size_scale.set(150)
        self.size_scale.pack(fill=tk.X, pady=5)
        
        # Кнопка установки
        ttk.Button(self.signature_tools_frame, text="✓ Установить подпись на страницу", 
                  command=self.place_signature).pack(fill=tk.X, pady=10)
        
        ttk.Separator(self.signature_tools_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # Инструкция
        instruction_text = ("Перетащите подпись\n"
                          "в нужное место\n\n"
                          "Ctrl+Enter - установить\n"
                          "Колесо мыши - зум")
        ttk.Label(self.signature_tools_frame, text=instruction_text, 
                 font=("Segoe UI", 8), foreground="#666", justify=tk.LEFT).pack(anchor=tk.W, pady=5)

        # Canvas с прокруткой
        self.canvas = tk.Canvas(self.main_container, bg="#525659", highlightthickness=0, cursor="cross")
        self.v_scroll = ttk.Scrollbar(self.main_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.main_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.on_canvas_scroll_y, xscrollcommand=self.h_scroll.set)

        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Биндинги
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)

    def create_bottom_bar(self):
        self.bottom_bar = ttk.Frame(self.root, style="Bottom.TFrame", padding=(10, 5))
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Левая часть: Статус
        self.status_label = ttk.Label(self.bottom_bar, text="Готов к работе", style="Bottom.TLabel")
        self.status_label.pack(side=tk.LEFT)

        # Правая часть: Навигация и инструменты (упаковываем справа налево)
        
        # 1. Навигация
        self.nav_frame = ttk.Frame(self.bottom_bar, style="Bottom.TFrame")
        self.nav_frame.pack(side=tk.RIGHT, padx=10)
        
        ttk.Label(self.nav_frame, text="Стр:", style="Bottom.TLabel").pack(side=tk.LEFT, padx=(0, 3))
        self.page_var = tk.IntVar(value=1)
        self.page_spin = ttk.Spinbox(self.nav_frame, from_=1, to=1, textvariable=self.page_var, 
                                    width=5, command=self.change_page)
        self.page_spin.pack(side=tk.LEFT, padx=2)
        self.page_spin.bind("<Return>", lambda e: self.change_page())
        self.page_spin.bind("<KP_Enter>", lambda e: self.change_page())
        self.total_pages_label = ttk.Label(self.nav_frame, text="/ 0", style="Bottom.TLabel")
        self.total_pages_label.pack(side=tk.LEFT, padx=(2, 0))

        # 2. Зум (скрыт по умолчанию)
        self.zoom_frame = ttk.Frame(self.bottom_bar, style="Bottom.TFrame")
        ttk.Label(self.zoom_frame, text="Зум:", style="Bottom.TLabel").pack(side=tk.LEFT, padx=(0, 3))
        self.zoom_var = tk.IntVar(value=100)
        self.zoom_scale = ttk.Scale(self.zoom_frame, from_=50, to=200, variable=self.zoom_var, 
                                   command=self.change_zoom, length=120)
        self.zoom_scale.pack(side=tk.LEFT, padx=5)
        self.zoom_percent_label = ttk.Label(self.zoom_frame, text="100%", width=5, style="Bottom.TLabel")
        self.zoom_percent_label.pack(side=tk.LEFT)

    def toggle_tools(self):
        """Показывает или скрывает инструменты в зависимости от состояния"""
        if self.pdf_path:
            self.zoom_frame.pack(side=tk.RIGHT, padx=15)
            self.total_pages_label.config(text=f"/ {len(self.pdf_images)}")
            self.page_spin.config(to=len(self.pdf_images))
        else:
            self.zoom_frame.pack_forget()
            
        if self.active_signature:
            self.signature_tools_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        else:
            self.signature_tools_frame.pack_forget()

    def show_about(self):
        messagebox.showinfo("О программе", 
                          "PDF Signature Professional\n\n"
                          "Версия 2.0\n\n"
                          "Программа для добавления подписей в PDF документы\n"
                          "с возможностью создания и редактирования подписей.")

    def load_pdf(self):
        path = filedialog.askopenfilename(
            title="Открыть PDF файл",
            filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")]
        )
        if not path: return
        
        if self.pdf_path:
            response = messagebox.askyesno("Подтверждение", 
                                          "Закрыть текущий PDF и открыть новый?")
            if not response:
                return
            self.close_pdf()
        
        self.pdf_path = path
        try:
            doc = fitz.open(path)
            self.pdf_images = []
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                self.pdf_images.append(img)
            self.current_page = 0
            self.page_var.set(1)
            self.allow_auto_page_switch = False
            self.placed_signatures = []
            self.active_signature = False
            self.toggle_tools()
            self.display_page()
            self.root.after(500, lambda: setattr(self, 'allow_auto_page_switch', True))
            filename = path.split('/')[-1].split('\\')[-1]
            self.status_label.config(text=f"Открыт: {filename} ({len(self.pdf_images)} стр.)")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить PDF:\n{e}")

    def close_pdf(self):
        if not self.pdf_path:
            messagebox.showinfo("Информация", "PDF не загружен")
            return
        
        if self.active_signature or len(self.placed_signatures) > 0:
            response = messagebox.askyesno("Подтверждение", 
                                          "Закрыть файл? Несохраненные изменения будут потеряны.")
            if not response:
                return
        
        self.pdf_path = None
        self.pdf_images = []
        self.current_page = 0
        self.placed_signatures = []
        self.signature_img = None
        self.signature_photo = None
        self.active_signature = False
        self.page_var.set(1)
        self.total_pages_label.config(text="/ 0")
        self.toggle_tools()
        self.canvas.delete("all")
        self.status_label.config(text="Файл закрыт")

    def create_signature(self):
        source_path = filedialog.askopenfilename(
            title="Выберите изображение с подписью",
            filetypes=[("Изображения", "*.png;*.jpg;*.jpeg;*.bmp"), ("Все файлы", "*.*")]
        )
        
        if not source_path:
            return
        
        crop_window = SignatureCropWindow(self.root, source_path)
        self.root.wait_window(crop_window.window)

    def load_signature(self):
        path = filedialog.askopenfilename(
            title="Загрузить подпись",
            filetypes=[("PNG файлы", "*.png"), ("Все изображения", "*.png;*.jpg;*.jpeg")]
        )
        if not path: return
        
        self.signature_path = path
        self.signature_img = Image.open(path)
        aspect = self.signature_img.width / self.signature_img.height
        self.sig_width = int(self.size_scale.get())
        self.sig_height = int(self.sig_width / aspect)
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1:
            canvas_width = 800
        if canvas_height <= 1:
            canvas_height = 600
        
        self.sig_x = canvas_width // 2 - self.sig_width // 2
        self.sig_y = canvas_height // 2 - self.sig_height // 2
        
        self.active_signature = True
        
        # Сбрасываем кэш для принудительной перерисовки
        if hasattr(self, 'sig_x_rel'): del self.sig_x_rel
        if hasattr(self, 'sig_y_rel'): del self.sig_y_rel
        if hasattr(self, '_last_sig_size'): del self._last_sig_size
        if hasattr(self, '_last_state'): del self._last_state
        
        self.toggle_tools()
        self.display_page()
        self.status_label.config(text="Подпись загружена. Разместите её и нажмите Ctrl+Enter")

    def place_signature(self):
        if not self.pdf_path:
            messagebox.showwarning("Предупреждение", "Сначала загрузите PDF")
            return
        
        if not self.active_signature:
            messagebox.showwarning("Предупреждение", "Сначала загрузите подпись")
            return
        
        # Рассчитываем относительные координаты
        page_img = self.pdf_images[self.current_page]
        page_width = int(page_img.width * self.scale_factor)
        page_height = int(page_img.height * self.scale_factor)
        
        self.placed_signatures.append({
            'page': self.current_page,
            'x_rel': self.sig_x_rel if hasattr(self, 'sig_x_rel') else (self.sig_x - self.offset_x) / page_width,
            'y_rel': self.sig_y_rel if hasattr(self, 'sig_y_rel') else (self.sig_y - self.offset_y) / page_height,
            'w_rel': self.sig_width / page_width,
            'h_rel': self.sig_height / page_height
        })
        
        self.active_signature = False
        
        # Удаляем активную подпись с canvas
        self.canvas.delete("signature")
        
        # Сбрасываем кэш для следующей подписи
        if hasattr(self, 'sig_x_rel'): del self.sig_x_rel
        if hasattr(self, 'sig_y_rel'): del self.sig_y_rel
        if hasattr(self, '_last_sig_size'): del self._last_sig_size
        if hasattr(self, '_last_state'): del self._last_state
        
        self.toggle_tools()
        self.display_page()
        
        count = len(self.placed_signatures)
        self.status_label.config(text=f"Подпись установлена! Всего подписей: {count}")

    def on_canvas_scroll_y(self, *args):
        self.v_scroll.set(*args)
        
        if not self.pdf_images or len(self.pdf_images) <= 1:
            return
        
        scroll_pos = float(args[0])
        scroll_end = float(args[1])
        
        if 0.01 < scroll_pos and scroll_end < 0.99:
            self.scroll_effort = 0
            self.last_scroll_pos = scroll_pos
            return

        if not self.allow_auto_page_switch:
            return

    def change_zoom(self, value):
        self.zoom_level = int(float(value))
        self.zoom_percent_label.config(text=f"{self.zoom_level}%")
        self.allow_auto_page_switch = False
        self.display_page()
        self.root.after(200, lambda: setattr(self, 'allow_auto_page_switch', True))

    def change_page(self):
        if not self.pdf_images: return
        try:
            page_num = self.page_var.get()
            if 1 <= page_num <= len(self.pdf_images):
                self.current_page = page_num - 1
                self.allow_auto_page_switch = False
                
                if self.active_signature:
                    canvas_width = self.canvas.winfo_width()
                    canvas_height = self.canvas.winfo_height()
                    if canvas_width <= 1:
                        canvas_width = 800
                    if canvas_height <= 1:
                        canvas_height = 600
                    self.sig_x = canvas_width // 2 - self.sig_width // 2
                    self.sig_y = canvas_height // 2 - self.sig_height // 2
                
                self.display_page()
                self.canvas.yview_moveto(0)
                self.root.after(200, lambda: setattr(self, 'allow_auto_page_switch', True))
            else:
                messagebox.showwarning("Ошибка", f"Введите номер страницы от 1 до {len(self.pdf_images)}")
                self.page_var.set(self.current_page + 1)
        except:
            self.page_var.set(self.current_page + 1)

    def resize_signature(self, value):
        if not self.signature_img: return
        aspect = self.signature_img.width / self.signature_img.height
        self.sig_width = int(float(value))
        self.sig_height = int(self.sig_width / aspect)
        self.display_page()

    def display_page(self):
        if not self.pdf_images: return
        
        page_img = self.pdf_images[self.current_page]
        zoom_factor = self.zoom_level / 100.0
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1: canvas_width, canvas_height = 800, 600
        
        scale_x = canvas_width / page_img.width
        scale_y = canvas_height / page_img.height
        base_scale = min(scale_x, scale_y, 1.0)
        self.scale_factor = base_scale * zoom_factor
        
        new_width = int(page_img.width * self.scale_factor)
        new_height = int(page_img.height * self.scale_factor)
        
        self.offset_x = max((canvas_width - new_width) // 2, 0)
        self.offset_y = max((canvas_height - new_height) // 2, 0)

        # 1. Обновляем фоновую страницу (только если изменился масштаб или страница)
        if not hasattr(self, '_last_state') or self._last_state != (self.current_page, self.scale_factor):
            self.canvas.delete("all") # Полная очистка только при смене страницы/зума
            page_resized = page_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.page_photo = ImageTk.PhotoImage(page_resized)
            self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.page_photo, tags="page")
            self._last_state = (self.current_page, self.scale_factor)
            self._draw_placed_signatures(new_width, new_height)
        
        # 2. Обновляем активную подпись (без удаления всего остального)
        if self.active_signature and self.signature_img:
            if not hasattr(self, 'sig_x_rel'):
                self.sig_x_rel = 0.5 - (self.sig_width / new_width / 2)
                self.sig_y_rel = 0.5 - (self.sig_height / new_height / 2)
            
            self.sig_x = self.offset_x + (self.sig_x_rel * new_width)
            self.sig_y = self.offset_y + (self.sig_y_rel * new_height)
            
            # Если картинка подписи изменилась (размер), пересоздаем её
            if not hasattr(self, '_last_sig_size') or self._last_sig_size != (self.sig_width, self.sig_height):
                sig_resized = self.signature_img.resize((self.sig_width, self.sig_height), Image.Resampling.LANCZOS)
                self.signature_photo = ImageTk.PhotoImage(sig_resized)
                self.canvas.delete("signature")
                self.canvas.create_image(self.sig_x, self.sig_y, anchor=tk.NW, image=self.signature_photo, tags="signature")
                self.canvas.create_rectangle(self.sig_x, self.sig_y, self.sig_x + self.sig_width, self.sig_y + self.sig_height, 
                                            outline="#e74c3c", width=2, tags=("signature", "sig_rect"))
                self._last_sig_size = (self.sig_width, self.sig_height)
            else:
                # Если размер тот же, просто двигаем существующие объекты по тегу
                items = self.canvas.find_withtag("signature")
                if len(items) > 0:
                    self.canvas.coords(items[0], self.sig_x, self.sig_y)
                    rect_items = self.canvas.find_withtag("sig_rect")
                    if len(rect_items) > 0:
                        self.canvas.coords(rect_items[0], self.sig_x, self.sig_y, self.sig_x + self.sig_width, self.sig_y + self.sig_height)
        else:
            # Если подпись неактивна, удаляем её с canvas
            self.canvas.delete("signature")

        self.canvas.configure(scrollregion=(0, 0, max(canvas_width, new_width), max(canvas_height, new_height)))

    def _draw_placed_signatures(self, new_width, new_height):
        """Вспомогательный метод для отрисовки уже поставленных подписей"""
        self.placed_photos = []
        for sig in self.placed_signatures:
            if sig['page'] == self.current_page:
                px = self.offset_x + (sig['x_rel'] * new_width)
                py = self.offset_y + (sig['y_rel'] * new_height)
                pw = sig['w_rel'] * new_width
                ph = sig['h_rel'] * new_height
                
                sig_resized = self.signature_img.resize((int(pw), int(ph)), Image.Resampling.LANCZOS)
                sig_photo = ImageTk.PhotoImage(sig_resized)
                self.placed_photos.append(sig_photo)
                
                self.canvas.create_image(px, py, anchor=tk.NW, image=sig_photo, tags="placed_sig")
                self.canvas.create_rectangle(px, py, px + pw, py + ph, outline="#2ecc71", width=2, tags="placed_sig")

    def is_cursor_over_signature(self, x, y):
        if not self.active_signature: return False
        canvas_x, canvas_y = self.canvas.canvasx(x), self.canvas.canvasy(y)
        return (self.sig_x <= canvas_x <= self.sig_x + self.sig_width and self.sig_y <= canvas_y <= self.sig_y + self.sig_height)

    def on_mouse_down(self, event):
        if self.is_cursor_over_signature(event.x, event.y):
            self.dragging = True
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.drag_start_x, self.drag_start_y = canvas_x - self.sig_x, canvas_y - self.sig_y

    def on_mouse_drag(self, event):
        if self.dragging:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            new_x = canvas_x - self.drag_start_x
            new_y = canvas_y - self.drag_start_y
            
            page_img = self.pdf_images[self.current_page]
            new_width = int(page_img.width * self.scale_factor)
            new_height = int(page_img.height * self.scale_factor)
            
            # Обновляем только относительные координаты
            self.sig_x_rel = (new_x - self.offset_x) / new_width
            self.sig_y_rel = (new_y - self.offset_y) / new_height
            
            # Вызываем display_page, который теперь умеет двигать объекты без мерцания
            self.display_page()

    def on_mouse_up(self, event):
        self.dragging = False

    def on_mouse_wheel(self, event):
        if event.num == 4 or event.delta > 0: direction = -1
        elif event.num == 5 or event.delta < 0: direction = 1
        else: direction = 0
        
        if not self.allow_auto_page_switch:
            self.allow_auto_page_switch = True
        
        if event.state & 0x0004:
            new_zoom = max(50, min(200, self.zoom_level - direction * 10))
            self.zoom_var.set(new_zoom)
            self.change_zoom(new_zoom)
            return
        
        bbox = self.canvas.bbox("all")
        if bbox:
            content_h = bbox[3] - bbox[1]
            canvas_h = self.canvas.winfo_height()
            scroll_start, scroll_end = self.v_scroll.get()

            if content_h > canvas_h:
                if scroll_end >= 0.99 and direction > 0:
                    self.scroll_effort += 1
                    if self.scroll_effort >= self.effort_threshold:
                        self.go_next_page()
                    return
                elif scroll_start <= 0.01 and direction < 0:
                    self.scroll_effort += 1
                    if self.scroll_effort >= self.effort_threshold:
                        self.go_prev_page()
                    return
                else:
                    self.scroll_effort = 0
                    self.canvas.yview_scroll(direction, "units")
                    return
        
        if self.pdf_images:
            if direction > 0: self.go_next_page()
            elif direction < 0: self.go_prev_page()

    def go_next_page(self):
        if self.current_page < len(self.pdf_images) - 1:
            self.scroll_effort = 0
            self.current_page += 1
            self.page_var.set(self.current_page + 1)
            
            if self.active_signature:
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                if canvas_width <= 1:
                    canvas_width = 800
                if canvas_height <= 1:
                    canvas_height = 600
                self.sig_x = canvas_width // 2 - self.sig_width // 2
                self.sig_y = canvas_height // 2 - self.sig_height // 2
            
            self.display_page()
            self.canvas.yview_moveto(0)

    def go_prev_page(self):
        if self.current_page > 0:
            self.scroll_effort = 0
            self.current_page -= 1
            self.page_var.set(self.current_page + 1)
            
            if self.active_signature:
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                if canvas_width <= 1:
                    canvas_width = 800
                if canvas_height <= 1:
                    canvas_height = 600
                self.sig_x = canvas_width // 2 - self.sig_width // 2
                self.sig_y = canvas_height // 2 - self.sig_height // 2
            
            self.display_page()
            self.canvas.yview_moveto(1)

    def save_signed_pdf(self):
        if not self.pdf_path:
            messagebox.showwarning("Предупреждение", "Загрузите PDF")
            return
        
        if not self.signature_path:
            messagebox.showwarning("Предупреждение", "Загрузите подпись")
            return
        
        if len(self.placed_signatures) == 0:
            messagebox.showwarning("Предупреждение", "Установите хотя бы одну подпись")
            return
        
        output_path = filedialog.asksaveasfilename(
            title="Сохранить подписанный PDF",
            defaultextension=".pdf", 
            filetypes=[("PDF файлы", "*.pdf")]
        )
        if not output_path: return
        
        try:
            reader = PdfReader(self.pdf_path)
            writer = PdfWriter()
            
            signatures_by_page = {}
            for sig in self.placed_signatures:
                page_idx = sig['page']
                if page_idx not in signatures_by_page:
                    signatures_by_page[page_idx] = []
                signatures_by_page[page_idx].append(sig)
            
            for page_idx, page in enumerate(reader.pages):
                if page_idx in signatures_by_page:
                    page_width_pt = float(page.mediabox.width)
                    page_height_pt = float(page.mediabox.height)
                    
                    packet = io.BytesIO()
                    c = canvas.Canvas(packet, pagesize=(page_width_pt, page_height_pt))
                    
                    for sig in signatures_by_page[page_idx]:
                        # Используем относительные координаты для точного позиционирования в PDF
                        x_pt = sig['x_rel'] * page_width_pt
                        y_pt = page_height_pt - (sig['y_rel'] + sig['h_rel']) * page_height_pt
                        w_pt = sig['w_rel'] * page_width_pt
                        h_pt = sig['h_rel'] * page_height_pt
                        
                        c.drawImage(self.signature_path, x_pt, y_pt, width=w_pt, height=h_pt, mask='auto')
                    
                    c.showPage()
                    c.save()
                    packet.seek(0)
                    
                    overlay_reader = PdfReader(packet)
                    overlay_page = overlay_reader.pages[0]
                    page.merge_page(overlay_page)
                
                writer.add_page(page)
            
            with open(output_path, "wb") as f:
                writer.write(f)
            
            messagebox.showinfo("Успех", f"PDF с {len(self.placed_signatures)} подписями сохранён:\n{output_path}")
            self.status_label.config(text=f"Сохранено: {output_path.split('/')[-1].split(chr(92))[-1]}")
        
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{e}")