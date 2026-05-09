import tkinter as tk


class BasePage(tk.Frame):
    def __init__(self, parent, app, title, subtitle):
        super().__init__(parent, bg="#f7f8fa")
        self.app = app
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        tk.Label(
            self,
            text=title,
            bg="#f7f8fa",
            fg="#111827",
            font=("Helvetica", 26, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            self,
            text=subtitle,
            bg="#f7f8fa",
            fg="#4b5563",
            font=("Helvetica", 12),
        ).grid(row=1, column=0, sticky="w", pady=(6, 20))

        body = tk.Frame(
            self,
            bg="#ffffff",
            highlightbackground="#e5e7eb",
            highlightthickness=1,
        )
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        self.body = body

        self.log = tk.Text(
            body,
            height=10,
            wrap="word",
            bg="#111827",
            fg="#f9fafb",
            insertbackground="#f9fafb",
            relief="flat",
            padx=16,
            pady=14,
            font=("Menlo", 11),
        )
        self.log.grid(row=1, column=0, sticky="nsew")

    def refresh(self):
        pass

    def append_log(self, text):
        self.log.insert("end", text)
        self.log.see("end")
