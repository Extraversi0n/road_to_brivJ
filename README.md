# Road to BrivJ – Overlay

A small tool that generates a transparent PNG overlay for **Idle Champions**, showing your progress toward your **Blacksmith Contracts (BSC)** target.

It reads the newest `getuserdetails` request from your local game log, calls the API via **POST**, and renders a clear, stream-friendly progress overlay for use in OBS or similar tools.

---

## Features

### Overlay
- Transparent PNG output
- Rounded progress bars
- Stacked **total BSC** bar
- Per-resource progress for:
  - Gold Chests
  - Silver Chests
  - Gems
- Total BSC breakdown from:
  - Base BSC
  - Gold Chests
  - Silver Chests
  - Gems
  - optional Champion/Event Chests
- Color legend for the total bar
- Locale-aware number formatting
- Configurable percentage display style

### Champion / Event support
- Optional **Champion Event Chests** contribution
- Event chest progress is shown **only in the total bar**
- Configurable:
  - Champion name
  - Silver chest ID
  - Gold chest ID
- Toggle for event gold chest valuation:
  - **Gear + BSC only**
  - **Gear + BSC + BC Tokens**

### ETA / Days Remaining
- Optional ETA display
- Supports:
  - **manual BSC/h**
  - **snapshot-derived BSC/h**
- Snapshot-derived rate takes priority when valid
- Manual `BSC/h` is used as fallback only

### Snapshot system
- Save local snapshots of current total BSC
- Build a snapshot history over time
- Estimate `BSC/h` from snapshot history
- Includes a **Snapshot Manager** to:
  - inspect saved snapshots
  - delete selected entries
  - delete the full history

### GUI
- Pick `webRequestLog.txt`
- Set output PNG path
- Set BSC goal
- **Extract from log**
  - auto-fills `user_id`
  - auto-fills `hash`
  - auto-fills `post.php` API URL
- Optional local saving of `user_id` / `hash`
- Hash field can be masked/unmasked

### Automation / headless mode
- `--headless` mode for Task Scheduler or scripts
- CLI overrides for:
  - log path
  - output path
  - goal
  - credentials
  - API URL
  - event settings
  - ETA settings
  - snapshot actions

### Runtime behavior
- EXE-friendly working directory handling
- Local icon cache
- TLS validation via `certifi`
- Font fallback for Windows/macOS/Linux

---

## How It Works

The tool:

1. Reads the **newest** `getuserdetails` line from `webRequestLog.txt`
2. Extracts:
   - `user_id`
   - `hash` / `hashh`
   - `post.php` URL  
   or derives the API URL from `play_server`
3. Calls the game API using **POST**
4. Calculates:
   - current BSC from contracts
   - BSC contribution from Gold / Silver / Gems
   - optional Champion/Event chest contribution
   - remaining BSC to target
5. Renders:
   - individual resource bars
   - a stacked total BSC bar
   - optional ETA / days remaining

---

## Overlay Logic

### Resource bars
Each resource bar answers:

> **How many units would still be needed if the goal were completed using only this resource?**

That means the shown goal per resource is:

- overall remaining BSC
- **plus** the contribution that resource already provides

### Total BSC bar
The total bar stacks all active BSC contributions into one combined progress bar:
- Base BSC
- Gold
- Silver
- Gems
- optional Champion/Event Chests

---

## Quick Start (EXE)

1. Go to **Releases** and download the latest `IdleChampsOverlay.exe`
2. Start the EXE
3. Set or confirm:
   - log path
   - output PNG
   - BSC goal
4. Click **Extract from log**
5. Optional:
   - enable Champion/Event Chests
   - enable ETA
   - save a snapshot
6. Click **Save & Run**

> Typical default log path:
>
> `C:/IdleChampions/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt`

---

## Run from Source

### Requirements
- Windows
- Python **3.9+**
- A recent `webRequestLog.txt`

### Install dependencies

```bash
pip install -r requirements.txt