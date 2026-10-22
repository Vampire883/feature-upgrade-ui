# AGENTS.md

## What this is
BitePOS is a single-file Python desktop POS app (`app.py`) using CustomTkinter, SQLite and ttk Treeviews. It is not a web app. There is no build step. Run it with `python app.py`.

## Structure of `app.py`
- **Top-level constants**: theme colors are `(light, dark)` tuples so CustomTkinter can switch modes. Use `resolve()` when passing a color to plain tk/ttk widgets (Canvas, Treeview styles). `F(size, bold)` builds fonts.
- **License system**: hardware-ID-based key check. Do not change the salt or the hashing, or existing customer license keys will stop working.
- **Database engine**: `init_db()` creates or migrates tables. Use `ensure_column` for additive migrations.
  - `sales`: one row per item line (`price` = unit price, `quantity`, `cost` = unit cost).
  - `orders` (v8+): one row per order with subtotal/discount/tax/total/tendered/change/note.
  - `held_orders`: parked carts stored as JSON.
  - Legacy (pre-v8) orders exist only in `sales`. `fetch_orders()` and `fetch_order_detail()` merge both sources, so always go through them.
- **App class**: each page is a `show_*` method. It starts with `begin_page(key, title, subtitle)`, which destroys and rebuilds the main container. Admin pages are gated in `navigate()` via `ask_pin()`.
- **POS state**: lives in `self.cart` (list of `{name, price, qty}`), `self.pos_state` (customer/table/note/discount), and `self.order_type`. That state survives page switches, but the widgets get rebuilt.

## Conventions
- Show feedback with `self.toast(msg, kind)`. Use messageboxes only for confirmations and errors.
- Use `make_dialog`, `make_card`, `make_tree`, `make_entry`, `ghost_button`, and `accent_button` for consistent styling.
- Format money with `self.money()`. Never hardcode the currency.
- Admin PIN is stored as `admin_pin_hash` in config. A legacy plain `admin_pin` is still accepted until it is changed.
