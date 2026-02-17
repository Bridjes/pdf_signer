import io
import sys
import fitz
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageEnhance, ImageFilter
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from .preview_window import PreviewWindow


class SignatureCropWindow:
    """Окно для выделения области подписи с оптимизированным масштабированием"""
    def __init__(self, parent, image_path):
        self.result = None
        self.image_path = image_path
        self.original_image = Image.open(image_path).convert("RGBA")
        
        # Параметры масштабирования
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        
        # Кэш для ускорения масштабирования
        self.cached_zoom = None
        self.cached_photo = None
        
        self.window = tk.Toplevel(parent)
        self.window.title("Редактор подписи")
        self.window.geometry("1000x850")
        
        # Убираем иконку перышка
        try:
            self.window.iconbitmap('')
        except:
            pass
        
        self.window.grab_set()
        
        # Главный контейнер
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Инструкция
        instruction = tk.Label(main_frame, 
                              text="Выделение: ЛКМ | Зум: Колесо мыши | Перемещение: ПКМ",
                              font=("Segoe UI", 10), bg="#34495e", fg="white", pady=8)
        instruction.pack(fill=tk.X, pady=(0, 10))
        
        # Кнопки
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="🍳 Предпросмотр", command=self.show_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 Сброс", command=self.reset_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        # Canvas с прокруткой
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#ecf0f1", relief="ridge", bd=2, cursor="crosshair")
        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Переменные состояния
        self.selection_start = None
        self.selection_rect = None
        self.selection_coords_orig = None
        self.preview_window = None
        
        # Отрисовка
        self.update_canvas_image()
        
        # Биндинги
        self.canvas.bind("<ButtonPress-1>", self.on_selection_start)
        self.canvas.bind("<B1-Motion>", self.on_selection_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_selection_end)
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<Button-4>", self.on_zoom)
        self.canvas.bind("<Button-5>", self.on_zoom)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        
        self.zoom_timer = None

    def update_canvas_image(self, force=False):
        if not force and self.cached_zoom == self.zoom_level and self.cached_photo:
            return
        
        width = int(self.original_image.width * self.zoom_level)
        height = int(self.original_image.height * self.zoom_level)
        
        if self.zoom_level < 1.0:
            resample = Image.Resampling.BILINEAR
        else:
            resample = Image.Resampling.LANCZOS
        
        resized = self.original_image.resize((width, height), resample)
        self.cached_photo = ImageTk.PhotoImage(resized)
        self.cached_zoom = self.zoom_level
        
        self.canvas.delete("image")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.cached_photo, tags="image")
        self.canvas.tag_lower("image")
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_zoom(self, event):
        if event.num == 4 or event.delta > 0:
            new_zoom = self.zoom_level * 1.15
        else:
            new_zoom = self.zoom_level / 1.15
        
        if self.min_zoom <= new_zoom <= self.max_zoom:
            self.zoom_level = new_zoom
            if self.zoom_timer:
                self.window.after_cancel(self.zoom_timer)
            self.zoom_timer = self.window.after(100, lambda: self.update_canvas_image(force=True))

    def reset_selection(self):
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
        self.selection_rect = None
        self.selection_coords_orig = None
        self.selection_start = None

    def on_selection_start(self, event):
        self.selection_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)

    def on_selection_drag(self, event):
        if not self.selection_start: return
        cur_x, cur_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.selection_rect: 
            self.canvas.delete(self.selection_rect)
        self.selection_rect = self.canvas.create_rectangle(
            self.selection_start[0], self.selection_start[1], cur_x, cur_y,
            outline="#e74c3c", width=2, dash=(4, 4))

    def on_selection_end(self, event):
        if not self.selection_start: return
        end_x, end_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        x1 = min(self.selection_start[0], end_x)
        y1 = min(self.selection_start[1], end_y)
        x2 = max(self.selection_start[0], end_x)
        y2 = max(self.selection_start[1], end_y)
        
        self.selection_coords_orig = (
            int(x1 / self.zoom_level),
            int(y1 / self.zoom_level),
            int(x2 / self.zoom_level),
            int(y2 / self.zoom_level)
        )

    def remove_white_background(self, image, brightness_threshold, saturation_threshold, smooth=True):
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        img = image.convert("RGBA")
        data = img.getdata()
        new_data = []
        
        for item in data:
            r, g, b, a = item
            brightness = (r + g + b) / 3
            max_c, min_c = max(r, g, b), min(r, g, b)
            saturation = max_c - min_c
            is_blue = (b > r + 5) and (b > g + 5)
            
            if brightness > brightness_threshold:
                new_data.append((255, 255, 255, 0))
            elif saturation < saturation_threshold and brightness > 120:
                new_data.append((255, 255, 255, 0))
            elif is_blue or brightness < 160:
                new_data.append(item)
            else:
                new_data.append((255, 255, 255, 0))
        
        img.putdata(new_data)
        
        if smooth:
            img = img.filter(ImageFilter.MedianFilter(size=3))
            img = img.filter(ImageFilter.SMOOTH)
        
        return img

    def show_preview(self):
        if not self.selection_coords_orig:
            messagebox.showwarning("Внимание", "Сначала выделите область!")
            return
        
        x1, y1, x2, y2 = self.selection_coords_orig
        
        if x2 - x1 < 10 or y2 - y1 < 10:
            messagebox.showwarning("Внимание", "Выделенная область слишком мала!")
            return
        
        cropped = self.original_image.crop((x1, y1, x2, y2))
        
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        
        self.preview_window = PreviewWindow(self.window, cropped, self)

    def cancel(self):
        self.result = None
        self.window.destroy()
