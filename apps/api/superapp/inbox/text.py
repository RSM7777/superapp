"""Mail is for reading. One cleaner, shared by every provider: flatten
HTML, drop tracking links and bracketed URL annotations, kill separator
art and whitespace canyons, and leave the words a person would actually
read in their mail app.
"""
import html as html_mod
import re as re_mod


_TAG_RE = re_mod.compile(r"<(script|style|head)[^>]*>.*?</\1>", re_mod.S | re_mod.I)


def clean_email_text(text: str) -> str:
    """Mail is for reading. Flatten HTML, drop tracking links and bracketed
    URL annotations, kill separator art and whitespace canyons — leave the
    words a person would actually read in their mail app."""
    t = text or ""
    if "<" in t and ">" in t:
        t = _TAG_RE.sub(" ", t)
        t = re_mod.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</h[1-6]>", "\n", t, flags=re_mod.I)
        t = re_mod.sub(r"<[^>]+>", " ", t)
        # Truncated bodies can end mid-tag; sweep tag-like leftovers too.
        t = re_mod.sub(r"<[a-zA-Z!/][^>]*>?", " ", t)
        t = html_mod.unescape(t)
    # Plain-text alternatives annotate links as "label [https://…]" and drag
    # in mile-long tracking URLs — none of it is reading material.
    t = re_mod.sub(r"[<\[(]\s*https?://[^\])>\s]+\s*[\])>]", "", t)
    t = re_mod.sub(r"https?://\S{25,}", "", t)
    t = re_mod.sub(r"\[[^\]\s]{25,}\]", "", t)
    t = re_mod.sub(r"^[\s>]*[-_=~*•—]{3,}[\s]*$", "", t, flags=re_mod.M)
    t = re_mod.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = re_mod.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
