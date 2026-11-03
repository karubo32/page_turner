"""
本めくり装置 GUI コントローラー  v4  — Warm Brown Edition
依存: pip install pyserial
実行: python page_turner_gui.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import queue
import re
import math

# ──────────────────────────────────────────
#  デザイントークン  (ウォームブラウン系)
# ──────────────────────────────────────────
BG        = "#F5EFE6"   # ページ背景  (クリーム)
SURFACE   = "#FDF8F2"   # カード面    (オフホワイト)
SURFACE2  = "#EDE0CE"   # サブ面      (薄茶)
BORDER    = "#D6C4A8"   # 罫線        (ベージュ)
TEXT      = "#2C1A0E"   # 主テキスト  (ダークブラウン)
TEXT2     = "#7A5C3E"   # 副テキスト  (ミディアムブラウン)
TEXT3     = "#B09070"   # プレースホルダー (薄ブラウン)

BLUE      = "#8B5E3C"   # プライマリ  (ウォームブラウン)
BLUE_D    = "#6F4A2D"   # ホバー      (ダークブラウン)
GREEN     = "#5A8A5A"   # 成功        (アースグリーン)
RED_C     = "#C0392B"   # 危険        (テラコッタ)
GREEN_C   = "#16A34A"   # 実行・開始   (グリーン)
AMBER     = "#C67C2A"   # 警告        (バーントオレンジ)
INDIGO    = "#7B5EA7"   # アクセント  (モーブ)

# Arduinoパラメータ（デフォルト値）
DEFAULT_TOTAL_PAGES = 527
CALIB_INTERVAL      = 50


# ──────────────────────────────────────────
#  カスタムウィジェット
# ──────────────────────────────────────────
class FlatButton(tk.Label):
    """枠なしフラットボタン（ホバーエフェクト付き）"""
    def __init__(self, parent, text, command=None,
                 bg=BLUE, fg="#FFFFFF", hover_bg=BLUE_D,
                 font_size=10, bold=False, radius=6,
                 padx=14, pady=7, **kw):
        weight = "bold" if bold else "normal"
        super().__init__(parent, text=text,
                         bg=bg, fg=fg,
                         font=("Segoe UI", font_size, weight),
                         cursor="hand2",
                         padx=padx, pady=pady, **kw)
        self._bg       = bg
        self._hover_bg = hover_bg
        self._cmd      = command
        self.bind("<Enter>",    lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>",    lambda e: self.configure(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._fire())

    def _fire(self):
        if self._cmd:
            self._cmd()

    def set_colors(self, bg, hover_bg=None):
        self._bg       = bg
        self._hover_bg = hover_bg or bg
        self.configure(bg=bg)


class Card(tk.Frame):
    """角丸風カード（実際は角丸なし・細ボーダー）"""
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=SURFACE,
                         highlightbackground=BORDER,
                         highlightthickness=1, **kw)


class SectionLabel(tk.Label):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, text=text.upper(),
                         bg=SURFACE, fg=TEXT3,
                         font=("Segoe UI", 8, "bold"),
                         anchor="w", **kw)


class ValueEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, width=6, **kw):
        super().__init__(parent, textvariable=textvariable,
                         width=width, relief="flat",
                         bg=SURFACE2, fg=TEXT,
                         insertbackground=TEXT,
                         highlightbackground=BORDER,
                         highlightthickness=1,
                         font=("Segoe UI", 11),
                         justify="center", **kw)


# ──────────────────────────────────────────
#  メインアプリ
# ──────────────────────────────────────────
class PageTurnerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Page Turner  |  Controller")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(980, 700)

        self.serial      = None
        self.connected   = False
        self.log_queue   = queue.Queue()
        self.running     = False
        self.calib_rows  = {}
        self.total_pages = DEFAULT_TOTAL_PAGES

        # Arduino の詳細設定（`set` コマンドの応答で埋まる）
        self.settings      = {}
        self.settings_win  = None
        self.settings_vars = {}

        self._build_ui()
        self._refresh_ports()
        self._poll_log()

    # ══════════════════════════════════════
    #  UI 構築
    # ══════════════════════════════════════
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_topbar()

        body = tk.Frame(self.root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        body.columnconfigure(0, weight=0, minsize=260)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_main(body)

    # ── トップバー ──
    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=SURFACE,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        # ロゴ
        logo_f = tk.Frame(bar, bg=SURFACE)
        logo_f.grid(row=0, column=0, padx=(20, 0), pady=14)
        tk.Label(logo_f, text="◈", bg=SURFACE, fg=BLUE,
                 font=("Segoe UI", 18)).pack(side="left")
        tk.Label(logo_f, text="  Page Turner", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(logo_f, text="  Controller", bg=SURFACE, fg=TEXT2,
                 font=("Segoe UI", 11)).pack(side="left")

        # 接続エリア
        conn = tk.Frame(bar, bg=SURFACE)
        conn.grid(row=0, column=2, padx=20, pady=12, sticky="e")

        tk.Label(conn, text="PORT", bg=SURFACE, fg=TEXT3,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))

        self.port_var   = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var,
                                       width=13, state="readonly",
                                       font=("Segoe UI", 10))
        self.port_combo.pack(side="left", padx=(0, 6))

        FlatButton(conn, "↺", command=self._refresh_ports,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT2,
                   font_size=12, padx=8, pady=4).pack(side="left", padx=(0, 10))

        self.conn_btn = FlatButton(conn, "Connect", command=self._toggle_connect,
                                   bg=GREEN, hover_bg="#059669",
                                   font_size=10, bold=True, padx=16, pady=6)
        self.conn_btn.pack(side="left", padx=(0, 8))

        # ステータスインジケーター
        self.status_canvas = tk.Canvas(conn, width=12, height=12,
                                       bg=SURFACE, highlightthickness=0)
        self.status_canvas.pack(side="left")
        self._status_dot = self.status_canvas.create_oval(2, 2, 10, 10, fill=RED_C, outline="")

        self.status_lbl = tk.Label(conn, text="Disconnected", bg=SURFACE, fg=TEXT3,
                                   font=("Segoe UI", 9))
        self.status_lbl.pack(side="left", padx=(4, 0))

    # ── サイドバー ──
    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=BG, width=260)
        sb.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        sb.grid_propagate(False)

        # ── 基本操作カード ──
        c1 = Card(sb)
        c1.pack(fill="x", pady=(0, 10))
        SectionLabel(c1, "Controls").pack(anchor="w", padx=14, pady=(10, 6))

        btn_row = tk.Frame(c1, bg=SURFACE)
        btn_row.pack(fill="x", padx=10, pady=(0, 6))
        FlatButton(btn_row, "▶  START", command=self._cmd_start,
                   bg=GREEN, hover_bg="#059669", bold=True).pack(side="left", padx=(0, 6))
        FlatButton(btn_row, "■  STOP", command=self._cmd_stop,
                   bg=RED_C, hover_bg="#DC2626", bold=True).pack(side="left")

        FlatButton(c1, "⌂  HOME", command=self._cmd_home,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=10).pack(fill="x", padx=10, pady=(0, 12))

        # ── ページジャンプカード ──
        c2 = Card(sb)
        c2.pack(fill="x", pady=(0, 10))
        SectionLabel(c2, "Page Jump").pack(anchor="w", padx=14, pady=(10, 6))
        prow = tk.Frame(c2, bg=SURFACE)
        prow.pack(fill="x", padx=10, pady=(0, 6))
        self.page_var = tk.StringVar(value="1")
        ValueEntry(prow, textvariable=self.page_var, width=7).pack(side="left", padx=(0, 8), ipady=4)
        self.page_max_lbl = tk.Label(prow, text=f"/ {self.total_pages}", bg=SURFACE, fg=TEXT2,
                 font=("Segoe UI", 9))
        self.page_max_lbl.pack(side="left", padx=(0, 10))
        FlatButton(prow, "Jump", command=self._cmd_page_jump,
                   font_size=10, padx=12, pady=5).pack(side="left")

        # Total Pages 設定行
        tprow = tk.Frame(c2, bg=SURFACE)
        tprow.pack(fill="x", padx=10, pady=(0, 12))
        tk.Label(tprow, text="Total pages", bg=SURFACE, fg=TEXT3,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        self.total_pages_var = tk.StringVar(value=str(self.total_pages))
        ValueEntry(tprow, textvariable=self.total_pages_var, width=6).pack(side="left", padx=(0, 8), ipady=3)
        FlatButton(tprow, "Set", command=self._cmd_set_total_pages,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=10, pady=3).pack(side="left")

        # ── ステップモードカード ──
        c3 = Card(sb)
        c3.pack(fill="x", pady=(0, 10))
        SectionLabel(c3, "Step Mode").pack(anchor="w", padx=14, pady=(10, 6))
        srow = tk.Frame(c3, bg=SURFACE)
        srow.pack(fill="x", padx=10, pady=(0, 12))
        FlatButton(srow, "STEP", command=self._cmd_step,
                   bg=INDIGO, hover_bg="#4F46E5",
                   font_size=10, padx=12, pady=5).pack(side="left", padx=(0, 6))
        FlatButton(srow, "▶ Next", command=self._cmd_next,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=10, padx=12, pady=5).pack(side="left", padx=(0, 6))
        FlatButton(srow, "■ OFF", command=self._cmd_step_off,
                   bg=RED_C, hover_bg="#DC2626", fg="#fff",
                   font_size=10, padx=10, pady=5).pack(side="left")

        # ── 速度カード ──
        c4 = Card(sb)
        c4.pack(fill="x", pady=(0, 10))
        SectionLabel(c4, "Speed").pack(anchor="w", padx=14, pady=(10, 6))
        sprow = tk.Frame(c4, bg=SURFACE)
        sprow.pack(fill="x", padx=10, pady=(0, 12))
        self.speed_var = tk.StringVar(value="1.5")
        ValueEntry(sprow, textvariable=self.speed_var, width=5).pack(side="left", padx=(0, 8), ipady=4)
        tk.Label(sprow, text="0.1 – 5.0", bg=SURFACE, fg=TEXT3,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        FlatButton(sprow, "Set", command=self._cmd_speed,
                   font_size=10, padx=12, pady=5).pack(side="left")

        # ── 手動サーボカード ──
        c5 = Card(sb)
        c5.pack(fill="x", pady=(0, 10))
        SectionLabel(c5, "Manual Servo  (paused only)").pack(anchor="w", padx=14, pady=(10, 6))

        for axis, var_attr, cmd_str in [("Z", "z_angle", "z"), ("Y", "y_angle", "y")]:
            arow = tk.Frame(c5, bg=SURFACE)
            arow.pack(fill="x", padx=10, pady=(0, 6))
            tk.Label(arow, text=axis, bg=SURFACE, fg=TEXT2,
                     font=("Segoe UI", 10, "bold"), width=2).pack(side="left")
            var = tk.StringVar(value="90")
            setattr(self, var_attr, var)
            ValueEntry(arow, textvariable=var, width=5).pack(side="left", padx=(4, 6), ipady=3)
            FlatButton(arow, "Go", command=lambda a=cmd_str, v=var: self._send(f"{a} {v.get()}"),
                       font_size=9, padx=10, pady=3).pack(side="left", padx=(0, 6))
            FlatButton(arow, f"{axis}+", command=lambda a=cmd_str: self._send(f"{a}+"),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=9, padx=8, pady=3).pack(side="left", padx=(0, 4))
            FlatButton(arow, f"{axis}−", command=lambda a=cmd_str: self._send(f"{a}-"),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=9, padx=8, pady=3).pack(side="left")
        tk.Frame(c5, bg=SURFACE, height=6).pack()

        # ── キャリブレーションカード ──
        c6 = Card(sb)
        c6.pack(fill="x", pady=(0, 10))
        SectionLabel(c6, "Calibration").pack(anchor="w", padx=14, pady=(10, 6))
        tk.Label(c6, text="調整は右のキャリブテーブルから行います",
                 bg=SURFACE, fg=TEXT3, font=("Segoe UI", 8),
                 wraplength=220, justify="left").pack(anchor="w", padx=14, pady=(0, 8))
        FlatButton(c6, "Reset All Data", command=self._cmd_calib_reset,
                   bg=SURFACE2, hover_bg="#FEE2E2", fg=RED_C,
                   font_size=10).pack(fill="x", padx=10, pady=(0, 12))

        # ── 詳細設定カード ──
        c7 = Card(sb)
        c7.pack(fill="x", pady=(0, 10))
        SectionLabel(c7, "Advanced").pack(anchor="w", padx=14, pady=(10, 6))
        FlatButton(c7, "⚙  詳細設定", command=self._open_settings,
                   bg=AMBER, hover_bg="#D97706", fg="#1A1D23",
                   font_size=10).pack(fill="x", padx=10, pady=(0, 12))

    # ── メインエリア ──
    def _build_main(self, parent):
        main = tk.Frame(parent, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=2)

        # コマンド入力バー
        cmd_card = Card(main)
        cmd_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        cmd_card.columnconfigure(1, weight=1)
        tk.Label(cmd_card, text="CMD", bg=SURFACE, fg=TEXT3,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, padx=(14, 8), pady=10)
        self.cmd_var = tk.StringVar()
        cmd_e = tk.Entry(cmd_card, textvariable=self.cmd_var,
                         relief="flat", bg=SURFACE2, fg=TEXT,
                         insertbackground=TEXT, font=("Segoe UI", 11),
                         highlightbackground=BORDER, highlightthickness=1)
        cmd_e.grid(row=0, column=1, sticky="ew", ipady=6, pady=10)
        cmd_e.bind("<Return>", lambda e: self._cmd_send_raw())
        FlatButton(cmd_card, "Send  ↵", command=self._cmd_send_raw,
                   font_size=10, padx=14, pady=6).grid(row=0, column=2, padx=(8, 12), pady=10)

        # キャリブテーブル
        self._build_calib_table(main)

        # ログ
        self._build_log(main)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.table_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.table_canvas.yview_scroll(1, "units")
        else:
            self.table_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _build_calib_table(self, parent):
        card = Card(parent)
        card.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        # カードヘッダー
        hdr = tk.Frame(card, bg=SURFACE)
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        tk.Label(hdr, text="Calibration Table", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        FlatButton(hdr, "↺  Fetch", command=self._cmd_table,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=10, pady=4).pack(side="right", padx=(6, 0))
        FlatButton(hdr, "Send All", command=self._send_all_calib,
                   bg=BLUE, hover_bg=BLUE_D,
                   font_size=9, padx=10, pady=4).pack(side="right")

        # 区切り
        tk.Frame(card, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        # 列ヘッダー
        col_hdr = tk.Frame(card, bg=SURFACE2)
        col_hdr.grid(row=2, column=0, sticky="ew")
        for i, (label, w) in enumerate([
            ("SLOT", 5), ("PAGE RANGE", 13), ("Z (now)", 9), ("ANGLE (set)", 12), ("", 7)
        ]):
            tk.Label(col_hdr, text=label, bg=SURFACE2, fg=TEXT3,
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="center").grid(row=0, column=i, padx=2, pady=5, sticky="ew")

        # スクロールエリア
        scroll_f = tk.Frame(card, bg=SURFACE)
        scroll_f.grid(row=3, column=0, sticky="nsew")
        card.rowconfigure(3, weight=1)
        scroll_f.columnconfigure(0, weight=1)
        scroll_f.rowconfigure(0, weight=1)

        self.table_canvas = tk.Canvas(scroll_f, bg=SURFACE, highlightthickness=0, height=180)
        self.table_canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(scroll_f, orient="vertical", command=self.table_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.table_canvas.configure(yscrollcommand=vsb.set)

        self.table_inner = tk.Frame(self.table_canvas, bg=SURFACE)
        win = self.table_canvas.create_window((0, 0), window=self.table_inner, anchor="nw")

        def _resize(e):
            self.table_canvas.configure(scrollregion=self.table_canvas.bbox("all"))
            self.table_canvas.itemconfig(win, width=self.table_canvas.winfo_width())

        self.table_inner.bind("<Configure>", _resize)
        self.table_canvas.bind("<Configure>", lambda e: self.table_canvas.itemconfig(win, width=e.width))

        # マウスホイールスクロール（Windows / macOS / Linux）
        self.table_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.table_canvas.bind("<Button-4>",   self._on_mousewheel)
        self.table_canvas.bind("<Button-5>",   self._on_mousewheel)
        self.table_inner.bind("<MouseWheel>",  self._on_mousewheel)
        self.table_inner.bind("<Button-4>",    self._on_mousewheel)
        self.table_inner.bind("<Button-5>",    self._on_mousewheel)

        tk.Frame(card, bg=SURFACE, height=8).grid(row=4, column=0)

        self._build_table_rows()

    def _build_table_rows(self):
        for w in self.table_inner.winfo_children():
            w.destroy()
        self.calib_rows.clear()

        calib_sections = (self.total_pages // CALIB_INTERVAL) + 1
        for slot in range(calib_sections):
            start_page = slot * CALIB_INTERVAL
            if start_page >= self.total_pages:
                break
            end_page = min(start_page + CALIB_INTERVAL - 1, self.total_pages - 1)

            angle_var = tk.StringVar(value="—")
            drag_state = {"x": None, "base": None}

            self.calib_rows[slot] = {
                "angle_var": angle_var,
                "z_lbl":     None,
                "drag":      drag_state,
            }

            row_bg = SURFACE if slot % 2 == 0 else "#FAFBFC"
            rf = tk.Frame(self.table_inner, bg=row_bg)
            rf.pack(fill="x")
            tk.Frame(rf, bg=BORDER, height=1).pack(fill="x")
            inner = tk.Frame(rf, bg=row_bg)
            inner.pack(fill="x", pady=4)
            for _w in (rf, inner):
                _w.bind("<MouseWheel>", self._on_mousewheel)
                _w.bind("<Button-4>",   self._on_mousewheel)
                _w.bind("<Button-5>",   self._on_mousewheel)

            # ── 行全体ドラッグでZ値変更 ──
            def _drag_start(e, s=slot):
                ds = self.calib_rows[s]["drag"]
                ds["x"] = e.x_root
                raw = self.calib_rows[s]["angle_var"].get().strip()
                try:
                    ds["base"] = int(raw)
                except ValueError:
                    try:    ds["base"] = int(self.calib_rows[s]["z_lbl"].cget("text"))
                    except: ds["base"] = 43

            def _drag_move(e, s=slot):
                ds = self.calib_rows[s]["drag"]
                if ds["x"] is None: return
                delta = (ds["x"] - e.x_root) // 2  # 左ドラッグ→値増加（浅い）
                new_val = max(-14, min(80, ds["base"] + delta))
                self.calib_rows[s]["angle_var"].set(str(new_val))

            def _drag_end(e, s=slot):
                self.calib_rows[s]["drag"]["x"] = None
                self._send_oz(s)

            def _bind_drag(widget, s=slot):
                widget.bind("<ButtonPress-1>",  lambda e, ss=s: _drag_start(e, ss))
                widget.bind("<B1-Motion>",       lambda e, ss=s: _drag_move(e, ss))
                widget.bind("<ButtonRelease-1>", lambda e, ss=s: _drag_end(e, ss))
                widget.configure(cursor="sb_h_double_arrow")
                widget.bind("<MouseWheel>", self._on_mousewheel)
                widget.bind("<Button-4>",   self._on_mousewheel)
                widget.bind("<Button-5>",   self._on_mousewheel)

            # Slot badge
            badge = tk.Label(inner, text=f" {slot} ", bg=INDIGO, fg="#fff",
                             font=("Segoe UI", 9, "bold"), padx=4, pady=1)
            badge.grid(row=0, column=0, padx=(10, 0))
            _bind_drag(badge, slot)

            # Page range
            pg_lbl = tk.Label(inner, text=f"p{start_page} – {end_page}", bg=row_bg, fg=TEXT2,
                     font=("Segoe UI", 9), width=13, anchor="center")
            pg_lbl.grid(row=0, column=1, padx=4)
            _bind_drag(pg_lbl, slot)

            # Z value (now)
            z_lbl = tk.Label(inner, text="—", bg=row_bg, fg=BLUE,
                             font=("Segoe UI", 10, "bold"), width=7, anchor="center")
            z_lbl.grid(row=0, column=2, padx=4)
            self.calib_rows[slot]["z_lbl"] = z_lbl
            _bind_drag(z_lbl, slot)

            # Angle entry（数値直接入力も可）
            ent = tk.Entry(inner, textvariable=angle_var, width=6,
                           relief="flat", bg=SURFACE2, fg=TEXT,
                           insertbackground=TEXT,
                           highlightbackground=BORDER, highlightthickness=1,
                           font=("Segoe UI", 10), justify="center")
            ent.grid(row=0, column=3, padx=6, ipady=3)
            ent.bind("<Return>", lambda e, s=slot: self._send_oz(s))

            # Apply button
            FlatButton(inner, "Apply", command=lambda s=slot: self._send_oz(s),
                       bg=BLUE, hover_bg=BLUE_D,
                       font_size=8, padx=8, pady=3).grid(row=0, column=4, padx=(0, 4))

            # Test button
            FlatButton(inner, "Test ▶", command=lambda s=slot, p=start_page: self._test_slot(s, p),
                       bg="#6D28D9", hover_bg="#5B21B6", fg="#fff",
                       font_size=8, padx=8, pady=3).grid(row=0, column=5, padx=(0, 10))

    def _build_log(self, parent):
        card = Card(parent)
        card.grid(row=2, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        hdr = tk.Frame(card, bg=SURFACE)
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        tk.Label(hdr, text="Serial Log", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        FlatButton(hdr, "Clear", command=self._clear_log,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT2,
                   font_size=9, padx=10, pady=4).pack(side="right")

        tk.Frame(card, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.log_text = scrolledtext.ScrolledText(
            card, bg="#1E1008", fg="#E8D5B0",
            font=("Cascadia Code", 9) if self._font_exists("Cascadia Code")
            else ("Courier New", 9),
            relief="flat", insertbackground="#E8D5B0",
            state="disabled", wrap="word",
            padx=12, pady=8,
            selectbackground=BLUE
        )
        self.log_text.grid(row=2, column=0, sticky="nsew")
        self.log_text.tag_config("send",  foreground="#F0A96A")   # warm orange
        self.log_text.tag_config("recv",  foreground="#A8D5A2")   # sage green
        self.log_text.tag_config("info",  foreground="#9C8060")   # muted brown
        self.log_text.tag_config("error", foreground="#E07070")   # soft red

    # ══════════════════════════════════════
    #  ヘルパー
    # ══════════════════════════════════════
    @staticmethod
    def _font_exists(name):
        try:
            import tkinter.font as tkfont
            return name in tkfont.families()
        except Exception:
            return False

    def _log(self, msg, tag="recv"):
        self.log_queue.put((msg, tag))

    def _poll_log(self):
        try:
            while True:
                msg, tag = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                ts = time.strftime("%H:%M:%S")
                prefix = "←  " if tag == "recv" else "→  " if tag == "send" else "   "
                self.log_text.insert("end", f"[{ts}]  {prefix}{msg}\n", tag)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
                self._parse_table_line(msg)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_log)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _parse_table_line(self, line):
        # 詳細設定の値（`set` コマンドの応答）
        m_set = re.search(r'\[SET\]\s+(\w+)=(-?\d+)', line)
        if m_set:
            self.settings[m_set.group(1)] = m_set.group(2)
            self.root.after(0, self._refresh_settings_fields)
            return

        # 総ページ数（`pages` の応答 / `pages <n>` の変更通知）
        m_pages = re.search(r'TOTAL PAGES(?:\s+SET)?:\s*(\d+)', line)
        if m_pages:
            n = int(m_pages.group(1))
            self.root.after(0, lambda: self._update_total_pages(n))
            return

        m = re.search(r'\[(\d+)\].*?Z=(-?\d+)', line)
        if not m:
            return
        slot, z_val = int(m.group(1)), m.group(2)
        # スロットがテーブルに存在しない場合は区間数が変わったとみなして再構築
        if slot not in self.calib_rows:
            self.root.after(0, self._build_table_rows)
            return
        row = self.calib_rows[slot]
        row["z_lbl"].configure(text=z_val)
        if row["angle_var"].get() in ("—", ""):
            row["angle_var"].set(z_val)

    # ══════════════════════════════════════
    #  シリアル通信
    # ══════════════════════════════════════
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        self.port_var.set(ports[0] if ports else "")

    def _toggle_connect(self):
        (self._disconnect if self.connected else self._connect)()

    def _connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showerror("Error", "ポートを選択してください")
            return
        try:
            self.serial    = serial.Serial(port, 115200, timeout=0.1)
            time.sleep(1.5)
            self.connected = True
            self.running   = True
            self.conn_btn.set_colors(RED_C, "#DC2626")
            self.conn_btn.configure(text="Disconnect")
            self.status_canvas.itemconfig(self._status_dot, fill=GREEN)
            self.status_lbl.configure(text=f"Connected  {port}", fg=GREEN)
            self._log(f"Connected: {port} @ 115200 bps", "info")
            threading.Thread(target=self._read_loop, daemon=True).start()
            # 総ページ数 → キャリブテーブル → 詳細設定 の順に自動取得
            self.root.after(400, self._fetch_all)
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def _disconnect(self):
        self.running = self.connected = False
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None
        self.conn_btn.set_colors(GREEN, "#059669")
        self.conn_btn.configure(text="Connect")
        self.status_canvas.itemconfig(self._status_dot, fill=RED_C)
        self.status_lbl.configure(text="Disconnected", fg=TEXT3)
        self._log("Disconnected", "info")

    def _read_loop(self):
        while self.running:
            try:
                if self.serial and self.serial.in_waiting:
                    line = self.serial.readline().decode("utf-8", errors="replace").strip()
                    if line:
                        self._log(line, "recv")
                else:
                    time.sleep(0.02)
            except Exception as e:
                self._log(f"Read error: {e}", "error")
                break

    def _send(self, cmd):
        if not self.connected or not self.serial:
            self._log("Not connected", "error")
            return
        try:
            self.serial.write((cmd + "\n").encode("utf-8"))
            self._log(cmd, "send")
        except Exception as e:
            self._log(f"Send error: {e}", "error")

    # ══════════════════════════════════════
    #  コマンドハンドラ
    # ══════════════════════════════════════
    def _cmd_start(self):  self._send("start")
    def _cmd_stop(self):   self._send("stop")
    def _cmd_home(self):   self._send("home")
    def _cmd_step(self):     self._send("step")
    def _cmd_step_off(self): self._send("step off")
    def _cmd_next(self):   self._send("n")

    def _fetch_all(self):
        """接続直後に総ページ数・キャリブテーブル・詳細設定をまとめて取得"""
        self._send("pages")
        self.root.after(400, lambda: self._send("table"))
        self.root.after(900, lambda: self._send("set"))

    def _cmd_set_total_pages(self):
        v = self.total_pages_var.get().strip()
        try:
            n = int(v)
            if 10 <= n <= 9999:
                self._send(f"pages {n}")
                # Arduino応答で自動同期するが、即時にGUIも更新
                self._update_total_pages(n)
            else:
                messagebox.showerror("Error", "総ページ数は 10〜9999 で入力")
        except ValueError:
            messagebox.showerror("Error", "整数を入力してください")

    def _update_total_pages(self, n: int):
        """total_pagesを更新してGUIを再構築"""
        if n == self.total_pages:
            # 区間数は変わらないので、取得済みのZ値を消さないよう再構築しない
            self.total_pages_var.set(str(n))
            return
        self.total_pages = n
        self.total_pages_var.set(str(n))
        self.page_max_lbl.configure(text=f"/ {n}")
        self._build_table_rows()

    def _cmd_table(self):
        for row in self.calib_rows.values():
            row["z_lbl"].configure(text="…")
            row["angle_var"].set("—")
        self._send("table")

    def _cmd_calib_reset(self):
        if messagebox.askyesno("Confirm", "キャリブデータを全消去しますか？"):
            self._send("calib_reset")
            for row in self.calib_rows.values():
                row["z_lbl"].configure(text="—")
                row["angle_var"].set("—")

    def _cmd_speed(self):
        v = self.speed_var.get().strip()
        try:
            f = float(v)
            if 0.1 <= f <= 5.0:
                self._send(f"speed {v}")
            else:
                messagebox.showerror("Error", "速度は 0.1〜5.0 で入力")
        except ValueError:
            messagebox.showerror("Error", "数値を入力してください")

    def _cmd_page_jump(self):
        v = self.page_var.get().strip()
        try:
            p = int(v)
            if 1 <= p <= self.total_pages:
                self._send(str(p))
            else:
                messagebox.showerror("Error", f"ページは 1〜{self.total_pages}")
        except ValueError:
            messagebox.showerror("Error", "数値を入力してください")

    def _send_oz(self, slot):
        val = self.calib_rows[slot]["angle_var"].get().strip()
        try:
            self._send(f"oz {slot} {int(val)}")
            self.root.after(600, self._cmd_table)
        except ValueError:
            messagebox.showerror("Error", f"Slot {slot}: 整数を入力してください")

    def _test_slot(self, slot, start_page):
        """指定スロット先頭ページのZ値でタップ1回テスト"""
        page = max(0, start_page)
        self._send(f"test {page}")

    def _send_all_calib(self):
        if not messagebox.askyesno("Confirm", "全スロットの設定角度を送信しますか？"):
            return
        for slot in sorted(self.calib_rows.keys()):
            val = self.calib_rows[slot]["angle_var"].get().strip()
            if val in ("—", ""):
                continue
            try:
                self._send(f"oz {slot} {int(val)}")
                time.sleep(0.15)
            except ValueError:
                self._log(f"Slot {slot}: invalid value '{val}' — skipped", "error")
        self.root.after(800, self._cmd_table)

    def _cmd_send_raw(self):
        cmd = self.cmd_var.get().strip()
        if cmd:
            self._send(cmd)
            self.cmd_var.set("")

    # ══════════════════════════════════════
    #  詳細設定ダイアログ
    # ══════════════════════════════════════
    SETTINGS_FIELDS = [
        ("yhome",  "Y ホーム位置",   "Y軸の待機角度"),
        ("zhome",  "Z ホーム位置",   "Z軸の待機角度"),
        ("ymin",   "Y 下限",         "Y軸が下回れない角度"),
        ("ymax",   "Y 上限",         "Y軸が超えられない角度"),
        ("zmin",   "Z 下限",         "Z軸が下回れない角度"),
        ("zmax",   "Z 上限",         "Z軸が超えられない角度"),
        ("pstart", "押さえ角(先頭)", "先頭ページでのページ押さえ角度"),
        ("pend",   "押さえ角(最終)", "最終ページでのページ押さえ角度"),
    ]

    # 入力を許す範囲。既定は 0〜255。
    # zmin だけは Z軸をパルス幅制御しているため 0° 未満も指定できる。
    SETTINGS_RANGE = {"zmin": (-30, 255)}
    SETTINGS_RANGE_DEFAULT = (0, 255)

    def _open_settings(self):
        # すでに開いていれば前面に出すだけ
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("詳細設定")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        def _on_close():
            self.settings_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        card = Card(win)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(card, text="サーボ設定", bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3,
                                                     sticky="w", padx=14, pady=(12, 2))
        tk.Label(card, text="変更するとArduinoのEEPROMに保存されます",
                 bg=SURFACE, fg=TEXT3, font=("Segoe UI", 8)).grid(
                     row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 8))

        self.settings_vars = {}
        for i, (key, label, hint) in enumerate(self.SETTINGS_FIELDS):
            r = i + 2
            tk.Label(card, text=label, bg=SURFACE, fg=TEXT2,
                     font=("Segoe UI", 10), anchor="w", width=13).grid(
                         row=r, column=0, sticky="w", padx=(14, 6), pady=4)

            var = tk.StringVar(value=self.settings.get(key, "—"))
            self.settings_vars[key] = var
            ValueEntry(card, textvariable=var, width=6).grid(
                row=r, column=1, pady=4, ipady=3)

            tk.Label(card, text=hint, bg=SURFACE, fg=TEXT3,
                     font=("Segoe UI", 8), anchor="w").grid(
                         row=r, column=2, sticky="w", padx=(10, 14))

        btn_row = tk.Frame(card, bg=SURFACE)
        btn_row.grid(row=len(self.SETTINGS_FIELDS) + 2, column=0, columnspan=3,
                     sticky="ew", padx=14, pady=(12, 14))

        FlatButton(btn_row, "↺  再取得", command=lambda: self._send("set"),
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=12, pady=5).pack(side="left")
        FlatButton(btn_row, "適用", command=self._apply_settings,
                   bg=BLUE, hover_bg=BLUE_D,
                   font_size=10, bold=True, padx=18, pady=5).pack(side="right")

        # 開いた時点の値を取り直す
        if self.connected:
            self._send("set")

    def _refresh_settings_fields(self):
        """`[SET]` 受信時に開いているダイアログの表示を更新する"""
        if self.settings_win is None or not self.settings_win.winfo_exists():
            return
        for key, var in self.settings_vars.items():
            if key in self.settings:
                var.set(self.settings[key])

    def _apply_settings(self):
        """変更された項目だけ `set <name> <val>` で送信する"""
        pending = []
        for key, _label, _hint in self.SETTINGS_FIELDS:
            raw = self.settings_vars[key].get().strip()
            if raw in ("—", ""):
                continue
            try:
                val = int(raw)
            except ValueError:
                messagebox.showerror("Error", f"{key}: 整数を入力してください")
                return
            lo, hi = self.SETTINGS_RANGE.get(key, self.SETTINGS_RANGE_DEFAULT)
            if not (lo <= val <= hi):
                messagebox.showerror("Error", f"{key}: {lo}〜{hi} で入力してください")
                return
            if self.settings.get(key) != str(val):
                pending.append((key, val))

        if not pending:
            self._log("設定に変更はありません", "info")
            return

        for delay, (key, val) in enumerate(pending):
            self.root.after(delay * 150, lambda k=key, v=val: self._send(f"set {k} {v}"))
        # 送信完了後に読み直して表示を同期
        self.root.after(len(pending) * 150 + 300, lambda: self._send("set"))


# ══════════════════════════════════════════
#  エントリーポイント
# ══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()

    w, h = 1020, 760
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    style = ttk.Style()
    style.theme_use("default")
    style.configure("TCombobox",
                    fieldbackground=SURFACE2, background=SURFACE2,
                    foreground=TEXT, selectbackground=BLUE,
                    borderwidth=1, relief="flat")
    style.configure("Vertical.TScrollbar",
                    background=SURFACE2, troughcolor=SURFACE,
                    borderwidth=0, arrowcolor=TEXT3, relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE2)])

    app = PageTurnerGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._disconnect(), root.destroy()))
    root.mainloop()
