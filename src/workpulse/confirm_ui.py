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
    from tkinter import ttk

    from workpulse.theme import (
        COLOR_BG,
        COLOR_BORDER,
        COLOR_SURFACE,
        COLOR_TEXT,
        COLOR_TEXT_MUTED,
        FONT_NORMAL,
        FONT_SMALL,
        FONT_TITLE,
        apply_ttk_theme,
    )

    history = history or []
    history_rows = chunk_history_into_rows(history, items_per_row=3)

    result: dict = {"text": predicted_text, "status": "auto_confirmed"}

    root = tk.Tk()
    root.title("作業内容の確認")
    root.attributes("-topmost", True)
    root.configure(bg=COLOR_BG)
    root.geometry(f"520x{260 + 44 * len(history_rows)}" if history else "520x260")
    root.minsize(360, 200)
    root.resizable(True, True)

    apply_ttk_theme(root)

    root.rowconfigure(2, weight=1)
    root.columnconfigure(0, weight=1)

    container = tk.Frame(root, bg=COLOR_BG, padx=20, pady=18)
    container.grid(row=0, column=0, rowspan=5, sticky="nsew")
    container.rowconfigure(2, weight=1)
    container.columnconfigure(0, weight=1)

    tk.Label(
        container,
        text="直近30分の作業内容を確認・編集してください",
        bg=COLOR_BG,
        fg=COLOR_TEXT,
        font=FONT_TITLE,
        anchor="w",
    ).grid(row=0, column=0, sticky="w", pady=(0, 12))

    entry_border = tk.Frame(container, bg=COLOR_BORDER, padx=1, pady=1)
    entry_border.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
    entry_border.rowconfigure(0, weight=1)
    entry_border.columnconfigure(0, weight=1)
    container.rowconfigure(1, weight=1)

    entry = tk.Text(
        entry_border,
        wrap="word",
        bg=COLOR_SURFACE,
        fg=COLOR_TEXT,
        insertbackground=COLOR_TEXT,
        relief="flat",
        font=FONT_NORMAL,
        padx=12,
        pady=10,
        borderwidth=0,
        highlightthickness=0,
    )
    entry.insert("1.0", predicted_text)
    entry.grid(row=0, column=0, sticky="nsew")

    def use_history_text(text: str) -> None:
        entry.delete("1.0", "end")
        entry.insert("1.0", text)

    next_row = 2
    if history:
        history_frame = tk.Frame(container, bg=COLOR_BG)
        history_frame.grid(row=next_row, column=0, sticky="ew", pady=(0, 8))
        next_row += 1

        tk.Label(
            history_frame,
            text="本日の記録から再利用",
            anchor="w",
            bg=COLOR_BG,
            fg=COLOR_TEXT_MUTED,
            font=FONT_SMALL,
        ).pack(side="top", anchor="w", pady=(0, 6))

        for row_items in history_rows:
            row_frame = tk.Frame(history_frame, bg=COLOR_BG)
            row_frame.pack(side="top", fill="x", pady=2)
            for item in row_items:
                label = truncate_for_button(item)
                ttk.Button(
                    row_frame,
                    text=label,
                    style="History.TButton",
                    command=lambda item=item: use_history_text(item),
                ).pack(side="left", padx=(0, 6))

    def on_confirm() -> None:
        text, status = determine_result(True, entry.get("1.0", "end").strip(), predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    button_row = tk.Frame(container, bg=COLOR_BG)
    button_row.grid(row=next_row, column=0, sticky="e", pady=(4, 0))
    ttk.Button(button_row, text="確定", style="Modern.TButton", command=on_confirm).pack()

    def on_timeout() -> None:
        text, status = determine_result(False, "", predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    root.after(timeout_seconds * 1000, on_timeout)
    root.bind("<Return>", lambda event: on_confirm())
    root.protocol("WM_DELETE_WINDOW", on_confirm)
    root.mainloop()

    return result["text"], result["status"]
