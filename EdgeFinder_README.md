# EdgeFinder: Your README

Your reference for handing the project to a fresh AI chat, the GitHub setup, and day-to-day use.

---

## The 4 files (this is your whole project)

| File | What it is | Where it lives in the repo |
|---|---|---|
| `edgefinder.py` | The entire program | repo root |
| `edgefinder.yml` | The GitHub workflow (schedule + run) | `.github/workflows/edgefinder.yml` |
| `HANDOFF.md` | Technical spec for a future AI | repo root |
| `EdgeFinder_README.md` | This file, for you | repo root |

Everything else in the repo (`docs/`, `edgefinder_betlog.json`, `edgefinder_snapshots.json`, `edgefinder_history/`) is auto-generated. You never edit those by hand.

---

## Making changes in a fresh AI chat

To save tokens, start a new chat and **attach only these 4 files:**
`edgefinder.py`, `edgefinder.yml`, `HANDOFF.md`, `EdgeFinder_README.md`.

Do NOT attach `edgefinder_betlog.json`, `edgefinder_snapshots.json`, or the CSVs. They are your growing data logs, the AI does not need them to change code, and they burn tokens.

**What to say:** "Here is my EdgeFinder betting tool. Read HANDOFF.md first, it explains the architecture and the decisions I don't want reverted. I want to [your change]."

Because HANDOFF.md carries the full context, you should not need to re-explain the whole project each time. Just state the change you want.

**After the AI makes the change, it should hand you back BOTH an updated `edgefinder.py` AND an updated `HANDOFF.md` (with a new changelog line).** Commit both together. If an AI gives you only the code, ask it for the refreshed HANDOFF too. This is the single habit that keeps the next chat from getting confused: the spec must always match the code.

One honest limit: no AI can auto-update these files across chats or reach into your GitHub. The flow is always the same. AI gives you updated files, you commit them.

---

## Updating a file in your repo

When you get a new `edgefinder.py` (or any file):

1. Open the file in your repo on github.com.
2. Click the pencil (Edit) icon.
3. Select all, delete, paste the new contents.
4. Click **Commit changes**.

The next run uses the new version.

---

## The automatic schedule

Runs **3x a day, about 10am, 2pm, and 6pm Central.** Each run finds today's plays, grades finished games, and snapshots the board for edge-over-time tracking. It runs daily even when you are not betting, so your tracker stays current if you take time off.

**Two GitHub scheduling quirks:**
1. **Activate it once by hand.** After you commit the workflow, GitHub often will not fire the first scheduled run on its own. Go to Actions, click EdgeFinder, click **Run workflow** once. After that it runs itself.
2. **It pauses after 60 days of no repo activity.** Each run commits results back, so normal use keeps it alive. If it ever stops, click Run workflow once to wake it.

Scheduled runs can be 10 to 30 minutes late during busy periods. Normal for GitHub.

---

## Using it on your phone

Dashboard lives at `https://YOURUSERNAME.github.io/edgefinder/`. Add it to your home screen from Safari's share menu for an app-like icon.

- **Board tab:** today's plays worth attention, with unit sizes and live/final badges.
- **Results tab:** record, ROI, breakdown by grade, charts, CSV downloads. Tap the pill to switch, no reload.

**To refresh now** instead of waiting: open the GitHub app, your repo, Actions, EdgeFinder, Run workflow. Wait about a minute, reload the page. (Or use the one-tap iPhone Shortcut from the original setup guide.)

---

## Where your data lives

All in the repo, persists across runs and time off:
- `edgefinder_betlog.json`: every recommended play and its graded result.
- `edgefinder_snapshots.json`: each run's readings, for edge-over-time.
- `bets.csv` / `snapshots.csv` (in `docs/`): the same data as spreadsheets, downloadable from the Results tab.

---

## API budget (why MLB-only at 3x/day)

The Odds API free tier is about 500 credits a month. Cost is markets x regions per call: 3 markets x 1 region = 3 credits per run, x 3 runs a day = about 270 a month. Comfortable headroom. Adding a sport or more runs can blow it. If you add one, have the AI recalculate cadence.

---

## Adding a sport later (football, basketball)

Tell a future AI you want to add, say, NFL. It should uncomment the sport, calibrate that sport's own grade thresholds (each sport's sharp gaps distribute differently), and adjust cadence to stay in budget. Do not just uncomment it yourself without recalibrating grades and checking the API math.

---

## Quick reminders

- Lines move. The board is fresh as of the last run; re-run before betting if it has been a while.
- Live/Final badges tell you if a play is still bettable. Red LIVE or grey Final means do not chase it.
- Rotate your Odds API key now and then (it has appeared in chats). Update the `ODDS_KEY` secret in repo Settings, Secrets and variables, Actions.
