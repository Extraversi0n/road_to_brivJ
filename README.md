# Road to BrivJ – Overlay
![Windows EXE](https://github.com/Extraversi0n/road_to_brivJ/actions/workflows/windows-build.yml/badge.svg)

![Overlay example](docs/overlay_example.png)

A small tool that generates a **transparent PNG overlay** for *Idle Champions*, showing your progress toward your **Blacksmith Contracts (BSC)** target.

- Reads **only the newest** `getuserdetails` line from `webRequestLog.txt`
- Calls the API using **POST** (robust; avoids 414)
- Renders:
  - **Stacked BSC** (Base + projection from **Gold** / **Silver** / **Gems**, all in BSC units)
  - **Resource bars**: “How many **units** would you still need if you finished the goal using only this resource?”  
    *(= overall remaining + your current contribution from that resource)*

---

## Features

- **GUI (default)**  
  - Pick `webRequestLog.txt`, set **BSC goal** and **output path**  
  - **Extract from log**: auto-fills `user_id`, `hash`, `mobile_client_version`, and `post.php` URL  
  - Manual **overrides** available (hash masked with a “show” toggle)  
  - **Save & Run** or **Skip (use saved)** (persists to `tracker_config.json`)
- **Headless mode** for Task Scheduler/scripts: `--headless` (no GUI)
- **Locale-aware integers** (thousand separators) & configurable **percent style**  
  (`--percent-style locale|dot|int`)
- **EXE-friendly**: bundled icons, TLS via `certifi`, font fallback, no console window

---

## Quick Start (EXE)

1. You can go to [Releases](https://github.com/Extraversi0n/road_to_brivJ/releases) and just download and use the "IdleChampsOverlay.exe" of the latest release if you are otherwise unfamiliar with github and python. 
2. Double-click the EXE → GUI opens.
3. Set Locations.
4. Click **Extract from log** (it reads only the newest `getuserdetails` line).  
5. Set **BSC goal** and **output** → **Run**.

> Default log path (Steam, typical):  
> `C:/IdleChampions/IdleDragons_Data/StreamingAssets/downloaded_files/webRequestLog.txt`

---

## Run from Source

**Requirements**
- Windows + Idle Champions (recent `webRequestLog.txt`)
- Python **3.9+** (tested 3.10–3.12)
- Dependencies:
  ```bash
  pip install -r requirements.txt
  # or:
  pip install pillow requests certifi
  ```

**Run**
```bash
python progress_tracker_extended.py
```

---

## Headless & Automation

Run without GUI (e.g., **Windows Task Scheduler**).

**EXE example**
```bat
IdleChampsOverlay.exe --headless --percent-style locale --goal-bsc 15360005 --output "C:\Overlay\overlay_extended.png"
```

**Python example**
```bat
pythonw.exe progress_tracker_extended.py --headless --percent-style locale
```

**CLI flags**
```
--headless                 run without GUI (use saved config + CLI overrides)
--log-path PATH            path to webRequestLog.txt
--output PATH              output image (overlay_extended.png)
--goal-bsc INT             target in BSC units
--user-id ID               override user_id
--hash VALUE               override hash
--mcv VALUE                override mobile_client_version
--api-url URL              override post.php URL
--percent-style [locale|dot|int]
                           percentage style: OS locale, always dot, or integer
```

> Leave overrides empty and the app auto-extracts values from the **newest** `getuserdetails` log line.

### Windows Task Scheduler (EXE)
1. **Program/script:** full path to `IdleChampsOverlay.exe`  
2. **Add arguments:** e.g.
   ```
   --headless --percent-style locale --output "C:\Overlay\overlay_extended.png"
   ```
3. **Start in:** the folder where the EXE lives (important for icons/config/output)  
4. Optional: set **Hidden** so nothing flashes  
5. Add a trigger (e.g., every 5 minutes), save

**Silent .BAT (optional)**
```bat
@echo off
cd /d "%~dp0"
IdleChampsOverlay.exe --headless --percent-style locale >nul 2>&1
```

---

## How It Works (quick)

- Reads only the **newest** `getuserdetails` line from the log
- Extracts `user_id`, `hash`/`hashh`, `mobile_client_version`, **post.php** URL  
  (or derives the URL from `play_server`)
- Uses **POST** (not GET)
- **Stacked BSC**: Base + Gold + Silver + Gems in BSC  
- **Resource bars**: unit requirements = global remaining **+** this resource’s contribution

---

## Config & Privacy

- Settings live in `tracker_config.json` (next to the EXE/script).  
- `user_id` & `hash` are **not saved** unless you explicitly enable **“Save user_id/hash to config”** in the GUI.
