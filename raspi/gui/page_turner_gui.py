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
import json
import os
import tkinter.font as tkfont

# Raspberry Pi has no Segoe UI; pick a font that also covers Japanese.
UI_FONT = "DejaVu Sans"
MONO_FONT = "DejaVu Sans Mono"
# Font sizes bumped for the 800x480 monitor (small labels were hard to read).
FONT_SIZE = {8: 10, 9: 11, 10: 12, 11: 12, 12: 14, 14: 15, 18: 18}

# ──────────────────────────────────────────
#  デザイントークン  (ウォームブラウン系)
# ──────────────────────────────────────────
BG        = "#F5EFE6"   # ページ背景  (クリーム)
SURFACE   = "#FDF8F2"   # カード面    (オフホワイト)
SURFACE2  = "#EDE0CE"   # サブ面      (薄茶)
BORDER    = "#D6C4A8"   # 罫線        (ベージュ)
TEXT      = "#2C1A0E"   # 主テキスト  (ダークブラウン)
TEXT2     = "#5A3E24"   # 副テキスト  (ミディアムブラウン)
TEXT3     = "#7F6245"   # プレースホルダー (薄ブラウン)

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
ANGLE_MIN, ANGLE_MAX = -14, 190   # firmware Z limits


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
                         font=(UI_FONT, FONT_SIZE.get(font_size, font_size), weight),
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
                         font=(UI_FONT, 10, "bold"),
                         anchor="w", **kw)


class ValueEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, width=6, **kw):
        super().__init__(parent, textvariable=textvariable,
                         width=width, relief="flat",
                         bg=SURFACE2, fg=TEXT,
                         insertbackground=TEXT,
                         highlightbackground=BORDER,
                         highlightthickness=1,
                         font=(UI_FONT, 12),
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

        self.serial      = None
        self.auto_connect = True   # turned off when the user presses Disconnect
        self.connected   = False
        self.log_queue   = queue.Queue()
        self.ui_queue    = queue.Queue()   # callables to run on the Tk thread
        self.motion_running = False
        self.last_angle     = {"y": None, "z": None}   # 最後に手動で動かした角度（scal の「今」用）
        self.motion_state   = "disconnected"   # disconnected / idle / running / paused
        self.current_page   = None
        self.device_total   = None
        self.running     = False
        self.calib_rows  = {}
        self.total_pages = DEFAULT_TOTAL_PAGES

        self._build_ui()
        self._refresh_ports()
        self._poll_log()
        self._setup_pirate_buttons()
        self.root.after(1000, self._link_tick)
        self._write_status()
        self.root.after(500, self._auto_connect_tick)

    # ══════════════════════════════════════
    #  UI 構築
    # ══════════════════════════════════════
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_topbar()

        body = tk.Frame(self.root, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(6, 8))
        body.columnconfigure(0, weight=0, minsize=290)
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
        logo_f.grid(row=0, column=0, padx=(12, 0), pady=6)
        tk.Label(logo_f, text="◈", bg=SURFACE, fg=BLUE,
                 font=(UI_FONT, 18)).pack(side="left")
        tk.Label(logo_f, text="  Page Turner", bg=SURFACE, fg=TEXT,
                 font=(UI_FONT, 15, "bold")).pack(side="left")

        # 接続エリア
        conn = tk.Frame(bar, bg=SURFACE)
        conn.grid(row=0, column=2, padx=12, pady=6, sticky="e")

        tk.Label(conn, text="PORT", bg=SURFACE, fg=TEXT3,
                 font=(UI_FONT, 10, "bold")).pack(side="left", padx=(0, 6))

        self.port_var   = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var,
                                       width=13, state="readonly",
                                       font=(UI_FONT, 12))
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
                                   font=(UI_FONT, 11))
        self.status_lbl.pack(side="left", padx=(4, 0))

    # ── サイドバー ──
    def _build_sidebar(self, parent):
        # Scrollable so every card is reachable on a small Raspberry Pi monitor.
        outer = tk.Frame(parent, bg=BG, width=290)
        outer.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        outer.grid_propagate(False)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        sb_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, width=272)
        sb_canvas.grid(row=0, column=0, sticky="nsew")
        sb_vsb = ttk.Scrollbar(outer, orient="vertical", command=sb_canvas.yview)
        sb_vsb.grid(row=0, column=1, sticky="ns")
        sb_canvas.configure(yscrollcommand=sb_vsb.set)
        sb = tk.Frame(sb_canvas, bg=BG)
        sb_win = sb_canvas.create_window((0, 0), window=sb, anchor="nw")
        sb.bind("<Configure>", lambda e: sb_canvas.configure(scrollregion=sb_canvas.bbox("all")))
        sb_canvas.bind("<Configure>", lambda e: sb_canvas.itemconfig(sb_win, width=e.width))

        def _sb_wheel(e):
            step = -1 if e.num == 4 else 1 if e.num == 5 else int(-e.delta / 120)
            sb_canvas.yview_scroll(step, "units")
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            outer.bind_all(ev, lambda e: _sb_wheel(e) if (str(e.widget) == str(outer)
                                                          or str(e.widget).startswith(str(outer) + ".")) else None, add="+")

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

        self.unmet_link = tk.BooleanVar(value=False)
        self.link_active = False    # 連動して動いている（START 済み）
        self.link_busy = False      # 1ページめくっている最中
        self.device_started = False # Arduino 側で start 済みか（以後は 'n' で1ページ）
        self._link_last = None      # 最後に見た UNMET 結果の時刻
        tk.Checkbutton(c1, text="UNMET と連動する",
                       variable=self.unmet_link, command=self._link_toggled,
                       bg=SURFACE, fg=TEXT, activebackground=SURFACE, selectcolor=SURFACE2,
                       highlightthickness=0, font=(UI_FONT, 11),
                       anchor="w").pack(fill="x", padx=8, pady=(0, 2))
        self.auto_loop = tk.BooleanVar(value=False)
        self._loop_pending = False   # END OF BOOK → rewind 中。終わったら続ける
        tk.Checkbutton(c1, text="最後まで行ったら最初から",
                       variable=self.auto_loop,
                       bg=SURFACE, fg=TEXT, activebackground=SURFACE, selectcolor=SURFACE2,
                       highlightthickness=0, font=(UI_FONT, 11),
                       anchor="w").pack(fill="x", padx=8, pady=(0, 6))

        FlatButton(c1, "⌂  HOME", command=self._cmd_home,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=10).pack(fill="x", padx=10, pady=(0, 6))
        FlatButton(c1, "⏮  1ページ目に戻る", command=lambda: self._send("rewind"),
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=10).pack(fill="x", padx=10, pady=(0, 6))
        FlatButton(c1, "◉  UNMET の写真", command=self._open_unmet_preview,
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
                 font=(UI_FONT, 11))
        self.page_max_lbl.pack(side="left", padx=(0, 10))
        FlatButton(prow, "Jump", command=self._cmd_page_jump,
                   font_size=10, padx=12, pady=5).pack(side="left")

        # Total Pages 設定行
        tprow = tk.Frame(c2, bg=SURFACE)
        tprow.pack(fill="x", padx=10, pady=(0, 12))
        tk.Label(tprow, text="Total pages", bg=SURFACE, fg=TEXT3,
                 font=(UI_FONT, 10)).pack(side="left", padx=(0, 6))
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

        # ── Testrun カード ──
        c_tr = Card(sb)
        c_tr.pack(fill="x", pady=(0, 10))
        SectionLabel(c_tr, "Testrun").pack(anchor="w", padx=14, pady=(10, 6))
        trrow = tk.Frame(c_tr, bg=SURFACE)
        trrow.pack(fill="x", padx=10, pady=(0, 12))
        FlatButton(trrow, "▶ Start", command=lambda: self._send("testrun"),
                   bg=GREEN_C, hover_bg="#16A34A",
                   font_size=10, padx=12, pady=5).pack(side="left", padx=(0, 6))
        FlatButton(trrow, "■ Stop", command=lambda: self._send("testrun stop"),
                   bg=RED_C, hover_bg="#DC2626", fg="#fff",
                   font_size=10, padx=10, pady=5).pack(side="left")
        tk.Label(c_tr, text="p.1から全ページ順にタップ・電源再投入後も継続",
                 bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10),
                 wraplength=220, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        # ── 速度カード ──
        c4 = Card(sb)
        c4.pack(fill="x", pady=(0, 10))
        SectionLabel(c4, "Speed").pack(anchor="w", padx=14, pady=(10, 6))
        sprow = tk.Frame(c4, bg=SURFACE)
        sprow.pack(fill="x", padx=10, pady=(0, 12))
        self.speed_var = tk.StringVar(value="1.5")
        ValueEntry(sprow, textvariable=self.speed_var, width=5).pack(side="left", padx=(0, 8), ipady=4)
        tk.Label(sprow, text="0.1 – 5.0", bg=SURFACE, fg=TEXT3,
                 font=(UI_FONT, 11)).pack(side="left", padx=(0, 10))
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
                     font=(UI_FONT, 12, "bold"), width=2).pack(side="left")
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

        # ── 詳細設定カード（ファームの set コマンド。EEPROM に保存される）──
        c_set = Card(sb)
        c_set.pack(fill="x", pady=(0, 10))
        SectionLabel(c_set, "Settings（動きの設定）").pack(anchor="w", padx=14, pady=(10, 2))
        tk.Label(c_set, text="値を変えて「適用」で保存（電源を切っても残る）。"
                             "「今」= Manual Servo で最後に動かした角度を入れる",
                 bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10),
                 wraplength=250, justify="left").pack(anchor="w", padx=14, pady=(0, 4))
        self.set_vars = {}
        self.set_device = {}   # Arduino が今持っている値
        # ("g", 見出し, 説明) / ("r", ラベル, [(設定名, 「今」の軸 or None, 前に付ける字), ...], 単位)
        layout = (
            ("g", "① 位置", "めくり終えたら「待機」で待ち、次は「開始」を通ってからめくる"),
            ("r", "待機", [("yhome", "y", "Y"), ("zhome", "z", "Z")], ""),
            ("r", "開始", [("ybase", "y", "Y"), ("zbase", "z", "Z")], ""),
            ("g", "② めくり方", "上から動く順。剥がすとき Y は 1→2→3 の角度を順に通る"),
            ("r", "持ち上げ Z", [("zlift", "z", "")], "°"),
            ("r", "揺らし幅 Y", [("ywiggle", None, "")], "°"),
            ("r", "剥がし Y 1", [("ypeel1", "y", "")], "°"),
            ("r", "剥がし Y 2", [("ypeel2", "y", "")], "°"),
            ("r", "剥がし Y 3", [("ypeel3", "y", "")], "°"),
            ("r", "剥がし速さ", [("ypspeed", None, "")], "%（100=標準）"),
            ("g", "③ 押さえ Z", "めくったページを押さえる角度。間のページは自動で少しずつ変わる"),
            ("r", "最初", [("pstart", "z", "")], "°"),
            ("r", "最後", [("pend", "z", "")], "°"),
            ("g", "④ 待ち", "1ページめくってから次をめくるまで"),
            ("r", "めくり後", [("pwait", None, "")], "秒"),
            ("g", "⑤ 動ける範囲", "ぶつからないための制限。この外へは動かない"),
            ("r", "Y", [("ymin", "y", "下"), ("ymax", "y", "上")], ""),
            ("r", "Z", [("zmin", "z", "下"), ("zmax", "z", "上")], ""),
        )
        for item in layout:
            if item[0] == "g":
                tk.Label(c_set, text=item[1], bg=SURFACE, fg=TEXT, font=(UI_FONT, 11, "bold"),
                         anchor="w").pack(fill="x", padx=12, pady=(8, 0))
                if item[2]:
                    tk.Label(c_set, text=item[2], bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10),
                             wraplength=250, justify="left").pack(anchor="w", padx=14, pady=(0, 2))
                continue
            _, label, fields, unit = item
            row = tk.Frame(c_set, bg=SURFACE)
            row.pack(fill="x", padx=10, pady=(2, 2))
            tk.Label(row, text=label, bg=SURFACE, fg=TEXT2, font=(UI_FONT, 11),
                     width=8 if len(fields) > 1 else 10, anchor="w").pack(side="left")
            for name, axis, prefix in fields:
                if prefix:
                    tk.Label(row, text=prefix, bg=SURFACE, fg=TEXT3,
                             font=(UI_FONT, 10)).pack(side="left", padx=(2, 1))
                var = tk.StringVar(value="")
                self.set_vars[name] = var
                ValueEntry(row, textvariable=var, width=4).pack(side="left", padx=(1, 2), ipady=2)
                if axis:   # 角度そのものの項目だけ「今」で取り込める
                    FlatButton(row, "今", command=lambda a=axis, v=var: self._scal_take_now(a, v),
                               bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                               font_size=9, padx=4, pady=1).pack(side="left", padx=(0, 2))
            if unit:
                tk.Label(row, text=unit, bg=SURFACE, fg=TEXT3,
                         font=(UI_FONT, 10)).pack(side="left", padx=(2, 0))
        srow = tk.Frame(c_set, bg=SURFACE)
        srow.pack(fill="x", padx=10, pady=(2, 12))
        FlatButton(srow, "適用", command=self._settings_apply,
                   font_size=9, padx=12, pady=3).pack(side="left", padx=(0, 4))
        FlatButton(srow, "↺ 読込", command=lambda: self._send("set"),
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=8, pady=3).pack(side="left")

        # ── 1ページ目に戻る動作カード（ファームの rw コマンド。EEPROM に保存）──
        c_rw = Card(sb)
        c_rw.pack(fill="x", pady=(0, 10))
        SectionLabel(c_rw, "Rewind（1ページ目に戻る）").pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(c_rw, text="段0から順に Y・Z を同時に動かす。速さ10=標準・大きいほど速い・0=一気に。"
                            "「今」で今の Y・Z を入れ、Go でその段へ動かして確認",
                 bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10),
                 wraplength=250, justify="left").pack(anchor="w", padx=14, pady=(0, 6))
        nrow = tk.Frame(c_rw, bg=SURFACE)
        nrow.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(nrow, text="使う段数", bg=SURFACE, fg=TEXT2, font=(UI_FONT, 11)).pack(side="left")
        self.rw_count = tk.StringVar(value="")
        ValueEntry(nrow, textvariable=self.rw_count, width=3).pack(side="left", padx=(6, 4), ipady=2)
        tk.Label(nrow, text="(0〜8)", bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10)).pack(side="left")
        hrow = tk.Frame(c_rw, bg=SURFACE)
        hrow.pack(fill="x", padx=10)
        for text, w in (("段", 2), ("Y", 4), ("Z", 4), ("速さ", 3), ("待ちms", 6)):
            tk.Label(hrow, text=text, bg=SURFACE, fg=TEXT3, font=(UI_FONT, 10),
                     width=w, anchor="w").pack(side="left", padx=(0, 2))
        self.rw_vars = []
        self.rw_device = {}
        for i in range(8):
            row = tk.Frame(c_rw, bg=SURFACE)
            row.pack(fill="x", padx=10, pady=(0, 3))
            tk.Label(row, text=str(i), bg=SURFACE, fg=TEXT2, font=(UI_FONT, 11),
                     width=2, anchor="w").pack(side="left")
            vs = [tk.StringVar(value="") for _ in range(4)]
            for v, w in zip(vs, (4, 4, 3, 4)):
                ValueEntry(row, textvariable=v, width=w).pack(side="left", padx=(0, 2), ipady=1)
            self.rw_vars.append(vs)
            FlatButton(row, "今", command=lambda vs=vs: self._rw_take_now(vs),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=9, padx=4, pady=1).pack(side="left", padx=(2, 2))
            FlatButton(row, "Go", command=lambda i=i: self._rw_go(i),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=9, padx=4, pady=1).pack(side="left")
        rrow = tk.Frame(c_rw, bg=SURFACE)
        rrow.pack(fill="x", padx=10, pady=(4, 12))
        FlatButton(rrow, "適用", command=self._rw_apply,
                   font_size=9, padx=12, pady=3).pack(side="left", padx=(0, 4))
        FlatButton(rrow, "↺ 読込", command=lambda: self._send("rw"),
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=8, pady=3).pack(side="left", padx=(0, 4))
        FlatButton(rrow, "⏮ 実行", command=lambda: self._send("rewind"),
                   bg=GREEN, hover_bg="#059669",
                   font_size=9, padx=8, pady=3).pack(side="left")

    # ── メインエリア ──
    def _build_main(self, parent):
        main = tk.Frame(parent, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=2)
        main.rowconfigure(2, weight=3)

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
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(4, 0))
        tk.Label(hdr, text="Calibration Table", bg=SURFACE, fg=TEXT,
                 font=(UI_FONT, 14, "bold")).pack(side="left")
        FlatButton(hdr, "↺  Fetch", command=self._cmd_table,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=9, padx=10, pady=4).pack(side="right", padx=(6, 0))
        FlatButton(hdr, "Send All", command=self._send_all_calib,
                   bg=BLUE, hover_bg=BLUE_D,
                   font_size=9, padx=10, pady=4).pack(side="right")

        # 区切り
        tk.Frame(card, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # 列ヘッダー
        col_hdr = tk.Frame(card, bg=SURFACE2)
        col_hdr.grid(row=2, column=0, sticky="ew")
        for i, (label, w) in enumerate([
            ("SLOT", 4), ("PAGES", 8), ("Z", 4), ("ANGLE  − / ＋", 13), ("", 10)
        ]):
            tk.Label(col_hdr, text=label, bg=SURFACE2, fg=TEXT3,
                     font=(UI_FONT, 10, "bold"), width=w,
                     anchor="center").grid(row=0, column=i, padx=2, pady=5, sticky="ew")

        # スクロールエリア
        scroll_f = tk.Frame(card, bg=SURFACE)
        scroll_f.grid(row=3, column=0, sticky="nsew")
        card.rowconfigure(3, weight=1)
        scroll_f.columnconfigure(0, weight=1)
        scroll_f.rowconfigure(0, weight=1)

        self.table_canvas = tk.Canvas(scroll_f, bg=SURFACE, highlightthickness=0, height=84)
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

        tk.Frame(card, bg=SURFACE, height=2).grid(row=4, column=0)

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
                new_val = max(ANGLE_MIN, min(ANGLE_MAX, ds["base"] + delta))
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
                             font=(UI_FONT, 11, "bold"), padx=4, pady=1)
            badge.grid(row=0, column=0, padx=(10, 0))
            _bind_drag(badge, slot)

            # Page range
            pg_lbl = tk.Label(inner, text=f"p{start_page} – {end_page}", bg=row_bg, fg=TEXT2,
                     font=(UI_FONT, 11), width=8, anchor="center")
            pg_lbl.grid(row=0, column=1, padx=4)
            _bind_drag(pg_lbl, slot)

            # Z value (now)
            z_lbl = tk.Label(inner, text="—", bg=row_bg, fg=BLUE,
                             font=(UI_FONT, 12, "bold"), width=4, anchor="center")
            z_lbl.grid(row=0, column=2, padx=4)
            self.calib_rows[slot]["z_lbl"] = z_lbl
            _bind_drag(z_lbl, slot)

            # Angle: − / entry / ＋ (wheel over the entry also changes it by 1°)
            ang_f = tk.Frame(inner, bg=row_bg)
            ang_f.grid(row=0, column=3, padx=4)
            FlatButton(ang_f, "−", command=lambda s=slot: self._nudge_angle(s, -1),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=12, bold=True, padx=9, pady=1).pack(side="left")
            ent = tk.Entry(ang_f, textvariable=angle_var, width=4,
                           relief="flat", bg=SURFACE2, fg=TEXT,
                           insertbackground=TEXT,
                           highlightbackground=BORDER, highlightthickness=1,
                           font=(UI_FONT, 12), justify="center")
            ent.pack(side="left", padx=3, ipady=3)
            ent.bind("<Return>", lambda e, s=slot: self._send_oz(s))
            for ev, step in (("<Button-4>", 1), ("<Button-5>", -1)):
                ent.bind(ev, lambda e, s=slot, d=step: (self._nudge_angle(s, d), "break")[1])
            ent.bind("<MouseWheel>", lambda e, s=slot: (
                self._nudge_angle(s, 1 if e.delta > 0 else -1), "break")[1])
            FlatButton(ang_f, "＋", command=lambda s=slot: self._nudge_angle(s, +1),
                       bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                       font_size=12, bold=True, padx=7, pady=1).pack(side="left")

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
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(4, 0))
        tk.Label(hdr, text="Serial Log", bg=SURFACE, fg=TEXT,
                 font=(UI_FONT, 14, "bold")).pack(side="left")
        FlatButton(hdr, "Clear", command=self._clear_log,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT2,
                   font_size=9, padx=10, pady=4).pack(side="right")

        tk.Frame(card, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.log_text = scrolledtext.ScrolledText(
            card, height=3, bg="#1E1008", fg="#E8D5B0",
            font=(MONO_FONT, 11),
            relief="flat", insertbackground="#E8D5B0",
            state="disabled", wrap="word",
            padx=12, pady=8,
            selectbackground=BLUE
        )
        self.log_text.grid(row=2, column=0, sticky="nsew")
        self.log_text.tag_config("send",  foreground="#F0A96A")   # warm orange
        self.log_text.tag_config("recv",  foreground="#A8D5A2")   # sage green
        self.log_text.tag_config("info",  foreground="#D2BC98")   # muted brown
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
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
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
        if ">> STARTED" in line or ">> RESUMED" in line or ">> NEXT PAGE" in line:
            self.device_started = True
        if ">> STEP: WAITING" in line or "=== END OF BOOK" in line or "最後のページです" in line:
            self.link_busy = False
            self.motion_running = False
            self.motion_state = "linked" if self.link_active else "paused"
            if "END OF BOOK" in line and self.auto_loop.get():
                # 1ページ目に戻してから続ける（連動中は連動したまま、次の結果からめくる）
                self._log("最後のページ → 1ページ目に戻って続けます", "info")
                self._loop_pending = True
                self.link_busy = True    # 戻している間に来た UNMET の結果では動かさない
                self.root.after(300, lambda: self._send("rewind"))
            elif "END OF BOOK" in line or "最後のページです" in line:
                if self.link_active:
                    self._log("最後のページなので UNMET 連動を止めました", "info")
                self.link_active = False
                self.motion_state = "paused"
        if ">> STARTED" in line or ">> RESUMED" in line:
            self.motion_running = True
            self.motion_state = "running"
        elif ">> PAUSED" in line:
            self.motion_running = False
            self.motion_state = "paused"
        m_axis = re.search(r'>> ([YZ]) -> (-?\d+)', line)
        if m_axis:
            self.last_angle[m_axis.group(1).lower()] = int(m_axis.group(2))
        m_set = re.search(r'\[SET\] (\w+)=(-?\d+)', line)
        if m_set and hasattr(self, "set_vars") and m_set.group(1) in self.set_vars:
            self.set_device[m_set.group(1)] = m_set.group(2)
            self.set_vars[m_set.group(1)].set(m_set.group(2))
        if ">> REWIND START" in line:
            self.motion_running = False
            self.motion_state = "rewinding"
        elif ">> REWIND DONE" in line:
            self.motion_state = "paused"
            if self._loop_pending:
                self._loop_pending = False
                self.link_busy = False
                if self.link_active:
                    self.motion_state = "linked"
                    self._log("1ページ目に戻りました。次の UNMET の結果からめくります", "info")
                else:
                    self._log("1ページ目に戻りました。続けてめくります", "info")
                    self.root.after(300, lambda: self._send("start"))
        m_rwn = re.search(r'\[RW\] n=(\d+)', line)
        if m_rwn and hasattr(self, "rw_count"):
            self.rw_device["n"] = m_rwn.group(1)
            self.rw_count.set(m_rwn.group(1))
        m_rw = re.search(r'\[RW\] (\d) y=(-?\d+) z=(-?\d+) s=(\d+) w=(\d+)', line)
        if m_rw and hasattr(self, "rw_vars"):
            i = int(m_rw.group(1))
            vals = m_rw.group(2, 3, 4, 5)
            self.rw_device[i] = tuple(vals)
            for v, val in zip(self.rw_vars[i], vals):
                v.set(val)
        m_scal = re.search(r'\[SCAL\] ([yz]) (-?\d+)>(-?\d+) (-?\d+)>(-?\d+)', line)
        if m_scal and hasattr(self, "scal_vars"):
            a = m_scal.group(1)
            if m_scal.group(2, 3, 4, 5) != ("0", "0", "180", "180"):
                for (n, side), g in zip(((1, "old"), (1, "new"), (2, "old"), (2, "new")), range(2, 6)):
                    self.scal_vars[(a, n, side)].set(m_scal.group(g))
        m_tap = re.search(r'p\.(\d+)\s*/\s*(\d+)', line)
        if m_tap:
            self.current_page, self.device_total = int(m_tap.group(1)), int(m_tap.group(2))
        m_total = re.search(r'(?:総ページ数|TOTAL PAGES(?: SET)?):\s*(\d+)', line)
        if m_total:
            self.device_total = int(m_total.group(1))
            if self.device_total != self.total_pages:
                # Keep the GUI's page count and table in step with the Arduino (rebuilding clears Z, so re-fetch).
                self.root.after(0, lambda n=self.device_total: (self._update_total_pages(n), self._send("table")))
        # Arduino から総ページ数変更通知を受信したら自動同期
        m_pages = re.search(r'TOTAL PAGES SET:\s*(\d+)', line)
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
        # Raspberry Pi: put USB serial (Arduino) first, before the built-in UART.
        ports.sort(key=lambda d: 0 if ("USB" in d or "ACM" in d) else 1)
        self.port_combo["values"] = ports
        self.port_var.set(ports[0] if ports else "")

    def _toggle_connect(self):
        if self.connected:
            self.auto_connect = False
            self._disconnect()
        else:
            self.auto_connect = True
            self._connect()

    def _auto_connect_tick(self):
        """Every 3 s: if not connected and a USB serial port exists, connect to it."""
        if self.auto_connect and not self.connected:
            usb = [p.device for p in serial.tools.list_ports.comports()
                   if "USB" in p.device or "ACM" in p.device]
            if usb:
                self._refresh_ports()
                self.port_var.set(usb[0])
                self._connect(quiet=True)
        self.root.after(3000, self._auto_connect_tick)

    def _connect(self, quiet=False):
        port = self.port_var.get()
        if not port:
            if not quiet:
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
            self.motion_state, self.motion_running = "idle", False
            self.device_started = False
            self.link_active = self.link_busy = False
            self.root.after(3600, lambda: self._send("set"))
            self.root.after(4300, lambda: self._send("rw"))
            threading.Thread(target=self._read_loop, daemon=True).start()
        except Exception as e:
            if quiet:
                self._log(f"自動接続に失敗: {e}", "error")
            else:
                messagebox.showerror("Connection Error", str(e))

    def _disconnect(self):
        self.running = self.connected = False
        self.motion_state, self.motion_running = "disconnected", False
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
                self._log("USB接続が切れました。ケーブルと電源を確認して Connect を押してください", "error")
                self.ui_queue.put(self._disconnect)
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
    #  Pirate Audio ボタン（Raspberry Pi のみ）
    # ══════════════════════════════════════
    def _setup_pirate_buttons(self):
        """A = 再生/停止、B = 1ページ目に戻る。X/Y は音量（volume_buttons.py）"""
        try:
            from gpiozero import Button
        except ImportError:
            return
        try:
            self._btn_a = Button(5, pull_up=True, bounce_time=0.05)
            self._btn_b = Button(6, pull_up=True, bounce_time=0.05)
        except Exception as e:
            self._log(f"Pirate Audio buttons unavailable: {e}", "info")
            return
        # gpiozero calls back from its own thread; hand off to the Tk thread.
        self._btn_a.when_pressed = lambda: self.ui_queue.put(self._on_button_a)
        self._btn_b.when_pressed = lambda: self.ui_queue.put(self._on_button_b)
        self._log("Pirate Audio: A=再生/停止  B=1ページ目に戻る", "info")

    STATUS_PATH = f"/run/user/{os.getuid()}/page_turner_status.json"

    def _write_status(self):
        """Publish state and page count for the Pirate Audio LCD once a second."""
        status = {
            "state": self.motion_state,
            "page": self.current_page,
            "total": self.device_total or self.total_pages,
            "updated": time.time(),
        }
        try:
            tmp = self.STATUS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(status, f)
            os.replace(tmp, self.STATUS_PATH)
        except OSError:
            pass
        self.root.after(1000, self._write_status)

    def _on_button_a(self):
        running = self.link_active if self.unmet_link.get() else self.motion_running
        self._log("[A] " + ("停止" if running else "再生"), "info")
        self._cmd_stop() if running else self._cmd_start()

    def _on_button_b(self):
        self._log("[B] 1ページ目に戻る", "info")
        self._send("rewind")

    # ══════════════════════════════════════
    #  コマンドハンドラ
    # ══════════════════════════════════════
    def _cmd_start(self):
        if self.unmet_link.get():
            self._link_start()
        else:
            self._send("start")

    def _cmd_stop(self):
        self._loop_pending = False   # 戻している途中で STOP したら、そのあと続けない
        if self.link_active:
            self.link_active = False
            self.link_busy = False
            self._log("UNMET 連動を止めました", "info")
        self._send("stop")

    def _link_toggled(self):
        if self.unmet_link.get():
            self._log("UNMET 連動 ON：START を押すと、UNMET の結果が出るたびに"
                      "「めくり後待ち」秒待って1ページめくります", "info")
        else:
            if self.link_active:
                self._cmd_stop()
            self._log("UNMET 連動 OFF：START でいつもどおり続けてめくります", "info")

    def _read_unmet_updated(self):
        try:
            with open(self.UNMET_RESULTS_PATH, encoding="utf-8") as f:
                return json.load(f).get("updated")
        except (OSError, ValueError):
            return None

    def _link_start(self):
        if not self.running:
            self._log("Arduino に接続してから START してください", "error")
            return
        self.link_active = True
        self.link_busy = False
        self._link_last = self._read_unmet_updated()   # 今ある結果では動かさない。次の結果から
        self.motion_state, self.motion_running = "linked", False
        self._send("step on")
        self._log("UNMET 連動 開始：次の結果が出たらめくります", "info")

    def _link_tick(self):
        # UNMET の結果ファイルを1秒ごとに見て、新しい結果が出たら1ページめくる
        try:
            if self.link_active:
                updated = self._read_unmet_updated()
                if updated is not None and updated != self._link_last:
                    self._link_last = updated
                    if self.link_busy:
                        self._log("[UNMET] 結果が出ましたが、めくっている最中なので見送ります", "info")
                    else:
                        wait = self.set_device.get("pwait", "?")
                        self._log(f"[UNMET] 結果が出ました → {wait} 秒待ってめくります", "info")
                        self.link_busy = True
                        self._send("n" if self.device_started else "start")
        finally:
            self.root.after(1000, self._link_tick)
    def _cmd_home(self):   self._send("home")
    def _cmd_step(self):     self._send("step")
    def _cmd_step_off(self): self._send("step off")
    def _cmd_next(self):   self._send("n")
    def _cmd_calib(self):  self._send("calib")

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

    def _nudge_angle(self, slot, delta):
        """Change a slot's angle by delta degrees (press Apply to save it)."""
        row = self.calib_rows[slot]
        try:
            base = int(row["angle_var"].get())
        except ValueError:
            try:
                base = int(row["z_lbl"].cget("text"))
            except ValueError:
                return   # nothing fetched yet
        row["angle_var"].set(str(max(ANGLE_MIN, min(ANGLE_MAX, base + delta))))

    def _scal_take_now(self, axis, var):
        # 「今」: Manual Servo / 矢印キーで最後に送った角度を欄に入れる
        if self.last_angle[axis] is None:
            self._log(f"{axis.upper()}軸を Manual Servo か矢印キーで動かしてから押してください", "error")
            return
        var.set(str(self.last_angle[axis]))

    def _scal_apply(self, axis):
        try:
            vals = [int(self.scal_vars[(axis, n, side)].get())
                    for n, side in ((1, "old"), (1, "new"), (2, "old"), (2, "new"))]
        except ValueError:
            messagebox.showerror("Servo Cal", f"{axis.upper()}1・{axis.upper()}2 の旧・新をすべて入れてください")
            return
        if vals[0] == vals[2]:
            messagebox.showerror("Servo Cal", "基準1と基準2は違う角度にしてください")
            return
        self._send(f"scal {axis} " + " ".join(map(str, vals)))

    def _settings_apply(self):
        # 変えた項目だけ set で送る（Arduino は1行ずつ処理するので間を空ける）
        cmds = []
        for name, var in self.set_vars.items():
            v = var.get().strip()
            if v == self.set_device.get(name):
                continue
            try:
                cmds.append(f"set {name} {int(v)}")
            except ValueError:
                messagebox.showerror("Settings", f"{name}: 整数を入れてください")
                return
        if not cmds:
            self._log("変更された設定はありません", "info")
            return
        for i, c in enumerate(cmds):
            self.root.after(250 * i, lambda c=c: self._send(c))

    def _rw_take_now(self, vs):
        # 「今」: Manual Servo / 矢印キーで最後に送った Y・Z を入れる
        if self.last_angle["y"] is None and self.last_angle["z"] is None:
            self._log("Manual Servo か矢印キーで Y・Z を動かしてから押してください", "error")
            return
        if self.last_angle["y"] is not None:
            vs[0].set(str(self.last_angle["y"]))
        if self.last_angle["z"] is not None:
            vs[1].set(str(self.last_angle["z"]))

    def _rw_row(self, i):
        vals = tuple(v.get().strip() for v in self.rw_vars[i])
        for v in vals:
            int(v)   # ValueError if not an integer
        return vals

    def _rw_go(self, i):
        # 未保存の値でも試せるよう、先にその段を送ってから動かす
        try:
            vals = self._rw_row(i)
        except ValueError:
            messagebox.showerror("Rewind", f"段{i}: Y・Z・速さ・待ちを整数で入れてください")
            return
        cmds = []
        if vals != self.rw_device.get(i):
            cmds.append(f"rw {i} {' '.join(vals)}")
        cmds.append(f"rw go {i}")
        for k, c in enumerate(cmds):
            self.root.after(400 * k, lambda c=c: self._send(c))

    def _rw_apply(self):
        cmds = []
        try:
            n = int(self.rw_count.get())
        except ValueError:
            messagebox.showerror("Rewind", "使う段数を 0〜8 で入れてください")
            return
        for i in range(8):
            try:
                vals = self._rw_row(i)
            except ValueError:
                if i < n:
                    messagebox.showerror("Rewind", f"段{i}: Y・Z・速さ・待ちを整数で入れてください")
                    return
                continue
            if vals != self.rw_device.get(i):
                cmds.append(f"rw {i} {' '.join(vals)}")
        if str(n) != self.rw_device.get("n"):
            cmds.append(f"rw n {n}")
        if not cmds:
            self._log("変更された段はありません", "info")
            return
        # 1行ごとに [RW] 一覧が返ってくるので、間を空けて送る
        for k, c in enumerate(cmds):
            self.root.after(400 * k, lambda c=c: self._send(c))

    UNMET_FRAME_PATH = f"/run/user/{os.getuid()}/unmet_frame.png"
    UNMET_RESULTS_PATH = f"/run/user/{os.getuid()}/unmet_results.json"

    def _open_unmet_preview(self):
        # 開いていれば前に出すだけ
        if getattr(self, "_pv_win", None) is not None and self._pv_win.winfo_exists():
            self._pv_win.lift()
            return
        win = tk.Toplevel(self.root, bg=SURFACE)
        win.title("UNMET の写真")
        win.transient(self.root)
        self._pv_win = win
        self._pv_mtime = None
        self._pv_photo = None
        self._pv_img = tk.Label(win, bg=SURFACE2, text="写真はまだありません\n（UNMET が動いていると 30 秒ごとに更新）",
                                fg=TEXT3, font=(UI_FONT, 11), wraplength=300)
        self._pv_img.pack(side="left", padx=10, pady=10)
        side = tk.Frame(win, bg=SURFACE)
        side.pack(side="left", fill="y", padx=(0, 12), pady=10)
        self._pv_info = tk.Label(side, bg=SURFACE, fg=TEXT, font=(UI_FONT, 12),
                                 justify="left", anchor="nw", wraplength=200)
        self._pv_info.pack(fill="x")
        FlatButton(side, "閉じる", command=win.destroy,
                   bg=SURFACE2, hover_bg=BORDER, fg=TEXT,
                   font_size=10, padx=14, pady=4).pack(side="bottom", anchor="e")
        self._pv_refresh()

    def _pv_refresh(self):
        win = getattr(self, "_pv_win", None)
        if win is None or not win.winfo_exists():
            return
        try:
            mtime = os.path.getmtime(self.UNMET_FRAME_PATH)
        except OSError:
            mtime = None
        if mtime is not None and mtime != self._pv_mtime:
            try:
                photo = tk.PhotoImage(file=self.UNMET_FRAME_PATH)
                # width/height were in text units while there was no image; switch to pixels
                self._pv_img.configure(image=photo, text="")
                self._pv_photo = photo   # keep a reference or Tk drops the image
                self._pv_mtime = mtime
            except tk.TclError:
                pass   # half-written or unreadable; try again next tick
        lines = []
        try:
            with open(self.UNMET_RESULTS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            for k, r in enumerate(data.get("results", [])[:3], 1):
                name = str(r.get("ja") or r.get("en", "")).split("、")[0]
                lines.append(f"{k}. {name}  {float(r.get('score', 0)) * 100:.0f}%")
        except (OSError, ValueError):
            pass
        if self._pv_mtime is not None:
            age = int(time.time() - self._pv_mtime)
            lines.append(f"\n撮影 {time.strftime('%H:%M:%S', time.localtime(self._pv_mtime))}\n（{age} 秒前）"
                         + ("\n※UNMET 停止中？" if age > 90 else ""))
        self._pv_info.configure(text="\n".join(lines) or "UNMET の結果はまだありません")
        win.after(1000, self._pv_refresh)

    def _scal_off(self):
        if messagebox.askyesno("Servo Cal", "サーボ補正をオフにしますか？（測り直すとき用）"):
            self._send("scal off")
            for var in self.scal_vars.values():
                var.set("")

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


# ══════════════════════════════════════════
#  エントリーポイント
# ══════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    for _name in ("Noto Sans CJK JP", "Noto Sans JP", "DejaVu Sans"):
        if _name in tkfont.families():
            UI_FONT = _name
            break

    w, h = 1020, 760
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    if sw < w or sh < h:
        # Small Raspberry Pi monitor: fill the screen (the sidebar scrolls).
        root.minsize(1, 1)
        root.geometry(f"{sw}x{sh}+0+0")
        root.attributes("-zoomed", True)
    else:
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
