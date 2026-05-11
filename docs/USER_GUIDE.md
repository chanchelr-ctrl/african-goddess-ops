# User Guide — African Goddess Operations

> Written for Tersia. How to do every common task, step by step. Keep this open while you work for the first week or two — it gets fast quickly.

## Daily start

1. Double-click **`start.bat`** in the project folder. A black PowerShell window opens. **Leave it open while you work.**
2. Your browser opens at `http://127.0.0.1:8000/`. If not, type that into the browser yourself.
3. Sign in. The home page is the **launchpad** — four big workflow rows: **Build · Track · Purchase · Data**. Click anywhere on a row to enter that workflow.
4. When you're done, close the browser tab. To shut down the app fully, close the black window.

## Reading the launchpad

The home page is a launchpad. Each row corresponds to one workflow and shows three at-a-glance KPIs on the right:

- **Build** — what you can make right now, total units producible, items blocked by stock.
- **Track** — projects in flight, units made vs. planned, runs this week.
- **Purchase** — materials at or below reorder, open POs, ZAR value on order.
- **Data** — active materials, BOM lines, change-log entries today.

Click anywhere on a row (the illustration, the label, the KPI tiles, or the chevron on the right) and you'll land on that workflow's page. Rows flag themselves with an alert tint when there's something needing your attention (e.g. materials below reorder turn the Purchase row warm-terracotta).

## All numbers display as whole numbers

Throughout the app, quantities, stock counts and ZAR values render as whole integers (no trailing decimals). The underlying data keeps full precision; you just see the clean round version on screen.

> **Why `.bat` and not `.ps1`?** Windows blocks unsigned PowerShell scripts by default for safety. The `.bat` files are tiny wrappers that launch the real `.ps1` scripts with permission to run. You can ignore the technicality — just double-click `start.bat`.

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

### 7. Plan & start a build

The **Build** workflow is the fastest way to check whether you can make N of something, and to spin up a project from that variant.

1. Click **Build** from the launchpad → **Plan a new build**.
2. The Sellable SKU field is a **smart search**: type "tangerine", "SBR01" or any part of the name and the dropdown filters live. Or open the dropdown and pick.
3. Enter a quantity and click **Check stock →**.
4. The page shows a **Materials needed** table — every raw material on this product's BOM with: per-unit qty, total need, in-stock, and a status pill (OK / Short by N). Rows that are short are highlighted in alert tint.
5. If everything is OK:
   - A **Start project** card appears with the project name **pre-filled** as `{qty} × {product} — {variant}`. You can keep or edit the name.
   - Click **Start project →** to spin up the project.
6. If anything is short, the same table tells you what to chase. Click **Go to Purchase →** to draft a PO from the low-stock list.

### 8. Read the launchpad

The launchpad on `/` is your morning check. It shows four workflow rows; each has three KPIs to the right. If a row goes warm-terracotta it's flagging something that needs attention. Click any row to enter its workflow page.

## Inventory Analytics — the Data page

The **Data** page (top menu → **Data**) is your inventory analytics dashboard. The top of the page has three drill-down charts; the table below lists every raw material; the bottom of the page holds Export / Import and the recent change log.

### The three charts

- **Material category** — donut by material type (Findings, Crystal, Natural Stone, Glass, Shell, Polymer/Clay, Wire & Cord, Pendants & Charms). Click a slice to drill into colour-family within that category; click again to see top materials by stock value.
- **Stock value (ZAR)** — donut showing total stock value per category, with the running total in the centre. Click a slice to see the top individual materials by R value in that category.
- **Bead analysis** — four levels of drill-down on the beads subset only. Bead material → colour family → size band → individual materials by R value.

Every chart has a **breadcrumb above the chart** that appears once you've drilled in. Click "All" or any earlier crumb to jump back to that level. Whatever you click in a chart also filters the table below.

### The materials table

- **Smart search** input above the table filters as you type — matches SKU, name, colour, shape, supplier, size.
- An **active filter pill** appears in copper when a chart segment is selected. Click the ✕ on the pill to clear.
- Table shows 11 columns including a colour-swatch dot and a stock-status pill (OK / Low / Out).
- Counts in the top-right ("23 of 81 materials") update as you filter.

### Export & import the master file

At the bottom of the Data page:

1. Click **Download MasterData.xlsx** to get a fresh Excel snapshot with three sheets — **MaterialMaster**, **ProductSpec**, **ChangeLog**.
2. Edit the .xlsx in Excel — change material attributes, costs, reorder points, or BOM quantities.
3. Come back to the Data page, click **Choose File**, pick your edited .xlsx, and click **Apply file to database**.
4. Optional: tick **Prune missing rows** to also remove materials/BOM lines that you deleted from the file (default is additive — won't remove anything not present).

Every change applied by the import is recorded in the **ChangeLog**, attributed to your username.

The database wins on conflict: the .xlsx you downloaded is a point-in-time snapshot. To see fresh figures, click Download again.

## Bulk import from the original spreadsheets

The app shipped with a one-shot importer that reads the client's original 3-file spreadsheet format and bootstraps the database. This is intended only for first-time setup or full re-imports.

```powershell
.\.venv\Scripts\python.exe manage.py migrate_bom_xlsx --dry-run
.\.venv\Scripts\python.exe manage.py migrate_bom_xlsx --with-initial-stock
```

After the bootstrap, the **standard way to apply edits** is through the **Data → Import** button on the web app (using the MasterData.xlsx format from `Export`). That's safer, integrates with the change log, and round-trips cleanly.

## Data — Export & Import

The app keeps everything in its database. The **Data** page (top menu → **Data**) lets you turn that into a single Excel file you can read, share, edit, or re-import.

### Export Data — get an Excel snapshot

1. Click **Data** in the top menu.
2. Click **Download MasterData.xlsx**.
3. Excel file downloads to your browser's downloads folder. Filename includes today's date and time.

The file has three sheets:

- **MaterialMaster** — every raw material. SKU, name, size, colour, costs, supplier, current stock on hand, ZAR value of stock on hand (computed live in Excel as Stock × Unit Cost). One row per material.
- **ProductSpec** — the full BOM. One row per (sellable SKU × material) combination, with the BOM quantity. Spec data only — no stock or cost (those live on the MaterialMaster sheet).
- **ChangeLog** — every recorded change to master/spec data: timestamp, who made the change, what changed, old value, new value.

The file is generated fresh every time you click Export — it's a snapshot of the current database. The app does **not** keep writing to the file after you download it. Edit it freely.

### Import Data — apply changes from an Excel file

1. Edit the .xlsx in Excel — change material names, costs, reorder points, or BOM quantities. Save the file.
2. On the **Data** page, click **Choose File** and pick your edited .xlsx.
3. Optional: tick **Prune missing rows** if you want materials/BOM lines that you removed from the file to also be removed from the database. Leave unticked (default) to only apply additions and edits.
4. Click **Apply file to database**.
5. The page reloads with a summary: how many materials were updated, how many BOM lines were created/updated, etc.

Every change made by the import is recorded in the **ChangeLog**, attributed to your username.

### What if I edit the database and the file at the same time?

The database wins. The .xlsx file you downloaded is a point-in-time snapshot — it does **not** automatically receive your in-app edits. To see fresh data, click **Download MasterData.xlsx** again.

### What's NOT in the export

- Purchase orders, projects, production runs, stock movements — these are operational records, not master data. They don't round-trip via the master file. (The app already keeps full audit trails for stock movements internally.)

## Backups

Every day at 6pm (or whenever Task Scheduler is set), `backup.ps1` automatically copies your database to `backups\db_YYYY-MM-DD_HHMM.sqlite3`. The last 30 backups are kept; older ones are deleted automatically.

To make a manual backup right now: double-click `backup.bat` in the project folder.

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
A: From the **Data** page click **Download MasterData.xlsx**. That gives them a single Excel file with every raw material, every BOM line, and every recorded change. For PO and production-run reports, use the admin's filter & export options.

## When something breaks

1. Take a screenshot of the error.
2. Note what you were trying to do.
3. Send to your consultant. Don't try to "fix" the database directly.
4. While waiting, you can keep using everything except the broken feature — the database is safe.
