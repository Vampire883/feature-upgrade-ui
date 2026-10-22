# BitePOS – Restaurant Edition (v8.0)

BitePOS is a point-of-sale desktop app for restaurants and cafés, built with Python and CustomTkinter. It runs on Windows. Data stays on the machine in a local SQLite database.

## Features

- **POS Terminal**: menu cards with emoji icons and stock badges, live search (F2), category chips with item counts, per-item quantity controls, percentage or fixed discounts, automatic tax, a kitchen note, and Takeaway / Dine-In (with table number) / Delivery orders.
- **Held orders**: park an order (F4) and resume it later.
- **Payments**: Cash / Card / Online. Cash payments get quick-amount buttons and a change calculator (F9 opens the payment screen).
- **Receipts and kitchen tickets**: printable HTML receipts, kitchen order tickets (KOT), and a WhatsApp-ready copy of the receipt.
- **Orders History**: one row per order, with search, date filters, view/reprint, and CSV export.
- **Analytics dashboard** (admin): net sales, order count, average order, and gross profit cards; a sales chart by hour or day; payment and channel breakdowns; best sellers; low-stock alerts.
- **Menu Management and Inventory** (admin): add/edit items with a live profit-margin preview, low/out-of-stock highlighting, quick and custom restocking, and stock value.
- **Settings** (admin): branding, currency, tax rate, low-stock threshold, admin PIN (stored hashed), WhatsApp order link, database backup.
- **Dark mode** toggle in the sidebar.

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

The default admin PIN is `1234`. Change it in Settings.

## Data files (created next to `app.py`)

| File | Purpose |
| --- | --- |
| `pos_database.db` | Menu items, sales lines, orders, held orders |
| `config.json` | Restaurant settings |
| `receipts/`, `receipts/kitchen/` | Saved HTML receipts and kitchen tickets |
| `.activated` | License activation marker |

Existing v7 databases are upgraded automatically on first launch, and old sales still show in history and analytics.
