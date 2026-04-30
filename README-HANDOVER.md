# SRC Class Rep Portal Handover

## What this is

This portal is designed to run on an SRC-owned Windows computer at no hosting cost.
Live data is stored in Windows AppData so it is preserved even after reinstall.

## Daily use

1. Double-click `Start SRC Portal.vbs`
2. The portal opens in the normal default web browser on local host
3. There is no command prompt window during normal use
4. If the portal is already running, double-clicking the launcher simply opens it again in the browser

## Optional stop shortcut

If SRC wants to fully stop the local portal service without restarting the computer:

1. Double-click `Stop SRC Portal.vbs`

This is only needed when they want to shut the local service down completely.

## Where data is stored (persistent)

The portal saves live data in a persistent Windows location.

Primary default:

`%APPDATA%\SRCClassRepPortal\`

If `%APPDATA%` is blocked by permissions, it automatically falls back to:

`persistent_data\` inside the app folder.

This means uninstalling/reinstalling the app folder does not remove historical records if the persistent location is kept.

## Office network use

If SRC wants other devices on the same office network to use the portal without internet hosting:

1. Run `Start SRC Portal (Office Network).vbs`
2. Keep that SRC computer turned on
3. Open the hosting computer's local IP address with port `5050` from another device

Example:

`http://192.168.1.25:5050/dashboard`

This still keeps the app inside the office/local network and avoids paid hosting.

## Backups

Run `Backup SRC Portal Data.bat` regularly.

This creates backup zip files in:

`<persistent_root>\backups\`

Each backup includes:

- `data\`
- `uploads\`

## Restore after a problem

1. Close the portal if it is open
2. Open the latest backup zip file from `<persistent_root>\backups\`
3. Copy the backed-up `data` and `uploads` folders back into `<persistent_root>\`
4. Start the portal again with `Start SRC Portal.vbs`

## Important folders

- `static\img\` : logo files
- `<persistent_root>\data\` : live records and history
- `<persistent_root>\uploads\` : uploaded files
- `<persistent_root>\backups\` : backup zip files
- `<persistent_root>\logs\portal.log` : error log file

## Logo

To use the real SRC logo, place the logo file in:

`static\img\`

Recommended filename:

`src-logo.png`

## If the portal does not open

Check these items:

1. Make sure the full project folder was copied together
2. Make sure `.venv\Scripts\python.exe` exists
3. Make sure no other app is already using port `5050`
4. Start again using `Start SRC Portal.vbs`

## Recommended SRC process

- Keep the portal on one SRC office computer
- Use `Start SRC Portal (Office Network).vbs` only if other office devices need access
- Back up at least weekly
- Export important data to Excel before major term changes
- Do not manually edit JSON files unless necessary
