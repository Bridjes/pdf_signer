import io
import sys
import fitz
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageEnhance, ImageFilter
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


class PreviewWindow:
    """Окно предпросмотра с оптимизированной работой и агрессивной синей коррекцией"""
    def __init__(self, parent, cropped_image, crop_window):
        self.crop_window = crop_window
        self.original_cropped = cropped_image.copy()
        self.processed_image = None
        self.zoom_level = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 10.0
        self.blue_intensity = 0
        
        # Параметры обработки
        self.threshold_var = tk.IntVar(value=190)
        self.saturation_var = tk.IntVar(value=50)
        self.smooth_var = tk.BooleanVar(value=True)
        
        self.window = tk.Toplevel(parent)
        self.window.title("Предпросмотр результата")
        self.window.geometry("800x850")
        
        # Убираем иконку перышка
        try:
            self.window.iconbitmap('')
        except:
            pass
        
        # Главный контейнер
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Верхняя панель с кнопками
        top_panel = ttk.Frame(main_frame)
        top_panel.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(top_panel, text="Предпросмотр очищенной подписи", 
                font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(top_panel, text="💾 Сохранить", command=self.save_image).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_panel, text="🔍 100%", command=self.reset_zoom).pack(side=tk.RIGHT, padx=5)
        
        # Панель настройки обработки
        processing_panel = ttk.LabelFrame(main_frame, text=" Настройки обработки ", padding="10")
        processing_panel.pack(fill=tk.X, pady=5)
        
        # Яркость
        ttk.Label(processing_panel, text="Яркость:").pack(side=tk.LEFT, padx=5)
        ttk.Scale(processing_panel, from_=150, to=255, variable=self.threshold_var, 
                 length=120, command=self.on_processing_change).pack(side=tk.LEFT, padx=5)
        
        # Насыщенность
        ttk.Label(processing_panel, text="Насыщенность:").pack(side=tk.LEFT, padx=5)
        ttk.Scale(processing_panel, from_=10, to=100, variable=self.saturation_var, 
                 length=120, command=self.on_processing_change).pack(side=tk.LEFT, padx=5)
        
        # Сглаживание
        ttk.Checkbutton(processing_panel, text="Сглаживание", 
                       variable=self.smooth_var, command=self.on_processing_change).pack(side=tk.LEFT, padx=10)
        
        # Панель коррекции цвета
        color_panel = ttk.LabelFrame(main_frame, text=" Коррекция цвета ", padding="10")
        color_panel.pack(fill=tk.X, pady=5)
        
        ttk.Label(color_panel, text="Синий оттенок:").pack(side=tk.LEFT, padx=5)
        
        self.blue_var = tk.IntVar(value=0)
        self.blue_scale = ttk.Scale(color_panel, from_=0, to=100,
                                   variable=self.blue_var, length=200,
                                   command=self.on_blue_change)
        self.blue_scale.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(color_panel, text="🔄 Сброс", command=self.reset_all).pack(side=tk.LEFT, padx=10)
        
        self.color_info = ttk.Label(color_panel, text="Оригинал", 
                                   font=("Segoe UI", 9, "italic"))
        self.color_info.pack(side=tk.LEFT, padx=5)
        
        # Canvas с прокруткой
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#ecf0f1", relief="ridge", bd=2)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Биндинги для зума
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<Button-4>", self.on_zoom)
        self.canvas.bind("<Button-5>", self.on_zoom)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        
        # Кэш для оптимизации
        self.cached_zoom = None
        self.cached_photo = None
        self.cached_blue_image = {}
        self.cached_processed = {}
        self.update_timer = None
        
        # Первичная обработка
        self.apply_processing()
    
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
    
    def on_processing_change(self, value=None):
        if self.update_timer:
            self.window.after_cancel(self.update_timer)
        
        self.update_timer = self.window.after(150, self.apply_processing)
    
    def apply_processing(self):
        cache_key = (self.threshold_var.get(), self.saturation_var.get(), self.smooth_var.get())
        
        if cache_key in self.cached_processed:
            base_processed = self.cached_processed[cache_key].copy()
        else:
            base_processed = self.remove_white_background(
                self.original_cropped,
                self.threshold_var.get(),
                self.saturation_var.get(),
                self.smooth_var.get()
            )
            if len(self.cached_processed) > 5:
                self.cached_processed.clear()
            self.cached_processed[cache_key] = base_processed.copy()
        
        self.processed_image = self.make_more_blue(base_processed, self.blue_intensity)
        self.cached_zoom = None
        self.update_display()
    
    def make_more_blue(self, image, intensity):
        if intensity <= 0:
            return image.copy()

        ALPHA_MIN = 240
        BR_MAX = 110
        GAMMA = 1.8
        INK_BLUE = (15, 45, 220)

        cache_key = (id(image), intensity)
        if cache_key in self.cached_blue_image:
            return self.cached_blue_image[cache_key].copy()

        blue_factor = intensity / 100.0

        img = image.convert("RGBA")
        data = img.getdata()
        new_data = []

        for (r, g, b, a) in data:
            if a < ALPHA_MIN:
                new_data.append((r, g, b, a))
                continue

            br = (r + g + b) / 3.0
            if br > BR_MAX:
                new_data.append((r, g, b, a))
                continue

            dark = (BR_MAX - br) / BR_MAX
            dark = max(0.0, min(1.0, dark))
            strength = blue_factor * (dark ** GAMMA)

            nr = int(r * (1.0 - strength) + INK_BLUE[0] * strength)
            ng = int(g * (1.0 - strength) + INK_BLUE[1] * strength)
            nb = int(b * (1.0 - strength) + INK_BLUE[2] * strength)

            new_data.append((
                max(0, min(255, nr)),
                max(0, min(255, ng)),
                max(0, min(255, nb)),
                a
            ))

        img.putdata(new_data)

        if len(self.cached_blue_image) > 10:
            self.cached_blue_image.clear()
        self.cached_blue_image[cache_key] = img.copy()

        return img
    
    def on_blue_change(self, value):
        intensity = int(float(value))
        self.blue_intensity = intensity
        
        if intensity == 0:
            self.color_info.config(text="Оригинал")
        elif intensity < 30:
            self.color_info.config(text="Лёгкий синий")
        elif intensity < 70:
            self.color_info.config(text="Средний синий")
        else:
            self.color_info.config(text="Насыщенный синий")
        
        if self.update_timer:
            self.window.after_cancel(self.update_timer)
        
        self.update_timer = self.window.after(150, self.apply_blue_correction)
    
    def apply_blue_correction(self):
        cache_key = (self.threshold_var.get(), self.saturation_var.get(), self.smooth_var.get())
        
        if cache_key in self.cached_processed:
            base_processed = self.cached_processed[cache_key].copy()
        else:
            base_processed = self.remove_white_background(
                self.original_cropped,
                self.threshold_var.get(),
                self.saturation_var.get(),
                self.smooth_var.get()
            )
            self.cached_processed[cache_key] = base_processed.copy()
        
        self.processed_image = self.make_more_blue(base_processed, self.blue_intensity)
        self.cached_zoom = None
        self.update_display()
    
    def reset_all(self):
        self.blue_var.set(0)
        self.blue_intensity = 0
        self.threshold_var.set(190)
        self.saturation_var.set(50)
        self.smooth_var.set(True)
        self.color_info.config(text="Оригинал")
        self.cached_blue_image.clear()
        self.cached_processed.clear()
        self.apply_processing()
    
    def create_checkered_background(self, width, height):
        bg = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(bg)
        checker_size = 10
        
        for i in range(0, width, checker_size):
            for j in range(0, height, checker_size):
                if (i // checker_size + j // checker_size) % 2:
                    draw.rectangle([i, j, i + checker_size, j + checker_size], fill='#cccccc')
        
        return bg
    
    def update_display(self):
        if not self.processed_image:
            return
            
        if self.cached_zoom == self.zoom_level and self.cached_photo:
            return
        
        width = int(self.processed_image.width * self.zoom_level)
        height = int(self.processed_image.height * self.zoom_level)
        
        if self.zoom_level < 1.0:
            resample = Image.Resampling.BILINEAR
        else:
            resample = Image.Resampling.LANCZOS
        
        scaled_img = self.processed_image.resize((width, height), resample)
        
        bg = self.create_checkered_background(width + 40, height + 40)
        bg.paste(scaled_img, (20, 20), scaled_img)
        
        self.cached_photo = ImageTk.PhotoImage(bg)
        self.cached_zoom = self.zoom_level
        
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.cached_photo)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def on_zoom(self, event):
        if event.num == 4 or event.delta > 0:
            new_zoom = self.zoom_level * 1.15
        else:
            new_zoom = self.zoom_level / 1.15
        
        if self.min_zoom <= new_zoom <= self.max_zoom:
            self.zoom_level = new_zoom
            self.cached_zoom = None
            self.update_display()
    
    def reset_zoom(self):
        self.zoom_level = 1.0
        self.cached_zoom = None
        self.update_display()
    
    def save_image(self):
        save_path = filedialog.asksaveasfilename(
            title="Сохранить подпись как",
            defaultextension=".png",
            filetypes=[("PNG файлы", "*.png"), ("Все файлы", "*.*")]
        )
        
        if save_path:
            try:
                self.processed_image.save(save_path, "PNG")
                
                color_note = ""
                if self.blue_intensity > 0:
                    color_note = f" (синий оттенок: {self.blue_intensity}%)"
                
                messagebox.showinfo("Успех", f"Подпись сохранена{color_note}:\n{save_path}")
                
                # Закрываем оба окна
                self.window.destroy()
                if self.crop_window and self.crop_window.window.winfo_exists():
                    self.crop_window.window.destroy()
                    
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")