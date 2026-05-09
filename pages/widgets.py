import tkinter as tk


def primary_button(parent, text, command):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg="#2563eb",
        fg="#ffffff",
        activebackground="#1d4ed8",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=20,
        pady=11,
        font=("Helvetica", 12, "bold"),
        cursor="hand2",
    )


def success_button(parent, text, command):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg="#16a34a",
        fg="#ffffff",
        activebackground="#15803d",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=20,
        pady=11,
        font=("Helvetica", 12, "bold"),
        cursor="hand2",
    )


def secondary_button(parent, text, command):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg="#fee2e2",
        fg="#991b1b",
        activebackground="#fecaca",
        activeforeground="#7f1d1d",
        relief="flat",
        bd=0,
        padx=20,
        pady=11,
        font=("Helvetica", 12, "bold"),
        cursor="hand2",
    )
