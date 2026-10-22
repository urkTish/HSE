# Licence keys: how to issue and renew them

Each install (one customer, one server) runs on a **licence key**. The key says who the customer
is, which plan they have, the last day of use and the limits. Keys are signed with your private
key. The app checks the signature with the public key that ships with it, so nobody can change a
key or make their own.

With **no key at all**, nothing is limited. That is how development, tests and demos run.

## One-time setup: make your signing key pair

Run this once on your own computer, from the `backend` folder:

```bash
uv run python -m app.licence_cli keygen
```

This writes two files:

- `~/.hse-licence/licence-private.pem`: your **private key**. Only you can read it. Back it up
  somewhere safe, such as a password manager or an encrypted USB stick. **Never commit it, e-mail
  it or copy it to a customer server.** If you lose it, you cannot issue new keys. If someone else
  gets it, they can make their own keys.
- `backend/app/data/licence_public_key.pem`: the **public key**. Commit this file. It ships with
  the app. Instead of committing it, you can set it on a server as `LICENCE_PUBLIC_KEY` (the PEM text).

Run `keygen` only once. Making a new pair later makes every key you have issued invalid. The
command refuses to overwrite an existing private key unless you add `--force`.

## Issue a key for a customer

```bash
# Free trial: 30 days from today, 1 project, 50 users, 10 GB, 100 AI questions a month
uv run python -m app.licence_cli issue --customer "ACME Airports" --bundle trial

# Paid plan: give the last day of use
uv run python -m app.licence_cli issue --customer "ACME Airports" --bundle professional --valid-until 2027-10-31
```

The command prints the terms, then the key (one long line starting with `HSE1.`). Send that line
to the customer.

Each plan has default limits, taken from the plans you set on 2026-10-21. You can change any of
them on the command line, for example `--max-projects 3`, `--max-users 120`,
`--max-storage-gb 100` or `--ai-questions-per-month 800`. Use `unlimited` to remove a limit.

| Plan | Projects | Users | Storage | AI questions / month |
|---|---|---|---|---|
| trial (30 days) | 1 | 50 | 10 GB | 100 |
| basic | 1 | no limit | 50 GB | 0 (no AI) |
| professional | 1 | no limit | 200 GB | 300 |
| enterprise | 1 | no limit | 500 GB | 1,000 |

Plans are priced per project, so for more projects set `--max-projects`. Add-ons are just bigger
numbers: +100 GB means `--max-storage-gb 150` on Basic, and +500 AI questions means
`--ai-questions-per-month 800` on Professional.

To check a key, for example one a customer sends back:

```bash
uv run python -m app.licence_cli show "HSE1...."
```

## Enter or renew a key on the customer's install

The HSE Manager signs in and opens **Licence** in the side menu. They paste the key and press
**Save key**. It takes effect at once, with no restart. A renewal works the same way, even after
the licence has ended.

For a new server, you can also put the key in the server settings (`LICENCE_KEY`, or
`LICENCE_FILE` with a path to a file holding the key). A key pasted on the Licence page always
wins over the server setting.

## What the customer sees

- **Trial:** a banner on every page says "Trial: N days left".
- **Paid plan:** the banner appears only in the last 30 days ("The licence ends in N days").
- **After the last day:** a red banner says "Licence expired, read-only". People can still sign
  in, view everything and export. Adding or changing records is refused with a clear message in
  English and Arabic. Some actions stay open because they are needed for safety or to renew: gate
  checks, musters and emergency events, the Licence page, sign-in and password reset.
- **Limits:** creating a project or user beyond the limit is refused with a clear message, and so
  is reopening a closed project or reactivating a user. AI questions stop for the month when the
  monthly number is used. They start again on the 1st, Riyadh time. File uploads stop when storage
  is full. From 80 % storage the HSE Manager sees a warning.
- The Licence page shows the plan, the last day and the usage of each limit.

## Trial terms (to state in the offer)

- The trial is free for 30 days. It includes the Basic features plus the AI assistant.
- Trial limits: 1 project, about 50 users, 10 GB storage and 100 AI questions.
- When the trial ends, the platform becomes **read-only** (view and export, no new records)
  until a plan is chosen.
- If the customer chooses a plan, all their data is kept. If not, their data is **deleted 30 days
  after the trial ends**, as required by the Saudi Personal Data Protection Law (PDPL). The
  Licence page shows that date.

The platform does **not** delete data by itself. When the date passes and the customer has not
converted, delete it yourself: remove the customer's server, or drop its database and its
`STORAGE_DIR` folder. Keep a short note of when you did it.
