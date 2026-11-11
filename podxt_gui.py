#!/usr/bin/env python3
"""POD XT library app: browse ~1000 artists, drag sounds onto the XT's 128 slots, commit.

Left: the artist library (search, filter, four sounds per artist).
Right: the XT's 32 banks x 4 slots. Drag a sound onto a slot, or an artist onto a bank
to fill A-D. Changed slots are marked until you press Commit, which backs up and
writes only those slots. Every XT action runs on a worker thread; the log shows output.
"""
import argparse
import contextlib
import io
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import podxt

# Palette: plum accent on a warm ground. Colour goes on data, status and the one primary action.
GROUND = "#f7f3f6"
SHEET = "#ffffff"
INK = "#1f1522"
INK2 = "#605862"
INK3 = "#756e77"
LINE = "#edeced"
LINE_STRONG = "#d8d6d9"
PLUM = "#5b2a5e"
PLUM_DEEP = "#3a1b3c"
PLUM_SOFT = "#ede7ed"
NEG = "#a8322f"

UI = ("Segoe UI", 10)
UI_SMALL = ("Segoe UI", 9)
UI_BOLD = ("Segoe UI Semibold", 10)
UI_TITLE = ("Segoe UI Semibold", 15)
MONO = ("Consolas", 9)

KINDS = {"cln": "Clean", "rhy": "Rhythm", "ld": "Lead", "sig": "Signature"}
SOURCES = {"All artists": None, "Your artists": "you", "Spotify picks": "spotify",
           "Curated": "curated", "Hand-tuned": "hand"}


class QueueWriter(io.TextIOBase):
    def __init__(self, q):
        self.q = q

    def write(self, s):
        self.q.put(("log", s))
        return len(s)


def sort_name(artist):
    return artist[4:].lower() if artist.lower().startswith("the ") else artist.lower()


def kind_of(key, patch):
    """Clean / Rhythm / Lead / Signature for generated sounds, the name for hand-tuned ones."""
    if "genre" in patch:
        return KINDS.get(key.rsplit("_", 1)[-1], patch.get("name", key))
    return patch.get("name", key)


def fit(text, n=21):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def fx_summary(patch):
    m = patch.get("models", {})
    on = patch.get("on", {})
    parts = [m.get("amp", "")]
    for block in ("stomp", "mod", "delay"):
        if on.get(block) and m.get(block):
            parts.append(m[block])
    return " + ".join(p for p in parts if p)


def dpi_aware():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        dpi_aware()
        super().__init__()
        self.scale = self.winfo_fpixels("1i") / 96
        self.title("POD XT Library")
        w = min(self.px(1360), self.winfo_screenwidth() - self.px(40))
        h = min(self.px(860), self.winfo_screenheight() - self.px(80))
        self.geometry(f"{w}x{h}+{self.px(20)}+{self.px(20)}")
        self.minsize(self.px(1100), self.px(600))
        self.configure(bg=GROUND)
        self.q = queue.Queue()
        self.busy = False
        self.on_done = None
        self.drag = None
        self.ghost = None
        self.selected_slot = None
        self.xt_names = {}

        self.style_widgets()
        self.load_data()
        self.build_top()
        body = tk.Frame(self, bg=GROUND)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.build_library(body)
        self.build_grid(body)
        self.build_log()
        self.refresh_tree()
        self.refresh_grid()
        self.after(100, self.pump)

    # ------------------------------------------------------------ look

    def px(self, n):
        return int(n * self.scale)

    def style_widgets(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=GROUND, foreground=INK, font=UI)
        s.configure("Treeview", background=SHEET, fieldbackground=SHEET, foreground=INK,
                    rowheight=self.px(26), borderwidth=0, font=UI)
        s.map("Treeview", background=[("selected", PLUM_SOFT)], foreground=[("selected", INK)])
        s.configure("Treeview.Heading", background=SHEET, foreground=INK3, relief="flat",
                    font=UI_SMALL, borderwidth=0)
        s.map("Treeview.Heading", background=[("active", SHEET)])
        s.configure("Primary.TButton", background=PLUM, foreground="white", borderwidth=0,
                    focusthickness=0, padding=(16, 7), font=UI_BOLD)
        s.map("Primary.TButton", background=[("disabled", LINE_STRONG), ("active", PLUM_DEEP)],
              foreground=[("disabled", SHEET)])
        s.configure("TButton", background=SHEET, foreground=INK, bordercolor=LINE_STRONG,
                    lightcolor=SHEET, darkcolor=SHEET, padding=(12, 6), font=UI)
        s.map("TButton", background=[("active", PLUM_SOFT), ("disabled", GROUND)],
              foreground=[("disabled", INK3)])
        s.configure("TMenubutton", background=SHEET, foreground=INK, padding=(12, 6))
        s.configure("TEntry", fieldbackground=SHEET, bordercolor=LINE_STRONG, padding=6)
        s.configure("TCombobox", fieldbackground=SHEET, background=SHEET, bordercolor=LINE_STRONG,
                    padding=4)
        s.configure("Vertical.TScrollbar", background=GROUND, troughcolor=GROUND,
                    bordercolor=GROUND, arrowcolor=INK3)

    # ------------------------------------------------------------ data

    def load_data(self):
        self.patches = podxt.all_patches()
        self.layout = podxt.load_layout()
        self.pending = {}
        lib = podxt.load_json(podxt.LIBRARY) if podxt.LIBRARY.exists() else {"artists": []}
        self.artist_info = {a["artist"]: a for a in lib.get("artists", [])}
        self.by_artist = {}
        for key, p in self.patches.items():
            self.by_artist.setdefault(p.get("artist", "Unsorted"), []).append(key)
        for artist in self.by_artist:
            self.artist_info.setdefault(artist, {"artist": artist, "genre": "", "source": "hand"})
            hand = [k for k in self.by_artist[artist] if "_" not in k[-4:] or k.rsplit("_", 1)[-1] not in KINDS]
            if hand:
                self.artist_info[artist]["source"] = (
                    "you" if self.artist_info[artist].get("source") == "you" else "hand")
        order = list(KINDS)
        for keys in self.by_artist.values():
            keys.sort(key=lambda k: order.index(k.rsplit("_", 1)[-1]) if k.rsplit("_", 1)[-1] in order else -1)

    def current(self, label):
        return self.pending.get(label, self.layout.get(label))

    # ------------------------------------------------------------ top bar

    def build_top(self):
        top = tk.Frame(self, bg=GROUND)
        top.pack(fill="x", padx=16, pady=(14, 10))
        tk.Label(top, text="POD XT Library", font=UI_TITLE, bg=GROUND, fg=INK).pack(side="left")
        n_art = len(self.by_artist)
        tk.Label(top, text=f"{n_art} artists, {len(self.patches)} sounds", font=UI_SMALL,
                 bg=GROUND, fg=INK3).pack(side="left", padx=(12, 0), pady=(5, 0))
        self.commit_btn = ttk.Button(top, text="Commit 0 changes", style="Primary.TButton",
                                     command=self.commit)
        self.commit_btn.pack(side="right")
        self.revert_btn = ttk.Button(top, text="Revert all", command=self.revert_all)
        self.revert_btn.pack(side="right", padx=(0, 8))
        ttk.Button(top, text="Read XT", command=self.read_xt).pack(side="right", padx=(0, 8))
        more = ttk.Menubutton(top, text="More")
        menu = tk.Menu(more, tearoff=False, bg=SHEET, fg=INK, activebackground=PLUM_SOFT,
                       activeforeground=INK)
        menu.add_command(label="Check connection", command=self.check)
        menu.add_command(label="Back up all 128 slots", command=self.backup)
        menu.add_command(label="Capture XT sound as a patch...", command=self.capture)
        more["menu"] = menu
        more.pack(side="right", padx=(0, 8))
        self.status = tk.Label(top, text="Ready", font=UI_SMALL, bg=GROUND, fg=INK3)
        self.status.pack(side="right", padx=(0, 16), pady=(5, 0))

    # ------------------------------------------------------------ library

    def build_library(self, parent):
        left = tk.Frame(parent, bg=SHEET, highlightthickness=1, highlightbackground=LINE)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        bar = tk.Frame(left, bg=SHEET)
        bar.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(bar, text="Library", font=UI_BOLD, bg=SHEET, fg=INK).pack(side="left")
        self.source = tk.StringVar(value="All artists")
        cb = ttk.Combobox(bar, textvariable=self.source, values=list(SOURCES), state="readonly", width=14)
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tree())
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.debounce_tree())
        e = ttk.Entry(bar, textvariable=self.search, width=28)
        e.pack(side="right", padx=8)
        tk.Label(bar, text="Search", font=UI_SMALL, bg=SHEET, fg=INK3).pack(side="right")

        wrap = tk.Frame(left, bg=SHEET)
        wrap.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 8))
        self.tree = ttk.Treeview(wrap, columns=("detail", "slot"), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Artist / sound", anchor="w")
        self.tree.heading("detail", text="Genre / amp and effects", anchor="w")
        self.tree.heading("slot", text="On XT", anchor="w")
        self.tree.column("#0", width=self.px(220), stretch=False)
        self.tree.column("detail", width=self.px(220))
        self.tree.column("slot", width=self.px(80), stretch=False)
        self.tree.tag_configure("artist", font=UI_BOLD, foreground=INK)
        self.tree.tag_configure("sound", foreground=INK2)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<ButtonPress-1>", self.tree_press)
        self.tree.bind("<B1-Motion>", self.drag_motion)
        self.tree.bind("<ButtonRelease-1>", self.drag_release)
        self.tree.bind("<Double-1>", lambda _e: self.audition())

        foot = tk.Frame(left, bg=SHEET)
        foot.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(foot, text="Drag a sound onto a slot, or an artist onto a bank to fill A-D.",
                 font=UI_SMALL, bg=SHEET, fg=INK3).pack(side="left")
        ttk.Button(foot, text="Audition", command=self.audition).pack(side="right")
        self._tree_job = None

    def debounce_tree(self):
        if self._tree_job:
            self.after_cancel(self._tree_job)
        self._tree_job = self.after(250, self.refresh_tree)

    def slot_of(self):
        where = {}
        for label in self.layout.keys() | self.pending.keys():
            key = self.current(label)
            if key:
                where.setdefault(key, []).append(label)
        return where

    def refresh_tree(self):
        q = self.search.get().strip().lower()
        src = SOURCES[self.source.get()]
        where = self.slot_of()
        open_items = {self.tree.item(i, "text") for i in self.tree.get_children() if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for artist in sorted(self.by_artist, key=sort_name):
            info = self.artist_info.get(artist, {})
            if src and info.get("source") != src:
                continue
            keys = self.by_artist[artist]
            hay = " ".join([artist, info.get("genre", "")] + [self.patches[k].get("name", "") for k in keys]).lower()
            if q and q not in hay:
                continue
            on = sorted({lbl for k in keys for lbl in where.get(k, [])}, key=podxt.parse_slot)
            pid = self.tree.insert("", "end", iid=f"artist::{artist}", text=artist,
                                   values=(info.get("genre", ""), " ".join(on[:3])), tags=("artist",),
                                   open=artist in open_items or bool(q and shown < 5))
            for k in keys:
                p = self.patches[k]
                self.tree.insert(pid, "end", iid=k, text=kind_of(k, p),
                                 values=(fx_summary(p), " ".join(sorted(where.get(k, []), key=podxt.parse_slot))),
                                 tags=("sound",))
            shown += 1

    # ------------------------------------------------------------ slot grid

    def build_grid(self, parent):
        right = tk.Frame(parent, bg=SHEET, highlightthickness=1, highlightbackground=LINE)
        right.pack(side="right", fill="both")
        head = tk.Frame(right, bg=SHEET)
        head.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(head, text="XT slots", font=UI_BOLD, bg=SHEET, fg=INK).pack(side="left")
        self.grid_note = tk.Label(head, text="", font=UI_SMALL, bg=SHEET, fg=INK3)
        self.grid_note.pack(side="right")
        cw, ch, bw = self.px(168), self.px(48), self.px(30)
        cols = tk.Frame(right, bg=SHEET)
        cols.pack(fill="x", padx=12)
        tk.Frame(cols, bg=SHEET, width=bw + self.px(6), height=1).pack(side="left")
        for letter in "ABCD":
            f = tk.Frame(cols, bg=SHEET, width=cw, height=self.px(18))
            f.pack(side="left", padx=2)
            f.pack_propagate(False)
            tk.Label(f, text=letter, font=UI_SMALL, bg=SHEET, fg=INK3, anchor="w").pack(
                fill="x", padx=self.px(9))

        holder = tk.Frame(right, bg=SHEET)
        holder.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        self.canvas = tk.Canvas(holder, bg=SHEET, highlightthickness=0,
                                width=bw + self.px(6) + 4 * (cw + 4) + self.px(8))
        sb = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        inner = tk.Frame(self.canvas, bg=SHEET)
        self.canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", self.wheel)

        self.cells = {}
        for bank in range(32):
            row = tk.Frame(inner, bg=SHEET)
            row.pack(fill="x", pady=2)
            num = tk.Frame(row, bg=SHEET, width=bw, height=ch)
            num.pack(side="left", padx=(0, self.px(6)))
            num.pack_propagate(False)
            tk.Label(num, text=str(bank + 1), anchor="e", font=UI_SMALL, bg=SHEET,
                     fg=INK3).pack(fill="both", expand=True)
            for i, letter in enumerate("ABCD"):
                label = f"{bank + 1}{letter}"
                cell = tk.Frame(row, bg=SHEET, highlightthickness=1, highlightbackground=LINE,
                                width=cw, height=ch)
                cell.pack(side="left", padx=2)
                cell.pack_propagate(False)
                bar = tk.Frame(cell, bg=SHEET, width=3)
                bar.pack(side="left", fill="y")
                text = tk.Frame(cell, bg=SHEET)
                text.pack(side="left", fill="both", expand=True, padx=(6, 4), pady=3)
                artist = tk.Label(text, text="", font=UI_BOLD, bg=SHEET, fg=INK, anchor="w")
                artist.pack(fill="x")
                sound = tk.Label(text, text="", font=UI_SMALL, bg=SHEET, fg=INK3, anchor="w")
                sound.pack(fill="x")
                parts = (cell, bar, text, artist, sound)
                for w in parts:
                    w.slot = label
                    w.bind("<ButtonPress-1>", lambda e, l=label: self.cell_press(e, l))
                    w.bind("<B1-Motion>", self.drag_motion)
                    w.bind("<ButtonRelease-1>", self.drag_release)
                    w.bind("<Double-1>", lambda _e, l=label: self.audition_slot(l))
                    w.bind("<Button-3>", lambda e, l=label: self.cell_menu(e, l))
                self.cells[label] = parts

    def wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        if w is not None and str(w).startswith(str(self.canvas)):
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def refresh_grid(self):
        for label, (cell, bar, text, artist, sound) in self.cells.items():
            key = self.current(label)
            p = self.patches.get(key, {})
            changed = label in self.pending
            bg = PLUM_SOFT if changed else SHEET
            for w in (cell, text, artist, sound):
                w.configure(bg=bg)
            bar.configure(bg=PLUM if changed else bg)
            cell.configure(highlightbackground=PLUM if label == self.selected_slot else LINE)
            artist.configure(text=fit(p.get("artist", "")) or "(empty)", fg=INK if p else INK3)
            kind = kind_of(key, p) if p else ""
            sub = (f"{kind}  {p.get('name', '')}" if kind != p.get("name") else kind) if p else ""
            xt = self.xt_names.get(label)
            if xt and p and not changed and xt != p.get("name"):
                sub, colour = f"On XT: {xt}", NEG
            else:
                colour = INK3
            sound.configure(text=sub, fg=colour)
        n = len(self.pending)
        self.commit_btn.configure(text=f"Commit {n} change{'s' if n != 1 else ''}")
        self.commit_btn.state(["!disabled"] if n and not self.busy else ["disabled"])
        self.revert_btn.state(["!disabled"] if n and not self.busy else ["disabled"])
        self.grid_note.configure(text=f"{n} uncommitted" if n else "Matches layout.json")

    def assign(self, label, key):
        if key == self.layout.get(label):
            self.pending.pop(label, None)
        else:
            self.pending[label] = key

    def cell_menu(self, e, label):
        menu = tk.Menu(self, tearoff=False, bg=SHEET, fg=INK, activebackground=PLUM_SOFT,
                       activeforeground=INK)
        menu.add_command(label=f"Audition {label}", command=lambda: self.audition_slot(label))
        if label in self.pending:
            menu.add_command(label="Revert this slot", command=lambda: self.revert(label))
        key = self.current(label)
        if key:
            menu.add_command(label="Show in library", command=lambda: self.reveal(key))
        menu.tk_popup(e.x_root, e.y_root)

    def reveal(self, key):
        self.search.set("")
        self.source.set("All artists")
        self.refresh_tree()
        if self.tree.exists(key):
            self.tree.item(self.tree.parent(key), open=True)
            self.tree.selection_set(key)
            self.tree.see(key)

    def revert(self, label):
        self.pending.pop(label, None)
        self.refresh_grid()
        self.refresh_tree()

    def revert_all(self):
        self.pending.clear()
        self.refresh_grid()
        self.refresh_tree()

    # ------------------------------------------------------------ drag and drop

    def tree_press(self, e):
        item = self.tree.identify_row(e.y)
        self.drag = {"from": "tree", "item": item, "x": e.x_root, "y": e.y_root, "moved": False} if item else None

    def cell_press(self, _e, label):
        self.selected_slot = label
        self.drag = {"from": "slot", "item": label, "x": _e.x_root, "y": _e.y_root, "moved": False}
        self.refresh_grid()

    def drag_text(self):
        d = self.drag
        if d["from"] == "slot":
            p = self.patches.get(self.current(d["item"]), {})
            return f"{d['item']}  {p.get('artist', '')}"
        if d["item"].startswith("artist::"):
            return f"{d['item'][8:]}  (all 4 sounds)"
        p = self.patches[d["item"]]
        return f"{p.get('artist', '')}  {kind_of(d['item'], p)}"

    def drag_motion(self, e):
        if not self.drag:
            return
        if not self.drag["moved"] and abs(e.x_root - self.drag["x"]) + abs(e.y_root - self.drag["y"]) < 6:
            return
        if not self.drag["moved"]:
            self.drag["moved"] = True
            self.ghost = tk.Toplevel(self)
            self.ghost.overrideredirect(True)
            self.ghost.attributes("-topmost", True)
            tk.Label(self.ghost, text=self.drag_text(), font=UI_BOLD, bg=PLUM, fg="white",
                     padx=10, pady=4).pack()
        self.ghost.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        # scroll the slot grid when dragging near its top or bottom edge
        cy, ch = self.canvas.winfo_rooty(), self.canvas.winfo_height()
        cx, cw = self.canvas.winfo_rootx(), self.canvas.winfo_width()
        if cx <= e.x_root <= cx + cw:
            edge = self.px(40)
            if cy - edge <= e.y_root < cy + edge:
                self.canvas.yview_scroll(-1, "units")
            elif cy + ch - edge < e.y_root <= cy + ch + edge:
                self.canvas.yview_scroll(1, "units")

    def drag_release(self, e):
        d, self.drag = self.drag, None
        if self.ghost:
            self.ghost.destroy()
            self.ghost = None
        if not d or not d["moved"]:
            return
        target = self.winfo_containing(e.x_root, e.y_root)
        label = getattr(target, "slot", None)
        if not label:
            return
        if d["from"] == "slot":
            src = d["item"]
            if src != label:
                a, b = self.current(src), self.current(label)
                self.assign(label, a)
                self.assign(src, b)
        elif d["item"].startswith("artist::"):
            keys = self.by_artist[d["item"][8:]][:4]
            bank = label[:-1]
            for letter, key in zip("ABCD", keys):
                self.assign(f"{bank}{letter}", key)
        else:
            self.assign(label, d["item"])
        self.selected_slot = label
        self.refresh_grid()
        self.refresh_tree()

    def cell_center(self, label):
        cell = self.cells[label][0]
        return cell.winfo_rootx() + cell.winfo_width() // 2, cell.winfo_rooty() + cell.winfo_height() // 2

    # ------------------------------------------------------------ XT actions

    def run(self, label, fn, done=None, **kw):
        if self.busy:
            messagebox.showinfo("Busy", "Wait for the current action to finish.")
            return
        self.busy = True
        self.on_done = done
        self.status.config(text=label + "...", fg=PLUM)
        self.refresh_grid()
        args = argparse.Namespace(usb=True, port=None, **kw)

        def work():
            result = None
            with contextlib.redirect_stdout(QueueWriter(self.q)):
                try:
                    result = fn(args) if kw or fn.__code__.co_argcount else fn()
                except SystemExit as e:
                    if e.code not in (None, 0):
                        print(f"Error: {e.code}")
                except Exception as e:  # USB errors etc.
                    print(f"Error: {e}")
            self.q.put(("done", result))

        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        try:
            while True:
                kind, item = self.q.get_nowait()
                if kind == "done":
                    self.busy = False
                    self.status.config(text="Ready", fg=INK3)
                    cb, self.on_done = self.on_done, None
                    if cb:
                        cb(item)
                    self.refresh_grid()
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", item)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def selected_key(self):
        sel = self.tree.selection()
        if sel and not sel[0].startswith("artist::"):
            return sel[0]
        if self.selected_slot:
            return self.current(self.selected_slot)
        return None

    def audition(self):
        key = self.selected_key()
        if not key:
            messagebox.showinfo("Audition", "Pick a sound in the library or a slot first.")
            return
        self.run("Auditioning", podxt.cmd_send, patch=key, gap=0)

    def audition_slot(self, label):
        key = self.current(label)
        if key:
            self.run(f"Auditioning {label}", podxt.cmd_send, patch=key, gap=0)

    def commit(self):
        if not self.pending:
            return
        pairs = dict(self.pending)
        lines = "\n".join(f"{l}: {self.patches[k].get('artist', '')} - {self.patches[k].get('name', k)}"
                          for l, k in sorted(pairs.items(), key=lambda kv: podxt.parse_slot(kv[0])))
        if not messagebox.askyesno("Commit to XT",
                                   f"Write {len(pairs)} slot(s) to the XT?\n"
                                   f"Each slot is backed up first.\n\n{lines[:1500]}"):
            return

        def done(failed):
            failed = set(failed or pairs)
            for label, key in pairs.items():
                if label not in failed:
                    self.layout[label] = key
                    self.pending.pop(label, None)
                    self.xt_names[label] = self.patches[key].get("name")
            podxt.save_layout(self.layout)
            self.refresh_tree()

        self.run(f"Committing {len(pairs)}", lambda: podxt.commit_layout(pairs), done=done)

    def read_xt(self):
        def done(names):
            if names:
                self.xt_names = names
                diff = [l for l, n in names.items()
                        if n and self.patches.get(self.layout.get(l), {}).get("name") != n]
                print(f"Read 128 slot names. {len(diff)} differ from layout.json.")
        self.run("Reading XT", lambda: podxt.read_slot_names(), done=done)

    def check(self):
        self.run("Checking", podxt.cmd_ports)

    def backup(self):
        self.run("Backing up", podxt.cmd_backup)

    def capture(self):
        name = simpledialog.askstring("Capture", "Save the XT's current sound as patch:", parent=self)
        if name:
            def done(_r):
                self.load_data()
                self.refresh_tree()
            self.run("Capturing", podxt.cmd_dump, done=done, save=name.strip())

    # ------------------------------------------------------------ log

    def build_log(self):
        frame = tk.Frame(self, bg=GROUND)
        frame.pack(fill="x", padx=16, pady=(0, 14))
        self.log = tk.Text(frame, height=6, wrap="word", state="disabled", bg=GROUND, fg=INK2,
                           font=MONO, relief="flat", highlightthickness=1,
                           highlightbackground=LINE, padx=8, pady=6)
        self.log.pack(fill="x")


if __name__ == "__main__":
    App().mainloop()
