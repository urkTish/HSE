# Put the HSE platform online (Oracle Cloud + Cloudflare)

This guide is for the owner. You only need a web browser — nothing is installed on your laptop.
At the end, you open `https://hse.<your-domain>`, type your email, receive a code by email, and
use the platform. The server accepts no connections from the internet; it only reaches out to
Cloudflare.

**Cost:** the server is free (Oracle "Always Free"). The only cost is a domain name, about
US$10 per year. **Time:** about one hour, plus waiting.

Words that may be new:

- **Server / instance** — a computer in Oracle's data centre that runs the platform.
- **Cloud Shell** — a black command window inside the Oracle website. You copy commands into it.
- **Tunnel** — a private link from the server to Cloudflare. Visitors reach the platform only
  through Cloudflare.
- **Access** — Cloudflare's door: only the email addresses you list can open the site.

Screens on the Oracle and Cloudflare websites change from time to time. Where a step says
*(menu names may differ slightly)*, look for the closest match.

---

## A. Oracle Cloud account

1. On your phone or laptop open **https://www.oracle.com/cloud/free/** and tap **Start for free**.
2. Fill in your name, email and country (**Saudi Arabia**). Confirm the email Oracle sends.
3. **Home region:** choose **Saudi Arabia West (Jeddah)** or **Saudi Arabia Central (Riyadh)**,
   whichever is offered.
   - The home region **cannot be changed later**.
   - Your data stays in Saudi Arabia.
4. Add a payment card. Oracle uses it only to check who you are; Always Free use is not charged.
5. Wait for the "Your account is ready" email (minutes to a few hours), then sign in at
   **https://cloud.oracle.com**.
6. **Upgrade to Pay As You Go** (strongly recommended):
   Menu ☰ → **Billing & Cost Management** → **Upgrade and Manage Payment** → **Pay As You Go**
   *(menu names may differ slightly)*.
   - Always Free resources stay free after the upgrade.
   - Oracle does not reclaim idle servers on these accounts, and it is easier to get an Ampere
     server when capacity is short.
7. **Budget alert**, so you hear about any charge at once:
   Menu ☰ → **Billing & Cost Management** → **Budgets** → **Create Budget**
   *(menu names may differ slightly)*.
   - Amount: **1** (in your account's currency).
   - Alert: **Actual spend**, **50 %** of the budget, sent to your email.

## B. Create the server

1. At the top right of the Oracle website, tap the **Developer tools** icon → **Cloud Shell**
   *(menu names may differ slightly)*. A black window opens at the bottom. Wait for the `$` prompt.
2. Make a login key for the server. Copy this line into Cloud Shell and press Enter:

   ```
   ssh-keygen -t ed25519 -f ~/.ssh/hse -N "" && cat ~/.ssh/hse.pub
   ```

   It prints one long line starting with `ssh-ed25519`. Select it and copy it.
   (The key stays in your Cloud Shell. Do not delete it.)
3. Menu ☰ → **Compute** → **Instances** → **Create instance**.
4. **Name:** `hse`.
5. **Image and shape** → **Edit**:
   - **Change image** → **Ubuntu** → **Canonical Ubuntu 24.04** → **Select image**.
   - **Change shape** → **Ampere** → **VM.Standard.A1.Flex** → **4 OCPUs** and **24 GB** memory
     → **Select shape**. It must show "Always Free-eligible".
6. **Networking:** keep **Create new virtual cloud network** and **Create new public subnet**, and
   make sure **Assign a public IPv4 address** is on. (Oracle's default network rules let only SSH
   in. Do not add other rules.)
7. **Add SSH keys** → **Paste public keys** → paste the `ssh-ed25519 …` line from step 2.
8. **Boot volume** → **Specify a custom boot volume size** → **100** GB.
9. Tap **Create**. After 1–3 minutes the state turns **Running**. Write down the
   **Public IP address** shown on the page (for example `141.147.10.20`).

**"Out of capacity" error?** Free Ampere servers are popular.
- Try again later (early morning or late evening often works); your settings stay in the form.
- If the form shows more than one **Availability domain**, try another one.
- Or choose **2 OCPUs and 12 GB** in step 5. That is enough to start; you can make it bigger later
  (Instance → **Edit** → shape) when capacity is available.

## C. Cloudflare account and domain

1. Open **https://dash.cloudflare.com/sign-up**, create an account and confirm the email.
2. Buy a domain: **Domain Registration** → **Register Domains** → search for a name, e.g.
   `mycompany-hse.com` → buy (about US$10 per year) *(menu names may differ slightly)*.
   Already have a domain? Use **Add a domain** instead and follow Cloudflare's steps.
3. Your platform's web address will be **`hse.<your-domain>`**, for example
   `hse.mycompany-hse.com`.

## D. Tunnel (the private link)

1. In Cloudflare, open **Zero Trust** from the left menu. The first time, choose a team name and
   the **Free** plan (up to 50 users). It may ask for a card even for the free plan; you are not
   charged.
2. **Networks** → **Tunnels** → **Create a tunnel** → **Cloudflared** → name it `hse` → **Save**
   *(menu names may differ slightly)*.
3. The next page shows install commands containing a very long code that starts with `eyJ`.
   This is the **tunnel token**. Copy the whole command (or only the `eyJ…` part) and keep it for
   step F. **Do not run these commands** and do not share the token.
4. Tap **Next**. Add a **public hostname** (in newer screens: **Published application route**):
   - Subdomain: `hse`
   - Domain: your domain
   - Service type: **HTTP**
   - URL: `frontend:3000`
5. Tap **Save**. The tunnel shows "Inactive" or "Down" until step F is done. That is normal.

## E. Access (only your people get in)

Do this **before** step F so the site is never open to the public.

1. Zero Trust → **Access** → **Applications** → **Add an application** → **Self-hosted**
   *(menu names may differ slightly)*.
2. Name: `HSE`. Session duration: **24 hours**. Domain / public hostname: subdomain `hse`, your
   domain.
3. Add a **policy**: name `Allowed people`, action **Allow**, rule **Include** → **Emails** → type
   each allowed email address (yours first).
4. Login method: **One-time PIN** (it is on by default). Save the application.

Up to 50 people are free.

## F. Install the platform (in Cloud Shell)

1. Open **Cloud Shell** again (as in B1) and connect to the server (use your IP address):

   ```
   ssh -i ~/.ssh/hse ubuntu@141.147.10.20
   ```

   The first time it asks "Are you sure you want to continue connecting?" — type `yes` and press
   Enter. The prompt changes to `ubuntu@hse:~$`.
2. Copy this line and press Enter:

   ```
   curl -fsSLo setup.sh https://raw.githubusercontent.com/urkTish/HSE/claude/hse-platform-build-kannxy/deploy/oracle/setup.sh && sudo bash setup.sh
   ```

3. It asks three questions. Paste the answer and press Enter each time:
   - **Web address:** `hse.<your-domain>`
   - **Administrator email:** your email (the one you put in Access)
   - **Tunnel token:** the command or `eyJ…` code from D3
4. Wait 10–20 minutes while it installs and builds. At the end it shows a box with your web
   address and a **Setup code** like `3fa9-0c1d-7be2`. Copy the setup code.
   If you close the window by mistake, connect again (step 1) and run `sudo bash setup.sh`
   again; it continues safely and shows the code again.
5. On your phone or laptop open **`https://hse.<your-domain>`**:
   - Cloudflare asks for your email → it sends a code → type the code.
   - The platform's **Set up this installation** page opens. Fill in the **Setup code**, your
     organisation name (English and Arabic), your first project, and your own name, email and a
     strong password (at least 12 characters). Tap **Create and sign in**.
   - You are signed in as **HSE Manager**. The platform asks you to set up **two-step
     verification** with an authenticator app on your phone (Microsoft Authenticator or Google
     Authenticator). You have 7 days; do it now and keep the recovery codes safe.

You are done. The platform restarts by itself after a server restart.

---

## G. Everyday use

### Add a person
1. **Cloudflare:** Zero Trust → Access → Applications → `HSE` → the `Allowed people` policy → add
   their email → Save.
2. **Platform:** sign in → **Users & roles** → **Invite user** → their email and role. They
   receive an email invitation (email sending must be set up, see below).

Remove a person the same way: delete them from the Access policy and deactivate them in the
platform.

### Email sending (needed for invitations and password resets)
Until this is set, emails wait in the platform and are not sent. You need an email account that
allows SMTP sending (your company's IT can give one, or e.g. a Gmail account with an "app
password"). In Cloud Shell, connected to the server:

```
sudo nano /opt/hse/.env
```

Fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (examples are in the
file). Save with **Ctrl+O**, Enter, and exit with **Ctrl+X**. Then apply:

```
sudo bash /opt/hse/deploy/oracle/update.sh
```

The same file holds the optional AI assistant key (`ANTHROPIC_API_KEY`) and licence key
(`LICENCE_KEY`; the licence can also be pasted on the platform's Licence page).

### Updates
In Cloud Shell, connected to the server:

```
sudo bash /opt/hse/deploy/oracle/update.sh
```

It makes a backup first, downloads the new version, updates the database and restarts. The site
is unavailable for a minute or two. Security updates of the operating system install by
themselves.

### Backups
- Made automatically every night at **02:30 Riyadh time**, kept for **14 days**, in
  `/var/backups/hse` on the server. Each backup holds the database, uploaded files and the
  settings with their encryption keys.
- Make one now: `sudo bash /opt/hse/deploy/oracle/backup.sh`
- See them / restore one (replaces all current data, after making a safety backup):

  ```
  sudo bash /opt/hse/deploy/oracle/restore.sh
  sudo bash /opt/hse/deploy/oracle/restore.sh /var/backups/hse/hse-backup-2026-11-07_023000.tar
  ```

These backups are on the same server. For a copy elsewhere, see **Extra** below.

### If the site does not open
1. **Cloudflare error page "tunnel" / 1033 / 502:** the server or the tunnel is down.
   - Oracle → Compute → Instances → `hse`: if it is **Stopped**, tap **Start**.
   - If it is running, connect in Cloud Shell and run:

     ```
     cd /opt/hse && sudo docker compose ps
     ```

     Every line should say `Up` (and `healthy`). If not: `sudo docker compose up -d`.
   - Still down: Oracle → instance → **Reboot**, wait 5 minutes.
2. **"Access denied" from Cloudflare:** that email is not in the Access policy (G, Add a person).
3. **Platform login fails:** use **Forgot your password?** on the sign-in page (needs email
   sending), or ask another HSE Manager.
4. For a technician, show the latest messages with
   `cd /opt/hse && sudo docker compose logs --tail 100` and copy them from the window.

### Costs to watch
- **Domain renewal** once a year (Cloudflare emails you; turn on auto-renew).
- **Oracle:** stay within Always Free: Ampere A1 up to 4 OCPUs and 24 GB in total, 200 GB of disk
  in total, 20 GB of Object Storage. The budget alert (A7) tells you if anything costs money.
  Do not create extra servers, load balancers or paid shapes.
- **Cloudflare Zero Trust:** free up to 50 users.
- **AI assistant** (optional): billed by Anthropic to the key's account.

---

## Extra: off-server copy of the backups (Oracle Object Storage, free up to 20 GB)

1. Oracle → Menu ☰ → **Storage** → **Buckets** → **Create Bucket** → name `hse-backups` → Create
   *(menu names may differ slightly)*.
2. Open the bucket → **Pre-Authenticated Requests** → **Create** → target **Bucket**, access
   **Permit object reads and writes**, expiry a few years ahead → Create. Copy the URL (it is
   shown once; it ends in `/o/`). Keep it secret: anyone with it can read the backups.
3. Optional: bucket → **Lifecycle Policy Rules** → delete objects older than 30 days, so the
   bucket stays under 20 GB.
4. In Cloud Shell, connected to the server: `sudo nano /opt/hse/.env`, paste the URL after
   `OCI_BACKUP_PAR_URL=`, save (Ctrl+O, Enter, Ctrl+X). From the next night each backup is also
   copied to the bucket. Test now with `sudo bash /opt/hse/deploy/oracle/backup.sh`.

To restore from the bucket on a new server: download the file from the bucket in the Oracle
website, upload it to Cloud Shell (Cloud Shell menu → **Upload**), copy it to the server with
`scp -i ~/.ssh/hse <file> ubuntu@<IP>:`, then run `restore.sh` with that file.

## Extra: notes for a technician

- Code: `/opt/hse` (git checkout). Settings and secrets: `/opt/hse/.env` (root only, generated by
  `setup.sh`; never commit it). Compose files: `docker-compose.yml` +
  `deploy/oracle/docker-compose.prod.yml`, selected by `COMPOSE_FILE` in `.env`, so
  `sudo docker compose …` in `/opt/hse` works directly.
- No container publishes a port. HTTPS ends at Cloudflare; `cloudflared` reaches
  `http://frontend:3000`, and Next.js proxies `/api/v1` to the backend. Cookies are `Secure`,
  `HttpOnly`, `SameSite=Lax`; the session IP comes from `CF-Connecting-IP`
  (`CLIENT_IP_HEADER`).
- Oracle's Ubuntu image already rejects all inbound traffic except SSH (iptables rules in
  `/etc/iptables/rules.v4`); `setup.sh` keeps them, or enables `ufw` with only SSH on other
  images. The Oracle VCN security list also allows only port 22 by default. To close SSH too,
  remove the port 22 ingress rule from the security list and open it only when needed.
- Virus scanning: `clamav/clamav-debian` (arm64). On a small server it can be switched off:
  `CLAMAV_HOST=` and remove `clamav` from `COMPOSE_PROFILES` in `.env`, then `update.sh` and
  `sudo docker compose rm -sf clamav`.
- `setup.sh --demo` loads the fake demo data instead of the first-time setup (trials only);
  `setup.sh --create-admin` creates the first administrator from the command line with a
  printed one-time password.
