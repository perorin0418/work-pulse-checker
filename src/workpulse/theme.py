from __future__ import annotations

"""アプリ全体で共有するモダンUIテーマ定義。GUI依存のため自動テスト対象外。"""

FONT_FAMILY = "Yu Gothic UI"
FONT_NORMAL = (FONT_FAMILY, 11)
FONT_BOLD = (FONT_FAMILY, 11, "bold")
FONT_TITLE = (FONT_FAMILY, 13, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_LARGE_BOLD = (FONT_FAMILY, 30, "bold")

# ダーク基調 + アクセントカラーのモダンパレット
COLOR_BG = "#1B1D2A"           # ウィンドウ背景（ダークスレート）
COLOR_SURFACE = "#242737"      # カード/入力欄の面
COLOR_SURFACE_ALT = "#2C3044"  # 補助面（履歴ボタン等）
COLOR_BORDER = "#3A3E56"
COLOR_TEXT = "#F1F2F6"
COLOR_TEXT_MUTED = "#9598B0"
COLOR_ACCENT = "#6C63FF"       # プライマリアクセント（紫系）
COLOR_ACCENT_HOVER = "#8079FF"
COLOR_ACCENT_TEXT = "#FFFFFF"
COLOR_WARN_ACCENT = "#FF8C42"  # カウントダウン用の暖色アクセント
COLOR_WARN_TEXT = "#FFD166"


def apply_ttk_theme(root) -> "object":
    """ttk.Style にモダンなフラットテーマを適用して返す。"""
    from tkinter import ttk

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        "Modern.TButton",
        background=COLOR_ACCENT,
        foreground=COLOR_ACCENT_TEXT,
        font=FONT_BOLD,
        padding=(18, 8),
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Modern.TButton",
        background=[("active", COLOR_ACCENT_HOVER), ("pressed", COLOR_ACCENT_HOVER)],
    )

    style.configure(
        "History.TButton",
        background=COLOR_SURFACE_ALT,
        foreground=COLOR_TEXT,
        font=FONT_NORMAL,
        padding=(10, 5),
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "History.TButton",
        background=[("active", COLOR_BORDER)],
    )

    style.configure("Modern.TFrame", background=COLOR_BG)
    style.configure("Surface.TFrame", background=COLOR_SURFACE_ALT)
    style.configure("Modern.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MUTED, font=FONT_NORMAL)
    style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=FONT_TITLE)
    style.configure("Surface.TLabel", background=COLOR_SURFACE_ALT, foreground=COLOR_TEXT_MUTED, font=FONT_SMALL)

    return style
