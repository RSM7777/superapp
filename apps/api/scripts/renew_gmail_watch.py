"""(Re)register push notifications for every connected mailbox.

Gmail's Pub/Sub watch expires after ~7 days; cron this daily. Also run once at
setup to start push delivery. Providers with no push configured are skipped.
"""
from superapp.db import SessionLocal
from superapp.inbox.base import MailNotConnected
from superapp.inbox.factory import client_for
from superapp.models import GmailAccount


def main() -> None:
    db = SessionLocal()
    for acct in db.query(GmailAccount).all():
        try:
            client = client_for(db, acct.user_id, acct)
        except MailNotConnected as exc:
            print(f"{acct.email}: {exc}")
            continue
        expiry, sub_id = client.subscribe()
        acct.watch_expiry = expiry
        if sub_id:
            acct.subscription_id = sub_id
        print(f"{acct.email} ({acct.provider}): watch until {expiry}")
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
