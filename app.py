import os
import sys
import csv
import json
import math
import html
import time
import shutil
import sqlite3
import hashlib
import datetime
import subprocess
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

APP_NAME = "BitePOS - Restaurant Edition"
APP_VERSION = "8.0 (Pro UI)"
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(BASE, "pos_database.db")
ACTIVATION_FILE = os.path.join(BASE, ".activated")
CONFIG_FILE = os.path.join(BASE, "config.json")
RECEIPTS_DIR = os.path.join(BASE, "receipts")
KITCHEN_DIR = os.path.join(RECEIPTS_DIR, "kitchen")

for _folder in (RECEIPTS_DIR, KITCHEN_DIR):
    os.makedirs(_folder, exist_ok=True)

# --- THEME (light, dark) ---
ctk.set_appearance_mode("Light")
BG_MAIN = ("#f3f4f6", "#0b0f19")
BG_CARD = ("#ffffff", "#141a29")
BG_SUBTLE = ("#f9fafb", "#1b2335")
HOVER = ("#f3f4f6", "#222b40")
ACCENT_ORANGE = "#ea580c"
ACCENT_HOVER = "#c2410c"
ACCENT_SOFT = ("#fff7ed", "#2b1b12")
TEXT_DARK = ("#111827", "#f3f4f6")
TEXT_MUTED = ("#6b7280", "#9ca3af")
BORDER_COLOR = ("#e5e7eb", "#263049")
SUCCESS = "#10b981"
SUCCESS_HOVER = "#059669"
DANGER = "#ef4444"
DANGER_SOFT = ("#fee2e2", "#3b1518")
INFO = "#2563eb"
INFO_HOVER = "#1d4ed8"
WARN = "#f59e0b"
WARN_SOFT = ("#fef3c7", "#3a2c0c")

FONT = "Segoe UI"
EMOJI_FONT = "Segoe UI Emoji"
MONO = "Consolas"

ORDER_TYPES = ["Takeaway", "Dine-In", "Delivery"]
PAYMENT_METHODS = ["Cash", "Card", "Online"]
PAYMENT_COLORS = {"Cash": SUCCESS, "Card": INFO, "Online": "#8b5cf6"}
DEFAULT_CATEGORIES = ["Appetizers", "Mains", "Soups", "Desserts", "Beverages", "Other"]
CATEGORY_EMOJI = {"Appetizers": "🥟", "Mains": "🍛", "Soups": "🍜", "Desserts": "🍰", "Beverages": "🥤", "Other": "🍽️"}
PERIODS = ["Today", "7 Days", "30 Days"]


def F(size, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)


def resolve(color):
    """Pick the light/dark variant of a color for plain tk widgets (Canvas, ttk)."""
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def open_path(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        webbrowser.open(Path(path).resolve().as_uri())


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def hash_pin(pin):
    return hashlib.sha256(f"bitepos-pin::{pin}".encode()).hexdigest()


def period_since(period):
    today = datetime.date.today()
    if period == "Today":
        return today.isoformat()
    if period == "7 Days":
        return (today - datetime.timedelta(days=6)).isoformat()
    if period == "30 Days":
        return (today - datetime.timedelta(days=29)).isoformat()
    return None

# ================= LICENSE SYSTEM =================
def get_hardware_id():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        return hashlib.sha256(str(guid).encode()).hexdigest()[:16].upper()
    except:
        return "UNKNOWN-HARDWARE"

def verify_license_file(filepath):
    hwid = get_hardware_id()
    secret_salt = "PRO_UPSCALER_SECRET_2024"
    expected_key = hashlib.sha256(f"{hwid}-{secret_salt}".encode()).hexdigest().upper()
    try:
        with open(filepath, "r") as f:
            provided_key = f.read().strip().upper()
        return provided_key == expected_key
    except:
        return False

def check_license():
    return os.path.exists(ACTIVATION_FILE)

def save_activation():
    with open(ACTIVATION_FILE, "w") as f:
        f.write("ACTIVATED")

# ================= DATABASE ENGINE =================
def db():
    return sqlite3.connect(DB_FILE)

def ensure_column(c, table, column, definition):
    cols = [row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, item_name TEXT, price REAL, cost REAL, quantity INTEGER, timestamp TEXT, order_type TEXT, payment_method TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT, cost REAL, price REAL, stock INTEGER)''')
    # v8: one row per order with totals, discounts and tax (sales keeps the per-item lines)
    c.execute('''CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, timestamp TEXT, customer TEXT, order_type TEXT, table_no TEXT, payment_method TEXT, subtotal REAL, discount REAL, tax REAL, total REAL, tendered REAL, change_due REAL, note TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS held_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT, payload TEXT, created TEXT)''')
    ensure_column(c, "items", "emoji", "TEXT DEFAULT ''")

    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()[0] == 0:
        items = [
            ("Chia Kiew Sah Mon", "Appetizers", 1.00, 2.40, 50, "🥟"),
            ("Tom Yum Soup", "Soups", 1.50, 3.50, 30, "🍜"),
            ("Green Curry", "Soups", 2.00, 4.20, 25, "🍛"),
            ("Fried Chicken", "Appetizers", 2.50, 5.00, 40, "🍗"),
            ("Iced Tea", "Beverages", 0.30, 1.50, 100, "🧋"),
            ("Coca Cola", "Beverages", 0.50, 1.50, 100, "🥤"),
            ("Mango Sticky Rice", "Desserts", 1.20, 3.00, 20, "🥭"),
            ("Spring Rolls", "Appetizers", 1.00, 2.80, 60, "🌯")
        ]
        c.executemany("INSERT INTO items (name, category, cost, price, stock, emoji) VALUES (?, ?, ?, ?, ?, ?)", items)
    conn.commit()
    conn.close()

def get_next_order_number():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT order_id FROM sales UNION SELECT order_id FROM orders")
    nums = []
    for (oid,) in c.fetchall():
        try:
            nums.append(int(str(oid).split("-")[-1]))
        except ValueError:
            pass
    conn.close()
    return f"ORD-{max(nums) + 1 if nums else 1001}"

def fetch_orders(since=None):
    """Order summaries, including legacy orders that only exist in the sales table."""
    conn = db()
    c = conn.cursor()
    rows = []
    params = (since,) if since else ()
    q = ("SELECT o.order_id, o.timestamp, o.customer, o.order_type, o.table_no, o.payment_method, o.subtotal, o.discount, o.tax, o.total, "
         "(SELECT COALESCE(SUM(quantity), 0) FROM sales s WHERE s.order_id = o.order_id) FROM orders o")
    if since:
        q += " WHERE o.timestamp >= ?"
    for r in c.execute(q, params).fetchall():
        rows.append(dict(order_id=r[0], timestamp=r[1] or "", customer=r[2] or "Walk-in", order_type=r[3] or "", table_no=r[4] or "",
                         payment=r[5] or "", subtotal=r[6] or 0, discount=r[7] or 0, tax=r[8] or 0, total=r[9] or 0, items=r[10] or 0))
    q = ("SELECT order_id, MIN(timestamp), MAX(order_type), MAX(payment_method), SUM(quantity), SUM(price * quantity) "
         "FROM sales WHERE order_id NOT IN (SELECT order_id FROM orders)")
    if since:
        q += " AND timestamp >= ?"
    q += " GROUP BY order_id"
    for r in c.execute(q, params).fetchall():
        rows.append(dict(order_id=r[0], timestamp=r[1] or "", customer="Walk-in", order_type=r[2] or "", table_no="",
                         payment=r[3] or "", subtotal=r[5] or 0, discount=0, tax=0, total=r[5] or 0, items=r[4] or 0))
    conn.close()
    rows.sort(key=lambda o: o["timestamp"], reverse=True)
    return rows

def fetch_order_detail(order_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT item_name, price, SUM(quantity) FROM sales WHERE order_id = ? GROUP BY item_name, price ORDER BY MIN(id)", (order_id,))
    lines = [dict(name=r[0], price=r[1] or 0, qty=r[2] or 1) for r in c.fetchall()]
    c.execute("SELECT order_id, timestamp, customer, order_type, table_no, payment_method, subtotal, discount, tax, total, tendered, change_due, note FROM orders WHERE order_id = ?", (order_id,))
    r = c.fetchone()
    if r:
        order = dict(order_id=r[0], timestamp=r[1] or "", customer=r[2] or "Walk-in", order_type=r[3] or "", table_no=r[4] or "",
                     payment=r[5] or "", subtotal=r[6] or 0, discount=r[7] or 0, tax=r[8] or 0, total=r[9] or 0,
                     tendered=r[10] or 0, change=r[11] or 0, note=r[12] or "")
    else:
        c.execute("SELECT MIN(timestamp), MAX(order_type), MAX(payment_method) FROM sales WHERE order_id = ?", (order_id,))
        ts, ot, pm = c.fetchone()
        sub = sum(l["price"] * l["qty"] for l in lines)
        order = dict(order_id=order_id, timestamp=ts or "", customer="Walk-in", order_type=ot or "", table_no="", payment=pm or "",
                     subtotal=sub, discount=0, tax=0, total=sub, tendered=0, change=0, note="")
    conn.close()
    return order, lines

# ================= WIDGETS =================
class BarChart(ctk.CTkFrame):
    """Minimal single-series bar chart drawn on a tk Canvas."""
    def __init__(self, master, height=230, value_fmt=str, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0, bg=resolve(BG_CARD))
        self.canvas.pack(fill="both", expand=True)
        self.labels, self.values = [], []
        self.value_fmt = value_fmt
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, labels, values):
        self.labels, self.values = labels, values
        self.redraw()

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        cv.configure(bg=resolve(BG_CARD))
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 40:
            return
        muted, grid = resolve(TEXT_MUTED), resolve(BORDER_COLOR)
        if not self.values or max(self.values) <= 0:
            cv.create_text(w / 2, h / 2, text="No sales in this period yet", fill=muted, font=F(12))
            return
        pad_l, pad_r, pad_t, pad_b = 8, 8, 22, 26
        plot_h = h - pad_t - pad_b
        vmax = max(self.values)
        for i in range(4):
            y = pad_t + plot_h * i / 3
            cv.create_line(pad_l, y, w - pad_r, y, fill=grid)
        n = len(self.values)
        slot = (w - pad_l - pad_r) / n
        bar_w = max(4, min(44, slot * 0.6))
        every = max(1, math.ceil(n / 10))
        for i, (label, v) in enumerate(zip(self.labels, self.values)):
            x = pad_l + slot * i + slot / 2
            y0 = h - pad_b - plot_h * v / vmax
            if v > 0:
                cv.create_rectangle(x - bar_w / 2, y0, x + bar_w / 2, h - pad_b, fill=ACCENT_ORANGE, outline="")
                if n <= 12:
                    cv.create_text(x, y0 - 9, text=self.value_fmt(v), fill=muted, font=F(9))
            if i % every == 0:
                cv.create_text(x, h - pad_b + 13, text=label, fill=muted, font=F(9))

# ================= LICENSE SCREEN =================
class LicenseScreen(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Activation Required")
        self.geometry("500x480")
        self.configure(fg_color=BG_MAIN)

        hwid = get_hardware_id()

        ctk.CTkLabel(self, text="🔒 BitePOS Activation", font=F(24, True), text_color=TEXT_DARK).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="This software requires a one-time license.", font=F(13), text_color=TEXT_MUTED).pack(pady=5)

        frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        frame.pack(pady=20, padx=40, fill="x")

        ctk.CTkLabel(frame, text="Your Hardware ID:", font=F(12), text_color=TEXT_MUTED).pack(pady=(15, 0))
        ctk.CTkLabel(frame, text=hwid, font=(MONO, 18, "bold"), text_color=ACCENT_ORANGE).pack(pady=(0, 5))

        def copy_id():
            self.clipboard_clear()
            self.clipboard_append(hwid)
            copy_btn.configure(text="✓ Copied")

        copy_btn = ctk.CTkButton(frame, text="📋 Copy ID", width=100, height=28, fg_color=BG_MAIN, text_color=TEXT_DARK, hover_color=HOVER, command=copy_id)
        copy_btn.pack(pady=(0, 15))

        ctk.CTkLabel(frame, text="1. Send the ID above to support.\n2. Load the license file they send you.", font=F(12), justify="left", text_color=TEXT_DARK).pack(pady=10, padx=20, anchor="w")

        self.btn_activate = ctk.CTkButton(self, text="📂 Load License File (.key)", fg_color=ACCENT_ORANGE, hover_color=ACCENT_HOVER, height=46, corner_radius=12, font=F(14, True), command=self.activate)
        self.btn_activate.pack(pady=(10, 5), padx=40, fill="x")

        self.btn_buy = ctk.CTkButton(self, text="💳 Buy a License Key", fg_color=SUCCESS, hover_color=SUCCESS_HOVER, height=46, corner_radius=12, font=F(14, True), command=self.open_store)
        self.btn_buy.pack(pady=(5, 20), padx=40, fill="x")

    def open_store(self):
        webbrowser.open("https://bojji7.gumroad.com/l/bite-pos")

    def activate(self):
        filepath = filedialog.askopenfilename(filetypes=[("License File", "*.key")])
        if not filepath: return
        if verify_license_file(filepath):
            save_activation()
            messagebox.showinfo("Success", "License Activated Successfully!")
            self.destroy()
            run_main_app()
        else:
            messagebox.showerror("Invalid", "The license file is invalid.")

# ================= MAIN APP =================
class App(ctk.CTk):
    def __init__(self):
        self.config_data = load_config()
        ctk.set_appearance_mode(self.config_data.get("appearance", "Light"))
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1420x900")
        self.minsize(1200, 760)
        self.configure(fg_color=BG_MAIN)

        self.cart = []
        self.order_type = "Takeaway"
        self.payment_method = "Cash"
        self.pos_state = self.default_pos_state()
        self.currency = self.config_data.get("currency", "$")
        self.is_admin = False
        self.failed_pin = 0
        self.pin_locked_until = 0
        self.current_page = None
        self.active_category = "All"
        self.menu_query = ""
        self.items_by_name = {}
        self.history_period = "7 Days"
        self.analytics_period = "7 Days"
        self.history_rows = []
        self._toast = None

        init_db()
        self.style_treeview()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.build_sidebar()
        self.build_topbar()

        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=1, column=1, sticky="nsew", padx=28, pady=(0, 24))

        self.bind("<F2>", lambda e: self.focus_search())
        self.bind("<F4>", lambda e: self.hold_order())
        self.bind("<F9>", lambda e: self.checkout())

        self.tick()
        self.show_pos()

    # ---------- config helpers ----------
    def save_config(self):
        with open(CONFIG_FILE, "w") as f: json.dump(self.config_data, f, indent=2)

    def check_pin(self, pin):
        if "admin_pin_hash" in self.config_data:
            return hash_pin(pin) == self.config_data["admin_pin_hash"]
        return pin == self.config_data.get("admin_pin", "1234")  # Default PIN

    def tax_rate(self):
        try:
            return max(0.0, float(self.config_data.get("tax_rate", 0)))
        except (TypeError, ValueError):
            return 0.0

    def low_stock_threshold(self):
        try:
            return int(self.config_data.get("low_stock", 5))
        except (TypeError, ValueError):
            return 5

    def money(self, value):
        sign = "-" if value < -0.004 else ""
        return f"{sign}{self.currency}{abs(value):,.2f}"

    def money_short(self, value):
        if value >= 1000:
            return f"{self.currency}{value / 1000:.1f}k"
        return f"{self.currency}{value:.0f}"

    def default_pos_state(self):
        return {"customer": "", "table": "", "note": "", "discount": "", "discount_mode": "%"}

    def sorted_categories(self, cats):
        cats = {c for c in cats if c}
        known = [c for c in DEFAULT_CATEGORIES if c in cats]
        return known + sorted(cats - set(known))

    def all_categories(self):
        conn = db()
        cats = {r[0] for r in conn.execute("SELECT DISTINCT category FROM items").fetchall()}
        conn.close()
        return self.sorted_categories(cats | set(DEFAULT_CATEGORIES))

    # ---------- shell ----------
    def style_treeview(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        bg, fg, head = resolve(BG_CARD), resolve(TEXT_DARK), resolve(BG_SUBTLE)
        style.configure("Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=36, borderwidth=0, font=F(11))
        style.configure("Treeview.Heading", background=head, foreground=resolve(TEXT_MUTED), font=F(10, True), relief="flat", padding=(8, 8))
        style.map("Treeview", background=[("selected", ACCENT_ORANGE)], foreground=[("selected", "white")])
        style.map("Treeview.Heading", background=[("active", head)])

    def build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=236, corner_radius=0, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.pack_propagate(False)

        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(pady=(28, 4), padx=20, anchor="w")
        ctk.CTkLabel(logo_frame, text="🍔", font=(EMOJI_FONT, 26)).pack(side="left")
        ctk.CTkLabel(logo_frame, text=" BitePOS", font=F(24, True), text_color=ACCENT_ORANGE).pack(side="left")
        self.rest_name_lbl = ctk.CTkLabel(self.sidebar, text=self.config_data.get("rest_name", "My Restaurant"), font=F(12), text_color=TEXT_MUTED)
        self.rest_name_lbl.pack(anchor="w", padx=22, pady=(0, 18))

        self.nav_items = [
            ("pos", "POS Terminal", "🛒", self.show_pos, False),
            ("orders", "Orders History", "🧾", self.show_orders, False),
            ("analytics", "Analytics", "📈", self.show_reports, True),
            ("menu", "Menu Management", "📖", self.show_menu_mgmt, True),
            ("inventory", "Inventory", "📦", self.show_inventory, True),
            ("settings", "Settings", "⚙️", self.show_settings, True),
        ]
        self.nav_buttons = {}
        section = None
        for key, name, icon, _, admin_only in self.nav_items:
            label = "ADMIN" if admin_only else "OPERATIONS"
            if label != section:
                section = label
                ctk.CTkLabel(self.sidebar, text=label, font=F(10, True), text_color=TEXT_MUTED).pack(anchor="w", padx=22, pady=(14, 4))
            btn = ctk.CTkButton(self.sidebar, text=f"{icon}   {name}", anchor="w", fg_color="transparent", text_color=TEXT_DARK, hover_color=HOVER,
                                height=42, corner_radius=10, font=F(13), command=lambda k=key: self.navigate(k))
            btn.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", pady=18, padx=16)

        self.dark_switch = ctk.CTkSwitch(bottom, text="🌙  Dark mode", font=F(12), text_color=TEXT_DARK, progress_color=ACCENT_ORANGE, command=self.toggle_dark_mode)
        if ctk.get_appearance_mode() == "Dark":
            self.dark_switch.select()
        self.dark_switch.pack(anchor="w", pady=(0, 12))

        self.admin_btn = ctk.CTkButton(bottom, text="👤 Admin Login", fg_color="transparent", border_width=1, border_color=BORDER_COLOR,
                                       text_color=TEXT_DARK, hover_color=HOVER, height=40, corner_radius=10, command=self.toggle_admin)
        self.admin_btn.pack(fill="x")
        ctk.CTkLabel(bottom, text=f"v{APP_VERSION}", font=F(10), text_color=TEXT_MUTED).pack(pady=(8, 0))
        self.update_admin_ui()

    def build_topbar(self):
        self.topbar = ctk.CTkFrame(self, height=84, corner_radius=0, fg_color="transparent")
        self.topbar.grid(row=0, column=1, sticky="ew", padx=28, pady=(14, 10))

        titles = ctk.CTkFrame(self.topbar, fg_color="transparent")
        titles.pack(side="left")
        self.page_title = ctk.CTkLabel(titles, text="POS Terminal", font=F(24, True), text_color=TEXT_DARK)
        self.page_title.pack(anchor="w")
        self.page_sub = ctk.CTkLabel(titles, text="", font=F(12), text_color=TEXT_MUTED)
        self.page_sub.pack(anchor="w")

        self.clock_lbl = ctk.CTkLabel(self.topbar, text="", font=F(13, True), text_color=TEXT_DARK, fg_color=BG_CARD, corner_radius=10, height=36)
        self.clock_lbl.pack(side="right", ipadx=12)

    def tick(self):
        self.clock_lbl.configure(text=datetime.datetime.now().strftime("🕒  %a %d %b  •  %I:%M %p"))
        self.after(15000, self.tick)

    def toast(self, message, kind="success"):
        colors = {"success": SUCCESS, "error": DANGER, "info": INFO, "warn": WARN}
        if self._toast is not None and self._toast.winfo_exists():
            self._toast.destroy()
        t = ctk.CTkFrame(self, fg_color=colors.get(kind, SUCCESS), corner_radius=12)
        ctk.CTkLabel(t, text=message, text_color="white", font=F(13, True)).pack(padx=18, pady=10)
        t.place(relx=0.985, rely=0.975, anchor="se")
        t.lift()
        self._toast = t
        self.after(2800, lambda: t.winfo_exists() and t.destroy())

    def make_dialog(self, title, width, height):
        d = ctk.CTkToplevel(self)
        d.title(title)
        d.configure(fg_color=BG_MAIN)
        d.resizable(False, False)
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - height) // 2)
        d.geometry(f"{width}x{height}+{x}+{y}")
        d.transient(self)

        def focus():
            if not d.winfo_exists():
                return
            try:
                d.grab_set()
            except tk.TclError:
                pass
            d.lift()
            d.focus_force()
        d.after(150, focus)
        d.bind("<Escape>", lambda e: d.destroy())
        return d

    def make_card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR, **kwargs)

    def make_tree(self, parent, columns, widths=None, anchors=None):
        wrap = self.make_card(parent)
        tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            tree.heading(col, text=col.upper(), anchor=(anchors or {}).get(col, "w"))
            tree.column(col, width=(widths or {}).get(col, 120), anchor=(anchors or {}).get(col, "w"))
        sb = ctk.CTkScrollbar(wrap, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=12)
        sb.pack(side="right", fill="y", padx=4, pady=12)
        tree.tag_configure("odd", background=resolve(BG_SUBTLE))
        tree.tag_configure("low", foreground=WARN)
        tree.tag_configure("out", foreground=DANGER)
        return wrap, tree

    def make_entry(self, parent, placeholder="", **kwargs):
        opts = dict(placeholder_text=placeholder, height=38, corner_radius=10, fg_color=BG_SUBTLE, border_color=BORDER_COLOR, text_color=TEXT_DARK, font=F(13))
        opts.update(kwargs)
        return ctk.CTkEntry(parent, **opts)

    def ghost_button(self, parent, text, command, **kwargs):
        opts = dict(text=text, command=command, height=38, corner_radius=10, fg_color=BG_CARD, text_color=TEXT_DARK, hover_color=HOVER,
                    border_width=1, border_color=BORDER_COLOR, font=F(12, True))
        opts.update(kwargs)
        return ctk.CTkButton(parent, **opts)

    def accent_button(self, parent, text, command, color=ACCENT_ORANGE, hover=ACCENT_HOVER, **kwargs):
        opts = dict(text=text, command=command, height=38, corner_radius=10, fg_color=color, hover_color=hover, text_color="white", font=F(12, True))
        opts.update(kwargs)
        return ctk.CTkButton(parent, **opts)

    # ---------- navigation & admin ----------
    def navigate(self, key):
        for k, _, _, fn, admin_only in self.nav_items:
            if k == key:
                if admin_only and not self.is_admin:
                    self.ask_pin(lambda: self.navigate(key))
                    return
                fn()
                return

    def begin_page(self, key, title, subtitle=""):
        self.current_page = key
        self.set_active_button(key)
        self.page_title.configure(text=title)
        self.page_sub.configure(text=subtitle)
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def set_active_button(self, active_key):
        for key, btn in self.nav_buttons.items():
            if key == active_key:
                btn.configure(fg_color=ACCENT_ORANGE, text_color="white", hover_color=ACCENT_HOVER, font=F(13, True))
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_DARK, hover_color=HOVER, font=F(13))

    def update_admin_ui(self):
        for key, name, icon, _, admin_only in self.nav_items:
            lock = "   🔒" if admin_only and not self.is_admin else ""
            self.nav_buttons[key].configure(text=f"{icon}   {name}{lock}")
        if self.is_admin:
            self.admin_btn.configure(text="🔓 Admin  •  Log out", fg_color=SUCCESS, hover_color=SUCCESS_HOVER, text_color="white", border_width=0)
        else:
            self.admin_btn.configure(text="👤 Admin Login", fg_color="transparent", hover_color=HOVER, text_color=TEXT_DARK, border_width=1)

    def toggle_admin(self):
        if self.is_admin:
            self.is_admin = False
            self.update_admin_ui()
            self.toast("Logged out of admin", "info")
            if self.current_page in ("analytics", "menu", "inventory", "settings"):
                self.show_pos()
        else:
            self.ask_pin()

    def ask_pin(self, on_success=None):
        d = self.make_dialog("Admin Access", 360, 340)
        ctk.CTkLabel(d, text="🔐", font=(EMOJI_FONT, 36)).pack(pady=(26, 2))
        ctk.CTkLabel(d, text="Admin Access", font=F(20, True), text_color=TEXT_DARK).pack()
        ctk.CTkLabel(d, text="Enter your admin PIN to continue", font=F(12), text_color=TEXT_MUTED).pack(pady=(2, 10))
        entry = self.make_entry(d, show="•", justify="center", height=46, width=210, font=F(20, True), fg_color=BG_CARD)
        entry.pack(pady=6)
        err = ctk.CTkLabel(d, text="", text_color=DANGER, font=F(12))
        err.pack()

        def submit(*_):
            remaining = int(self.pin_locked_until - time.time())
            if remaining > 0:
                err.configure(text=f"Too many attempts. Try again in {remaining}s")
                return
            if self.check_pin(entry.get()):
                self.is_admin = True
                self.failed_pin = 0
                d.destroy()
                self.update_admin_ui()
                self.toast("Admin mode unlocked")
                (on_success or self.show_reports)()
            else:
                self.failed_pin += 1
                entry.delete(0, "end")
                if self.failed_pin % 5 == 0:
                    self.pin_locked_until = time.time() + 30
                    err.configure(text="Too many attempts. Locked for 30s")
                else:
                    err.configure(text=f"Incorrect PIN ({self.failed_pin} failed)")

        self.accent_button(d, "Unlock", submit, height=42, width=210).pack(pady=(6, 0))
        entry.bind("<Return>", submit)
        d.after(250, entry.focus_set)

    def toggle_dark_mode(self):
        mode = "Dark" if self.dark_switch.get() else "Light"
        ctk.set_appearance_mode(mode)
        self.config_data["appearance"] = mode
        self.save_config()
        self.style_treeview()
        self.navigate(self.current_page or "pos")

    # ================= POS PAGE =================
    def show_pos(self):
        self.begin_page("pos", "POS Terminal", "Tap items to build an order   •   F2 search   •   F4 hold   •   F9 charge")

        pos_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        pos_frame.pack(fill="both", expand=True)

        cart_frame = ctk.CTkFrame(pos_frame, width=390, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        cart_frame.pack(side="right", fill="y")
        cart_frame.pack_propagate(False)
        self.build_cart_panel(cart_frame)

        menu_area = ctk.CTkFrame(pos_frame, fg_color="transparent")
        menu_area.pack(side="left", fill="both", expand=True, padx=(0, 20))

        self.search_entry = self.make_entry(menu_area, "🔍  Search menu items…   (F2)", height=44, corner_radius=12, fg_color=BG_CARD)
        self.search_entry.pack(fill="x")
        if self.menu_query:
            self.search_entry.insert(0, self.menu_query)
        self.search_entry.bind("<KeyRelease>", self.on_search)
        self.search_entry.bind("<Escape>", lambda e: self.reset_search())

        self.cat_frame = ctk.CTkFrame(menu_area, fg_color="transparent")
        self.cat_frame.pack(fill="x", pady=(12, 6))

        self.items_grid = ctk.CTkScrollableFrame(menu_area, fg_color="transparent")
        self.items_grid.pack(fill="both", expand=True)

        self.load_menu_items()
        self.refresh_cart()

    def build_cart_panel(self, cart_frame):
        s = self.pos_state
        head = ctk.CTkFrame(cart_frame, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 4))
        title_row = ctk.CTkFrame(head, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text="Current Order", font=F(18, True), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkButton(title_row, text="Clear", width=56, height=28, corner_radius=8, fg_color="transparent", text_color=DANGER,
                      hover_color=DANGER_SOFT, font=F(12, True), command=self.clear_cart).pack(side="right")
        self.order_no_lbl = ctk.CTkLabel(head, text=f"{get_next_order_number()}", font=F(12), text_color=TEXT_MUTED)
        self.order_no_lbl.pack(anchor="w")

        self.customer_entry = self.make_entry(head, "👤  Customer name (optional)", height=36)
        self.customer_entry.pack(fill="x", pady=(8, 6))
        if s["customer"]:
            self.customer_entry.insert(0, s["customer"])

        type_row = ctk.CTkFrame(head, fg_color="transparent")
        type_row.pack(fill="x")
        self.order_type_seg = ctk.CTkSegmentedButton(type_row, values=ORDER_TYPES, height=32, font=F(12, True), command=self.set_order_type,
                                                     selected_color=ACCENT_ORANGE, selected_hover_color=ACCENT_HOVER)
        self.order_type_seg.set(self.order_type)
        self.order_type_seg.pack(side="left", fill="x", expand=True)
        self.table_entry = self.make_entry(type_row, "Table #", width=76, height=32)
        self.table_entry.pack(side="right", padx=(8, 0))
        if s["table"]:
            self.table_entry.insert(0, s["table"])
        self.table_entry.configure(state="normal" if self.order_type == "Dine-In" else "disabled")

        # Bottom section is packed before the list so it stays pinned to the panel bottom
        bottom = ctk.CTkFrame(cart_frame, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=(6, 16))

        self.note_entry = self.make_entry(bottom, "📝  Kitchen note (e.g. no chili)", height=34)
        self.note_entry.pack(fill="x", pady=(0, 6))
        if s["note"]:
            self.note_entry.insert(0, s["note"])

        disc_row = ctk.CTkFrame(bottom, fg_color="transparent")
        disc_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(disc_row, text="🏷️ Discount", font=F(12, True), text_color=TEXT_DARK).pack(side="left")
        self.discount_mode_seg = ctk.CTkSegmentedButton(disc_row, values=["%", "Fixed"], width=110, height=30, font=F(12, True),
                                                        command=self.set_discount_mode, selected_color=INFO, selected_hover_color=INFO_HOVER)
        self.discount_mode_seg.set(s["discount_mode"])
        self.discount_mode_seg.pack(side="right")
        self.discount_entry = self.make_entry(disc_row, "0", width=80, height=30, justify="right")
        self.discount_entry.pack(side="right", padx=8)
        if s["discount"]:
            self.discount_entry.insert(0, s["discount"])

        for entry in (self.customer_entry, self.table_entry, self.note_entry, self.discount_entry):
            entry.bind("<KeyRelease>", self.on_pos_input)

        totals = ctk.CTkFrame(bottom, fg_color=BG_SUBTLE, corner_radius=12)
        totals.pack(fill="x", pady=(0, 10))
        totals.grid_columnconfigure(0, weight=1)

        def total_row(r, label, bold=False, color=TEXT_MUTED):
            lbl = ctk.CTkLabel(totals, text=label, font=F(12, bold), text_color=color)
            lbl.grid(row=r, column=0, sticky="w", padx=14, pady=(8 if r == 0 else 0, 0))
            val = ctk.CTkLabel(totals, text="", font=F(12, bold), text_color=color)
            val.grid(row=r, column=1, sticky="e", padx=14, pady=(8 if r == 0 else 0, 0))
            return lbl, val

        _, self.subtotal_val = total_row(0, "Subtotal")
        _, self.discount_val = total_row(1, "Discount")
        self.tax_lbl, self.tax_val = total_row(2, "Tax")
        ctk.CTkLabel(totals, text="Total", font=F(15, True), text_color=TEXT_DARK).grid(row=3, column=0, sticky="w", padx=14, pady=(4, 10))
        self.total_val = ctk.CTkLabel(totals, text="", font=F(24, True), text_color=ACCENT_ORANGE)
        self.total_val.grid(row=3, column=1, sticky="e", padx=14, pady=(4, 10))

        actions = ctk.CTkFrame(bottom, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 8))
        actions.grid_columnconfigure((0, 1), weight=1, uniform="act")
        self.ghost_button(actions, "⏸  Hold  (F4)", self.hold_order).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.held_btn = self.ghost_button(actions, "📂  Held (0)", self.show_held_orders)
        self.held_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.charge_btn = self.accent_button(bottom, "Charge", self.checkout, color=INFO, hover=INFO_HOVER, height=50, corner_radius=12, font=F(16, True))
        self.charge_btn.pack(fill="x")

        self.cart_count_lbl = ctk.CTkLabel(cart_frame, text="", font=F(11, True), text_color=TEXT_MUTED)
        self.cart_count_lbl.pack(anchor="w", padx=20, pady=(8, 0))
        self.cart_list = ctk.CTkScrollableFrame(cart_frame, fg_color="transparent")
        self.cart_list.pack(fill="both", expand=True, padx=10, pady=(0, 4))

    def on_pos_input(self, *_):
        if self.current_page != "pos":
            return
        self.pos_state.update(customer=self.customer_entry.get(), table=self.table_entry.get(),
                              note=self.note_entry.get(), discount=self.discount_entry.get())
        self.update_totals()

    def set_discount_mode(self, value):
        self.pos_state["discount_mode"] = value
        self.update_totals()

    def focus_search(self):
        if self.current_page == "pos":
            self.search_entry.focus_set()

    def on_search(self, *_):
        self.menu_query = self.search_entry.get()
        self.load_menu_items()

    def reset_search(self):
        self.menu_query = ""
        self.search_entry.delete(0, "end")
        self.load_menu_items()
        self.focus()

    def filter_category(self, category):
        self.active_category = category
        self.load_menu_items()

    def grid_columns(self):
        width = self.winfo_width()
        if width < 200:
            width = 1420
        return max(2, min(5, (width - 236 - 390 - 110) // 185))

    def load_menu_items(self):
        if self.current_page != "pos":
            return
        conn = db()
        rows = conn.execute("SELECT id, name, category, cost, price, stock, COALESCE(emoji, '') FROM items ORDER BY category, name").fetchall()
        conn.close()
        self.items_by_name = {r[1]: {"id": r[0], "category": r[2], "cost": r[3], "price": r[4], "stock": r[5], "emoji": r[6]} for r in rows}

        categories = self.sorted_categories({r[2] for r in rows})
        if self.active_category != "All" and self.active_category not in categories:
            self.active_category = "All"

        for widget in self.cat_frame.winfo_children():
            widget.destroy()
        for cat in ["All"] + categories:
            count = len(rows) if cat == "All" else sum(1 for r in rows if r[2] == cat)
            active = cat == self.active_category
            ctk.CTkButton(self.cat_frame, text=f"{cat}  ·  {count}", width=70, height=34, corner_radius=17, font=F(12, True),
                          fg_color=ACCENT_ORANGE if active else BG_CARD, text_color="white" if active else TEXT_DARK,
                          hover_color=ACCENT_HOVER if active else HOVER, border_width=0 if active else 1, border_color=BORDER_COLOR,
                          command=lambda c=cat: self.filter_category(c)).pack(side="left", padx=(0, 8))

        q = self.menu_query.strip().lower()
        visible = [r for r in rows
                   if (self.active_category == "All" or r[2] == self.active_category)
                   and (not q or q in r[1].lower() or q in (r[2] or "").lower())]
        self.render_item_cards(visible)

    def render_item_cards(self, visible):
        grid = self.items_grid
        for widget in grid.winfo_children():
            widget.destroy()
        if not visible:
            ctk.CTkLabel(grid, text="🔎", font=(EMOJI_FONT, 40)).pack(pady=(60, 4))
            ctk.CTkLabel(grid, text="No items match your search", font=F(15, True), text_color=TEXT_DARK).pack()
            ctk.CTkLabel(grid, text="Try another name or press Esc to clear", font=F(12), text_color=TEXT_MUTED).pack()
            return

        cols = self.grid_columns()
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="menu")
        low = self.low_stock_threshold()

        for index, (item_id, name, category, cost, price, stock, emoji) in enumerate(visible):
            sold_out = stock <= 0
            card = ctk.CTkFrame(grid, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
            card.grid(row=index // cols, column=index % cols, padx=6, pady=6, sticky="nsew")

            thumb = ctk.CTkFrame(card, height=84, fg_color=BG_SUBTLE if sold_out else ACCENT_SOFT, corner_radius=12)
            thumb.pack(fill="x", padx=10, pady=(10, 8))
            thumb.pack_propagate(False)
            icon = ctk.CTkLabel(thumb, text=emoji or CATEGORY_EMOJI.get(category, "🍽️"), font=(EMOJI_FONT, 34))
            icon.pack(expand=True)

            name_lbl = ctk.CTkLabel(card, text=name, font=F(13, True), text_color=TEXT_DARK, wraplength=150, justify="left", anchor="w")
            name_lbl.pack(fill="x", padx=12)
            ctk.CTkLabel(card, text=category, font=F(11), text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=12)

            meta = ctk.CTkFrame(card, fg_color="transparent")
            meta.pack(fill="x", padx=12, pady=(4, 6))
            price_lbl = ctk.CTkLabel(meta, text=self.money(price), font=F(15, True), text_color=ACCENT_ORANGE)
            price_lbl.pack(side="left")
            if sold_out:
                badge_text, badge_bg, badge_fg = "Sold out", DANGER_SOFT, DANGER
            elif stock <= low:
                badge_text, badge_bg, badge_fg = f"{stock} left", WARN_SOFT, WARN
            else:
                badge_text, badge_bg, badge_fg = f"{stock} in stock", BG_SUBTLE, TEXT_MUTED
            ctk.CTkLabel(meta, text=badge_text, font=F(10, True), fg_color=badge_bg, text_color=badge_fg, corner_radius=8, height=22).pack(side="right", ipadx=6)

            ctk.CTkButton(card, text="Sold out" if sold_out else "+ Add to order", height=32, corner_radius=10, font=F(12, True),
                          fg_color=BG_SUBTLE, hover_color=ACCENT_SOFT, text_color=TEXT_DARK, text_color_disabled=TEXT_MUTED,
                          state="disabled" if sold_out else "normal",
                          command=lambda n=name: self.add_to_cart(n)).pack(fill="x", padx=10, pady=(0, 10))
            if not sold_out:
                for widget in (card, thumb, icon, name_lbl, price_lbl):
                    widget.bind("<Button-1>", lambda e, n=name: self.add_to_cart(n))

    def set_order_type(self, value):
        self.order_type = value
        self.table_entry.configure(state="normal" if value == "Dine-In" else "disabled")
        if value == "Dine-In":
            self.table_entry.focus_set()

    def add_to_cart(self, name):
        info = self.items_by_name.get(name)
        if not info:
            return
        line = next((i for i in self.cart if i["name"] == name), None)
        qty = line["qty"] if line else 0
        if qty + 1 > info["stock"]:
            self.toast(f"Only {info['stock']} × {name} in stock", "warn")
            return
        if line:
            line["qty"] += 1
        else:
            self.cart.append({"name": name, "price": info["price"], "qty": 1})
        self.refresh_cart()

    def change_qty(self, name, delta):
        if delta > 0:
            self.add_to_cart(name)
            return
        for item in self.cart:
            if item["name"] == name:
                item["qty"] += delta
                if item["qty"] <= 0:
                    self.cart.remove(item)
                break
        self.refresh_cart()

    def remove_line(self, name):
        self.cart = [i for i in self.cart if i["name"] != name]
        self.refresh_cart()

    def clear_cart(self):
        had_items = bool(self.cart)
        self.cart = []
        self.pos_state = self.default_pos_state()
        if self.current_page == "pos":
            self.show_pos()
        if had_items:
            self.toast("Order cleared", "info")

    def compute_totals(self):
        s = self.pos_state
        subtotal = sum(i["price"] * i["qty"] for i in self.cart)
        try:
            dval = max(0.0, float(s.get("discount") or 0))
        except ValueError:
            dval = 0.0
        if s.get("discount_mode") == "Fixed":
            discount = min(dval, subtotal)
        else:
            discount = subtotal * min(dval, 100) / 100
        rate = self.tax_rate()
        tax = (subtotal - discount) * rate / 100
        total = round(subtotal - discount + tax, 2)
        return {"subtotal": subtotal, "discount": discount, "tax": tax, "tax_rate": rate, "total": total}

    def update_totals(self):
        if self.current_page != "pos":
            return
        t = self.compute_totals()
        self.subtotal_val.configure(text=self.money(t["subtotal"]))
        self.discount_val.configure(text=f"− {self.money(t['discount'])}")
        self.tax_lbl.configure(text=f"Tax ({t['tax_rate']:g}%)")
        self.tax_val.configure(text=self.money(t["tax"]))
        self.total_val.configure(text=self.money(t["total"]))
        self.charge_btn.configure(text=f"💳  Charge {self.money(t['total'])}   (F9)", state="normal" if self.cart else "disabled")

    def refresh_cart(self):
        if self.current_page != "pos":
            return
        for widget in self.cart_list.winfo_children():
            widget.destroy()

        if not self.cart:
            ctk.CTkLabel(self.cart_list, text="🧺", font=(EMOJI_FONT, 38)).pack(pady=(40, 4))
            ctk.CTkLabel(self.cart_list, text="No items yet", font=F(14, True), text_color=TEXT_DARK).pack()
            ctk.CTkLabel(self.cart_list, text="Tap a menu item to start an order", font=F(12), text_color=TEXT_MUTED).pack()

        for item in self.cart:
            row = ctk.CTkFrame(self.cart_list, fg_color=BG_SUBTLE, corner_radius=10)
            row.pack(fill="x", pady=4, padx=2)
            row.grid_columnconfigure(0, weight=1)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=0, sticky="w", padx=(10, 4), pady=8)
            ctk.CTkLabel(info, text=item["name"], font=F(12, True), text_color=TEXT_DARK, wraplength=130, justify="left", anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"{self.money(item['price'])} each", font=F(10), text_color=TEXT_MUTED).pack(anchor="w")

            qty = ctk.CTkFrame(row, fg_color="transparent")
            qty.grid(row=0, column=1, padx=4)
            for text, delta in (("−", -1), ("+", 1)):
                btn = ctk.CTkButton(qty, text=text, width=28, height=28, corner_radius=8, font=F(14, True), fg_color=BG_CARD,
                                    text_color=TEXT_DARK, hover_color=ACCENT_SOFT, border_width=1, border_color=BORDER_COLOR,
                                    command=lambda n=item["name"], d=delta: self.change_qty(n, d))
                btn.pack(side="left")
                if delta < 0:
                    ctk.CTkLabel(qty, text=str(item["qty"]), width=28, font=F(13, True), text_color=TEXT_DARK).pack(side="left")

            ctk.CTkLabel(row, text=self.money(item["price"] * item["qty"]), font=F(12, True), text_color=ACCENT_ORANGE, width=64, anchor="e").grid(row=0, column=2, padx=4)
            ctk.CTkButton(row, text="✕", width=24, height=24, corner_radius=6, fg_color="transparent", text_color=TEXT_MUTED,
                          hover_color=DANGER_SOFT, command=lambda n=item["name"]: self.remove_line(n)).grid(row=0, column=3, padx=(0, 6))

        count = sum(i["qty"] for i in self.cart)
        self.cart_count_lbl.configure(text=f"ITEMS  ·  {count}")
        self.held_btn.configure(text=f"📂  Held ({self.held_count()})")
        self.update_totals()

    # ---------- held orders ----------
    def held_count(self):
        conn = db()
        n = conn.execute("SELECT COUNT(*) FROM held_orders").fetchone()[0]
        conn.close()
        return n

    def hold_order(self):
        if self.current_page != "pos":
            return
        if not self.cart:
            self.toast("Add items before holding an order", "warn")
            return
        s = self.pos_state
        if s["customer"].strip():
            label = s["customer"].strip()
        elif s["table"].strip() and self.order_type == "Dine-In":
            label = f"Table {s['table'].strip()}"
        else:
            label = f"{self.order_type} order"
        payload = json.dumps({"cart": self.cart, "pos_state": s, "order_type": self.order_type})
        conn = db()
        conn.execute("INSERT INTO held_orders (label, payload, created) VALUES (?, ?, ?)",
                     (label, payload, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        self.cart = []
        self.pos_state = self.default_pos_state()
        self.show_pos()
        self.toast(f"Order held: {label}", "info")

    def show_held_orders(self):
        conn = db()
        rows = conn.execute("SELECT id, label, payload, created FROM held_orders ORDER BY id DESC").fetchall()
        conn.close()

        d = self.make_dialog("Held Orders", 480, 540)
        ctk.CTkLabel(d, text="📂  Held Orders", font=F(20, True), text_color=TEXT_DARK).pack(anchor="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(d, text="Parked orders waiting to be finished", font=F(12), text_color=TEXT_MUTED).pack(anchor="w", padx=24, pady=(0, 10))

        lst = ctk.CTkScrollableFrame(d, fg_color="transparent")
        lst.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        if not rows:
            ctk.CTkLabel(lst, text="No held orders right now.", font=F(13), text_color=TEXT_MUTED).pack(pady=40)

        for hid, label, payload, created in rows:
            data = json.loads(payload)
            cart = data.get("cart", [])
            n = sum(i["qty"] for i in cart)
            sub = sum(i["price"] * i["qty"] for i in cart)
            card = self.make_card(lst)
            card.pack(fill="x", pady=5)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=14, pady=10)
            ctk.CTkLabel(info, text=label, font=F(14, True), text_color=TEXT_DARK).pack(anchor="w")
            ctk.CTkLabel(info, text=f"{n} items  •  {self.money(sub)}  •  held at {created[11:16]}", font=F(11), text_color=TEXT_MUTED).pack(anchor="w")
            ctk.CTkButton(card, text="🗑", width=36, height=34, corner_radius=8, fg_color="transparent", text_color=DANGER, hover_color=DANGER_SOFT,
                          command=lambda h=hid: self.delete_held(h, d)).pack(side="right", padx=(0, 10))
            self.accent_button(card, "Resume", lambda h=hid: self.resume_held(h, d), width=84, height=34).pack(side="right", padx=4)

    def resume_held(self, hid, dialog):
        if self.cart and not messagebox.askyesno("Replace current order?", "The current order will be replaced. Hold it first if you still need it.", parent=dialog):
            return
        conn = db()
        row = conn.execute("SELECT payload FROM held_orders WHERE id = ?", (hid,)).fetchone()
        conn.execute("DELETE FROM held_orders WHERE id = ?", (hid,))
        conn.commit()
        conn.close()
        dialog.destroy()
        if not row:
            return
        data = json.loads(row[0])
        self.cart = data.get("cart", [])
        self.pos_state = {**self.default_pos_state(), **data.get("pos_state", {})}
        self.order_type = data.get("order_type", "Takeaway")
        self.show_pos()
        self.toast("Held order resumed", "info")

    def delete_held(self, hid, dialog):
        if not messagebox.askyesno("Delete held order?", "This held order will be discarded.", parent=dialog):
            return
        conn = db()
        conn.execute("DELETE FROM held_orders WHERE id = ?", (hid,))
        conn.commit()
        conn.close()
        dialog.destroy()
        self.show_held_orders()
        if self.current_page == "pos":
            self.held_btn.configure(text=f"📂  Held ({self.held_count()})")

    # ---------- payment ----------
    def checkout(self):
        if self.current_page != "pos":
            return
        if not self.cart:
            self.toast("The order is empty", "warn")
            return
        self.on_pos_input()
        t = self.compute_totals()
        total = t["total"]

        d = self.make_dialog("Take Payment", 440, 560)
        ctk.CTkLabel(d, text="AMOUNT DUE", font=F(11, True), text_color=TEXT_MUTED).pack(pady=(26, 0))
        ctk.CTkLabel(d, text=self.money(total), font=F(38, True), text_color=ACCENT_ORANGE).pack()
        items = sum(i["qty"] for i in self.cart)
        ctk.CTkLabel(d, text=f"{items} items  •  {self.order_type}", font=F(12), text_color=TEXT_MUTED).pack(pady=(0, 14))

        bottom = ctk.CTkFrame(d, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=24, pady=(0, 22))
        err = ctk.CTkLabel(bottom, text="", font=F(12), text_color=DANGER)
        err.pack()

        method = tk.StringVar(value=self.payment_method)
        cash_frame = self.make_card(d)

        def toggle(*_):
            if method.get() == "Cash":
                cash_frame.pack(fill="x", padx=24, pady=12)
            else:
                cash_frame.pack_forget()

        seg = ctk.CTkSegmentedButton(d, values=PAYMENT_METHODS, variable=method, height=40, font=F(13, True), command=toggle,
                                     selected_color=INFO, selected_hover_color=INFO_HOVER)
        seg.pack(fill="x", padx=24)

        ctk.CTkLabel(cash_frame, text="Cash received", font=F(12, True), text_color=TEXT_MUTED).pack(anchor="w", padx=16, pady=(14, 4))
        tendered_entry = self.make_entry(cash_frame, f"{total:.2f}", height=44, font=F(18, True), justify="right")
        tendered_entry.pack(fill="x", padx=16)

        quick = ctk.CTkFrame(cash_frame, fg_color="transparent")
        quick.pack(fill="x", padx=12, pady=8)
        suggestions = [total]
        for step in (5, 10, 20, 50, 100):
            v = math.ceil(total / step) * step
            if v > total and v not in suggestions:
                suggestions.append(v)
        suggestions = suggestions[:4]
        quick.grid_columnconfigure(tuple(range(len(suggestions))), weight=1, uniform="q")

        change_lbl = ctk.CTkLabel(cash_frame, text="", font=F(16, True), text_color=SUCCESS)
        change_lbl.pack(pady=(0, 14))

        def tendered_value():
            raw = tendered_entry.get().strip()
            if not raw:
                return total
            try:
                return float(raw)
            except ValueError:
                return None

        def update_change(*_):
            v = tendered_value()
            if v is None:
                change_lbl.configure(text="Enter a valid amount", text_color=DANGER)
            elif v + 1e-9 < total:
                change_lbl.configure(text=f"Short by {self.money(total - v)}", text_color=DANGER)
            else:
                change_lbl.configure(text=f"Change due: {self.money(v - total)}", text_color=SUCCESS)

        def set_amount(v):
            tendered_entry.delete(0, "end")
            tendered_entry.insert(0, f"{v:.2f}")
            update_change()

        for i, v in enumerate(suggestions):
            self.ghost_button(quick, "Exact" if i == 0 else self.money(v), lambda v=v: set_amount(v), height=34).grid(row=0, column=i, sticky="ew", padx=4)
        tendered_entry.bind("<KeyRelease>", update_change)
        update_change()

        def confirm(*_):
            m = method.get()
            tendered, change = total, 0.0
            if m == "Cash":
                v = tendered_value()
                if v is None or v + 1e-9 < total:
                    err.configure(text="Cash received must cover the total.")
                    return
                tendered, change = v, v - total
            self.payment_method = m
            d.destroy()
            self.finalize_order(t, m, tendered, change)

        self.accent_button(bottom, "✓  Complete Payment", confirm, color=SUCCESS, hover=SUCCESS_HOVER, height=50, corner_radius=12, font=F(16, True)).pack(fill="x", pady=(4, 6))
        ctk.CTkButton(bottom, text="Cancel", height=30, fg_color="transparent", text_color=TEXT_MUTED, hover_color=HOVER, command=d.destroy).pack(fill="x")
        d.bind("<Return>", confirm)
        toggle()
        d.after(250, tendered_entry.focus_set)

    def finalize_order(self, t, method, tendered, change):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_num = get_next_order_number()
        s = self.pos_state
        customer = s.get("customer", "").strip() or "Walk-in"
        table = s.get("table", "").strip() if self.order_type == "Dine-In" else ""
        note = s.get("note", "").strip()

        conn = db()
        c = conn.cursor()
        try:
            for item in self.cart:
                c.execute("SELECT cost FROM items WHERE name = ?", (item["name"],))
                cost_res = c.fetchone()
                item_cost = cost_res[0] if cost_res else 0.0
                c.execute("INSERT INTO sales (order_id, item_name, price, cost, quantity, timestamp, order_type, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (order_num, item["name"], item["price"], item_cost, item["qty"], now, self.order_type, method))
                c.execute("UPDATE items SET stock = stock - ? WHERE name = ?", (item["qty"], item["name"]))
            c.execute("INSERT INTO orders (order_id, timestamp, customer, order_type, table_no, payment_method, subtotal, discount, tax, total, tendered, change_due, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (order_num, now, customer, self.order_type, table, method, t["subtotal"], t["discount"], t["tax"], t["total"], tendered, change, note))
            conn.commit()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Could not save the order:\n{e}")
            return
        finally:
            conn.close()

        order = dict(order_id=order_num, timestamp=now, customer=customer, order_type=self.order_type, table_no=table, payment=method,
                     subtotal=t["subtotal"], discount=t["discount"], tax=t["tax"], total=t["total"], tendered=tendered, change=change, note=note)
        lines = [dict(name=i["name"], price=i["price"], qty=i["qty"]) for i in self.cart]

        self.cart = []
        self.pos_state = self.default_pos_state()
        self.show_pos()
        self.show_receipt_dialog(order, lines, just_paid=True)

    # ---------- receipts & kitchen tickets ----------
    def _receipt_row(self, left, right, width):
        space = width - len(right) - 1
        if len(left) > space:
            left = left[:space - 1] + "…"
        return left.ljust(space) + " " + right

    def build_receipt_text(self, o, lines):
        W = 34
        cfg = self.config_data
        out = [cfg.get("rest_name", "My Restaurant").center(W)]
        for key in ("rest_address", "rest_phone"):
            if cfg.get(key):
                out.append(cfg[key].center(W))
        out.append("-" * W)
        out.append(f"Order   : {o['order_id']}")
        out.append(f"Date    : {o['timestamp']}")
        out.append(f"Customer: {o['customer']}")
        order_type = o["order_type"] + (f" (Table {o['table_no']})" if o.get("table_no") else "")
        out.append(f"Type    : {order_type}")
        out.append(f"Payment : {o['payment']}")
        out.append("-" * W)
        for l in lines:
            out.append(self._receipt_row(f"{l['qty']} x {l['name']}", self.money(l["price"] * l["qty"]), W))
        out.append("-" * W)
        out.append(self._receipt_row("Subtotal", self.money(o["subtotal"]), W))
        if o["discount"] > 0.004:
            out.append(self._receipt_row("Discount", f"-{self.money(o['discount'])}", W))
        if o["tax"] > 0.004:
            taxable = o["subtotal"] - o["discount"]
            rate = o["tax"] / taxable * 100 if taxable > 0 else self.tax_rate()
            out.append(self._receipt_row(f"Tax ({rate:.4g}%)", self.money(o["tax"]), W))
        out.append(self._receipt_row("TOTAL", self.money(o["total"]), W))
        if o["payment"] == "Cash" and o.get("tendered"):
            out.append(self._receipt_row("Cash", self.money(o["tendered"]), W))
            out.append(self._receipt_row("Change", self.money(o.get("change", 0)), W))
        out.append("-" * W)
        out.append(cfg.get("footer_msg", "Thank you!"))
        return "\n".join(out)

    def build_kitchen_ticket(self, o, lines):
        W = 30
        out = ["KITCHEN TICKET".center(W), "=" * W,
               o["order_id"].ljust(W - 5) + (o["timestamp"][11:16] or ""),
               (o["order_type"] + (f"  -  TABLE {o['table_no']}" if o.get("table_no") else "")).upper(),
               f"Customer: {o['customer']}", "-" * W]
        for l in lines:
            out.append(f"{l['qty']:>2} x {l['name']}")
        if o.get("note"):
            out += ["-" * W, "NOTE:", o["note"]]
        out.append("=" * W)
        return "\n".join(out)

    def save_html(self, text, order, kind="receipt"):
        folder = KITCHEN_DIR if kind == "kitchen" else RECEIPTS_DIR
        clean_name = "".join(ch for ch in order["customer"] if ch.isalnum()) or "Guest"
        clean_date = order["timestamp"].replace(" ", "_").replace(":", "-")
        prefix = "KOT_" if kind == "kitchen" else ""
        filepath = os.path.join(folder, f"{prefix}{order['order_id']}_{clean_name}_{clean_date}.html")
        size = 18 if kind == "kitchen" else 13
        html_content = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(order['order_id'])}</title>"
            f"<style>body{{font-family:Consolas,monospace;width:320px;margin:24px auto;font-size:{size}px}}"
            "pre{white-space:pre-wrap;font-family:inherit}"
            "button{width:100%;padding:10px;margin-bottom:16px;border:0;border-radius:8px;background:#ea580c;color:#fff;font-size:15px;cursor:pointer}"
            "@media print{button{display:none}body{margin:0}}</style></head><body>"
            "<button onclick='window.print()'>Print</button>"
            f"<pre>{html.escape(text)}</pre></body></html>"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        return filepath

    def show_receipt_dialog(self, order, lines, just_paid=True):
        text = self.build_receipt_text(order, lines)
        d = self.make_dialog("Payment Successful" if just_paid else f"Order {order['order_id']}", 470, 700)

        if just_paid:
            ctk.CTkLabel(d, text="✅  Payment successful", font=F(20, True), text_color=SUCCESS).pack(pady=(22, 2))
        else:
            ctk.CTkLabel(d, text="🧾  Order details", font=F(20, True), text_color=TEXT_DARK).pack(pady=(22, 2))
        ctk.CTkLabel(d, text=f"{order['order_id']}   •   {self.money(order['total'])}   •   {order['payment']}", font=F(13, True), text_color=ACCENT_ORANGE).pack()
        if just_paid and order["payment"] == "Cash" and order.get("change", 0) > 0.004:
            ctk.CTkLabel(d, text=f"Give change: {self.money(order['change'])}", font=F(18, True), text_color=TEXT_DARK,
                         fg_color=WARN_SOFT, corner_radius=10, height=40).pack(pady=(10, 0), ipadx=14)

        btns = ctk.CTkFrame(d, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=24, pady=(8, 20))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="r")

        box = ctk.CTkTextbox(d, font=(MONO, 12), fg_color=BG_CARD, text_color=TEXT_DARK, border_width=1, border_color=BORDER_COLOR, corner_radius=12, wrap="none")
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=24, pady=(14, 6))

        def do_print():
            path = self.save_html(text, order, "receipt")
            webbrowser.open(Path(path).resolve().as_uri())
            self.toast("Receipt saved and opened for printing")

        def do_kitchen():
            path = self.save_html(self.build_kitchen_ticket(order, lines), order, "kitchen")
            webbrowser.open(Path(path).resolve().as_uri())
            self.toast("Kitchen ticket sent to browser for printing")

        def do_whatsapp():
            self.clipboard_clear()
            self.clipboard_append(f"```\n{text}\n```")
            self.toast("Receipt copied — paste it in WhatsApp with Ctrl+V")

        self.ghost_button(btns, "🖨️  Print receipt", do_print, height=42).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=4)
        self.ghost_button(btns, "🍳  Kitchen ticket", do_kitchen, height=42).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=4)
        self.accent_button(btns, "💬  Copy for WhatsApp", do_whatsapp, color="#25D366", hover="#128C7E", height=42).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=4)
        self.accent_button(btns, "New order" if just_paid else "Close", d.destroy, height=42).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=4)

    # ================= ORDERS HISTORY =================
    def show_orders(self):
        self.begin_page("orders", "Orders History", "Every completed order   •   double-click a row to view or reprint")

        toolbar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))
        self.hist_search = self.make_entry(toolbar, "🔍  Search order #, customer, payment…", width=320, fg_color=BG_CARD)
        self.hist_search.pack(side="left")
        self.hist_search.bind("<KeyRelease>", lambda e: self.load_orders_table())
        self.hist_period = ctk.CTkSegmentedButton(toolbar, values=PERIODS + ["All"], height=38, font=F(12, True), command=lambda v: self.load_orders_table(),
                                                  selected_color=ACCENT_ORANGE, selected_hover_color=ACCENT_HOVER)
        self.hist_period.set(self.history_period)
        self.hist_period.pack(side="left", padx=12)
        self.ghost_button(toolbar, "⬇  Export CSV", lambda: self.export_csv(self.history_rows, "orders")).pack(side="right")
        self.ghost_button(toolbar, "🧾  View / Reprint", self.open_selected_order).pack(side="right", padx=8)

        self.hist_summary = ctk.CTkLabel(self.main_container, text="", font=F(13, True), text_color=TEXT_MUTED)
        self.hist_summary.pack(anchor="w", pady=(0, 8))

        cols = ("Order", "Time", "Customer", "Type", "Payment", "Items", "Total")
        wrap, self.ord_tree = self.make_tree(self.main_container, cols,
                                             widths={"Order": 110, "Time": 160, "Customer": 180, "Type": 150, "Payment": 100, "Items": 70, "Total": 110},
                                             anchors={"Items": "center", "Total": "e"})
        wrap.pack(fill="both", expand=True)
        self.ord_tree.bind("<Double-1>", lambda e: self.open_selected_order())
        self.load_orders_table()

    def load_orders_table(self):
        self.history_period = self.hist_period.get()
        rows = fetch_orders(period_since(self.history_period))
        q = self.hist_search.get().strip().lower()
        if q:
            rows = [r for r in rows if any(q in str(r[k]).lower() for k in ("order_id", "customer", "payment", "order_type", "table_no"))]
        self.history_rows = rows
        for row in self.ord_tree.get_children():
            self.ord_tree.delete(row)
        for i, r in enumerate(rows):
            order_type = r["order_type"] + (f" · T{r['table_no']}" if r["table_no"] else "")
            self.ord_tree.insert("", "end", values=(r["order_id"], r["timestamp"], r["customer"], order_type, r["payment"], r["items"], self.money(r["total"])),
                                 tags=("odd",) if i % 2 else ())
        collected = sum(r["total"] for r in rows)
        self.hist_summary.configure(text=f"{len(rows)} orders   •   {self.money(collected)} collected")

    def open_selected_order(self):
        sel = self.ord_tree.selection()
        if not sel:
            self.toast("Select an order first", "warn")
            return
        order_id = self.ord_tree.item(sel[0])["values"][0]
        order, lines = fetch_order_detail(str(order_id))
        self.show_receipt_dialog(order, lines, just_paid=False)

    def export_csv(self, rows, name):
        if not rows:
            self.toast("Nothing to export", "warn")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"bitepos_{name}_{datetime.date.today().isoformat()}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Order", "Timestamp", "Customer", "Type", "Table", "Payment", "Items", "Subtotal", "Discount", "Tax", "Total"])
            for r in rows:
                w.writerow([r["order_id"], r["timestamp"], r["customer"], r["order_type"], r["table_no"], r["payment"], r["items"],
                            f"{r['subtotal']:.2f}", f"{r['discount']:.2f}", f"{r['tax']:.2f}", f"{r['total']:.2f}"])
        self.toast(f"Exported {len(rows)} orders")

    # ================= ANALYTICS =================
    def show_reports(self):
        self.begin_page("analytics", "Analytics", "Revenue, profit and best sellers at a glance")
        period = self.analytics_period
        since = period_since(period)

        page = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        page.pack(fill="both", expand=True)
        page.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")

        orders = fetch_orders(since)
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=4, sticky="ew", padx=6, pady=(0, 6))
        seg = ctk.CTkSegmentedButton(toolbar, values=PERIODS, height=38, font=F(12, True), selected_color=ACCENT_ORANGE, selected_hover_color=ACCENT_HOVER,
                                     command=lambda v: (setattr(self, "analytics_period", v), self.show_reports()))
        seg.set(period)
        seg.pack(side="left")
        self.ghost_button(toolbar, "⬇  Export CSV", lambda: self.export_csv(orders, f"report_{period.replace(' ', '').lower()}")).pack(side="right")
        self.ghost_button(toolbar, "↻  Refresh", self.show_reports).pack(side="right", padx=8)

        conn = db()
        c = conn.cursor()
        cost = c.execute("SELECT COALESCE(SUM(cost * quantity), 0) FROM sales WHERE timestamp >= ?", (since,)).fetchone()[0]
        top_items = c.execute("SELECT item_name, SUM(quantity), SUM(price * quantity) FROM sales WHERE timestamp >= ? GROUP BY item_name ORDER BY 2 DESC LIMIT 6", (since,)).fetchall()
        low_items = c.execute("SELECT name, stock FROM items WHERE stock <= ? ORDER BY stock ASC LIMIT 8", (self.low_stock_threshold(),)).fetchall()
        conn.close()

        net = sum(o["subtotal"] - o["discount"] for o in orders)
        discounts = sum(o["discount"] for o in orders)
        count = len(orders)
        avg = net / count if count else 0
        profit = net - cost
        margin = profit / net * 100 if net else 0

        kpis = [
            ("Net sales", self.money(net), f"{self.money(discounts)} in discounts", "💰"),
            ("Orders", f"{count}", f"{sum(o['items'] for o in orders)} items sold", "🧾"),
            ("Average order", self.money(avg), "net sales per order", "📊"),
            ("Gross profit", self.money(profit), f"{margin:.0f}% margin after food cost", "📈"),
        ]
        for col, (title, value, sub, icon) in enumerate(kpis):
            card = self.make_card(page)
            card.grid(row=1, column=col, sticky="nsew", padx=6, pady=6)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(14, 0))
            ctk.CTkLabel(top, text=title.upper(), font=F(11, True), text_color=TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(top, text=icon, font=(EMOJI_FONT, 16)).pack(side="right")
            ctk.CTkLabel(card, text=value, font=F(26, True), text_color=TEXT_DARK).pack(anchor="w", padx=16)
            ctk.CTkLabel(card, text=sub, font=F(11), text_color=TEXT_MUTED).pack(anchor="w", padx=16, pady=(0, 14))

        # Revenue chart
        if period == "Today":
            labels = [f"{h:02d}h" for h in range(24)]
            values = [0.0] * 24
            for o in orders:
                try:
                    values[int(o["timestamp"][11:13])] += o["subtotal"] - o["discount"]
                except (ValueError, IndexError):
                    pass
            chart_title = "Net sales by hour"
        else:
            days = 7 if period == "7 Days" else 30
            start = datetime.date.today() - datetime.timedelta(days=days - 1)
            dates = [start + datetime.timedelta(days=i) for i in range(days)]
            index = {d.isoformat(): i for i, d in enumerate(dates)}
            labels = [d.strftime("%a") if days == 7 else d.strftime("%d %b") for d in dates]
            values = [0.0] * days
            for o in orders:
                i = index.get(o["timestamp"][:10])
                if i is not None:
                    values[i] += o["subtotal"] - o["discount"]
            chart_title = "Net sales by day"

        chart_card = self.make_card(page)
        chart_card.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(chart_card, text=chart_title, font=F(15, True), text_color=TEXT_DARK).pack(anchor="w", padx=18, pady=(14, 0))
        ctk.CTkLabel(chart_card, text=f"{period}  •  peak {self.money(max(values) if values else 0)}", font=F(11), text_color=TEXT_MUTED).pack(anchor="w", padx=18)
        chart = BarChart(chart_card, height=240, value_fmt=self.money_short)
        chart.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        chart.set_data(labels, values)

        # Payments & channels
        pay_card = self.make_card(page)
        pay_card.grid(row=2, column=3, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(pay_card, text="Payments", font=F(15, True), text_color=TEXT_DARK).pack(anchor="w", padx=18, pady=(14, 6))
        collected = sum(o["total"] for o in orders) or 1
        for m in PAYMENT_METHODS:
            amount = sum(o["total"] for o in orders if o["payment"] == m)
            self.breakdown_row(pay_card, m, self.money(amount), amount / collected, PAYMENT_COLORS[m])
        ctk.CTkLabel(pay_card, text="Order channels", font=F(15, True), text_color=TEXT_DARK).pack(anchor="w", padx=18, pady=(14, 6))
        for ot in ORDER_TYPES:
            n = sum(1 for o in orders if o["order_type"] == ot)
            self.breakdown_row(pay_card, ot, f"{n} orders", n / count if count else 0, ACCENT_ORANGE)
        ctk.CTkFrame(pay_card, fg_color="transparent", height=8).pack()

        # Top sellers
        top_card = self.make_card(page)
        top_card.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(top_card, text="🏆  Best sellers", font=F(15, True), text_color=TEXT_DARK).pack(anchor="w", padx=18, pady=(14, 6))
        if not top_items:
            ctk.CTkLabel(top_card, text="No items sold in this period.", font=F(12), text_color=TEXT_MUTED).pack(anchor="w", padx=18, pady=(0, 16))
        best = top_items[0][1] if top_items else 1
        for rank, (name, qty, revenue) in enumerate(top_items, start=1):
            self.breakdown_row(top_card, f"{rank}.  {name}", f"{qty} sold  •  {self.money(revenue or 0)}", (qty or 0) / best, ACCENT_ORANGE)
        ctk.CTkFrame(top_card, fg_color="transparent", height=8).pack()

        # Low stock
        low_card = self.make_card(page)
        low_card.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=6, pady=6)
        head = ctk.CTkFrame(low_card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkLabel(head, text="⚠️  Low stock", font=F(15, True), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkButton(head, text="Open inventory →", width=60, height=26, fg_color="transparent", text_color=ACCENT_ORANGE, hover_color=ACCENT_SOFT,
                      font=F(12, True), command=self.show_inventory).pack(side="right")
        if not low_items:
            ctk.CTkLabel(low_card, text="✓  Everything is well stocked.", font=F(12, True), text_color=SUCCESS).pack(anchor="w", padx=18, pady=(0, 16))
        for name, stock in low_items:
            row = ctk.CTkFrame(low_card, fg_color=BG_SUBTLE, corner_radius=10)
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row, text=name, font=F(12, True), text_color=TEXT_DARK).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(row, text="Sold out" if stock <= 0 else f"{stock} left", font=F(11, True),
                         text_color=DANGER if stock <= 0 else WARN).pack(side="right", padx=12)
        ctk.CTkFrame(low_card, fg_color="transparent", height=8).pack()

    def breakdown_row(self, parent, label, value, share, color):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=3)
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(fill="x")
        ctk.CTkLabel(line, text=label, font=F(12), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(line, text=value, font=F(12, True), text_color=TEXT_DARK).pack(side="right")
        bar = ctk.CTkProgressBar(row, height=8, corner_radius=4, progress_color=color, fg_color=BG_SUBTLE)
        bar.pack(fill="x", pady=(2, 2))
        bar.set(max(0.0, min(1.0, share)))

    # ================= MENU MANAGEMENT =================
    def show_menu_mgmt(self):
        self.begin_page("menu", "Menu Management", "Add, edit and organise what you sell   •   double-click to edit")

        toolbar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))
        self.menu_search = self.make_entry(toolbar, "🔍  Search items…", width=280, fg_color=BG_CARD)
        self.menu_search.pack(side="left")
        self.menu_search.bind("<KeyRelease>", lambda e: self.load_menu_table())
        self.menu_cat_filter = ctk.CTkOptionMenu(toolbar, values=["All categories"] + self.all_categories(), height=38, corner_radius=10,
                                                 fg_color=BG_CARD, button_color=ACCENT_ORANGE, button_hover_color=ACCENT_HOVER, text_color=TEXT_DARK,
                                                 command=lambda v: self.load_menu_table())
        self.menu_cat_filter.pack(side="left", padx=10)
        self.accent_button(toolbar, "+  Add Menu Item", lambda: self.item_dialog(on_saved=self.load_menu_table)).pack(side="right")
        self.ghost_button(toolbar, "🗑  Delete", self.delete_menu_item, text_color=DANGER).pack(side="right", padx=8)
        self.ghost_button(toolbar, "✏️  Edit", self.edit_selected_menu_item).pack(side="right")

        cols = ("ID", "Item", "Category", "Price", "Cost", "Margin")
        wrap, self.menu_tree = self.make_tree(self.main_container, cols, widths={"ID": 60, "Item": 240, "Category": 140, "Price": 100, "Cost": 100, "Margin": 100},
                                              anchors={"ID": "center", "Price": "e", "Cost": "e", "Margin": "e"})
        wrap.pack(fill="both", expand=True)
        self.menu_tree.bind("<Double-1>", lambda e: self.edit_selected_menu_item())
        self.load_menu_table()

    def load_menu_table(self):
        for row in self.menu_tree.get_children(): self.menu_tree.delete(row)
        conn = db()
        rows = conn.execute("SELECT id, name, category, price, cost, COALESCE(emoji, '') FROM items ORDER BY category, name").fetchall()
        conn.close()
        q = self.menu_search.get().strip().lower()
        cat = self.menu_cat_filter.get()
        i = 0
        for item_id, name, category, price, cost, emoji in rows:
            if q and q not in name.lower():
                continue
            if cat != "All categories" and category != cat:
                continue
            margin = f"{(price - cost) / price * 100:.0f}%" if price else "—"
            icon = emoji or CATEGORY_EMOJI.get(category, "🍽️")
            self.menu_tree.insert("", "end", values=(item_id, f"{icon}  {name}", category, self.money(price), self.money(cost), margin),
                                  tags=("odd",) if i % 2 else ())
            i += 1

    def selected_item_id(self, tree):
        sel = tree.selection()
        if not sel:
            self.toast("Select an item first", "warn")
            return None
        return tree.item(sel[0])["values"][0]

    def edit_selected_menu_item(self):
        item_id = self.selected_item_id(self.menu_tree)
        if item_id is not None:
            self.item_dialog(item_id, on_saved=self.load_menu_table)

    def item_dialog(self, item_id=None, on_saved=None):
        existing = None
        if item_id is not None:
            conn = db()
            existing = conn.execute("SELECT name, category, cost, price, stock, COALESCE(emoji, '') FROM items WHERE id = ?", (item_id,)).fetchone()
            conn.close()

        d = self.make_dialog("Edit Item" if existing else "Add Menu Item", 460, 600)
        ctk.CTkLabel(d, text="✏️  Edit item" if existing else "➕  New menu item", font=F(20, True), text_color=TEXT_DARK).pack(anchor="w", padx=26, pady=(22, 10))

        form = ctk.CTkFrame(d, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=26)
        form.grid_columnconfigure((0, 1, 2), weight=1, uniform="f")

        def field(label, row, col, span=1, widget=None):
            ctk.CTkLabel(form, text=label, font=F(12, True), text_color=TEXT_MUTED).grid(row=row * 2, column=col, columnspan=span, sticky="w", padx=4, pady=(8, 2))
            w = widget or self.make_entry(form)
            w.grid(row=row * 2 + 1, column=col, columnspan=span, sticky="ew", padx=4)
            return w

        name_e = field("Item name", 0, 0, span=3)
        cat_cb = field("Category", 1, 0, span=2, widget=ctk.CTkComboBox(form, values=self.all_categories(), height=38, corner_radius=10, fg_color=BG_SUBTLE,
                                                                       border_color=BORDER_COLOR, button_color=ACCENT_ORANGE, button_hover_color=ACCENT_HOVER,
                                                                       text_color=TEXT_DARK, font=F(13)))
        emoji_e = field("Icon (emoji)", 1, 2, widget=self.make_entry(form, "🍜", justify="center"))
        cost_e = field("Cost (hidden)", 2, 0)
        price_e = field("Selling price", 2, 1)
        stock_e = field("Stock", 2, 2)

        margin_lbl = ctk.CTkLabel(form, text="", font=F(12, True), text_color=SUCCESS)
        margin_lbl.grid(row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(14, 0))
        err = ctk.CTkLabel(form, text="", font=F(12), text_color=DANGER)
        err.grid(row=7, column=0, columnspan=3, sticky="w", padx=4)

        if existing:
            name, category, cost, price, stock, emoji = existing
            name_e.insert(0, name)
            cat_cb.set(category or "Other")
            if emoji:
                emoji_e.insert(0, emoji)
            cost_e.insert(0, f"{cost:.2f}")
            price_e.insert(0, f"{price:.2f}")
            stock_e.insert(0, str(stock))
        else:
            cat_cb.set(self.active_category if self.active_category != "All" else "Appetizers")

        def update_margin(*_):
            try:
                c, p = float(cost_e.get() or 0), float(price_e.get())
                if p > 0:
                    margin_lbl.configure(text=f"Profit per sale: {self.money(p - c)}  ({(p - c) / p * 100:.0f}% margin)",
                                         text_color=SUCCESS if p >= c else DANGER)
                    return
            except ValueError:
                pass
            margin_lbl.configure(text="")

        for e in (cost_e, price_e):
            e.bind("<KeyRelease>", update_margin)
        update_margin()

        def save():
            name = name_e.get().strip()
            if not name:
                err.configure(text="Please enter an item name.")
                return
            try:
                cost = float(cost_e.get() or 0)
                price = float(price_e.get())
                stock = int(float(stock_e.get() or 0))
            except ValueError:
                err.configure(text="Cost, price and stock must be numbers.")
                return
            if cost < 0 or price < 0 or stock < 0:
                err.configure(text="Values can't be negative.")
                return
            category = cat_cb.get().strip() or "Other"
            emoji = emoji_e.get().strip()
            conn = db()
            try:
                if existing:
                    conn.execute("UPDATE items SET name=?, category=?, cost=?, price=?, stock=?, emoji=? WHERE id=?",
                                 (name, category, cost, price, stock, emoji, item_id))
                else:
                    conn.execute("INSERT INTO items (name, category, cost, price, stock, emoji) VALUES (?, ?, ?, ?, ?, ?)",
                                 (name, category, cost, price, stock, emoji))
                conn.commit()
            except sqlite3.IntegrityError:
                err.configure(text="An item with this name already exists.")
                return
            finally:
                conn.close()
            d.destroy()
            self.toast(f"{'Updated' if existing else 'Added'} {name}")
            if on_saved:
                on_saved()

        bottom = ctk.CTkFrame(d, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=26, pady=(0, 22))
        self.accent_button(bottom, "Save changes" if existing else "Add item", save, height=46, font=F(14, True)).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(bottom, text="Cancel", height=30, fg_color="transparent", text_color=TEXT_MUTED, hover_color=HOVER, command=d.destroy).pack(fill="x")
        d.after(250, name_e.focus_set)

    def delete_menu_item(self):
        item_id = self.selected_item_id(self.menu_tree)
        if item_id is None:
            return
        if messagebox.askyesno("Confirm", "Delete this item from the menu?"):
            conn = db()
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.commit()
            conn.close()
            self.load_menu_table()
            self.toast("Item deleted", "info")

    # ================= INVENTORY =================
    def show_inventory(self):
        self.begin_page("inventory", "Inventory", "Track stock levels and restock quickly   •   double-click to edit")

        self.inv_kpis = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.inv_kpis.pack(fill="x", pady=(0, 10))

        toolbar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))
        self.inv_search = self.make_entry(toolbar, "🔍  Search items…", width=280, fg_color=BG_CARD)
        self.inv_search.pack(side="left")
        self.inv_search.bind("<KeyRelease>", lambda e: self.load_inventory_table())
        self.low_only = ctk.CTkSwitch(toolbar, text="Low stock only", font=F(12), text_color=TEXT_DARK, progress_color=ACCENT_ORANGE,
                                      command=self.load_inventory_table)
        self.low_only.pack(side="left", padx=14)
        self.accent_button(toolbar, "+50", lambda: self.restock_item(50), width=60).pack(side="right")
        self.accent_button(toolbar, "+10", lambda: self.restock_item(10), width=60).pack(side="right", padx=8)
        self.ghost_button(toolbar, "📦  Restock…", self.restock_custom).pack(side="right")
        self.ghost_button(toolbar, "✏️  Edit", self.edit_inventory_dialog).pack(side="right", padx=8)

        cols = ("ID", "Item", "Category", "Cost", "Price", "Stock", "Status")
        wrap, self.inv_tree = self.make_tree(self.main_container, cols,
                                             widths={"ID": 60, "Item": 230, "Category": 130, "Cost": 90, "Price": 90, "Stock": 80, "Status": 120},
                                             anchors={"ID": "center", "Cost": "e", "Price": "e", "Stock": "center"})
        wrap.pack(fill="both", expand=True)
        self.inv_tree.bind("<Double-1>", lambda e: self.edit_inventory_dialog())
        self.load_inventory_table()

    def load_inventory_table(self):
        for row in self.inv_tree.get_children(): self.inv_tree.delete(row)
        conn = db()
        rows = conn.execute("SELECT id, name, category, cost, price, stock FROM items ORDER BY stock ASC, name").fetchall()
        conn.close()
        low = self.low_stock_threshold()
        q = self.inv_search.get().strip().lower()
        low_only = bool(self.low_only.get())
        i = 0
        for item_id, name, category, cost, price, stock in rows:
            if q and q not in name.lower():
                continue
            if low_only and stock > low:
                continue
            if stock <= 0:
                status, tag = "⛔ Out of stock", "out"
            elif stock <= low:
                status, tag = "⚠️ Low", "low"
            else:
                status, tag = "✓ In stock", ""
            tags = tuple(t for t in (tag, "odd" if i % 2 else "") if t)
            self.inv_tree.insert("", "end", values=(item_id, name, category, self.money(cost), self.money(price), stock, status), tags=tags)
            i += 1

        for widget in self.inv_kpis.winfo_children():
            widget.destroy()
        self.inv_kpis.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="ik")
        stats = [
            ("Menu items", str(len(rows)), TEXT_DARK),
            ("Low stock", str(sum(1 for r in rows if 0 < r[5] <= low)), WARN),
            ("Out of stock", str(sum(1 for r in rows if r[5] <= 0)), DANGER),
            ("Stock value (at cost)", self.money(sum(max(r[5], 0) * (r[3] or 0) for r in rows)), ACCENT_ORANGE),
        ]
        for col, (label, value, color) in enumerate(stats):
            card = self.make_card(self.inv_kpis)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 3 else 6))
            ctk.CTkLabel(card, text=label.upper(), font=F(11, True), text_color=TEXT_MUTED).pack(anchor="w", padx=16, pady=(12, 0))
            ctk.CTkLabel(card, text=value, font=F(22, True), text_color=color).pack(anchor="w", padx=16, pady=(0, 12))

    def edit_inventory_dialog(self):
        item_id = self.selected_item_id(self.inv_tree)
        if item_id is not None:
            self.item_dialog(item_id, on_saved=self.load_inventory_table)

    def restock_item(self, amount=10):
        item_id = self.selected_item_id(self.inv_tree)
        if item_id is None:
            return
        conn = db()
        conn.execute("UPDATE items SET stock = stock + ? WHERE id = ?", (amount, item_id))
        conn.commit()
        conn.close()
        self.load_inventory_table()
        self.toast(f"Added {amount} to stock")

    def restock_custom(self):
        item_id = self.selected_item_id(self.inv_tree)
        if item_id is None:
            return
        value = ctk.CTkInputDialog(text="How many units to add?", title="Restock").get_input()
        if value is None:
            return
        try:
            amount = int(value)
        except ValueError:
            self.toast("Please enter a whole number", "error")
            return
        self.restock_item(amount)

    # ================= SETTINGS =================
    def show_settings(self):
        self.begin_page("settings", "Settings", "Branding, billing, security and data")

        container = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure((0, 1), weight=1, uniform="s")

        def section(title, subtitle, row, col, span=1):
            card = self.make_card(container)
            card.grid(row=row, column=col, columnspan=span, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(card, text=title, font=F(16, True), text_color=TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 0))
            ctk.CTkLabel(card, text=subtitle, font=F(12), text_color=TEXT_MUTED).pack(anchor="w", padx=20, pady=(0, 6))
            return card

        def add_entry(parent, label, key, default_val, is_textbox=False, show=None):
            ctk.CTkLabel(parent, text=label, font=F(12, True), text_color=TEXT_MUTED).pack(anchor="w", padx=20, pady=(6, 2))
            if is_textbox:
                entry = ctk.CTkTextbox(parent, height=64, fg_color=BG_SUBTLE, border_color=BORDER_COLOR, border_width=1, corner_radius=10, text_color=TEXT_DARK, font=F(13))
                entry.insert("1.0", self.config_data.get(key, default_val))
            else:
                entry = self.make_entry(parent, show=show) if show else self.make_entry(parent)
                value = str(self.config_data.get(key, default_val)) if key else ""
                if value:
                    entry.insert(0, value)
            entry.pack(fill="x", padx=20, pady=(0, 4))
            return entry

        brand = section("🏪  Restaurant branding", "Shown on receipts and in the sidebar", 0, 0)
        self.rest_name_entry = add_entry(brand, "Restaurant Name", "rest_name", "My Restaurant")
        self.rest_address_entry = add_entry(brand, "Address", "rest_address", "123 Main Street")
        self.rest_phone_entry = add_entry(brand, "Phone Number", "rest_phone", "+92 300 1234567")
        self.footer_entry = add_entry(brand, "Receipt Footer Message", "footer_msg", "Thank you for visiting!", is_textbox=True)
        ctk.CTkFrame(brand, fg_color="transparent", height=10).pack()

        billing = section("💵  Billing & stock", "Applied to every new order", 0, 1)
        self.currency_entry = add_entry(billing, "Currency Symbol", "currency", "$")
        self.tax_entry = add_entry(billing, "Tax / VAT rate (%)", "tax_rate", "0")
        self.low_stock_entry = add_entry(billing, "Low stock alert at (units)", "low_stock", "5")

        ctk.CTkLabel(billing, text="🔐  Change admin PIN", font=F(14, True), text_color=TEXT_DARK).pack(anchor="w", padx=20, pady=(14, 0))
        ctk.CTkLabel(billing, text="Leave blank to keep the current PIN", font=F(11), text_color=TEXT_MUTED).pack(anchor="w", padx=20)
        self.new_pin_entry = add_entry(billing, "New PIN (4–8 digits)", None, "", show="•")
        self.confirm_pin_entry = add_entry(billing, "Confirm new PIN", None, "", show="•")
        ctk.CTkFrame(billing, fg_color="transparent", height=10).pack()

        def save_settings():
            try:
                tax = float(self.tax_entry.get() or 0)
                low = int(self.low_stock_entry.get() or 0)
            except ValueError:
                self.toast("Tax rate and low stock must be numbers", "error")
                return
            if not 0 <= tax <= 100 or low < 0:
                self.toast("Tax must be 0–100% and low stock 0 or more", "error")
                return
            new_pin = self.new_pin_entry.get().strip()
            if new_pin:
                if not (new_pin.isdigit() and 4 <= len(new_pin) <= 8):
                    self.toast("PIN must be 4–8 digits", "error")
                    return
                if new_pin != self.confirm_pin_entry.get().strip():
                    self.toast("PINs don't match", "error")
                    return
                self.config_data["admin_pin_hash"] = hash_pin(new_pin)
                self.config_data.pop("admin_pin", None)
            self.config_data["rest_name"] = self.rest_name_entry.get()
            self.config_data["rest_address"] = self.rest_address_entry.get()
            self.config_data["rest_phone"] = self.rest_phone_entry.get()
            self.config_data["currency"] = self.currency_entry.get() or "$"
            self.config_data["footer_msg"] = self.footer_entry.get("1.0", "end-1c")
            self.config_data["tax_rate"] = tax
            self.config_data["low_stock"] = low
            self.currency = self.config_data["currency"]
            self.save_config()
            self.rest_name_lbl.configure(text=self.config_data["rest_name"] or "My Restaurant")
            self.show_settings()
            self.toast("Settings saved" + (" — PIN updated" if new_pin else ""))

        save_bar = ctk.CTkFrame(container, fg_color="transparent")
        save_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 8))
        self.accent_button(save_bar, "💾  Save Settings", save_settings, color=SUCCESS, hover=SUCCESS_HOVER, height=46, font=F(14, True)).pack(fill="x")

        wa = section("💬  WhatsApp ordering", "Give this link to customers so they can order via WhatsApp", 2, 0)
        phone = self.config_data.get("rest_phone", "").replace(" ", "").replace("+", "").replace("-", "")
        wa_link = f"https://wa.me/{phone}?text=Hi, I want to place an order."
        wa_link_frame = ctk.CTkFrame(wa, fg_color=BG_SUBTLE, corner_radius=10)
        wa_link_frame.pack(fill="x", padx=20, pady=(6, 18))
        ctk.CTkLabel(wa_link_frame, text=wa_link, font=(MONO, 11), text_color=INFO, wraplength=360, justify="left").pack(side="left", padx=12, pady=10)

        def copy_link():
            self.clipboard_clear()
            self.clipboard_append(wa_link)
            self.toast("WhatsApp link copied")
        self.ghost_button(wa_link_frame, "Copy", copy_link, width=64, height=32).pack(side="right", padx=10)

        data = section("🗄️  Data", "Back up your sales and menu, or open saved receipts", 2, 1)
        btns = ctk.CTkFrame(data, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(6, 18))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="d")

        def backup():
            path = filedialog.asksaveasfilename(defaultextension=".db", initialfile=f"bitepos_backup_{datetime.date.today().isoformat()}.db",
                                                filetypes=[("Database", "*.db")])
            if path:
                shutil.copy2(DB_FILE, path)
                self.toast("Backup saved")
        self.ghost_button(btns, "💾  Back up database", backup, height=42).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.ghost_button(btns, "📁  Open receipts folder", lambda: open_path(RECEIPTS_DIR), height=42).grid(row=0, column=1, sticky="ew", padx=(4, 0))

def run_main_app():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    if not check_license():
        license_app = LicenseScreen()
        license_app.mainloop()
    else:
        run_main_app()
