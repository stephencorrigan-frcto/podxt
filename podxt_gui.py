#!/usr/bin/env python3
"""Desktop window for podxt.py: browse patches, audition, store to slots, back up.

Every action runs the matching podxt command on a worker thread and streams its
output into the log pane. Only one action talks to the XT at a time.
"""
import argparse
import contextlib
import io
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import podxt


class QueueWriter(io.TextIOBase):
    def __init__(self, q):
        self.q = q

    def write(self, s):
        self.q.put(s)
        return len(s)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("POD XT Patch Loader")
        self.geometry("980x640")
        self.minsize(720, 480)
        self.log_q = queue.Queue()
        self.busy = False
        self.patches = {}

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(top, textvariable=self.search, width=30).pack(side="left", padx=6)
        self.status = ttk.Label(top, text="")
        self.status.pack(side="right")
        ttk.Button(top, text="Check connection", command=self.check).pack(side="right", padx=6)

        body = ttk.PanedWindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=8)

        table = ttk.Frame(body)
        cols = ("slot", "name", "amp", "description")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (60, 150, 160, 520)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor="w", stretch=(c == "description"))
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.audition())
        body.add(table, weight=3)

        logf = ttk.Frame(body)
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        body.add(logf, weight=1)

        btns = ttk.Frame(self, padding=8)
        btns.pack(fill="x")
        self.buttons = [
            ttk.Button(btns, text="Audition (send to edit buffer)", command=self.audition),
            ttk.Button(btns, text="Store to slot...", command=self.store),
            ttk.Button(btns, text="Back up all slots", command=self.backup),
            ttk.Button(btns, text="Capture XT sound...", command=self.capture),
            ttk.Button(btns, text="Store whole library", command=self.store_library),
        ]
        for b in self.buttons:
            b.pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Reload patches", command=self.reload).pack(side="right")

        self.reload()
        self.after(100, self.pump)

    # ------------------------------------------------------------ data

    def reload(self):
        try:
            self.patches = podxt.load_json(podxt.PATCHES)
        except OSError as e:
            messagebox.showerror("patches.json", str(e))
            self.patches = {}
        self.refresh()

    def refresh(self):
        q = self.search.get().lower()
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for key, p in self.patches.items():
            row = (p.get("slot", ""), p.get("name", key), p.get("models", {}).get("amp", ""),
                   p.get("description", ""))
            if q and q not in " ".join(row).lower():
                continue
            self.tree.insert("", "end", iid=key, values=row)
        keep = [k for k in keep if self.tree.exists(k)]
        if keep:
            self.tree.selection_set(keep)
            self.tree.see(keep[0])

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No patch", "Pick a patch first.")
            return None
        return sel[0]

    # ------------------------------------------------------------ running commands

    def run(self, label, fn, **kw):
        if self.busy:
            messagebox.showinfo("Busy", "Wait for the current action to finish.")
            return
        self.busy = True
        for b in self.buttons:
            b.state(["disabled"])
        self.status.config(text=label + "...")
        args = argparse.Namespace(usb=True, port=None, **kw)

        def work():
            with contextlib.redirect_stdout(QueueWriter(self.log_q)):
                try:
                    fn(args)
                except SystemExit as e:
                    if e.code not in (None, 0):
                        print(f"Error: {e.code}")
                except Exception as e:  # USB errors etc.
                    print(f"Error: {e}")
            self.log_q.put(None)

        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        try:
            while True:
                item = self.log_q.get_nowait()
                if item is None:
                    self.busy = False
                    for b in self.buttons:
                        b.state(["!disabled"])
                    self.status.config(text="Ready")
                    self.reload()
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", item)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.pump)

    # ------------------------------------------------------------ actions

    def check(self):
        self.run("Checking", podxt.cmd_ports)

    def audition(self):
        key = self.selected()
        if key:
            self.run("Sending", podxt.cmd_send, patch=key, gap=0)

    def store(self):
        key = self.selected()
        if not key:
            return
        default = self.patches[key].get("slot", "")
        slot = simpledialog.askstring("Store to slot",
                                      "Slot to overwrite (1A-32D). The old patch is backed up first.",
                                      initialvalue=default, parent=self)
        if slot:
            self.run("Storing", podxt.cmd_store, patch=key, slot=slot.strip())

    def backup(self):
        self.run("Backing up", podxt.cmd_backup)

    def capture(self):
        name = simpledialog.askstring("Capture", "Save the XT's current sound as patch:", parent=self)
        if name:
            self.run("Capturing", podxt.cmd_dump, save=name.strip())

    def store_library(self):
        if messagebox.askyesno("Store whole library",
                               "Overwrite every slot that has a patch assigned?\n"
                               "Run 'Back up all slots' first if you want the current ones."):
            self.run("Storing library", podxt.cmd_store_library)


if __name__ == "__main__":
    App().mainloop()
