HSE Platform - portable Windows edition
=======================================

This is the whole HSE platform (including the Quality module) in one folder. You unzip it
and double-click HSE.exe. Nothing is installed, no administrator rights are needed, and
nothing is put on the internet: the platform runs only on this laptop and only this
laptop's browser can open it.

Needs: Windows 10 or 11 (64-bit), about 2 GB of free disk space, 8 GB of memory
recommended.


1. Download
-----------

1. Open the repository on GitHub, click "Actions", then "Portable Windows" on the left.
2. Open the newest run with a green tick.
3. At the bottom of the page, under "Artifacts", click "HSE-Platform-Windows".
   The file HSE-Platform-Windows.zip is downloaded (you must be signed in to GitHub).


2. Unzip
--------

1. In your Downloads folder, right-click HSE-Platform-Windows.zip and choose
   "Properties". If you see an "Unblock" box at the bottom, tick it and click OK.
   (This avoids extra Windows warnings.)
2. Right-click the zip again, choose "Extract All...", pick your Desktop or Documents,
   and click "Extract".
3. Do not start HSE.exe from inside the zip: always unzip first.


3. Start
--------

1. Open the extracted folder "HSE-Platform-Windows" and double-click HSE.exe.
2. A black window opens and shows the progress.
   - The first start prepares the database and loads the demo data. This takes a few
     minutes. Later starts take less than a minute.
3. When it says "The platform is running", your browser opens the sign-in page by itself
   (address http://127.0.0.1:3000, or another number after the colon if 3000 is busy).


4. Sign in (demo accounts)
--------------------------

All demo accounts use the password:  Demo-Passw0rd!2026

  faisal.harbi@example.com     HSE Manager
  hatem.shehri@example.com     QA/QC Manager, Construction (project ANIA-EXP)
  reem.mutairi@example.com     QA/QC Manager, Logistics (project RUH-CCH)

Both Quality profiles are loaded at the same time, so you can compare Construction and
Logistics by signing in as Hatem and as Reem (use a private browser window for the second
person if you want both open at once).

All names, companies and records in the demo data are fictional.


5. Stop
-------

Close the black window (or click in it and press Ctrl+C). The platform stops and the
database is closed properly. Your data is kept for the next start.

If you double-click HSE.exe while it is already running, it just opens the browser again.


6. Where your data lives
------------------------

Everything is in the "data" folder next to HSE.exe:

  data\pgdata     the database
  data\uploads    uploaded files and photos
  data\config     generated secret keys (secrets.env) and optional settings (settings.env)
  data\logs       log files (send these if something goes wrong)

The secret keys in data\config\secrets.env are needed to read the database. Keep the data
folder private and never share it.


7. Back up
----------

1. Stop the platform (close the black window).
2. Copy the whole "data" folder somewhere safe (for example a USB drive or OneDrive).

To restore: stop the platform, delete its data folder, and copy your backup "data"
folder back next to HSE.exe.


8. Start fresh
--------------

Stop the platform and delete the "data" folder. The next start creates a new, empty
database with the demo data again.


9. Move to a newer version
--------------------------

1. Stop the platform.
2. Unzip the new version into a new folder.
3. Move the "data" folder from the old folder into the new one (next to HSE.exe).
4. Start the new HSE.exe. It updates the database structure by itself and keeps your data.


10. Windows or company warnings
-------------------------------

HSE.exe is not signed with a company certificate, so Windows may warn you:

- "Windows protected your PC" (SmartScreen): click "More info", then "Run anyway".
- "This app has been blocked by your system administrator", or nothing happens at all:
  your company's IT policy does not allow programs from this folder. Ask IT to allow
  the folder (or HSE.exe and the programs under its "runtime" folder).
- Windows Firewall should not ask anything: the platform listens only on this laptop
  (127.0.0.1) and is not reachable from the network.


11. Good to know
----------------

- No virus scanning of uploads in this edition. The server edition scans every uploaded
  file; here scanning is switched off. Only upload files you trust.
- Emails (invitations, alerts) are not sent; they stay in the platform's outbox. To send
  them, put your mail server details in data\config\settings.env (examples inside) and
  restart.
- Two-step verification is optional for everyone in this edition (it is compulsory for
  HSE Managers on a server). To make it compulsory, see data\config\settings.env.
- The AI assistant needs an internet connection and an API key, so it answers "not
  available" in this edition unless ANTHROPIC_API_KEY is set in data\config\settings.env.
- Only one person on this laptop uses it. Phones and other computers cannot reach it.
- If something goes wrong, the black window says what happened and which log file in
  data\logs has the details.


Technical notes
---------------

- Programs: PostgreSQL 16 on 127.0.0.1:54329 (data\pgdata, password authentication with a
  generated password), the API (uvicorn) on 127.0.0.1:54330, the timed jobs
  (app.scheduler), and the Next.js server on 127.0.0.1:3000 (or the next free port). The
  web build's /api proxy points at 127.0.0.1:54330, so that port is fixed.
- First start: initdb (UTF-8, ICU en-US collation), random secrets in
  data\config\secrets.env (POSTGRES_PASSWORD, JWT_SECRET, FIELD_ENCRYPTION_KEY,
  BLIND_INDEX_KEY, ATTACHMENT_URL_SECRET), then `alembic upgrade head` and
  `python -m app.seed`. Every start runs `alembic upgrade head`; the seed runs only until
  data\config\seeded exists.
- ENVIRONMENT=development. ENVIRONMENT=production requires COOKIE_SECURE=true, which needs
  HTTPS; the platform is served over plain http on 127.0.0.1 here, so secure cookies
  would never be sent back. The production check that matters (no dev-only secrets) is
  met anyway because every secret is generated randomly on first start. The demo seed
  also refuses to run in production. No HSE_CLOCK_* setting is used.
- Other portable switches, all environment variables set by HSE.exe (the application
  code is the same as the server deployment): COOKIE_SECURE=false, CLAMAV_HOST empty,
  MFA_REQUIRED_ROLES empty, STORAGE_DIR=data\uploads,
  FRONTEND_BASE_URL=http://127.0.0.1:<port>. data\config\settings.env may override them
  (except DATABASE_URL and STORAGE_DIR).
- HSE.exe options: --no-browser, --stop (asks a running HSE.exe on the same folder to stop),
  --data <folder>, --web-port <n>, --pg-port <n>, --version.
- Built and smoke-tested by .github/workflows/portable-windows.yml (portable/build.ps1,
  portable/smoke.ps1); the launcher source is portable/launcher (Go, standard library only).
