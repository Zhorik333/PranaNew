# MVP Release Checklist

Use this checklist before the first MVP release of PranaNew. Keep all real credentials only in the local or server `.env` file and never paste them into issues, chats, commits, logs, or screenshots.

## 1. Code and backlog readiness

- [ ] All P0 backlog tasks are completed and closed before MVP release.
- [ ] TASK-120 local setup documentation is up to date.
- [ ] TASK-122 systemd service example exists at `deploy/prananew-bot.service.example`.
- [ ] The release commit is on `master` and pushed to origin.
- [ ] Working tree is clean before deployment.

```bash
git status --short --branch
git pull --ff-only origin master
```

## 2. Database and migrations

- [ ] A fresh PostgreSQL database exists for the release environment.
- [ ] The release environment has a private `.env` with the production database connection string.
- [ ] Apply migrations to a clean PostgreSQL database and confirm they finish without errors.
- [ ] The database role used by the bot has only the permissions needed by the app.
- [ ] Keep a rollback or backup plan before accepting real bookings.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_init.sql
```

## 3. Local verification

- [ ] Python dependencies are installed in `.venv`.
- [ ] Compile check passes.
- [ ] Full unittest suite passes.
- [ ] No real secrets appear in README, docs, tests, commits, or logs.

```bash
.venv/bin/python -m compileall bot tests
.venv/bin/python -m unittest discover -s tests -v
```

## 4. Telegram smoke test

- [ ] Start one bot process only; do not run two polling instances with the same Telegram bot token.
- [ ] Bot starts without configuration errors.
- [ ] Bot answers `/start` in a private chat.
- [ ] The persistent client menu is visible after `/start`.
- [ ] `getWebhookInfo` has an empty webhook URL when polling is used.

```bash
.venv/bin/python -m bot.main
```

## 5. Admin smoke test

- [ ] Add the bot to the admin Telegram group.
- [ ] Send `/chatid` in the admin group and set the returned id in the private server `.env`.
- [ ] Restart the bot after updating `.env`.
- [ ] `/admin` opens the admin menu only in the configured admin chat.
- [ ] Admin can generate slots with `/generate DATE STEP START END [CAPACITY]`.
- [ ] Admin can view generated slots with `/admin_slots DATE`.
- [ ] Admin can block and unblock a test slot.
- [ ] Admin can change capacity for a test slot without going below occupied count.

## 6. Client booking smoke test

- [ ] Client can open available slots from the main menu.
- [ ] Client can book one or multiple consecutive slots.
- [ ] Pickup time equals the last selected slot.
- [ ] Double booking is rejected or returns the existing active booking idempotently.
- [ ] Client can cancel an active booking.
- [ ] Admin receives the new-booking notification.
- [ ] Admin receives the client-cancellation notification.
- [ ] Admin can mark a booking completed.
- [ ] Completed booking creates or schedules a review request.

## 7. Security and secrets

- [ ] `.env` is not tracked by git.
- [ ] Telegram bot token is stored only in private environment files.
- [ ] Production database credentials are stored only in private environment files.
- [ ] Admin chat id is treated as private operational data.
- [ ] Logs use structured redaction and do not print secrets.
- [ ] Public review output escapes user-controlled text.
- [ ] Admin reports escape user-controlled text.

```bash
git ls-files .env
git status --short --ignored
```

## 8. Deployment readiness

- [ ] Server path, Linux user, group, and `.env` location match the installed systemd unit.
- [ ] `deploy/prananew-bot.service.example` is copied or adapted to the server as `prananew-bot.service`.
- [ ] The server `.env` file permissions are restricted to the bot user or administrator.
- [ ] systemd can start and restart the bot.
- [ ] Service status is healthy after restart.
- [ ] Logs after restart contain startup events and no secret values.

```bash
systemctl status prananew-bot
journalctl -u prananew-bot -n 100 --no-pager
```

## 9. Release decision

- [ ] Language switching works for RU/EN/SR.
- [ ] Public reviews page opens and paginates safely.
- [ ] Rate limiting does not block normal client/admin flows.
- [ ] `/analytics YYYY-MM-DD` returns a daily admin report.
- [ ] Release owner confirms the smoke booking can be deleted or left as test history.
- [ ] Release owner gives explicit go/no-go.

Decision:

- Release version or commit:
- Release date:
- Release owner:
- Go/no-go:
- Notes:
