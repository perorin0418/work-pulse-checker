from __future__ import annotations


def determine_result(user_submitted: bool, user_text: str, predicted_text: str) -> tuple[str, str]:
    if user_submitted:
        return user_text, "confirmed"
    return predicted_text, "auto_confirmed"


def truncate_for_button(text: str, max_length: int = 20) -> str:
    """履歴再利用ボタンに表示するラベル用に長いテキストを省略する。"""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def chunk_history_into_rows(items: list[str], items_per_row: int = 3) -> list[list[str]]:
    """履歴ボタンを複数行に折り返して配置するため、items_per_row件ずつに分割する。"""
    return [items[i : i + items_per_row] for i in range(0, len(items), items_per_row)]


def run_confirm_dialog(
    predicted_text: str,
    timeout_seconds: int = 300,
    history: list[str] | None = None,
) -> tuple[str, str]:
    """作業内容確認ダイアログを表示する。GUI依存のため自動テスト対象外(手動検証のみ)。

    history には本日すでに確定済みの作業内容（新しい順、重複除去済み）を渡す。
    各項目はボタンとして表示され、クリックすると入力欄にそのテキストが入る。
    """
    import tkinter as tk

    history = history or []
    history_rows = chunk_history_into_rows(history, items_per_row=3)

    result: dict = {"text": predicted_text, "status": "auto_confirmed"}

    root = tk.Tk()
    root.title("作業内容の確認")
    root.attributes("-topmost", True)
    root.geometry(f"480x{220 + 40 * len(history_rows)}" if history else "480x220")
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

    def use_history_text(text: str) -> None:
        entry.delete("1.0", "end")
        entry.insert("1.0", text)

    if history:
        history_frame = tk.Frame(root)
        history_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))

        tk.Label(history_frame, text="本日の記録から再利用:", anchor="w").pack(
            side="top", anchor="w"
        )

        for row_items in history_rows:
            row_frame = tk.Frame(history_frame)
            row_frame.pack(side="top", fill="x")
            for item in row_items:
                label = truncate_for_button(item)
                tk.Button(
                    row_frame,
                    text=label,
                    command=lambda item=item: use_history_text(item),
                ).pack(side="left", padx=(0, 4), pady=2)

    button_row = 3 if history else 2

    def on_confirm() -> None:
        text, status = determine_result(True, entry.get("1.0", "end").strip(), predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    tk.Button(root, text="確定", command=on_confirm).grid(row=button_row, column=0, pady=(4, 12))

    def on_timeout() -> None:
        text, status = determine_result(False, "", predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    root.after(timeout_seconds * 1000, on_timeout)
    root.bind("<Return>", lambda event: on_confirm())
    root.protocol("WM_DELETE_WINDOW", on_confirm)
    root.mainloop()

    return result["text"], result["status"]
