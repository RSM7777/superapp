"""The one place that turns an account row into a working mail client.

Before this existed, twelve call sites each did the same three things by
hand: build the vault key as an f-string, decrypt the token, and construct
GmailClient. Adding a second provider would have meant editing all twelve.
Now they call `client_for` or `send_via`.

The vault key is `{provider}:{email}`, which for the accounts that already
exist reproduces the exact string they were stored under, because `provider`
defaults to "gmail". No token is re-encrypted and nobody re-consents.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import GmailAccount, InboxMessage
from ..vault import get_token, store_token
from .base import MailClient, MailNotConnected
from .gmail_client import GmailClient
from .stub_client import StubMailClient

DEFAULT_PROVIDER = "gmail"


def provider_of(acct: GmailAccount) -> str:
    return (getattr(acct, "provider", "") or DEFAULT_PROVIDER).strip().lower()


def vault_key(acct: GmailAccount) -> str:
    """Where this mailbox's credential lives. Historic Gmail rows resolve to
    the same "gmail:{email}" they were written under."""
    return f"{provider_of(acct)}:{acct.email}"


def configured(provider: str = DEFAULT_PROVIDER) -> bool:
    """Is this provider set up on the server at all? Used to decide whether a
    provider may be offered for linking, never to decide whether a specific
    mailbox is real."""
    settings = get_settings()
    if provider == "stub":
        return True
    if provider == "gmail":
        return bool(settings.google_client_id)
    if provider == "outlook":
        return bool(getattr(settings, "microsoft_client_id", ""))
    return False


def link_client(provider: str = DEFAULT_PROVIDER) -> MailClient:
    """A credential-less client, for the OAuth dance only: building the
    consent URL and redeeming the code. It cannot read or send."""
    if provider == "stub":
        return StubMailClient()
    if provider == "gmail":
        return GmailClient()
    raise MailNotConnected(f"No mail provider named {provider!r} is configured.")


def client_for(db: Session, user_id: str, acct: GmailAccount) -> MailClient:
    """A client bound to one mailbox's stored credential.

    Raises MailNotConnected when there is no usable token. It never falls
    back to a stub: a mailbox that cannot send must fail, not pretend.
    """
    provider = provider_of(acct)
    if provider == "stub":
        return StubMailClient(address=acct.email)

    raw = get_token(db, user_id=user_id, provider=vault_key(acct))
    if not raw:
        raise MailNotConnected(
            f"{acct.email} isn't connected any more. Sign in again to reconnect it.")
    token = json.loads(raw)

    def _write_back(new_token: dict) -> None:
        # Some providers rotate the refresh token on every refresh and expect
        # the old one dropped. Persisting here keeps the mailbox alive.
        store_token(db, user_id=user_id, provider=vault_key(acct),
                    token=json.dumps(new_token))

    if provider == "gmail":
        return GmailClient(token, on_token_refresh=_write_back)
    raise MailNotConnected(f"{acct.email} uses an unsupported provider ({provider}).")


def account_for(db: Session, user_id: str, email: str) -> GmailAccount:
    """The mailbox an address belongs to. A message records only the address,
    and an address belongs to one provider in practice, but the table permits
    a duplicate across providers — so order, and never let the answer depend
    on row order."""
    acct = db.scalar(select(GmailAccount)
                     .where(GmailAccount.user_id == user_id, GmailAccount.email == email)
                     .order_by(GmailAccount.created_at, GmailAccount.id))
    if acct is None:
        raise MailNotConnected(f"{email} is not one of your connected mailboxes.")
    return acct


def client_for_message(db: Session, user_id: str, msg: InboxMessage) -> MailClient:
    """The client that owns a given message, i.e. the mailbox it arrived in."""
    return client_for(db, user_id, account_for(db, user_id, msg.account_email))


def send_via(db: Session, user_id: str, msg: InboxMessage, body: str,
             *, auto: bool = False) -> str:
    """Reply to `msg` from the mailbox it arrived in. Returns the sent id.

    Both identifiers travel because providers disagree about what a reply
    attaches to: Gmail threads on thread_id, Graph replies to a message id.
    """
    client = client_for_message(db, user_id, msg)
    return client.send_reply(to_addr=msg.from_addr, subject=msg.subject, body=body,
                             thread_id=msg.thread_id, external_id=msg.gmail_msg_id,
                             auto=auto)
