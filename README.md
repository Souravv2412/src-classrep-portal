# SRC Class Representative Portal

Web app for managing class representative applications, meetings, awards, engagement points, ranking, and bulk email workflows.

## Preview

### Sample Data Snapshot (Demo)
| Metric | Sample Value |
|---|---:|
| Total Class Reps | 86 |
| Meetings This Term | 14 |
| Avg Attendance | 78% |
| Awards Issued | 22 |
| Emails Sent | 145 |

### Screenshots
![Dashboard](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/dashboard.png)
![Class Reps](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/class-reps.png)
![Meetings](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/meetings.png)
![Awards](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/awards.png)
![Engagement](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/engagement.png)
![Emails](https://raw.githubusercontent.com/Souravv2412/src-classrep-portal/main/docs/screenshots/emails.png)

## Core Features

- Dashboard with live term summary and top reps
- Class rep directory with search + campus/intake/year filters
- Meeting creation and attendance tracking (`attended`, `regrets`, `absent`)
- Awards (monthly + yearly) with filters
- Engagement points + term ranking + archive
- Email center with templates, recipient search, select-all, and send confirmation
- Points history in rep detail (explains why score changed)

## Security Access (for shared link use)

This app supports login protection through environment variables:

- `SRC_PORTAL_ADMIN_USERNAME`
- `SRC_PORTAL_ADMIN_PASSWORD`

When both are set, only logged-in users can access and edit data.

## Data Persistence

Data is saved in local files under:

- `SRC_PORTAL_DATA_ROOT/data`
- `SRC_PORTAL_DATA_ROOT/uploads`

If `SRC_PORTAL_DATA_ROOT` is not set, app fallback paths are used.

## Render Deployment

1. Keep repository public/private as you prefer.
2. In Render, create a new **Web Service** from this repo.
3. Render auto-detects `render.yaml`. If asked manually, use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
4. Add a **Persistent Disk** and mount it at:
   - `/var/data`
5. Set environment variables:
   - `SRC_PORTAL_DATA_ROOT=/var/data`
   - `SRC_PORTAL_OPEN_BROWSER=0`
   - `SRC_PORTAL_ADMIN_USERNAME=<your_username>`
   - `SRC_PORTAL_ADMIN_PASSWORD=<your_password>`
6. Deploy and open `/health` to confirm service status.

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_portal.py
```
