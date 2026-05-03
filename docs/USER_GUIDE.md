# User Guide — African Goddess Operations

> Written for Tersia. How to do every common task, step by step. Keep this open while you work for the first week or two — it gets fast quickly.

## Daily start

1. Double-click `start.ps1` in the project folder. A black window opens. **Leave it open while you work.**
2. Your browser opens at `http://127.0.0.1:8000/`. If not, type that into the browser yourself.
3. Sign in. The home page is the **Operations Dashboard**.
4. When you're done, close the browser tab. To shut down the app fully, close the black window.

## The 7 things you'll do most

### 1. Add a new raw material

1. Click **Raw materials** in the top menu (or go to **Admin home → Raw materials**).
2. Click **Add raw material** (top right).
3. Fill in:
   - **SKU**: a short code only used by you (e.g. `BEAD-RED-6MM`). No spaces. Must be unique.
   - **Name**: the human-friendly name.
   - **Unit**: how you count it (pieces, grams, metres, etc.).
   - **Current stock**: how many you have right now.
   - **Reorder point**: when stock drops to or below this number, the dashboard flags it RED.
   - **Reorder quantity**: how many you typically order when restocking.
   - **Last paid unit cost**: in ZAR. Used for stock-value and product-cost calculations.
   - **Preferred supplier**: pick from the list. (Add suppliers under Suppliers first if needed.)
4. Click **Save**.

### 2. Add a new product

1. Click **Products → Add product**.
2. Fill in: SKU, name, pillar (Body Adornments / Sacred Tools / Bamboo Clothing / Other), retail price (ZAR).
3. **In the same form**, scroll to "Bom lines" — add each raw material that goes into one unit of this product:
   - Pick the raw material from the dropdown.
   - Enter the quantity used **per unit of the finished product**.
4. Click **Save**.
5. Go back to the Products list. You'll see automatically computed:
   - **Material cost** — sum of (each BOM ingredient × its last-paid cost).
   - **Margin %** — how much profit per unit at the listed retail price.
   - **Can make** — how many units you can build right now from current raw-material stock.

### 3. Record a production run (deduct raw materials when you've made things)

This is the heartbeat of the system. Whenever you've finished making N units of a product, log it here so stock deducts automatically.

1. Click **Production runs → Add production run**.
2. Pick the product.
3. Enter how many you made.
4. Pick a date (defaults to today).
5. Add a note if you want.
6. Click **Save**.

What happens automatically:
- The system checks: do I have enough of every raw material? If not, you get an error showing what's short. **Nothing is deducted unless the whole run can be made.**
- If yes: each raw material's stock drops by `BOM quantity × run quantity`.
- An audit log entry is created for every deduction (visible under **Stock movements**).

**Production runs cannot be edited or deleted once saved.** If you made a mistake, add a manual stock adjustment (see #6 below).

### 4. Create a purchase order

1. Click **Purchase orders → Add purchase order**.
2. Pick the supplier.
3. Status defaults to **Draft**. Leave it there for now.
4. Enter expected delivery date (optional).
5. Add the lines: which raw material, how many, at what unit cost.
6. Click **Save**.

The system auto-generates a reference like `PO-20260503-001`. Email or WhatsApp this reference to your supplier when you place the order.

### 5. Mark a purchase order as received

When the parcel arrives:

1. Open the PO from the Purchase orders list.
2. Change **Status** to **Received**.
3. Click **Save**.

Automatic side-effects:
- Each line's quantity is **added** to the corresponding raw material's stock.
- The raw material's "last paid unit cost" is updated to the cost on this PO.
- A stock movement is recorded for the audit log.

The **Received date** auto-fills to today if you don't set it.

### 6. Manual stock adjustment

Use this when you've recounted and the actual count doesn't match the system, or when you've used materials for testing/breakage.

1. Click **Stock movements → Add stock movement**.
2. Pick the raw material.
3. Enter **Delta** — a positive number to *add* stock, a negative number (with the minus sign) to *subtract*.
4. Reason will default to "Manual adjustment."
5. Add a note explaining why (very useful 6 months later).
6. Click **Save**.

### 7. Read the dashboard

The home page (`/`) shows you, at a glance:
- **How many raw materials are below their reorder point** (red number = act today).
- **How many open purchase orders** you're waiting on.
- **Total stock value** at last-paid cost.
- **Materials needing reorder** — table you can act on.
- **Open POs** — click a reference to open the PO.
- **Recent production runs**.

If everything is healthy ("Everything is above its reorder point"), you have nothing to act on today.

## Bulk import from spreadsheet

If you have years of data in spreadsheets, you can import it in one go. Open PowerShell in the project folder, then:

```powershell
.\.venv\Scripts\python.exe manage.py import_suppliers path\to\suppliers.csv --dry-run
.\.venv\Scripts\python.exe manage.py import_materials path\to\materials.csv --dry-run
.\.venv\Scripts\python.exe manage.py import_products  path\to\products.csv  --dry-run
.\.venv\Scripts\python.exe manage.py import_boms      path\to\boms.csv      --dry-run
```

The `--dry-run` flag validates the file without writing to the database. Read the output, fix any errors, then re-run **without** `--dry-run` to commit.

**Order matters.** Suppliers first, then materials (which reference suppliers by name), then products, then BOMs (which reference both).

CSV column requirements:

- **suppliers.csv**: required `name`; optional `contact_name`, `email`, `phone`, `website`, `typical_lead_time_days`, `notes`, `is_active`
- **materials.csv**: required `sku`, `name`; optional `unit`, `current_stock`, `reorder_point`, `reorder_quantity`, `last_paid_unit_cost`, `preferred_supplier_name`, `notes`, `is_active`
- **products.csv**: required `sku`, `name`; optional `pillar`, `retail_price_zar`, `notes`, `is_active`
- **boms.csv**: required `product_sku`, `material_sku`, `quantity`; optional `notes`

## Backups

Every day at 6pm (or whenever Task Scheduler is set), `backup.ps1` automatically copies your database to `backups\db_YYYY-MM-DD_HHMM.sqlite3`. The last 30 backups are kept; older ones are deleted automatically.

To make a manual backup right now: double-click `backup.ps1` in the `scripts` folder.

To restore from a backup:
1. Close the app (close the black PowerShell window).
2. Rename the chosen backup file from `backups\db_2026-05-03_1800.sqlite3` to `db.sqlite3`, and move it to the project root (replacing the current `db.sqlite3`).
3. Run `start.ps1` again.

## Common questions

**Q: I made 3 necklaces but the system says "not enough stock."**
A: Check the error message — it tells you exactly which raw material is short and by how much. Either: (a) add stock for that material via a Purchase Order receipt, or (b) record a manual adjustment if you actually have it but the count is wrong.

**Q: I created a Production Run but want to delete it.**
A: Production Runs cannot be deleted (this is intentional — keeps the audit trail honest). Instead, record a positive Stock Movement adjustment for each raw material that was wrongly deducted, with a note explaining what happened.

**Q: I changed my mind about a PO before it shipped.**
A: Open the PO, change Status to "Cancelled," and Save. No stock side-effects.

**Q: How do I see what was purchased from supplier X over the year?**
A: Purchase orders list → filter by Supplier → date range filter at the top.

**Q: My stock numbers look weird. How do I check?**
A: Open PowerShell in the project folder and run `.\.venv\Scripts\python.exe manage.py reconcile_stock`. It compares each material's current stock to the audit-trail sum and flags any discrepancies. Add `--fix` to recompute from the audit log.

**Q: I want to give my accountant the year's data.**
A: Run `.\.venv\Scripts\python.exe manage.py export_all`. It writes a dated folder under `exports\` with one CSV per table. Send the folder to your accountant.

## When something breaks

1. Take a screenshot of the error.
2. Note what you were trying to do.
3. Send to your consultant. Don't try to "fix" the database directly.
4. While waiting, you can keep using everything except the broken feature — the database is safe.
