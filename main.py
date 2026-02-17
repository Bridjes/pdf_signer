"""
Точка входа в приложение PDF Signature Tool
"""
import tkinter as tk
from gui import PDFSignerApp

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFSignerApp(root)
    root.mainloop()
