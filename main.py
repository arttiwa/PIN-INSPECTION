def main():
    try:
        from pages.app import PinInspectionUI
    except ModuleNotFoundError as exc:
        if exc.name == "_tkinter":
            print("Tkinter is not installed for this Python interpreter.")
            print("On macOS with Homebrew Python, run:")
            print("  brew install python-tk@3.13")
            print("Then run this app again from the same .venv.")
            return 1
        raise

    app = PinInspectionUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
