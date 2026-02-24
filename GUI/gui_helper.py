import tkinter as tk
from tkinter import messagebox, simpledialog

def _get_root():
    """Creates a hidden, always-on-top root window for dialogs."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    return root

def ask_yes_no(title, prompt, default=True):
    root = _get_root()
    # messagebox pauses execution until the user clicks Yes or No
    result = messagebox.askyesno(title, prompt, parent=root)
    root.destroy()
    return result

def ask_string(title, prompt):
    root = _get_root()
    result = simpledialog.askstring(title, prompt, parent=root)
    root.destroy()
    # Return empty string if user hits Cancel, mimicking an empty 'Enter' press
    return result if result is not None else ""

def ask_choice(title, prompt, choices, default=None):
    root = _get_root()
    root.deiconify()
    root.title(title)
    
    # Center the custom choice window
    w, h = 320, 150
    x = int(root.winfo_screenwidth()/2 - w/2)
    y = int(root.winfo_screenheight()/2 - h/2)
    root.geometry(f'{w}x{h}+{x}+{y}')
    root.attributes('-topmost', True)

    selection = tk.StringVar(value=default if default else choices[0])

    tk.Label(root, text=prompt, pady=15, font=("Arial", 10), wraplength=300).pack()

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="both", expand=True, pady=10, padx=10)

    def on_click(choice_val):
        selection.set(choice_val)
        root.destroy()

    for c in choices:
        btn = tk.Button(btn_frame, text=c.title(), command=lambda val=c: on_click(val))
        btn.pack(side="left", expand=True, fill="x", padx=5)

    root.wait_window()
    return selection.get()
