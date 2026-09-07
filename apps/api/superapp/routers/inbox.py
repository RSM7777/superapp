"""Nano inbox endpoints (Phase 3).

Connect: /inbox/connect/stub for the offline mailbox; the OAuth pair
(/gmail/auth-url + /gmail/callback) for real Gmail. The Pub/Sub webhook is
Google-facing (secret path token, no bearer). Draft actions are the only way
mail ever leaves: send requires an explicit tap AND scope tier >= send.
"""
import base64
import hashlib
import hmac as hmac_mod
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents.base import render_screen, run_think
from ..auth import current_user_id
from ..config import get_settings
from ..db import get_db
from ..inbox.gmail_client import GmailClient
from ..models import InboxMessage
from ..substrate import append_event
from ..substrate.inbox import get_draft, upsert_account
from ..vault import store_token

router = APIRouter(prefix="/v1", tags=["inbox"])


def _connect(db: Session, *, user_id: str, email: str, token: dict,
             provider: str = "gmail") -> dict:
    from ..inbox.factory import client_for, vault_key
    acct = upsert_account(db, user_id=user_id, email=email, provider=provider)
    store_token(db, user_id=user_id, provider=vault_key(acct), token=json.dumps(token))
    try:  # push registration is a nicety; never block a link on it
        expiry, sub_id = client_for(db, user_id, acct).subscribe()
        if expiry:
            acct.watch_expiry = expiry
        if sub_id:
            acct.subscription_id = sub_id
    except Exception:  # noqa: BLE001
        pass
    append_event(db, user_id=user_id, type="gmail_connected", agent="inbox", domain="inbox",
                 payload={"email": email, "provider": provider})
    # Initial backfill + triage (the onboarding "scan" moment).
    run_think(db, agent="inbox", user_id=user_id, trigger={"kind": "email_sync", "reason": "backfill"})
    return render_screen(db, agent="inbox", user_id=user_id).model_dump()


@router.post("/inbox/connect/stub")
def connect_stub(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    from ..inbox.factory import configured
    if configured("gmail"):
        raise HTTPException(status_code=400, detail="Live Gmail configured; use /v1/gmail/auth-url")
    from ..inbox.stub_client import STUB_ADDRESS
    return _connect(db, user_id=user_id, email=STUB_ADDRESS, token={"stub": True},
                    provider="stub")


def _sign_state(user_id: str) -> str:
    key = get_settings().api_token.encode()
    sig = hmac_mod.new(key, user_id.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}.{sig}"


def _verify_state(state: str) -> str:
    user_id, _, sig = state.rpartition(".")
    if not user_id or not hmac_mod.compare_digest(_sign_state(user_id), state):
        raise HTTPException(status_code=403, detail="Bad OAuth state")
    return user_id


@router.get("/gmail/auth-url")
def gmail_auth_url(user_id: str = Depends(current_user_id)):
    from ..inbox.factory import configured, link_client
    if not configured("gmail"):
        raise HTTPException(status_code=400, detail="Set SUPERAPP_GOOGLE_CLIENT_ID first")
    return {"auth_url": link_client("gmail").auth_url(state=_sign_state(user_id))}


@router.get("/gmail/callback")
def gmail_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    """OAuth redirect target (browser; Google can't send our bearer). Identity
    comes from the HMAC-signed state we generated in auth-url."""
    user_id = _verify_state(state)
    from ..inbox.factory import link_client
    token = link_client("gmail").exchange_code(code)
    email = GmailClient(token).address()
    _connect(db, user_id=user_id, email=email, token=token)
    from ..agents.inbox import _heal_reauth
    _heal_reauth(db, user_id)
    db.commit()
    return HTMLResponse(f"""<!doctype html><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<body style='font-family:-apple-system,sans-serif;background:#08070E;color:#F4F2FA;
display:flex;flex-direction:column;align-items:center;justify-content:center;
height:100vh;margin:0;gap:12px'>
<div style='font-size:40px'>&#10003;</div>
<div style='font-size:20px'>{email} connected</div>
<div style='color:#8A87A3;font-size:14px'>Returning to Super App&hellip;</div>
<a href='superapp://gmail-connected' style='color:#C7B8FF'>Open the app</a>
<script>setTimeout(function() {{ location.href = 'superapp://gmail-connected'; }}, 600);</script>
</body>""")


@router.post("/inbox/sync")
def sync_now(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    return run_think(db, agent="inbox", user_id=user_id, trigger={"kind": "email_sync"})


@router.post("/gmail/webhook/{token}")
async def gmail_webhook(token: str, request: Request, background: BackgroundTasks,
                        db: Session = Depends(get_db)):
    """Pub/Sub push: mail triaged seconds after it arrives."""
    settings = get_settings()
    if token != settings.gmail_webhook_token:
        raise HTTPException(status_code=403, detail="Bad webhook token")
    payload = await request.json()  # {message: {data: b64 {emailAddress, historyId}}}
    email = None
    try:
        email = json.loads(base64.b64decode(payload["message"]["data"]))["emailAddress"]
    except (KeyError, TypeError, ValueError):
        pass
    from ..models import GmailAccount
    from sqlalchemy import select

    if email:
        accts = list(db.scalars(select(GmailAccount).where(GmailAccount.email == email)))
    else:  # undecodable envelope: sync every connected user rather than miss mail
        accts = list(db.scalars(select(GmailAccount)))
    # Ack Pub/Sub immediately; triage continues in the background (Google
    # retries un-acked pushes, which would double-trigger slow syncs).
    from ..routers.screen import _background_think

    for user in {a.user_id for a in accts}:
        background.add_task(_background_think, "inbox", user,
                            {"kind": "email_sync", "reason": "pubsub"})
    return {"ok": True}


class DraftEdit(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


@router.put("/inbox/drafts/{draft_id}")
def edit_draft(draft_id: str, body: DraftEdit, user_id: str = Depends(current_user_id),
               db: Session = Depends(get_db)):
    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    if draft.status == "sent":
        raise HTTPException(status_code=409, detail="Already sent")
    # The edit diff is the voice-learning signal (roadmap §Phase 3).
    append_event(db, user_id=user_id, type="draft_edited", agent="inbox", domain="inbox",
                 payload={"draft_id": draft.id, "before": draft.body[:2000], "after": body.body[:2000]})
    draft.body = body.body
    from ..models import utcnow as _utcnow
    draft.edited_at = _utcnow()
    if draft.status != "auto_pending":   # an edit inside the window keeps the window
        draft.status = "edited"
    else:
        from ..autosend import refresh_activity
        msg = db.get(InboxMessage, draft.message_id)
        if msg is not None:
            refresh_activity(db, draft, msg)   # the lock screen shows the new words
    db.commit()
    return {"ok": True}


@router.post("/inbox/drafts/{draft_id}/send")
def send_draft(draft_id: str, user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """The user's tap IS the approval. Gated by the trust ladder."""
    settings = get_settings()
    if settings.gmail_scope_tier not in ("send", "modify"):
        raise HTTPException(status_code=403,
                            detail="Sending is off (gmail_scope_tier=read). Climb the trust ladder first.")
    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    if draft.status == "sent":
        raise HTTPException(status_code=409, detail="Already sent")
    if draft.status == "auto_sending":
        raise HTTPException(status_code=409, detail="Already on its way")
    was_edited = draft.status == "edited" or draft.edited_at is not None
    was_auto = draft.status == "auto_pending"   # "Send now" inside the window
    if was_auto:
        # Exactly one sender wins the draft: the tap, the timer or a backstop.
        from ..autosend import claim
        if not claim(db, draft.id):
            raise HTTPException(status_code=409, detail="Already on its way")
        draft.status = "auto_sending"
    msg = db.get(InboxMessage, draft.message_id)
    from ..inbox.factory import send_via
    try:
        sent_id = send_via(db, user_id, msg, draft.body)
    except Exception:
        if was_auto:   # give it back as an ordinary ask rather than strand it
            draft.status = "waiting"
            draft.auto_send_at = None
            draft.claimed_at = None
            db.commit()
            from ..autosend import end_activity_held
            end_activity_held(db, user_id)
        raise
    from ..kernel import record_decision
    from ..models import utcnow
    draft.status = "sent"
    draft.sent_at = utcnow()
    draft.auto_send_at = None
    draft.claimed_at = None
    msg.settled = True
    if was_auto:
        db.commit()   # the send is real; make the status durable now
        from ..autosend import end_activity_sent
        end_activity_sent(db, user_id, msg.from_name)
    append_event(db, user_id=user_id, type="draft_sent", agent="inbox", domain="inbox",
                 payload={"draft_id": draft.id, "gmail_sent_id": sent_id, "edited": was_edited})
    from ..llm.provider import LLMProvider
    from ..people import update_person
    update_person(db, LLMProvider(), user_id, email=msg.from_addr,
                  name=msg.from_name, direction="user_wrote",
                  subject=msg.subject, body=draft.body[:4000])
    # The tap is a typed verdict: sent-as-written is the kernel's cleanest signal.
    record_decision(db, user_id=user_id, agent="inbox", action_key="inbox.send_reply",
                    decided_by="user", verdict="edited" if was_edited else "accepted",
                    payload={"draft_id": draft.id})
    from ..memory import remember
    remember(db, user_id=user_id, domain="inbox", kind="sent", ref_id=draft.id,
             content=f"Nano replied to {msg.from_name} ({msg.from_addr}) — "
                     f"{msg.subject}: {draft.body[:600]}")
    db.commit()
    return render_screen(db, agent="inbox", user_id=user_id).model_dump()


class DeferBody(BaseModel):
    # Minutes to ADD to local time to get UTC (JS getTimezoneOffset convention).
    tz_offset_minutes: int = 0


@router.post("/inbox/drafts/{draft_id}/now")
def undefer_draft(draft_id: str, user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """'Answer now' on a deferred card — bring the ask back immediately."""
    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    draft.defer_until = None
    append_event(db, user_id=user_id, type="draft_undeferred", agent="inbox", domain="inbox",
                 payload={"draft_id": draft.id})
    db.commit()
    return render_screen(db, agent="inbox", user_id=user_id).model_dump()


@router.post("/inbox/drafts/{draft_id}/manual")
def manual_draft(draft_id: str, user_id: str = Depends(current_user_id),
                 db: Session = Depends(get_db)):
    """'I'll send it myself': the auto-reply window closes and the draft
    becomes an ordinary ask waiting for the person's tap."""
    from ..autosend import cancel as _cancel_auto
    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    if draft.status == "sent":
        raise HTTPException(status_code=409, detail="Already sent")
    if draft.status == "auto_sending":
        raise HTTPException(status_code=409, detail="Already on its way")
    _cancel_auto(db, draft, reason="manual")
    db.commit()
    return render_screen(db, agent="inbox", user_id=user_id).model_dump()


@router.post("/inbox/drafts/{draft_id}/defer")
def defer_draft(draft_id: str, body: DeferBody | None = None,
                user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """'Ask me at 6pm' — hides the ask until 18:00 in the USER'S timezone."""
    from datetime import datetime, time, timedelta, timezone

    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    if draft.status == "auto_sending":
        raise HTTPException(status_code=409, detail="Already on its way")
    from ..autosend import cancel as _cancel_auto
    _cancel_auto(db, draft, reason="deferred")   # "later" is never "send itself"
    offset = timedelta(minutes=(body.tz_offset_minutes if body else 0))
    now_local = datetime.now(timezone.utc) - offset
    six_pm_local = datetime.combine(now_local.date(), time(18, 0))
    if six_pm_local <= now_local.replace(tzinfo=None):
        six_pm_local += timedelta(days=1)
    draft.defer_until = six_pm_local.replace(tzinfo=timezone.utc) + offset
    append_event(db, user_id=user_id, type="draft_deferred", agent="inbox", domain="inbox",
                 payload={"draft_id": draft.id})
    from ..kernel import record_decision
    record_decision(db, user_id=user_id, agent="inbox", action_key="inbox.send_reply",
                    decided_by="user", verdict="deferred", payload={"draft_id": draft.id})
    db.commit()
    return render_screen(db, agent="inbox", user_id=user_id).model_dump()


# ---- native inbox screen state (Nano V1 design) -----------------------------

_HANDLED_LABELS = {
    "promotion": ("Promotions and sales", "archived"),
    "newsletter": ("Newsletters", "filed under Reading"),
    "social": ("Social notifications", "filed"),
    "automated": ("Automated notices", "filed"),
    "receipt": ("Receipts", "filed"),
    "other": ("Other noise", "filed"),
}


@router.get("/inbox/state")
def inbox_state(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """Structured state for the native inbox screen: the three tiers of the
    V1 design — Needs you, Worth knowing (expandable), handled-without-you
    with a category breakdown — plus sent mail and the sync stamp."""
    from ..substrate.inbox import inbox_context

    # The app's own polls are a backstop for auto-reply windows that closed
    # while no timer was alive (a restart inside the window).
    try:
        from ..autosend import send_due
        send_due(db, user_id=user_id)
    except Exception:  # noqa: BLE001
        pass
    data = inbox_context(db, user_id)
    by_reason = dict(data.get("cleared_by_reason", {}))
    receipts = len(data.get("receipts", []))
    if receipts:
        by_reason["receipt"] = receipts
    categories = []
    for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        name, verb = _HANDLED_LABELS.get(reason or "other", _HANDLED_LABELS["other"])
        categories.append({"name": name, "n": f"{n} {verb}", "count": n})

    from sqlalchemy import select as _select

    from ..models import Event
    last_sync = db.scalar(_select(Event).where(
        Event.user_id == user_id, Event.type == "inbox_synced")
        .order_by(Event.created_at.desc()).limit(1))

    from ..models import UserFact
    flag = db.scalar(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain == "inbox",
        UserFact.key == "reauth_needed"))
    reauth = None
    if flag and (flag.value or {}).get("needed"):
        from ..inbox.factory import configured, link_client
        reauth = {"needed": True,
                  "email": (flag.value or {}).get("email", ""),
                  "auth_url": (link_client("gmail").auth_url(state=_sign_state(user_id))
                               if configured("gmail") else None)}

    ar_fact = _autoreply_fact(db, user_id)
    auto_kinds = list((ar_fact.value or {}).get("kinds", [])) if ar_fact else []
    auto_senders = list((ar_fact.value or {}).get("senders", [])) if ar_fact else []
    prio_kinds, prio_senders = _priority_fact_maps(db, user_id)

    return {
        "connected": data.get("connected", False),
        "mailboxes": data.get("mailboxes", []),
        "reauth": reauth,
        "auto_reply_kinds": auto_kinds,
        "auto_reply_senders": auto_senders,
        "priority_kinds": list(prio_kinds),
        "priority_senders": list(prio_senders),
        "synced_at": last_sync.created_at.isoformat() if last_sync else None,
        "needs_reply": data.get("needs_reply", []),
        "worth_knowing": data.get("worth_knowing", []),
        "handled_count": sum(c["count"] for c in categories),
        "handled_categories": categories,
        "sent": data.get("sent", []),
    }


@router.get("/people")
def list_people(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    from ..people import people_for_voice
    return {"people": people_for_voice(db, user_id, limit=25)}


@router.post("/inbox/backfill")
def backfill_inbox(background: BackgroundTasks,
                   user_id: str = Depends(current_user_id),
                   db: Session = Depends(get_db)):
    """Ingest ~40 recent Primary emails (first fill). Triage runs in the
    background; the screen catches up on the next refresh."""
    from ..routers.screen import _background_think
    background.add_task(_background_think, "inbox", user_id, {"kind": "backfill"})
    return {"ok": True}


@router.post("/inbox/drafts/{draft_id}/dismiss")
def dismiss_draft(draft_id: str, user_id: str = Depends(current_user_id),
                  db: Session = Depends(get_db)):
    """'Not this one': the draft leaves, the ask settles, the kernel learns."""
    draft = get_draft(db, user_id=user_id, draft_id=draft_id)
    if draft.status == "sent":
        raise HTTPException(status_code=409, detail="Already sent")
    if draft.status == "auto_sending":
        raise HTTPException(status_code=409, detail="Already on its way")
    from ..autosend import cancel as _cancel_auto
    _cancel_auto(db, draft, reason="dismissed")
    draft.status = "dismissed"
    msg = db.get(InboxMessage, draft.message_id)
    if msg is not None:
        msg.settled = True
    from ..kernel import record_decision
    record_decision(db, user_id=user_id, agent="inbox", action_key="inbox.send_reply",
                    decided_by="user", verdict="rejected",
                    payload={"draft_id": draft.id})
    append_event(db, user_id=user_id, type="draft_dismissed", agent="inbox",
                 domain="inbox", payload={"draft_id": draft.id})
    db.commit()
    return {"ok": True}


class AutoReplyBody(BaseModel):
    kind: str | None = Field(default=None, max_length=120)
    sender: str | None = Field(default=None, max_length=320)


def _as_map(v) -> dict:
    """Accept the legacy list form and the map form; return a name->true map."""
    if isinstance(v, dict):
        return dict(v)
    if isinstance(v, list):
        return {str(x): True for x in v}
    return {}


def _fit(value: dict, limit: int = 900) -> dict:
    """Keep a mutes/autoreply fact under the user_facts size cap, dropping the
    oldest entries first (dicts preserve insertion order)."""
    import json as _json
    while len(_json.dumps(value, default=str)) > limit:
        for field in ("senders", "kinds"):
            m = value.get(field)
            if isinstance(m, dict) and m:
                m.pop(next(iter(m)))
                break
        else:
            break
    return value


def set_auto_reply(db: Session, user_id: str, *, kind: str | None = None,
                   sender: str | None = None, on: bool = True) -> dict:
    """Turn auto-reply on/off for a KIND (a type of email) or a SENDER (a
    specific person). Stored as validator-safe name->true maps. The single
    place both the endpoint and the voice brain write this rule."""
    from ..substrate.facts import write_fact
    fact = _autoreply_fact(db, user_id)
    kinds = _as_map(fact.value.get("kinds")) if fact and fact.value else {}
    senders = _as_map(fact.value.get("senders")) if fact and fact.value else {}
    if kind:
        k = kind.strip()[:120]
        kinds = {x: v for x, v in kinds.items() if x.lower() != k.lower()}
        if on:
            kinds[k] = True
    if sender:
        a = sender.strip().lower()[:320]
        senders = {x: v for x, v in senders.items() if x.lower() != a}
        if on:
            senders[a] = True
    value = _fit({"kinds": kinds, "senders": senders})
    write_fact(db, user_id=user_id, domain="inbox", key="auto_reply_kinds",
               value=value, confidence=1.0, source_agent="inbox")
    return value


def send_matching_pending_drafts(db: Session, user_id: str, *,
                                 kind: str | None = None,
                                 sender: str | None = None) -> int:
    """Turning on auto-reply for a kind or sender also clears what's already
    waiting: send the pending drafts that match, right now. Same gates as the
    background auto-sender (scope tier, suspicious skip, exfiltration guard)."""
    settings = get_settings()
    if settings.gmail_scope_tier not in ("send", "modify"):
        return 0
    from sqlalchemy import select as _select

    from ..kernel import record_decision
    from ..llm.provider import LLMProvider
    from ..models import InboxDraft, InboxMessage, utcnow
    from ..people import update_person
    from ..policy import assess, draft_leaks_new_destination, has_placeholder
    from ..substrate.inbox import AUTO_REPLIES_PER_THREAD, replies_sent_in_thread

    kind_l = (kind or "").strip().lower()
    sender_l = (sender or "").strip().lower()
    if not kind_l and not sender_l:
        return 0
    sent = 0
    drafts = list(db.scalars(_select(InboxDraft).where(
        InboxDraft.user_id == user_id,
        InboxDraft.status.in_(("waiting", "edited")))))
    for d in drafts:
        msg = db.get(InboxMessage, d.message_id)
        if msg is None or msg.tier != "needs_reply" or msg.settled:
            continue
        nk = (getattr(msg, "note_kind", "") or "").lower()
        addr = (msg.from_addr or "").lower()
        if not ((kind_l and nk == kind_l) or (sender_l and addr == sender_l)):
            continue
        if getattr(msg, "suspicious", False):
            continue  # a steering email never auto-sends, even on an explicit rule
        if getattr(msg, "rule_promoted", False):
            continue  # a "never miss" rule surfaced it; the model saw no ask to answer
        if replies_sent_in_thread(db, user_id=user_id,
                                  thread_id=msg.thread_id) >= AUTO_REPLIES_PER_THREAD:
            continue  # the loop backstop: this thread has had its auto-replies today
        if not assess("inbox.auto_reply", provenance="user").allowed:
            continue
        if has_placeholder(d.body):
            continue  # a [time]-style blank is unfinished writing; the user fills it
        if draft_leaks_new_destination(d.body, msg.body_text or "",
                                       allowed=f"{msg.from_addr} {msg.account_email}"):
            continue
        from ..inbox.factory import send_via
        try:
            sent_id = send_via(db, user_id, msg, d.body, auto=True)
        except Exception:  # noqa: BLE001
            continue
        d.status = "sent"
        d.sent_at = utcnow()
        msg.tier = "worth_knowing"
        append_event(db, user_id=user_id, type="draft_sent", agent="inbox", domain="inbox",
                     payload={"draft_id": d.id, "gmail_sent_id": sent_id,
                              "auto": True, "kind": nk, "on_enable": True})
        update_person(db, LLMProvider(), user_id, email=msg.from_addr, name=msg.from_name,
                      direction="user_wrote", subject=msg.subject, body=d.body[:4000])
        record_decision(db, user_id=user_id, agent="inbox", action_key="inbox.auto_reply",
                        decided_by="user", verdict="accepted",
                        payload={"draft_id": d.id, "kind": nk})
        sent += 1
    return sent


def _autoreply_fact(db: Session, user_id: str):
    from sqlalchemy import select as _select

    from ..models import UserFact
    return db.scalar(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain == "inbox",
        UserFact.key == "auto_reply_kinds"))


@router.post("/inbox/autoreply")
def add_autoreply(body: AutoReplyBody, user_id: str = Depends(current_user_id),
                  db: Session = Depends(get_db)):
    """Delegate one stream: future mail of this kind gets its reply sent.
    Every auto-reply surfaces under Worth knowing — never silent."""
    if not body.kind and not body.sender:
        raise HTTPException(status_code=422, detail="kind or sender required")
    value = set_auto_reply(db, user_id, kind=body.kind, sender=body.sender)
    sent_now = send_matching_pending_drafts(db, user_id, kind=body.kind, sender=body.sender)
    append_event(db, user_id=user_id, type="autoreply_enabled", agent="inbox",
                 domain="inbox", payload={"kind": body.kind or "", "sender": body.sender or "",
                                          "sent_now": sent_now})
    db.commit()
    return {"ok": True, "kinds": list(value.get("kinds", {})),
            "senders": list(value.get("senders", {})), "sent_now": sent_now}


@router.delete("/inbox/autoreply")
def remove_autoreply(body: AutoReplyBody, user_id: str = Depends(current_user_id),
                     db: Session = Depends(get_db)):
    value = set_auto_reply(db, user_id, kind=body.kind, sender=body.sender, on=False)
    db.commit()
    return {"ok": True, "kinds": list(value.get("kinds", {})),
            "senders": list(value.get("senders", {}))}


class MuteBody(BaseModel):
    kind: str | None = Field(default=None, max_length=120)
    sender: str | None = Field(default=None, max_length=320)


@router.post("/inbox/mute")
def mute(body: MuteBody, user_id: str = Depends(current_user_id),
         db: Session = Depends(get_db)):
    """'Stop showing <kind>' / 'Never from <sender>' — a standing filter.
    Muted mail still syncs; it just files itself into handled."""
    if not body.kind and not body.sender:
        raise HTTPException(status_code=422, detail="kind or sender required")
    from sqlalchemy import select as _select

    from ..models import UserFact
    from ..substrate.facts import write_fact
    fact = db.scalar(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain == "inbox",
        UserFact.key == "mutes"))
    kinds = _as_map(fact.value.get("kinds")) if fact and fact.value else {}
    senders = _as_map(fact.value.get("senders")) if fact and fact.value else {}
    if body.kind:
        kinds[body.kind.strip()[:120]] = True
    if body.sender:
        senders[_clean_sender(body.sender)[:320]] = True
    value = _fit({"kinds": kinds, "senders": senders})
    write_fact(db, user_id=user_id, domain="inbox", key="mutes", value=value,
               confidence=1.0, source_agent="inbox")
    append_event(db, user_id=user_id, type="inbox_muted", agent="inbox", domain="inbox",
                 payload={"kind": body.kind or "", "sender": body.sender or ""})
    db.commit()
    return {"ok": True, "mutes": value}


class PriorityBody(BaseModel):
    kind: str | None = Field(default=None, max_length=120)
    sender: str | None = Field(default=None, max_length=320)


# A bare domain rule on one of these would promote every stranger who mails
# from that provider. A person there is named by their exact address.
_CONSUMER_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.co.in", "yahoo.co.uk", "yahoo.in", "ymail.com", "rocketmail.com",
    "hotmail.co.uk", "hotmail.co.in", "outlook.co.uk", "outlook.in", "live.co.uk", "live.in",
    "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "pm.me",
    "zoho.com", "zohomail.in", "gmx.com", "gmx.de", "mail.com", "rediffmail.com", "yandex.com",
}


def _clean_sender(raw: str) -> str:
    """'Sai <sai@x.com>' -> 'sai@x.com'; '@Amazon.com' -> 'amazon.com'."""
    from email.utils import parseaddr
    _, addr = parseaddr(raw or "")
    return (addr or raw or "").strip().lower().lstrip("@")


def _priority_fact_maps(db: Session, user_id: str) -> tuple[dict, dict]:
    from sqlalchemy import select as _select

    from ..models import UserFact
    fact = db.scalar(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain == "inbox",
        UserFact.key == "priority"))
    kinds = _as_map(fact.value.get("kinds")) if fact and fact.value else {}
    senders = _as_map(fact.value.get("senders")) if fact and fact.value else {}
    return kinds, senders


@router.post("/inbox/priority")
def priority(body: PriorityBody, user_id: str = Depends(current_user_id),
             db: Session = Depends(get_db)):
    """'Never let me miss X' — the opposite of mute. Anything matching goes
    to needs_reply at triage, with a reply drafted, however the model would
    otherwise have filed it. A sender here is treated as a whole domain by
    default, so one rule survives them changing which address they send from."""
    if not body.kind and not body.sender:
        raise HTTPException(status_code=422, detail="kind or sender required")
    from sqlalchemy import select as _select

    from ..models import UserFact
    from ..substrate.facts import write_fact
    fact = db.scalar(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain == "inbox",
        UserFact.key == "priority"))
    kinds = _as_map(fact.value.get("kinds")) if fact and fact.value else {}
    senders = _as_map(fact.value.get("senders")) if fact and fact.value else {}
    if body.kind:
        kinds[body.kind.strip()[:120]] = True
    if body.sender:
        addr = _clean_sender(body.sender)[:320]
        if "@" not in addr and addr in _CONSUMER_DOMAINS:
            raise HTTPException(
                status_code=422,
                detail=f"{addr} is a shared mail provider, so that rule would flag every "
                       "stranger on it. Give me the person's address instead.")
        senders[addr] = True
    before = len(kinds) + len(senders)
    value = _fit({"kinds": kinds, "senders": senders})
    if len(value["kinds"]) + len(value["senders"]) < before:
        # A standing promise must never be dropped silently to make room.
        raise HTTPException(status_code=409,
                            detail="That's as many standing rules as I can hold. Drop one first.")
    write_fact(db, user_id=user_id, domain="inbox", key="priority", value=value,
               confidence=1.0, source_agent="inbox")
    append_event(db, user_id=user_id, type="inbox_prioritised", agent="inbox", domain="inbox",
                 payload={"kind": body.kind or "", "sender": body.sender or ""})
    db.commit()
    return {"ok": True, "priority": value}


@router.delete("/inbox/priority")
def unpriority(body: PriorityBody, user_id: str = Depends(current_user_id),
               db: Session = Depends(get_db)):
    """Drop a 'never miss' rule. Mail from that sender or kind goes back to
    being filed on the model's judgement."""
    if not body.kind and not body.sender:
        raise HTTPException(status_code=422, detail="kind or sender required")
    from ..substrate.facts import write_fact
    kinds, senders = _priority_fact_maps(db, user_id)
    before = len(kinds) + len(senders)
    if body.kind:
        want = body.kind.strip().lower()
        kinds = {k: v for k, v in kinds.items() if k.lower() != want}
    if body.sender:
        want = _clean_sender(body.sender)
        senders = {k: v for k, v in senders.items() if k.lower().lstrip("@") != want}
    value = {"kinds": kinds, "senders": senders}
    if len(kinds) + len(senders) == before:
        return {"ok": True, "priority": value, "removed": False}  # nothing to drop
    write_fact(db, user_id=user_id, domain="inbox", key="priority", value=value,
               confidence=1.0, source_agent="inbox")
    append_event(db, user_id=user_id, type="inbox_unprioritised", agent="inbox", domain="inbox",
                 payload={"kind": body.kind or "", "sender": body.sender or ""})
    db.commit()
    return {"ok": True, "priority": value}


@router.post("/inbox/notes/{message_id}/settle")
def settle_note(message_id: str, user_id: str = Depends(current_user_id),
                db: Session = Depends(get_db)):
    """Swipe-away: one note leaves the list, nothing else changes."""
    m = db.get(InboxMessage, message_id)
    if m is None or m.user_id != user_id:
        raise HTTPException(status_code=404, detail="No such message")
    m.settled = True
    db.commit()
    return {"ok": True}


@router.post("/inbox/notes/clear")
def clear_notes(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """The Worth-knowing 'Clear' button: mark every note as seen/settled."""
    from sqlalchemy import select as _select
    n = 0
    for m in db.scalars(_select(InboxMessage).where(
            InboxMessage.user_id == user_id, InboxMessage.tier == "worth_knowing",
            InboxMessage.settled.is_(False))):
        m.settled = True
        n += 1
    append_event(db, user_id=user_id, type="notes_cleared", agent="inbox",
                 domain="inbox", payload={"count": n})
    db.commit()
    return {"cleared": n}


@router.get("/inbox/mailboxes")
def list_mailboxes(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """The connected mailboxes, for the profile page — link as many as you like."""
    from ..substrate.inbox import inbox_context
    data = inbox_context(db, user_id)
    return {"mailboxes": data.get("mailboxes", [])}


@router.get("/profile/knows")
def profile_knows(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """'What Nano knows' — the people it has learned, and what it knows about you."""
    from sqlalchemy import select as _select

    from ..models import Person, UserFact
    people = list(db.scalars(_select(Person).where(Person.user_id == user_id)
                             .order_by(Person.email_count.desc()).limit(40)))
    people_rows = [{
        "name": p.name or p.email, "email": p.email,
        "relationship": p.relationship or "", "summary": p.summary or "",
        "facts": p.facts or [],
    } for p in people]
    # Genuine learned beliefs — not plumbing, not the daily brief, not tokens.
    _DENY = {"morning_brief", "reflection_brief", "heartbeat_state", "mutes",
             "auto_reply_kinds", "reauth_needed", "expo_push_token",
             "apns_device_token", "liveactivity_start_token",
             "liveactivity_update_token"}
    facts = list(db.scalars(_select(UserFact).where(
        UserFact.user_id == user_id, UserFact.domain != "system")
        .order_by(UserFact.confidence.desc(), UserFact.learned_at.desc()).limit(80)))
    fact_rows = []
    for f in facts:
        if f.key in _DENY:
            continue
        keep = (f.domain in ("identity", "goals", "playbooks")
                or f.key.startswith("reflected_")
                or f.key in ("reply_style", "signature_name"))
        if not keep:
            continue
        v = f.value or {}
        if f.domain == "playbooks":
            text = (v.get("how") or v.get("when") or "").strip()
        else:
            text = (v.get("belief") or v.get("text") or v.get("notes")
                    or v.get("name") or "").strip()
        if not text and isinstance(v, dict):
            text = ", ".join(f"{k}: {vv}" for k, vv in list(v.items())[:2]
                             if isinstance(vv, (str, int, float)))
        if text:
            fact_rows.append({"domain": f.domain, "key": f.key,
                              "belief": str(text)[:200],
                              "learned_at": f.learned_at.isoformat()})
    fact_rows = fact_rows[:40]
    return {
        "facets": [{"name": "People", "n": len(people_rows)},
                   {"name": "About you", "n": len(fact_rows)}],
        "people": people_rows,
        "facts": fact_rows,
    }
