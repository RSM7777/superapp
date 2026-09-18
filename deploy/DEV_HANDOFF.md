# Dev handoff: getting Nano running on Rohit's own VM

This is everything a developer needs to stand the app up on the Hostinger VM
and get it onto Rohit's phone. None of it waits for the consolidation work:
the container shape (one API process, one Postgres, Caddy in front) is the
same today and after every planned phase, so this can be done now and the
phases land inside it later.

What is NOT covered here, on purpose: writing any of the six build phases in
`docs/CONSOLIDATION.md`. That is separate work.

## 1. Things only Rohit can provide

| Item | Why | Where it goes |
|---|---|---|
| Hostinger VM login (SSH) | to install Docker and run the stack | you |
| A domain pointed at the VM's IP (A record) | Caddy needs a hostname to issue HTTPS; a free DuckDNS name works if he owns none | `SUPERAPP_DOMAIN` |
| Anthropic API key | the model. Currently EMPTY in his `.env`; nothing thinks without it | `SUPERAPP_ANTHROPIC_API_KEY` |
| Google OAuth client ID + secret | Google sign-in and Gmail. He has the client ID; the secret was never entered | `SUPERAPP_GOOGLE_CLIENT_ID`, `SUPERAPP_GOOGLE_CLIENT_SECRET` |
| Apple developer account | to build the iPhone app under his own team; previous builds were on Harshith's | Expo / TestFlight |
| (optional) Voyage API key | semantic memory search; without it search is keyword-only and says so | `SUPERAPP_VOYAGE_API_KEY` |

Do not put secrets in chat, tickets or commits. They go into `/opt/super-app/.env`
on the VM, by hand, and nowhere else.

## 2. On the VM (once)

```bash
# as root
apt-get update && apt-get install -y docker.io docker-compose-plugin git
mkdir -p /opt/super-app && cd /opt/super-app
git clone https://github.com/RSM7777/superapp.git .
git checkout consolidated
cp apps/api/.env.example .env      # then edit .env: fill the keys from section 1
```

In `.env`, set at minimum:

```
SUPERAPP_DOMAIN=<the domain from section 1>
SUPERAPP_DATABASE_URL=postgresql+psycopg2://superapp:<choose-a-password>@db:5432/superapp
SUPERAPP_API_TOKEN=<a long random string; the phone uses it>
SUPERAPP_VAULT_KEY=<a Fernet key: python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
SUPERAPP_ANTHROPIC_API_KEY=<from Rohit>
SUPERAPP_GOOGLE_CLIENT_ID=<from Rohit>
SUPERAPP_GOOGLE_CLIENT_SECRET=<from Rohit>
SUPERAPP_GOOGLE_REDIRECT_URI=https://<domain>/v1/gmail/callback
SUPERAPP_GOOGLE_SIGNIN_REDIRECT_URI=https://<domain>/v1/auth/google/callback
SUPERAPP_GMAIL_SCOPE_TIER=read        # read | send | modify. Start at read.
SUPERAPP_DEFAULT_TIMEZONE=America/Los_Angeles
```

Match the Postgres password in `deploy/docker-compose.prod.yml` (`POSTGRES_PASSWORD`).

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml logs -f api
```

The API container runs `alembic upgrade head` before it serves (see
`apps/api/docker-entrypoint.sh`). You should see the migration lines, then
"Application startup complete". Then from your laptop:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/docs     # expect 200
```

The `scout` service in the prod compose is the old research/browser worker.
It is optional and the plan removes it; leave it stopped
(`docker compose ... stop scout`) unless someone asks for flight watches.

## 3. In Google Cloud Console (once)

The OAuth client must list BOTH redirect URIs above, exactly, under
"Authorized redirect URIs". Until they match, Google sign-in and "connect
Gmail" return `redirect_uri_mismatch`.

Known catch: a Google OAuth app in **Testing** mode expires refresh tokens
every 7 days, so Gmail disconnects weekly and asks to sign in again. The app
already handles the re-sign-in. Publishing the app removes the limit but,
for Gmail scopes, triggers Google's verification review. Rohit decides which
he prefers; either works.

## 4. The phone

The app currently reads its server address from `apps/mobile/app.json`
(`extra.apiUrl`, pointing at the previous server). To use Rohit's VM:

1. Set `extra.apiUrl` to `https://<domain>` and `extra.apiToken` to the
   `SUPERAPP_API_TOKEN` from `.env`.
2. Build under Rohit's Apple team: `cd apps/mobile && npm install && npx expo run:ios`
   for the simulator, or an EAS/TestFlight build for his phone.

A small follow-up (already in the plan as part of phase 1) adds a
server-URL field to the sign-in screen so the address is typed once instead
of built in. Until then, changing servers means a rebuild.

## 5. What "working" looks like

- `https://<domain>/docs` loads.
- Sign in with Google on the phone succeeds (allowlisted to Rohit's address).
- "Connect Gmail" completes and the inbox screen fills within a minute.
- `docker compose logs api` shows no tracebacks after a sync.
- `docker exec -it <db container> pg_dump -U superapp superapp > /root/backup-$(date +%F).sql` works;
  put that in cron nightly until the scheduled backup job lands (plan row 41).

## 6. Not needed now

Plaid (banking), Telegram, WhatsApp, Gmail Pub/Sub push, Instacart, Voyage.
All optional; all off when their keys are empty; none block daily use.
