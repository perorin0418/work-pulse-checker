from __future__ import annotations

import sys

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


def enable_windows_dpi_awareness() -> None:
    """Windowsのディスプレイ拡大率を考慮させ、文字が小さく描画される問題を防ぐ。

    tkinterはデフォルトでDPI非対応として扱われ、OSがウィンドウを拡大率分だけ
    ビットマップ拡大するため文字がぼやけて小さく見える。プロセスをDPI対応に
    することで、Tkinter自身に正しい解像度で描画させる。Windows以外では何もしない。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            # Per-Monitor v2 DPI awareness（Windows 10 1703+）
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            try:
                # System DPI awareness（Windows 8.1+）
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                # Windows Vista〜8向けフォールバック
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def apply_tk_scaling(root) -> None:
    """OSのディスプレイ拡大率に合わせてtkinterの論理DPIスケーリングを設定する。

    enable_windows_dpi_awareness() でプロセスをDPI対応にした後は、
    tkinterが実DPIを取得できるようになるため、tk_scaling を実測値に合わせて
    明示的に更新し、フォント・ウィジェットサイズを画面と一致させる。
    """
    try:
        # 96 DPIを基準(scaling=1.0)としてWindowsの拡大率と対応させる
        actual_dpi = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", actual_dpi / 72.0)
    except Exception:
        pass


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
