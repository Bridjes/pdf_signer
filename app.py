import io
import sys
import fitz
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


class PDFSignerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Подписант")
        self.root.geometry("1200x800")
        
        # Данные
        self.pdf_path = None
        self.signature_path = None
        self.pdf_images = []
        self.current_page = 0
        self.signature_img = None
        self.signature_photo = None
        
        # Позиция и размер подписи
        self.sig_x = 100
        self.sig_y = 100
        self.sig_width = 150
        self.sig_height = 50
        self.scale_factor = 1.0
        self.zoom_level = 100
        
        # Список размещенных подписей: [{page, x, y, width, height}, ...]
        self.placed_signatures = []
        
        # Флаг активной подписи (есть ли текущая редактируемая подпись)
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
        
        self.create_widgets()
    
    def create_widgets(self):
        # Верхняя панель - строка 1
        top_frame1 = tk.Frame(self.root)
        top_frame1.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))
        
        tk.Button(top_frame1, text="Открыть PDF", command=self.load_pdf).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame1, text="Закрыть PDF", command=self.close_pdf).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame1, text="Загрузить подпись", command=self.load_signature).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame1, text="✓ Установить", command=self.place_signature, 
                  bg="#4CAF50", fg="white", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame1, text="Сохранить PDF", command=self.save_signed_pdf, 
                  bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame1, text="Закрыть PDF", command=self.close_pdf,
                  bg="#F75C5C", fg="white").pack(side=tk.LEFT, padx=5)
        
        # Выбор страницы
        tk.Label(top_frame1, text="Стр:").pack(side=tk.LEFT, padx=(20, 5))
        self.page_var = tk.IntVar(value=1)
        self.page_spinbox = tk.Spinbox(top_frame1, from_=1, to=1, textvariable=self.page_var, 
                                       width=5, command=self.change_page)
        self.page_spinbox.pack(side=tk.LEFT, padx=5)
        
        self.page_spinbox.bind("<Return>", lambda e: self.change_page())
        self.page_spinbox.bind("<KP_Enter>", lambda e: self.change_page())
        
        # Верхняя панель - строка 2
        top_frame2 = tk.Frame(self.root)
        top_frame2.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))
        
        # Масштаб документа
        tk.Label(top_frame2, text="Масштаб:").pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(top_frame2, text="-", command=self.zoom_out, width=2).pack(side=tk.LEFT, padx=2)
        self.zoom_var = tk.IntVar(value=100)
        self.zoom_scale = tk.Scale(top_frame2, from_=50, to=200, orient=tk.HORIZONTAL,
                                   variable=self.zoom_var, command=self.change_zoom, 
                                   length=120, showvalue=True)
        self.zoom_scale.pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame2, text="+", command=self.zoom_in, width=2).pack(side=tk.LEFT, padx=2)
        tk.Label(top_frame2, text="%").pack(side=tk.LEFT)
        
        # Размер подписи
        tk.Label(top_frame2, text="Размер подписи:").pack(side=tk.LEFT, padx=(20, 5))
        self.size_scale = tk.Scale(top_frame2, from_=50, to=500, orient=tk.HORIZONTAL, 
                                   command=self.resize_signature, length=120)
        self.size_scale.set(150)
        self.size_scale.pack(side=tk.LEFT, padx=5)
        
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(canvas_frame, bg="white", cursor="cross")
        self.v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=self.on_canvas_scroll_y, xscrollcommand=self.h_scroll.set)

        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        
        self.status_label = tk.Label(self.root, text="Загрузите PDF и подпись", 
                                     bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
    
    def close_pdf(self):
        """Закрыть текущий PDF и очистить все данные"""
        if not self.pdf_path:
            messagebox.showinfo("Информация", "PDF не загружен")
            return
        
        # Спрашиваем подтверждение, если есть неустановленные подписи
        if self.active_signature:
            response = messagebox.askyesno("Подтверждение", 
                                          "У вас есть неустановленная подпись. Закрыть файл?")
            if not response:
                return
        
        # Очищаем все данные
        self.pdf_path = None
        self.pdf_images = []
        self.current_page = 0
        self.placed_signatures = []
        self.signature_img = None
        self.signature_photo = None
        self.active_signature = False
        self.page_spinbox.config(to=1)
        self.page_var.set(1)
        self.canvas.delete("all")
        self.status_label.config(text="PDF закрыт. Загрузите новый файл")
        messagebox.showinfo("Успех", "PDF закрыт")
    
    def place_signature(self):
        """Подтвердить установку текущей подписи"""
        if not self.pdf_path:
            messagebox.showwarning("Предупреждение", "Сначала загрузите PDF")
            return
        
        if not self.active_signature:
            messagebox.showwarning("Предупреждение", "Сначала загрузите подпись")
            return
        
        # Сохраняем текущую позицию и размер подписи
        self.placed_signatures.append({
            'page': self.current_page,
            'x': self.sig_x,
            'y': self.sig_y,
            'width': self.sig_width,
            'height': self.sig_height
        })
        
        # Убираем активную подпись (она теперь установлена)
        self.active_signature = False
        
        # Обновляем отображение
        self.display_page()
        
        count = len(self.placed_signatures)
        self.status_label.config(text=f"Подпись установлена! Всего подписей: {count}")
        messagebox.showinfo("Успех", f"Подпись #{count} установлена на странице {self.current_page + 1}")
    
    def on_canvas_scroll_y(self, *args):
        """Обработчик вертикальной прокрутки с защитой от случайного переключения"""
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
        
    def zoom_in(self):
        new_zoom = min(200, self.zoom_var.get() + 10)
        self.zoom_var.set(new_zoom)
        self.change_zoom(new_zoom)
    
    def zoom_out(self):
        new_zoom = max(50, self.zoom_var.get() - 10)
        self.zoom_var.set(new_zoom)
        self.change_zoom(new_zoom)
    
    def change_zoom(self, value):
        self.zoom_level = int(float(value))
        self.allow_auto_page_switch = False
        self.display_page()
        self.root.after(200, lambda: setattr(self, 'allow_auto_page_switch', True))
    
    def load_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path: return
        
        # Если уже открыт PDF, предлагаем закрыть
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
            self.page_spinbox.config(to=len(self.pdf_images))
            self.page_var.set(1)
            self.allow_auto_page_switch = False
            self.placed_signatures = []
            self.active_signature = False
            self.display_page()
            self.root.after(500, lambda: setattr(self, 'allow_auto_page_switch', True))
            self.status_label.config(text=f"PDF загружен: {len(self.pdf_images)} страниц")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить PDF:\n{e}")
    
    def load_signature(self):
        path = filedialog.askopenfilename(filetypes=[("PNG files", "*.png"), ("All images", "*.png;*.jpg;*.jpeg")])
        if not path: return
        
        self.signature_path = path
        self.signature_img = Image.open(path)
        aspect = self.signature_img.width / self.signature_img.height
        self.sig_width = int(self.size_scale.get())
        self.sig_height = int(self.sig_width / aspect)
        
        # Новая подпись появляется в центре текущей страницы
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1:
            canvas_width = 800
        if canvas_height <= 1:
            canvas_height = 600
        
        # Позиционируем в центре видимой области
        self.sig_x = canvas_width // 2 - self.sig_width // 2
        self.sig_y = canvas_height // 2 - self.sig_height // 2
        
        # Активируем редактируемую подпись
        self.active_signature = True
        
        self.display_page()
        self.status_label.config(text=f"Подпись загружена. Разместите её и нажмите '✓ Установить'")
    
    def change_page(self):
        if not self.pdf_images: return
        try:
            page_num = self.page_var.get()
            if 1 <= page_num <= len(self.pdf_images):
                self.current_page = page_num - 1
                self.allow_auto_page_switch = False
                
                # Если есть активная подпись, перемещаем её на новую страницу
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
        self.canvas.delete("all")
        page_img = self.pdf_images[self.current_page]
        zoom_factor = self.zoom_level / 100.0
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 800, 600
        
        scale_x = canvas_width / page_img.width
        scale_y = canvas_height / page_img.height
        base_scale = min(scale_x, scale_y, 1.0)
        self.scale_factor = base_scale * zoom_factor
        
        new_width = int(page_img.width * self.scale_factor)
        new_height = int(page_img.height * self.scale_factor)
        page_resized = page_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.page_photo = ImageTk.PhotoImage(page_resized)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.page_photo, tags="page")
        
        # Отображаем все установленные подписи на текущей странице (зеленые рамки)
        placed_photos = []
        for sig in self.placed_signatures:
            if sig['page'] == self.current_page:
                sig_resized = self.signature_img.resize((sig['width'], sig['height']), Image.Resampling.LANCZOS)
                sig_photo = ImageTk.PhotoImage(sig_resized)
                placed_photos.append(sig_photo)
                
                self.canvas.create_image(sig['x'], sig['y'], anchor=tk.NW, image=sig_photo, tags="placed_sig")
                self.canvas.create_rectangle(sig['x'], sig['y'], 
                                            sig['x'] + sig['width'], 
                                            sig['y'] + sig['height'],
                                            outline="green", width=2, tags="placed_sig")
        
        # Сохраняем ссылки на изображения
        self.placed_photos = placed_photos
        
        # Отображаем текущую (редактируемую) подпись (красная рамка)
        if self.active_signature and self.signature_img:
            sig_resized = self.signature_img.resize((self.sig_width, self.sig_height), Image.Resampling.LANCZOS)
            self.signature_photo = ImageTk.PhotoImage(sig_resized)
            self.canvas.create_image(self.sig_x, self.sig_y, anchor=tk.NW, image=self.signature_photo, tags="signature")
            self.canvas.create_rectangle(self.sig_x, self.sig_y, self.sig_x + self.sig_width, self.sig_y + self.sig_height, 
                                        outline="red", width=3, tags="signature")
        
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # Подсчитываем подписи на текущей странице
        sigs_on_page = sum(1 for sig in self.placed_signatures if sig['page'] == self.current_page)
        status_text = f"Страница {self.current_page + 1} из {len(self.pdf_images)}"
        if sigs_on_page > 0:
            status_text += f" | Подписей на странице: {sigs_on_page}"
        if len(self.placed_signatures) > 0:
            status_text += f" | Всего подписей: {len(self.placed_signatures)}"
        self.status_label.config(text=status_text)
    
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
            self.sig_x, self.sig_y = canvas_x - self.drag_start_x, canvas_y - self.drag_start_y
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
            
            # Если есть активная подпись, перемещаем её на новую страницу
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
            
            # Если есть активная подпись, перемещаем её на новую страницу
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
        
        output_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not output_path: return
        
        try:
            reader = PdfReader(self.pdf_path)
            writer = PdfWriter()
            
            # Группируем подписи по страницам
            signatures_by_page = {}
            for sig in self.placed_signatures:
                page_idx = sig['page']
                if page_idx not in signatures_by_page:
                    signatures_by_page[page_idx] = []
                signatures_by_page[page_idx].append(sig)
            
            # Обрабатываем каждую страницу
            for page_idx, page in enumerate(reader.pages):
                if page_idx in signatures_by_page:
                    # Создаем overlay для этой страницы
                    page_width_pt = float(page.mediabox.width)
                    page_height_pt = float(page.mediabox.height)
                    
                    packet = io.BytesIO()
                    c = canvas.Canvas(packet, pagesize=(page_width_pt, page_height_pt))
                    
                    # Добавляем все подписи на эту страницу
                    for sig in signatures_by_page[page_idx]:
                        page_img = self.pdf_images[page_idx]
                        pdf_scale_x = page_width_pt / (page_img.width * self.scale_factor)
                        pdf_scale_y = page_height_pt / (page_img.height * self.scale_factor)
                        
                        x_pt = sig['x'] * pdf_scale_x
                        y_pt = page_height_pt - (sig['y'] + sig['height']) * pdf_scale_y
                        w_pt = sig['width'] * pdf_scale_x
                        h_pt = sig['height'] * pdf_scale_y
                        
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
            self.status_label.config(text=f"Сохранено: {output_path}")
        
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PDFSignerApp(root)
    root.mainloop()
