[EdgeFinder_GitHub_Setup.md](https://github.com/user-attachments/files/29523658/EdgeFinder_GitHub_Setup.md)
# EdgeFinder on GitHub — Setup Guide

Goal: tap a button, GitHub runs the script on its own servers (not your laptop, so your work firewall can't block it), and your iPhone shows a fresh dashboard.

You'll do this once. It takes about 15 minutes. After that it's just "tap to refresh."

---

## What you're uploading (2 files)

1. **edgefinder.py** — the program (renamed from edgefinder_github.py — see Step 2)
2. **edgefinder.yml** — the instructions that tell GitHub how to run it

Everything else (the dashboard, your bet log) gets created automatically when it runs.

---

## STEP 1 — Create the repository (2 min)

1. Go to **github.com** and sign in.
2. Top-right, click the **+** then **New repository**.
3. Name it: `edgefinder`
4. Set it to **Public** (free Pages needs this).
5. Check **"Add a README file"** (so the repo isn't empty).
6. Click **Create repository**.

---

## STEP 2 — Upload edgefinder.py (3 min)

1. **Rename the file first:** the file I gave you is `edgefinder_github.py`. Rename it on your computer to exactly **`edgefinder.py`** (the workflow looks for that name).
2. In your new repo, click **Add file ▸ Upload files**.
3. Drag in **edgefinder.py**.
4. Down below, click **Commit changes**.

---

## STEP 3 — Add the workflow file (3 min)

The workflow has to live in a specific folder (`.github/workflows/`). Easiest way to create that folder is to type the path:

1. In your repo, click **Add file ▸ Create new file**.
2. In the filename box at the top, type exactly:
   ```
   .github/workflows/edgefinder.yml
   ```
   (As you type the slashes, GitHub turns them into folders automatically.)
3. Open the **edgefinder.yml** file I gave you, copy ALL of its contents, and paste into the big editor box.
4. Click **Commit changes**.

---

## STEP 4 — Add your API key as a secret (2 min)

Your Odds API key shouldn't sit in public code, so GitHub stores it encrypted.

1. In your repo, click **Settings** (top menu).
2. Left sidebar: **Secrets and variables ▸ Actions**.
3. Click **New repository secret**.
4. Name: `ODDS_KEY`
5. Secret: paste your key: `82149bd2ee25ae592612b8335b553d88`
   *(Better yet, generate a fresh one at the-odds-api.com since this one has been shared in chat — then paste the new one here.)*
6. Click **Add secret**.

---

## STEP 5 — Turn on GitHub Pages (2 min)

This makes your dashboard viewable as a web page.

1. Still in **Settings**, left sidebar: **Pages**.
2. Under **Source**, pick **Deploy from a branch**.
3. Branch: **main**, folder: **/docs**. Click **Save**.
4. (The page won't exist until the first run — that's next.)

---

## STEP 6 — Run it for the first time (2 min)

1. Click **Actions** (top menu).
2. If GitHub asks to enable workflows, click the green **I understand my workflows, enable them**.
3. Left sidebar: click **EdgeFinder**.
4. Right side: click **Run workflow ▸ Run workflow** (green button).
5. Wait ~1–2 minutes. A yellow dot turns green when it's done.

Your dashboard is now live at:
```
https://YOURUSERNAME.github.io/edgefinder/
```
(Replace YOURUSERNAME with your GitHub username. First load can take 2-3 min for Pages to wake up.)

---

## STEP 7 — Put it on your iPhone home screen (1 min)

1. Open that `github.io` link in **Safari** on your iPhone.
2. Tap the **Share** icon (square with up-arrow).
3. **Add to Home Screen**.
4. Name it "EdgeFinder", tap **Add**.

Now you have an app icon that opens your dashboard full-screen.

---

## How you'll use it day to day

**To refresh the data:** the dashboard only updates when the workflow runs. Two ways to trigger it from your phone:

**Easy way (no extra setup):**
- Install the **GitHub** app (App Store), sign in.
- Open your repo ▸ **Actions** ▸ **EdgeFinder** ▸ **Run workflow**.
- Wait a minute, then open your EdgeFinder home-screen icon.

**One-tap way (optional, 10 min to set up):** see the "iPhone Shortcut" section below — it makes a single button that triggers the run.

---

## OPTIONAL — One-tap iPhone Shortcut

This creates a real one-tap button. It needs a GitHub access token.

### First, make a token:
1. On github.com: click your avatar ▸ **Settings** ▸ **Developer settings** (very bottom of left sidebar).
2. **Personal access tokens ▸ Fine-grained tokens ▸ Generate new token**.
3. Name: `edgefinder-shortcut`. Expiration: your choice (90 days is fine).
4. **Repository access:** Only select repositories ▸ pick `edgefinder`.
5. **Permissions:** expand **Repository permissions**, find **Actions**, set to **Read and write**.
6. Generate, then **copy the token** (you won't see it again).

### Then, build the Shortcut:
1. Open the **Shortcuts** app on iPhone ▸ **+** (new shortcut).
2. Add action: **Get Contents of URL**.
3. URL:
   ```
   https://api.github.com/repos/YOURUSERNAME/edgefinder/actions/workflows/edgefinder.yml/dispatches
   ```
4. Tap **Show More**:
   - **Method:** POST
   - **Headers:** add two —
     - `Accept` = `application/vnd.github+json`
     - `Authorization` = `Bearer YOUR_TOKEN_HERE`
   - **Request Body:** JSON, with one field: `ref` = `main`
5. (Optional) add a second action: **Wait** 90 seconds, then **Open URL** ▸ your github.io link.
6. Name the shortcut "Refresh EdgeFinder", and add it to your home screen from the share menu.

Now: tap the shortcut → it tells GitHub to run → wait a bit → dashboard's fresh.

---

## A few honest notes

- **First load lag:** GitHub Pages can take a couple minutes to update after a run. If you tap refresh and the board looks old, give it 1-2 min and reload.
- **Public dashboard:** anyone with your exact `github.io/edgefinder` link can see the board. It's not searchable or linked anywhere, but it's not private. No personal info is on it, just odds. Your API key stays hidden (it's a secret).
- **It's the same engine** as the local version — value scan, S-D sharp grades, unit sizing, live status, results tracker — just running in the cloud. Your bet log lives in the repo and persists between runs.
- **Lines move:** the board is fresh as of the run. Re-trigger before betting if it's been a while.
- **Auto-schedule (optional):** if you want it to refresh on its own (say Thu/Fri/Sat afternoons), open `edgefinder.yml`, delete the `#` marks on the `schedule:` and `cron:` lines, and commit. Then you don't even have to tap.

---

## If something doesn't work

- **No "Run workflow" button:** make sure `edgefinder.yml` is in `.github/workflows/` exactly, and you enabled Actions (Step 6.2).
- **Workflow runs but fails (red X):** click the failed run to see the log. Most common: the `ODDS_KEY` secret name is misspelled (must be exactly `ODDS_KEY`).
- **Page shows 404:** Pages takes a few minutes the first time. Also double-check Settings ▸ Pages is set to main /docs.
- **Dashboard not updating:** confirm the run finished green in the Actions tab, then hard-refresh the page.
