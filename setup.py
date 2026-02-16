import sys
from cx_Freeze import setup, Executable
import os

# Имя главного файла
main_script = "app.py"

# Список дополнительных файлов и папок, которые нужно включить
include_files = [
    ("poppler", "poppler"),
    # Добавь сюда другие нужные файлы/папки
]

# Опционально: если используешь иконку
icon_file = 'logo.ico'  # Например: "icon.ico"

# Опции для сборки
build_exe_options = {
    "packages": [
        "os",
        "tkinter",
        "PIL",
        "PyPDF2",
        "reportlab",
        "pdf2image",
    ],
    "include_files": include_files,
}

# Для Windows: добавляем base="Win32GUI" чтобы не было консоли
base = "Win32GUI"

setup(
    name="PDF подпись",
    version="1.0",
    description="Подписать pdf с помощью png",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            main_script,
            base=base,
            icon=icon_file
        )
    ]
)
