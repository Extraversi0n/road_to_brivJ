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
```

Alternatively:

```bash
pip install pillow requests certifi
```

---

## Headless / CLI Usage

### Python example

```bat
pythonw.exe progress_tracker_extended.py --headless --percent-style locale
```

### EXE example

```bat
IdleChampsOverlay.exe --headless --percent-style locale --goal-bsc 15360005 --output "C:\Overlay\overlay_extended.png"
```

### Example with snapshot saving enabled

```bat
IdleChampsOverlay.exe --headless --percent-style locale --save-snapshot --output "C:\Overlay\overlay_extended.png"
```

### Example with snapshot ETA enabled

```bat
IdleChampsOverlay.exe --headless --percent-style locale --eta-enable --eta-use-snapshot --output "C:\Overlay\overlay_extended.png"
```

---

## CLI Flags

```text
--headless
    Run without GUI

--log-path PATH
    Path to webRequestLog.txt

--output PATH
    Output PNG path

--goal-bsc INT
    Target in BSC units

--user-id ID
    Override user_id

--hash VALUE
    Override hash

--api-url URL
    Override post.php URL

--percent-style [locale|dot|int]
    Percentage style:
    - locale = OS locale decimal separator
    - dot    = always dot
    - int    = rounded integer percent

--event-enable
    Enable Champion/Event chest contribution

--event-name TEXT
    Champion/Event label used in the total bar

--event-silver-id INT
    Event silver chest ID

--event-gold-id INT
    Event gold chest ID

--event-no-bc-tokens
    Use Gear + BSC only (without BC Tokens) for event gold chest average

--eta-enable
    Enable ETA / Days Remaining

--eta-bsc-per-hour FLOAT
    Manual BSC/h value

--eta-use-snapshot
    Use snapshot-derived BSC/h when valid

--save-snapshot
    Save a snapshot on this run

--reset-snapshots
    Clear snapshot history before running
```

---

## Manual BSC/h Format

The manual `BSC/h` field accepts all of the following formats:

- `1800`
- `1800.5`
- `1800,5`

If a valid snapshot-derived rate is available, it is used first.  
The manual value is only used as a fallback.

---

## Snapshot System

Snapshots are stored locally in:

```text
bsc_snapshot.json
```

Each snapshot stores:
- a timestamp
- the total BSC at that time

The tool can use this history to calculate an average **BSC per hour**.

### Snapshot Manager
The GUI includes a **Snapshot Manager** where you can:
- inspect stored snapshots
- delete selected snapshots
- delete all snapshots

---

## Icons & Cache

Downloaded icon PNGs are cached locally in:

```text
overlay_icon_cache/
```

If icon downloads fail, the overlay still renders — just without icons.

---

## Config & Privacy

Settings are stored locally in:

```text
tracker_config.json
```

### Important
- `user_id` and `hash` are **only saved if you explicitly enable**
  **“Save user_id/hash to config (local)”**
- If that option is disabled again, those values are removed from the config
- This makes it safer to share the repository or distribute builds

---

## Recommended `.gitignore`

These local/runtime files should **not** be committed:

```gitignore
tracker_config.json
bsc_snapshot.json
overlay_icon_cache/
overlay_extended.png
build/
dist/
*.spec
__pycache__/
*.py[cod]
.venv/
env/
venv/
```

---

## Windows Task Scheduler Example

### Program/script
```text
C:\Path\To\IdleChampsOverlay.exe
```

### Add arguments
```text
--headless --percent-style locale --output "C:\Overlay\overlay_extended.png"
```

### Start in
```text
C:\Path\To\
```

Make sure **Start in** points to the folder where the EXE lives so that local config, cache, and output behave correctly.

### Optional example with snapshots
```text
--headless --percent-style locale --save-snapshot --eta-enable --eta-use-snapshot --output "C:\Overlay\overlay_extended.png"
```

---

## Troubleshooting

### “Could not find a `getuserdetails` line…”
- Start the game
- verify the correct log path
- use **Extract from log**
- or provide `user_id`, `hash`, and `api_url` manually

### ETA uses manual BSC/h instead of snapshots
This usually means snapshot data is not usable yet, for example:
- no snapshots exist
- not enough time has passed
- total BSC has not increased since the older snapshot

### Icons are missing
If needed, delete:

```text
overlay_icon_cache/
```

and run again so the icons can be downloaded again.

---

## Sharing / Safety

If you share this project with others:

- **do not commit** `tracker_config.json`
- **do not commit** `bsc_snapshot.json`
- do not include personal/local files in release zips

---

## License

Use, adapt, and share responsibly.

---

Enjoy the Briv grind 🙂