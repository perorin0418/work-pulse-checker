from __future__ import annotations


def determine_result(user_submitted: bool, user_text: str, predicted_text: str) -> tuple[str, str]:
    if user_submitted:
        return user_text, "confirmed"
    return predicted_text, "auto_confirmed"


def run_confirm_dialog(predicted_text: str, timeout_seconds: int = 300) -> tuple[str, str]:
    """作業内容確認ダイアログを表示する。GUI依存のため自動テスト対象外(手動検証のみ)。"""
    import tkinter as tk

    result: dict = {"text": predicted_text, "status": "auto_confirmed"}

    root = tk.Tk()
    root.title("作業内容の確認")
    root.attributes("-topmost", True)
    root.geometry("480x220")
    root.minsize(320, 160)
    root.resizable(True, True)

    root.rowconfigure(1, weight=1)
    root.columnconfigure(0, weight=1)

    tk.Label(root, text="直近30分の作業内容を確認・編集してください").grid(
        row=0, column=0, sticky="w", padx=12, pady=(12, 4)
    )

    entry = tk.Text(root, wrap="word")
    entry.insert("1.0", predicted_text)
    entry.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)

    def on_confirm() -> None:
        text, status = determine_result(True, entry.get("1.0", "end").strip(), predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    tk.Button(root, text="確定", command=on_confirm).grid(row=2, column=0, pady=(4, 12))

    def on_timeout() -> None:
        text, status = determine_result(False, "", predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    root.after(timeout_seconds * 1000, on_timeout)
    root.bind("<Return>", lambda event: on_confirm())
    root.protocol("WM_DELETE_WINDOW", on_confirm)
    root.mainloop()

    return result["text"], result["status"]
