# African Goddess — Operations App: Client Test Plan

| | |
|---|---|
| **Document version** | 0.2 |
| **App version** | 0.3.0 |
| **Date** | 9 May 2026 |
| **Audience** | Tersia (operator) — first walk-through |
| **Goal of this session** | Confirm the app supports the daily operational flow, surface anything missing or confusing, decide what's next. |

---

## How to start

1. Open the app: **http://127.0.0.1:8000/**
2. Log in: username **`tersia`**
3. You'll land on the **Dashboard**.

The top nav reflects how you actually work, in order: **Dashboard → Build → Track → Purchase → Data**. That's the order this document walks through.

---

## Scenario 1 — Morning check-in: "What needs my attention today?"

**Why it matters.** Every workday starts with a status read: which materials are running low, which orders are still open with Temu, which builds are mid-flight, what's been sold lately. Without this, the spreadsheet was your morning routine.

**What this achieves.** A single screen replaces the morning spreadsheet review. You see the things that drive your day: stock value, on-order value, low-stock count, open PO count, in-flight projects, and recent production.

**Click-through.**
1. Land on the Dashboard (the home page).
2. Read the **KPI tiles** across the top: stock value, on-order value, counts of low-stock / open POs / in-flight builds.
3. Scroll the **Low stock** table — anything in red needs reordering.
4. Scroll the **Open POs** table — anything that's been "Sent" but not yet "Received".
5. Scroll the **In-flight projects** — builds you've started but not finished.
6. Scroll **Recent production runs** — the last 10 things you actually made.

**What "good" looks like.** You can tell within 30 seconds: "today I need to reorder X, finish build Y, and there's a parcel from Temu I'm still waiting on."

**Feedback to capture.**
- Are these the right KPIs? Anything missing?
- Are the column orders intuitive?
- Anything confusing visually?

---

## Scenario 2 — Plan a build: "Can I make 10 Sugar Bush earrings, palette 3?"

**Why it matters.** Before you start beading, you want to know: do I have enough materials? If not, what am I short of, and by how much? Today this means scanning multiple sheet rows and doing maths in your head.

**What this achieves.** Pick a product variant, type a quantity, and the app instantly tells you whether you have enough — and if not, exactly which materials are short and by how much.

**Click-through.**
1. Click **Build** in the top nav.
2. Browse the list of variants you *can* make right now (sorted by max units possible).
3. Click **Check sufficiency** (or scroll down to the picker).
4. Pick a variant from the dropdown — e.g. *SBR03 Lime Green earrings*.
5. Enter a quantity — e.g. **10**.
6. Click **Check**.
7. Read the result:
   - Green panel = enough materials → click **Start project**
   - Red panel = shortfall list → scroll the table to see which beads/findings are short

**What "good" looks like.** No need to flip back to the spreadsheet. The shortfall list is specific enough to act on (e.g. "short by 12 of GC396655 8mm Amethyst").

**Feedback to capture.**
- Is the variant dropdown easy to find your product in?
- Does the shortfall language read naturally?
- Should "Start project" be more prominent / less prominent?

---

## Scenario 3 — Run a build: "I made 5 today, deduct the stock"

**Why it matters.** Every production session consumes raw materials. Without an accurate deduction, your stock numbers drift away from reality, and you end up reordering too late or too early.

**What this achieves.** One click logs production. Stock for every BOM line is deducted automatically. The audit trail records what was made, when, and by whom. The project's progress bar updates.

**Click-through.**
1. Click **Track** in the top nav.
2. Click into your in-flight project (e.g. the one you just started in Scenario 2).
3. Scroll to the production form for the line item.
4. Type the quantity made today — e.g. **5**.
5. Click **Record run**.
6. Confirm:
   - The "Made" count went up by 5.
   - The "Remaining" went down by 5.
   - Each material listed under the BOM has its stock reduced.
7. (Optional) Click **Mark complete** when done.

**What "good" looks like.** You feel safe trusting the stock numbers without re-counting beads.

**Feedback to capture.**
- Is "Record run" the right verb? Or "Log production" / "I made"?
- Should the page show stock-after numbers next to stock-before?
- Anything you wish was visible while you record?

---

## Scenario 4 — Reorder: "I need beads — draft a Temu order"

**Why it matters.** Today you scroll the spreadsheet, eyeball the red cells, build a Temu cart by hand, and risk missing items.

**What this achieves.** The app shows every material currently below reorder point, suggests how many packs to buy (rounded up to whole packs), and bundles selected items into a draft Purchase Order in one click. It also opens Temu pre-loaded with a search for each item.

**Click-through.**
1. Click **Purchase** in the top nav.
2. Read the **Reorder candidates** table — every low-stock material with the suggested pack count.
3. (Optional) For any single material, click **Search on Temu** to open Temu in a new tab pre-searched.
4. Tick the materials you want on this PO (or use **Select all**).
5. Click **Draft PO**.
6. You're taken to the new PO, status **Draft**, with one line per material you selected.

**What "good" looks like.** You went from "I need to reorder" to "I have a draft PO" in under a minute.

**Feedback to capture.**
- Are the suggested pack counts sensible?
- Should the table sort by something other than alphabetical?
- Any materials missing from the list that you'd expect?

---

## Scenario 5 — Place the order on Temu and mark it sent

**Why it matters.** Until the PO is marked "Sent", it's just a wishlist. We need a clean handover: I drafted, I ordered, I'm waiting.

**What this achieves.** Two-stage status (Draft → Sent → Received) tracks the lifecycle. The Temu order ID + tracking number live on the PO, so you can find it later.

**Click-through.**
1. From the PO detail page, click **Open in Temu (managed browser)**.
2. A Chromium window opens, pre-searched for every line on the PO.
3. Drive the cart and checkout in that window — buy as you normally would.
4. After checkout, copy the order confirmation text from Temu.
5. Back in the app, click **Paste receipt** on the PO.
6. Paste the text → click **Parse**.
7. Confirm the parsed order ID + tracking number look right → click **Apply**.
8. The PO flips to **Sent** automatically.

**What "good" looks like.** No retyping. The order ID and tracking number end up on the PO without manual entry.

**Feedback to capture.**
- Does the managed-browser flow feel safe?
- Did the paste-and-parse pick up the right fields?
- Should we automate cart-building too, or is hand-driven the right line?

---

## Scenario 6 — Receive the parcel: "Stock just arrived"

**Why it matters.** Until you mark it Received, your stock numbers don't reflect what's physically on the shelf. Receiving must be one click.

**What this achieves.** Marking "Received" instantly tops up `current_stock` for every line, writes a stock movement per material (audit trail), and updates the last-paid unit cost in case prices changed.

**Click-through.**
1. Click **Purchase** → click into the open PO.
2. Click **Mark received**.
3. Confirm.
4. Go back to the Dashboard — stock value should have gone up; low-stock count should have dropped.

**What "good" looks like.** You see your stock recover the moment you confirm receipt — no second step, no spreadsheet edit.

**Feedback to capture.**
- Should "Received" require unit-by-unit confirmation, or is one-click trust correct?
- Do you want to record short shipments here, or via a separate adjustment?

---

## Scenario 7 — Cancel a PO that won't arrive

**Why it matters.** Sometimes Temu cancels, sometimes you change your mind. If a PO was already marked Received but the parcel never came, stock has to be reversed without losing the audit trail.

**What this achieves.** Two-step cancel: the app shows you exactly what stock will be reversed, then on confirm writes negative `ADJUSTMENT` movements (the originals stay — that's history). The PO flips to `CANCELLED`.

**Click-through.**
1. Open any PO that's `DRAFT`, `SENT`, or `RECEIVED`.
2. Click **Cancel PO**.
3. Read the reversal preview (what will be subtracted from stock if the PO was Received).
4. Confirm cancellation.
5. PO is now `CANCELLED`. Stock movements show both the original receipt and the reversal.

**What "good" looks like.** You feel safe cancelling — the math is shown to you before you commit.

**Feedback to capture.**
- Does the reversal preview help you trust the cancel button?
- Is "Cancel PO" too easy / too hard to find?

---

## Scenario 8 — Export and import master data

**Why it matters.** Sometimes you want to share material/spec data with the consultant or a supplier, edit it in Excel, or apply bulk changes back to the app. The Data page gives you a single canonical workbook for round-tripping.

**What this achieves.** A fresh `MasterData_*.xlsx` is generated on demand from the live database — three sheets: `MaterialMaster` (every raw material with stock), `ProductSpec` (every BOM line), `ChangeLog` (every recorded change). The same file can be uploaded back to apply edits.

**Click-through.**
1. Click **Data** in the top nav.
2. Read the four counters at the top: # materials, # sellable SKUs, # BOM lines, # change-log entries.
3. Click **Download MasterData.xlsx** — Excel file lands in your downloads folder.
4. Open it in Excel. Look at the three sheets. Confirm the figures match your mental model (e.g. SBR01DNL has 16 + 22 + 4 = 42 variant beads on the ProductSpec sheet).
5. Make a small change in `MaterialMaster` — e.g. update a Reorder Point for one material. Save the .xlsx.
6. Back in the app, click **Choose File** → pick the edited file → leave Prune unticked → **Apply file to database**.
7. The page reloads with a summary banner. Scroll to the **Recent changes** table — your edit appears with your username.

**What "good" looks like.** You feel like the app and the spreadsheet are the same data, looked at two ways. No silent overwrites, no surprises.

**Feedback to capture.**
- Do the column names make sense?
- Anything missing you'd want on the export?
- Is the Prune option clear, or should it be hidden?

---

## Scenario 9 — Manage materials and BOMs (the back office)

**Why it matters.** New beads, new findings, new product types — the catalogue isn't static. There needs to be a place to edit it.

**What this achieves.** The Django admin (under `/admin/`) gives you full CRUD on every model: raw materials, products, variants, BOMs, suppliers, POs, projects, and the read-only stock-movement and change-log audit trails. This is your back-office.

**Click-through.**
1. Go to **`/admin/`** (or click the admin link in the nav, if shown).
2. Browse **Raw materials** — see all 81 current materials with current stock, reorder point, last-paid cost, supplier.
3. Browse **Product variants** — see margin%, can-make-units, and edit the BOM right there (inline table).
4. Browse **Stock movements** — read-only audit trail of every stock change ever made.

**What "good" looks like.** You can fix a typo in a bead description, change a reorder point, or add a new product without calling the consultant.

**Feedback to capture.**
- Is the admin too dense? (It's a power-user UI by design.)
- Which fields do you actually edit often vs. never?

---

## Things to look for across the whole session

- **Speed:** does the app feel fast, or are there pages where you wait?
- **Wording:** any labels that don't match how you talk about the work?
- **Trust:** do the numbers feel right? Anything that looks off vs. the spreadsheet?
- **Friction:** anywhere you'd want one fewer click, or one fewer field?

---

## What's deliberately *not* in this version

These were scoped out of v0.2 — flag if any are now blockers:

- Sales tracking (removed for now — design preserved for re-add when channel decisions firm up)
- WooCommerce auto-sync
- Email / SMS low-stock alerts (visible in dashboard only)
- Multi-user with separate roles (single Tersia login)
- Variant pricing per Sugar Bush vs. African Goddess channel
- Mobile/PWA layout

---

## Open the conversation with these prompts

If the client gets quiet, try:

1. *"Walk me through your morning. Does this dashboard answer what you'd ask?"*
2. *"When you ran out of beads last time, what would have helped?"*
3. *"What part of this still feels like the spreadsheet?"*
4. *"What's the one feature you'd quit your spreadsheet for today?"*
5. *"What scares you about giving up the spreadsheet?"*

---

## After the meeting

Capture in this section (or a new doc) — what to keep, what to change, what's next:

- **Keep:**
- **Change:**
- **Add:**
- **Remove:**
- **Next session:**
