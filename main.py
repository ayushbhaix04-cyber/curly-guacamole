#!/usr/bin/env python3
import logging
import random
import string
import json
import re
import time
import os
import asyncio
import html as html_lib
import unicodedata
import difflib
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    ChatJoinRequestHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest

# ================= CONFIG =================
# NEVER hard-code the token. Set it as an environment variable: BOT_TOKEN=xxxx
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable is not set.")

BOT_NAME = "ARJUN VOTE"
BOT_USERNAME = os.getenv("BOT_USERNAME", "arjunvotebot")   # change to your new bot's username
OWNER_ID = int(os.getenv("OWNER_ID", "8413435583"))

# ================= PREMIUM EMOJIS =================
EMOJI_VOTE = "5267095979097610740"
EMOJI_JOIN = "6237668294896131350"
EMOJI_CANCEL = "6240245571626475799"
EMOJI_MAIN_MENU = "6240245571626475799"
EMOJI_BACK = "6217402478825049695"
EMOJI_CREATE = "5208891329626521299"
EMOJI_CONNECT = "5244710862953941180"
EMOJI_MANAGE = "6237621548472081271"
EMOJI_ADD_VOTES = "6240003971126139705"
EMOJI_REMOVE_VOTES = "6240003971126139705"
EMOJI_LEADERBOARD = "6240027791014765668"
EMOJI_END_GIVEAWAY = "6240085923397114865"
EMOJI_ADMIN = "6237595159329113605"
EMOJI_BROADCAST = "6237668294896131350"
EMOJI_STATS = "6239790794719370356"
EMOJI_SETTINGS = "6237621548472081271"
EMOJI_USERS = "6237867138997034625"
EMOJI_BACKUP = "6237900592497302202"
EMOJI_CLEAR = "6240152061598504832"
EMOJI_CHANNEL = "6237510794150419802"
EMOJI_NOTIFICATION = "6240073270423462835"
EMOJI_CONFIRM = "6239815031219820750"
EMOJI_REFRESH = "6240085923397114865"
EMOJI_WELCOME = "6332080283176672910"
EMOJI_FIRE = "6334449730734529256"
EMOJI_ARROW = "6332591195306334733"
EMOJI_CHART = "6332186798365612896"
EMOJI_HEART = "6237558987978447573"
EMOJI_ROCKET = "5188481279963715781"
EMOJI_CROWN = "6332246180583447893"
EMOJI_ERROR = "6334723470475139278"
EMOJI_ENDED = "6237572882197650867"
EMOJI_STAR = "6239815031219820750"
EMOJI_ID = "6237547619200014867"
EMOJI_GIFT = "6239894475229895983"
EMOJI_WINE = "6237510794150419802"
EMOJI_SMILE = "6237867138997034625"
EMOJI_LOVE = "6334437167955188087"
EMOJI_LIGHTNING = "6240073270423462835"
EMOJI_POINTER = "6237732706520668707"
EMOJI_ALERT = "6240152061598504832"
EMOJI_CLOWN = "6237900592497302202"
EMOJI_SEARCH = "6239790794719370356"
EMOJI_SPEAKER = "5217968773071401144"
EMOJI_LINK = "5289511602393984968"
EMOJI_CONFETTI = "6240085923397114865"
EMOJI_LOCATION = "6240101054566897479"
EMOJI_RIGHT = "6240295371772271503"
EMOJI_DIAMOND = "6240003971126139705"
EMOJI_CALENDAR = "6240027791014765668"
EMOJI_WINNER = "6332435498446888848"
EMOJI_MONEY_BAG = "6332246180583447893"
EMOJI_CELEBRATE = "6237621707385871360"
EMOJI_INBOX = "6237973405077871246"
EMOJI_LOCK = "6332490478323243268"
EMOJI_SHIELD = "6237595159329113605"

# ================= COLOR STYLES =================
BUTTON_STYLE_PRIMARY = "primary"
BUTTON_STYLE_SUCCESS = "success"
BUTTON_STYLE_DANGER = "danger"

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def esc(text):
    """HTML-escape user supplied text (names, titles)."""
    return html_lib.escape(str(text if text is not None else ""))


# ================= JSON DATABASE =================
DATA_FILE = "bot_data.json"


def load_data():
    global giveaways, all_users, channel_history, required_channels, join_requests
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            giveaways = data.get("giveaways", {})
            all_users = data.get("all_users", {})
            channel_history = data.get("channel_history", {})
            required_channels = data.get("required_channels", [])
            # Pending join requests for mandatory channels: {chat_id(str): set(user_id)}
            join_requests = {
                str(k): set(int(x) for x in v)
                for k, v in data.get("join_requests", {}).items()
            }
            # Restore runtime-only sets and integer user IDs after JSON load.
            for _gid, _g in giveaways.items():
                _g["users"] = {int(k): v for k, v in _g.get("users", {}).items()}
                _g["vote_counts"] = {int(k): int(v) for k, v in _g.get("vote_counts", {}).items()}
                _g["voted_users"] = {int(k): set(v) for k, v in _g.get("voted_users", {}).items()}
                _g["vote_msgs"] = {int(k): v for k, v in _g.get("vote_msgs", {}).items()}
                # New fields (safe defaults for old data)
                _g["mode"] = _g.get("mode", "manual")
                _g["pending"] = {int(k): v for k, v in _g.get("pending", {}).items()}
                _g["rejected"] = [int(x) for x in _g.get("rejected", [])]
                _g["vote_log"] = _g.get("vote_log", [])
                _g["extra_channel"] = _g.get("extra_channel")
                _g["disqualified"] = [int(x) for x in _g.get("disqualified", [])]
            logger.info(f"Loaded: {len(giveaways)} giveaways, {len(all_users)} users, "
                        f"{len(required_channels)} required channels")
        else:
            giveaways = {}
            all_users = {}
            channel_history = {}
            required_channels = []
            join_requests = {}
    except Exception as e:
        logger.error(f"Error loading: {e}")
        giveaways = {}
        all_users = {}
        channel_history = {}
        required_channels = []
        join_requests = {}


def save_data():
    try:
        data = {
            "giveaways": giveaways,
            "all_users": all_users,
            "channel_history": channel_history,
            "required_channels": required_channels,
            "join_requests": join_requests,
            "last_saved": datetime.now().isoformat()
        }

        def json_safe(obj):
            if isinstance(obj, set):
                return list(obj)
            if isinstance(obj, dict):
                return {str(k): json_safe(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [json_safe(v) for v in obj]
            return obj

        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_safe(data), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving: {e}")


def save_user(user_id, username, first_name, last_name=None, source=None):
    if str(user_id) not in all_users:
        all_users[str(user_id)] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "source": source or "unknown",
            "total_votes_given": 0,
            "total_giveaways_joined": 0
        }
        save_data()
    else:
        all_users[str(user_id)]["last_active"] = datetime.now().isoformat()
        if username:
            all_users[str(user_id)]["username"] = username
        save_data()
    return True


def update_user_stats(user_id, action):
    user_id_str = str(user_id)
    if user_id_str in all_users:
        if action == "vote":
            all_users[user_id_str]["total_votes_given"] = all_users[user_id_str].get("total_votes_given", 0) + 1
        elif action == "join":
            all_users[user_id_str]["total_giveaways_joined"] = all_users[user_id_str].get("total_giveaways_joined", 0) + 1
        save_data()


def update_channel_history(channel_identifier, channel_display, channel_id, user_id, user_name, action, giveaway_id=None):
    channel_key = str(channel_identifier)

    if channel_key not in channel_history:
        channel_history[channel_key] = {
            "channel_identifier": channel_identifier,
            "channel_display": channel_display,
            "channel_id": channel_id,
            "type": "public" if str(channel_identifier).startswith('@') else "private",
            "total_giveaways": 0,
            "giveaways": [],
            "created_by": user_id,
            "created_by_name": user_name,
            "first_created": datetime.now().isoformat()
        }

    if action == "create":
        channel_history[channel_key]["total_giveaways"] += 1
        channel_history[channel_key]["giveaways"].append({
            "giveaway_id": giveaway_id,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "participants": 0
        })
        channel_history[channel_key]["last_giveaway"] = datetime.now().isoformat()
    elif action == "end" and giveaway_id:
        for g in channel_history[channel_key]["giveaways"]:
            if g.get("giveaway_id") == giveaway_id:
                g["status"] = "ended"
                g["ended_at"] = datetime.now().isoformat()
                break

    save_data()


# ================= INITIALIZE =================
giveaways = {}
all_users = {}
user_sessions = {}
admin_sessions = {}
channel_history = {}
required_channels = []   # mandatory join channels (owner managed)
join_requests = {}       # pending join requests for mandatory channels {chat_id(str): set(user_id)}

# ================= SECURITY / ANTI-ABUSE =================
SECURITY_ENABLED = True
AUTO_BAN_ON_ABUSE = True
PROFILE_ABUSE_CHECK_ENABLED = True
AUTO_BAN_ON_PROFILE_ABUSE = True

# Vote anti-abuse thresholds.
VOTE_WINDOW_SECONDS = 30
MAX_VOTES_IN_WINDOW = 8
MAX_TARGETS_IN_WINDOW = 6
SUSPICIOUS_SCORE_LIMIT = 3

# ---- Bad-word lists -------------------------------------------------------
# STRONG terms are blocked even when hidden INSIDE a longer word (xfuckerx, bitchass, drugdealer...)
STRONG_ABUSE = {
    "fuck", "bitch", "asshole", "bastard", "motherfucker", "madarchod", "madharchod",
    "behenchod", "bhenchod", "chutiya", "chutiye", "bhosdike", "bhosdi", "bhosdika",
    "bakchod", "nigger", "faggot"
}
STRONG_ADULT = {"pornhub", "pornstar", "onlyfans", "sexcam", "sexvideo", "xvideos", "xnxx"}
STRONG_DRUGS = {"drug", "cocaine", "marijuana", "methamphetamine", "fentanyl"}
STRONG_ILLEGAL = {"terrorist", "terrorism", "rapist", "pedophile", "paedophile", "murderer"}

# EXACT terms are blocked only as a whole word (so real names like "Brandi" stay safe)
EXACT_ABUSE = {
    "fucking", "fucker", "shit", "dick", "piss", "cunt", "whore", "slut", "idiot", "stupid",
    "gaand", "gand", "gandu", "bc", "mc", "randi", "harami", "kamina", "kamine", "kutte", "kutta",
    "bitches"
}
EXACT_ADULT = {
    "porn", "porno", "pornography", "xxx", "nsfw", "nude", "nudes", "sex", "sexting", "hentai",
    "escort", "callgirl", "prostitute"
}
EXACT_DRUGS = {"weed", "meth", "lsd", "mdma", "ganja", "charas", "afeem", "heroin", "cannabis", "drugs"}
EXACT_ILLEGAL = {"illegal", "scam", "scammer", "fraud", "rape", "pedo", "nazi", "hitler", "suicide",
                 "murder", "carding", "darkweb"}

# Kept for compatibility with older code
ABUSE_WORDS = STRONG_ABUSE | EXACT_ABUSE
ADULT_WORDS = STRONG_ADULT | EXACT_ADULT

_REASONS = {
    "abuse": "abusive/profane language",
    "adult": "18+ / adult content",
    "drugs": "drugs / illegal activity",
    "illegal": "illegal / harmful content",
}

banned_users = set()
suspicious_scores = defaultdict(int)
vote_activity = defaultdict(deque)


_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i",
    "ѕ": "s", "ј": "j", "ԁ": "d", "ɡ": "g", "ν": "v", "ο": "o", "α": "a", "ε": "e",
})
_LEET = {"@": "a", "4": "a", "3": "e", "!": "i", "|": "i", "0": "o", "$": "s", "5": "s", "7": "t", "8": "b"}


def _collapse(word):
    """fuuuuck -> fuck"""
    return re.sub(r"(.)\1+", r"\1", word)


def _build_lookup():
    exact, exact_c, strong = {}, {}, {}
    for terms, cat in ((EXACT_ABUSE, "abuse"), (EXACT_ADULT, "adult"),
                       (EXACT_DRUGS, "drugs"), (EXACT_ILLEGAL, "illegal")):
        for t in terms:
            exact[t] = cat
    for terms, cat in ((STRONG_ABUSE, "abuse"), (STRONG_ADULT, "adult"),
                       (STRONG_DRUGS, "drugs"), (STRONG_ILLEGAL, "illegal")):
        for t in terms:
            exact[t] = cat
            strong[t] = cat
    for t, cat in exact.items():
        ct = _collapse(t)
        if len(ct) >= 4:                 # avoid short collapsed words causing false positives
            exact_c[ct] = cat
    return exact, exact_c, strong


_EXACT_LOOKUP, _EXACT_LOOKUP_C, _STRONG_LOOKUP = _build_lookup()


def _clean_text(text):
    """Unicode tricks (fancy fonts, accents, zero-width chars, look-alike letters) -> plain lowercase."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff\u00ad]", "", text)
    return text.lower().translate(_HOMOGLYPHS)


def _tokens(text):
    """Words of the text. 'f u c k' / 'f.u.c.k' are merged back into 'fuck'."""
    raw = re.sub(r"[^a-z0-9]+", " ", text).split()
    merged, buf = [], ""
    for tok in raw:
        if len(tok) == 1:
            buf += tok
        else:
            if buf:
                merged.append(buf)
                buf = ""
            merged.append(tok)
    if buf:
        merged.append(buf)
    return merged


def normalize_security_text(text):
    """Kept for compatibility: plain normalized text."""
    t = _clean_text(text)
    for old, new in _LEET.items():
        t = t.replace(old, new)
    t = t.replace("1", "i")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _match_token(tok):
    """Returns the category of a bad word if this token is one, else None."""
    col = _collapse(tok)
    if tok in _EXACT_LOOKUP:
        return _EXACT_LOOKUP[tok]
    if col in _EXACT_LOOKUP:
        return _EXACT_LOOKUP[col]
    if col in _EXACT_LOOKUP_C:
        return _EXACT_LOOKUP_C[col]
    if len(tok) >= 4:
        for term, cat in _STRONG_LOOKUP.items():          # hidden inside a longer word
            if term in tok or term in col:
                return cat
    if len(tok) >= 6:
        for term, cat in _STRONG_LOOKUP.items():          # small spelling tricks (fuckr, bhosdika...)
            if len(term) >= 6 and abs(len(term) - len(tok)) <= 2:
                if difflib.SequenceMatcher(None, tok, term).ratio() >= 0.88:
                    return cat
    return None


def contains_banned_content(text):
    """Rule-based filter with leet-speak / unicode / spacing / repeated-letter / spelling-trick detection."""
    base = _clean_text(text)
    if not base.strip():
        return False, ""

    variants = [base]
    for one_as in ("i", "l"):
        t = base
        for old, new in _LEET.items():
            t = t.replace(old, new)
        variants.append(t.replace("1", one_as))
        variants.append(t.replace("1", one_as).replace("v", "u"))    # fvck -> fuck

    for variant in variants:
        for tok in _tokens(variant):
            cat = _match_token(tok)
            if cat:
                return True, _REASONS[cat]

    return False, ""


def check_profile_for_abuse(user):
    """Check username and display-name fields before allowing bot access."""
    if not PROFILE_ABUSE_CHECK_ENABLED or not user:
        return False, ""

    profile_fields = (
        ("username", user.username or ""),
        ("first name", user.first_name or ""),
        ("last name", user.last_name or ""),
    )

    for field_name, value in profile_fields:
        if value:
            found, _reason = contains_banned_content(value)
            if found:
                return True, f"{field_name} contains a banned word"

    return False, ""


def is_security_banned(user_id):
    return int(user_id) in banned_users


def security_ban_user(user_id, reason):
    uid = int(user_id)
    banned_users.add(uid)
    all_users.setdefault(str(uid), {})
    all_users[str(uid)]["security_banned"] = True
    all_users[str(uid)]["security_ban_reason"] = reason
    all_users[str(uid)]["security_banned_at"] = datetime.now().isoformat()
    save_data()
    # A banned account must also disappear from running giveaways
    try:
        asyncio.get_running_loop().create_task(purge_banned_user(uid))
    except RuntimeError:
        pass


def register_vote_activity(voter_id, target_id):
    now = time.monotonic()
    q = vote_activity[int(voter_id)]
    q.append((now, int(target_id)))
    while q and now - q[0][0] > VOTE_WINDOW_SECONDS:
        q.popleft()
    votes = len(q)
    targets = len({target for _, target in q})
    suspicious = votes > MAX_VOTES_IN_WINDOW or targets > MAX_TARGETS_IN_WINDOW
    return suspicious, votes, targets


def load_security_state():
    for uid, data in all_users.items():
        if data.get("security_banned"):
            banned_users.add(int(uid))


load_data()
load_security_state()

request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)


def premium_button(text, callback_data=None, url=None, emoji_id=None, style=None):
    if url:
        return InlineKeyboardButton(text=text, url=url, icon_custom_emoji_id=emoji_id, style=style)
    return InlineKeyboardButton(text=text, callback_data=callback_data, icon_custom_emoji_id=emoji_id, style=style)


BOT_REF = None   # set in main(); used for background clean-ups


async def disqualify_participant(bot, giveaway_id, user_id, notify=True):
    """Removes a participant from a giveaway (post deleted, votes cleared) and blocks re-joining."""
    g = giveaways.get(giveaway_id)
    if not g or user_id not in g.get("users", {}):
        return False

    g["users"].pop(user_id, None)
    g["vote_counts"].pop(user_id, None)
    g["voted_users"].pop(user_id, None)
    g.get("pending", {}).pop(user_id, None)
    msg_id = g.get("vote_msgs", {}).pop(user_id, None)
    g["vote_log"] = [e for e in g.get("vote_log", []) if e.get("target") != user_id]
    if user_id not in g.setdefault("disqualified", []):
        g["disqualified"].append(user_id)
    save_data()

    if msg_id:
        try:
            await bot.delete_message(chat_id=g["channel_id"], message_id=msg_id)
        except Exception as e:
            logger.warning(f"Could not delete participant post: {e}")

    if notify:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>DISQUALIFIED</b>\n\n"
                     f"You were disqualified from the giveaway of <b>{esc(g.get('channel_display'))}</b>.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    return True


async def purge_banned_user(user_id):
    """A banned user is removed from every active giveaway."""
    if BOT_REF is None:
        return
    for gid, g in list(giveaways.items()):
        if not g.get("ended") and user_id in g.get("users", {}):
            await disqualify_participant(BOT_REF, gid, user_id, notify=False)


def is_owner(user_id):
    return user_id == OWNER_ID


def is_manager(user_id, giveaway):
    """Creator of the giveaway or the bot owner."""
    return user_id == giveaway.get("creator") or is_owner(user_id)


async def send_notification_to_owner(context, title, message):
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"<b>{title}</b>\n\n{message}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send: {e}")


# ================= PARTICIPANT POST (2 BUTTONS) =================
def participant_markup(giveaway_id, user_id, votes):
    """Two buttons under every participant: [current votes] [vote now -> opens the bot]."""
    vote_link = f"https://t.me/{BOT_USERNAME}?start=v_{giveaway_id}_{user_id}"
    return InlineKeyboardMarkup([[
        premium_button(f"Votes: {votes}", callback_data=f"vinfo_{giveaway_id}_{user_id}",
                       emoji_id=EMOJI_CHART, style=BUTTON_STYLE_PRIMARY),
        premium_button("Vote Now", url=vote_link, emoji_id=EMOJI_VOTE, style=BUTTON_STYLE_SUCCESS)
    ]])


async def update_vote_button_in_channel(context, giveaway_id, user_id, new_votes):
    try:
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return False

        message_id = giveaway.get("vote_msgs", {}).get(user_id)
        if not message_id:
            return False
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=giveaway['channel_id'],
                message_id=message_id,
                reply_markup=participant_markup(giveaway_id, user_id, new_votes)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to edit: {e}")
            return False
    except Exception as e:
        logger.error(f"Error updating: {e}")
        return False


# ================= MEMBERSHIP / MANDATORY JOIN =================
def is_member_status(member):
    if member.status in ("member", "administrator", "creator"):
        return True
    if member.status == "restricted" and getattr(member, "is_member", False):
        return True
    return False


def has_pending_request(chat_id, user_id):
    """True if the user has sent a join request to this (mandatory) channel."""
    return int(user_id) in join_requests.get(str(chat_id), set())


async def check_membership(bot, chat_id, user_id):
    """True = member, False = not a member, None = could not check (bot problem)."""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return is_member_status(member)
    except Exception as e:
        logger.warning(f"Membership check failed for chat {chat_id}: {e}")
        return None


async def get_missing_channels(bot, user_id):
    """Mandatory channels the user has NOT joined. Owner is exempt.
    A pending join request (request-link channels) counts as joined.
    If the bot cannot check a channel (removed/not admin) it is skipped so nobody gets locked out."""
    if is_owner(user_id):
        return []
    missing = []
    for ch in required_channels:
        result = await check_membership(bot, ch["chat_id"], user_id)
        if result is False:
            if has_pending_request(ch["chat_id"], user_id):
                continue
            missing.append(ch)
    return missing


async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Records join requests sent to mandatory channels (request-to-join invite links)."""
    req = update.chat_join_request
    if not req:
        return
    chat_id = req.chat.id
    tracked_ids = {c["chat_id"] for c in required_channels}
    tracked_ids |= {(g.get("extra_channel") or {}).get("chat_id") for g in giveaways.values() if not g.get("ended")}
    if chat_id not in tracked_ids:
        return
    join_requests.setdefault(str(chat_id), set()).add(req.from_user.id)
    save_data()
    logger.info(f"Join request recorded: user {req.from_user.id} -> chat {chat_id}")


async def send_force_join_prompt(context, user_id, missing, payload=None, query=None):
    keyboard = []
    for ch in missing:
        keyboard.append([premium_button(f"JOIN {ch.get('title', 'CHANNEL')[:28]}", url=ch["link"],
                                        emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)])
    verify_cb = f"verify_fsub_{payload}" if payload else "verify_fsub"
    keyboard.append([premium_button("I'VE JOINED - VERIFY", callback_data=verify_cb,
                                    emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_PRIMARY)])

    names = "\n".join(f"• {esc(ch.get('title', 'Channel'))}" for ch in missing)
    text = (
        f"<tg-emoji emoji-id='{EMOJI_LOCK}'>🔒</tg-emoji> <b>JOIN OUR CHANNELS FIRST</b>\n\n"
        f"<i>You must join the channel(s) below to use {BOT_NAME} BOT:</i>\n\n"
        f"{names}\n\n"
        f"<b>1️⃣</b> Tap <b>JOIN</b> on each channel\n"
        f"<b>2️⃣</b> Tap <b>I'VE JOINED - VERIFY</b>\n\n"
        f"<i>⚠️ If you leave later, the votes you gave will be removed.</i>"
    )
    markup = InlineKeyboardMarkup(keyboard)

    if query is not None:
        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML", reply_markup=markup)


async def force_join_gate(update, context, payload=None):
    """For messages/commands. Returns True when the user is blocked."""
    user = update.effective_user
    if not user or is_owner(user.id) or not required_channels:
        return False
    missing = await get_missing_channels(context.bot, user.id)
    if not missing:
        return False
    await send_force_join_prompt(context, user.id, missing, payload)
    return True


async def force_join_gate_callback(update, context):
    """For button presses in private chat. Returns True when the user is blocked."""
    query = update.callback_query
    user = query.from_user
    if is_owner(user.id) or not required_channels:
        return False
    missing = await get_missing_channels(context.bot, user.id)
    if not missing:
        return False
    await query.answer()
    await send_force_join_prompt(context, user.id, missing, query=query)
    return True


async def verify_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    prefix = "verify_fsub_"
    payload = query.data[len(prefix):] if query.data.startswith(prefix) and len(query.data) > len(prefix) else None

    missing = await get_missing_channels(context.bot, user.id)
    if missing:
        await query.answer("❌ You still haven't joined all required channels!", show_alert=True)
        await send_force_join_prompt(context, user.id, missing, payload, query=query)
        return

    await query.answer("✅ Verified!")
    try:
        await query.message.delete()
    except Exception:
        pass

    if payload:
        await handle_payload(update, context, payload)
    else:
        await send_main_menu(context, user.id)


async def deduct_votes_of_voter(context, voter_id, only_channel_id=None):
    """Remove every vote this user has given (in active giveaways). Returns number removed."""
    removed = 0
    updates = []
    for gid, g in giveaways.items():
        if g.get("ended"):
            continue
        if (only_channel_id is not None and g.get("channel_id") != only_channel_id
                and (g.get("extra_channel") or {}).get("chat_id") != only_channel_id):
            continue
        for target, voters in g.get("voted_users", {}).items():
            if voter_id in voters:
                voters.discard(voter_id)
                g["vote_counts"][target] = max(0, g["vote_counts"].get(target, 0) - 1)
                g["vote_log"] = [e for e in g.get("vote_log", [])
                                 if not (e.get("voter") == voter_id and e.get("target") == target)]
                removed += 1
                updates.append((gid, target, g["vote_counts"][target]))

    if removed:
        save_data()
        for gid, target, new_votes in updates:
            await update_vote_button_in_channel(context, gid, target, new_votes)
            await asyncio.sleep(0.1)
    return removed


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When someone LEAVES a giveaway channel or a mandatory channel -> deduct the votes they gave."""
    cmu = update.chat_member
    if not cmu:
        return
    user = cmu.new_chat_member.user
    if user.is_bot:
        return

    was_in = is_member_status(cmu.old_chat_member)
    now_in = is_member_status(cmu.new_chat_member)
    if not (was_in and not now_in):
        return

    chat_id = cmu.chat.id
    required_ids = {c["chat_id"] for c in required_channels}
    extra_ids = {(g.get("extra_channel") or {}).get("chat_id") for g in giveaways.values() if not g.get("ended")}
    extra_ids.discard(None)

    if chat_id in required_ids:
        # Left a mandatory channel -> forget any stored join request too
        pending = join_requests.get(str(chat_id))
        if pending and user.id in pending:
            pending.discard(user.id)
            save_data()
        scope = None            # remove votes in ALL active giveaways
    elif chat_id in extra_ids:
        # Left a giveaway's extra force-join channel -> forget join request, remove votes there
        pending = join_requests.get(str(chat_id))
        if pending and user.id in pending:
            pending.discard(user.id)
            save_data()
        scope = chat_id
    elif any(g.get("channel_id") == chat_id and not g.get("ended") for g in giveaways.values()):
        scope = chat_id         # left a giveaway channel -> remove votes in that channel's giveaways
    else:
        return

    removed = await deduct_votes_of_voter(context, user.id, scope)
    if removed:
        logger.info(f"User {user.id} left chat {chat_id}: removed {removed} votes")
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>You left <i>{esc(cmu.chat.title or 'a channel')}</i></b>\n\n"
                     f"<b>{removed}</b> vote(s) you gave were removed. Rejoin and vote again if you wish.",
                parse_mode="HTML"
            )
        except Exception:
            pass


# ================= MAIN MENU HELPERS =================
def main_keyboard():
    return InlineKeyboardMarkup([
        [premium_button("CONNECT", url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages",
                        emoji_id=EMOJI_CONNECT, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("CREATE", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY),
         premium_button("MANAGE", callback_data="my_giveaways", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY)]
    ])


def welcome_text():
    return (
        f"<b><tg-emoji emoji-id='{EMOJI_WELCOME}'>🙂</tg-emoji> WELCOME TO {BOT_NAME} GIVEAWAY BOT</b>\n\n"
        f"<i><tg-emoji emoji-id='{EMOJI_FIRE}'>☄️</tg-emoji> Create Powerful Vote Giveaways</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_ARROW}'>🔜</tg-emoji> Real Time Vote System</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> Advanced Management Tools</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_HEART}'>❤️‍🔥</tg-emoji> Leaderboard & Analytics</i>\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_ROCKET}'>🚀</tg-emoji> START CREATING NOW!</b>"
    )


async def send_main_menu(context, chat_id):
    await context.bot.send_message(chat_id=chat_id, text=welcome_text(), parse_mode="HTML",
                                   reply_markup=main_keyboard())


# ================= START COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if SECURITY_ENABLED and user and user.id != OWNER_ID:
        if is_security_banned(user.id):
            await update.message.reply_text("🚫 You are banned from using this bot.")
            return

        profile_found, profile_reason = check_profile_for_abuse(user)
        if profile_found and AUTO_BAN_ON_PROFILE_ABUSE:
            security_ban_user(user.id, profile_reason)
            await send_notification_to_owner(
                context,
                "🚨 PROFILE SECURITY AUTO-BAN",
                f"👤 {esc(user.full_name or 'Unknown')}\n"
                f"🔹 Username: @{esc(user.username or 'N/A')}\n"
                f"🆔 <code>{user.id}</code>\n"
                f"⚠️ Reason: {profile_reason}"
            )
            await update.message.reply_text(
                "🚫 Your name/username contains a banned word. You have been banned."
            )
            return

    save_user(user.id, user.username, user.first_name, user.last_name, source="/start")

    payload = context.args[0] if context.args else None

    if payload:
        if payload.startswith("v_"):
            parts = payload.split("_")
            if len(parts) != 3 or parts[1] not in giveaways:
                payload = "INVALID"
        elif payload not in giveaways:
            payload = "INVALID"

    if payload == "INVALID":
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>INVALID LINK</b>",
            parse_mode="HTML"
        )
        return

    # Step 1: Mandatory channels gate
    if await force_join_gate(update, context, payload):
        return

    if payload:
        await handle_payload(update, context, payload)
        return

    await update.message.reply_text(text=welcome_text(), parse_mode="HTML", reply_markup=main_keyboard())


async def handle_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Routes a /start payload: 'v_<gid>_<uid>' = vote link, '<gid>' = giveaway join link."""
    if payload.startswith("v_"):
        parts = payload.split("_")
        try:
            await handle_vote_link(update, context, parts[1], int(parts[2]))
        except (IndexError, ValueError):
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>INVALID LINK</b>",
                parse_mode="HTML"
            )
    else:
        await handle_giveaway_link(update, context, payload)


async def get_giveaway_channel_link(context, giveaway):
    fallback = f"https://t.me/{BOT_USERNAME}?startchannel=true"
    identifier = str(giveaway.get("channel", ""))
    try:
        if identifier.startswith('@'):
            return f"https://t.me/{identifier[1:]}"
        chat = await context.bot.get_chat(giveaway.get("channel_id"))
        if chat.invite_link:
            return chat.invite_link
        if chat.username:
            return f"https://t.me/{chat.username}"
    except Exception:
        pass
    return fallback


# ================= VOTING (DEEP LINK FLOW) =================
async def cast_vote(context, user, giveaway_id, target_id):
    """Core voting logic. Returns (ok, html_text)."""
    g = giveaways.get(giveaway_id)
    if not g or g.get("ended"):
        return False, f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> <b>GIVEAWAY ENDED</b>"
    if target_id not in g["users"]:
        return False, f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Participant not found!</b>"
    if is_security_banned(user.id):
        return False, "🚫 You are banned from this bot."
    if user.id == target_id:
        return False, f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>You can't vote for yourself!</b>"

    voted = g["voted_users"].setdefault(target_id, set())
    if user.id in voted:
        return False, (f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>ALREADY VOTED!</b>\n\n"
                       f"You have already voted for <b>{esc(g['users'][target_id])}</b>.")

    suspicious, vote_count, target_count = register_vote_activity(user.id, target_id)
    if suspicious:
        suspicious_scores[user.id] += 1
        if suspicious_scores[user.id] >= SUSPICIOUS_SCORE_LIMIT:
            security_ban_user(user.id, "suspicious multi/fake voting activity")
            await send_notification_to_owner(
                context,
                "🚨 SECURITY AUTO-BAN",
                f"👤 {esc(user.full_name or 'Unknown')}\n🆔 <code>{user.id}</code>\n⚠️ Reason: suspicious voting ({vote_count} votes / {target_count} targets in {VOTE_WINDOW_SECONDS}s)"
            )
            return False, "🚫 Suspicious voting detected. You are banned."
        return False, "⚠️ Voting too quickly. Please slow down."

    voted.add(user.id)
    g["vote_counts"][target_id] = g["vote_counts"].get(target_id, 0) + 1
    new_votes = g["vote_counts"][target_id]
    g.setdefault("vote_log", []).append({
        "voter": user.id,
        "voter_name": user.full_name or user.first_name or str(user.id),
        "target": target_id,
        "time": datetime.now().isoformat()
    })
    save_data()
    update_user_stats(user.id, "vote")

    await update_vote_button_in_channel(context, giveaway_id, target_id, new_votes)

    return True, (
        f"<tg-emoji emoji-id='{EMOJI_CELEBRATE}'>🎉</tg-emoji> <b>VOTE RECORDED!</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>You voted for:</b> {esc(g['users'][target_id])}\n"
        f"<tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> <b>Current votes:</b> {new_votes}"
    )


async def get_extra_missing(context, giveaway, user_id):
    """Returns the giveaway's extra force-join channel if the user has NOT joined it, else None.
    A pending join request counts as joined. If the bot can't check, nobody is locked out."""
    extra = giveaway.get("extra_channel")
    if not extra or is_owner(user_id):
        return None
    result = await check_membership(context.bot, extra["chat_id"], user_id)
    if result is False and not has_pending_request(extra["chat_id"], user_id):
        return extra
    return None


def build_extra_required(giveaway_id, giveaway, extra, still=False):
    """Participant must join the creator's extra channel before joining the giveaway."""
    title = "STILL NOT JOINED" if still else "ONE MORE CHANNEL REQUIRED"
    keyboard = [
        [premium_button(f"JOIN {str(extra.get('title', 'CHANNEL'))[:28]}", url=extra["link"],
                        emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("TRY AGAIN", callback_data=f"retry_join_{giveaway_id}", emoji_id=EMOJI_REFRESH,
                        style=BUTTON_STYLE_PRIMARY)]
    ]
    text = (
        f"<tg-emoji emoji-id='{EMOJI_LOCK}'>🔒</tg-emoji> <b>{title}</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {esc(giveaway.get('channel_display', 'Channel'))}\n"
        f"<tg-emoji emoji-id='{EMOJI_CHANNEL}'>📢</tg-emoji> <b>Required channel:</b> {esc(extra.get('title', 'Channel'))}\n\n"
        f"<i>The giveaway creator requires you to join this channel too.</i>\n\n"
        f"<b>1️⃣</b> Click <b>JOIN</b> below\n"
        f"<b>2️⃣</b> Click <b>TRY AGAIN</b> to verify"
    )
    return text, InlineKeyboardMarkup(keyboard)


def build_vote_extra_prompt(giveaway_id, target_id, giveaway, extra):
    """Voter must join the creator's extra channel before voting."""
    target_name = esc(giveaway["users"].get(target_id, "Participant"))
    keyboard = [
        [premium_button(f"JOIN {str(extra.get('title', 'CHANNEL'))[:28]}", url=extra["link"],
                        emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("VERIFY & VOTE", callback_data=f"vchk_{giveaway_id}_{target_id}",
                        emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_PRIMARY)]
    ]
    text = (
        f"<tg-emoji emoji-id='{EMOJI_LOCK}'>🔒</tg-emoji> <b>ONE MORE CHANNEL REQUIRED TO VOTE</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_CHANNEL}'>📢</tg-emoji> <b>Required channel:</b> {esc(extra.get('title', 'Channel'))}\n"
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>You are voting for:</b> {target_name}\n\n"
        f"<b>1️⃣</b> Tap <b>JOIN</b>\n"
        f"<b>2️⃣</b> Tap <b>VERIFY & VOTE</b>"
    )
    return text, InlineKeyboardMarkup(keyboard)


def build_vote_join_prompt(giveaway_id, target_id, giveaway, link):
    channel_display = esc(giveaway.get("channel_display", giveaway.get("channel", "Channel")))
    target_name = esc(giveaway["users"].get(target_id, "Participant"))
    keyboard = [
        [premium_button("JOIN HOST CHANNEL", url=link, emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("VERIFY & VOTE", callback_data=f"vchk_{giveaway_id}_{target_id}",
                        emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_PRIMARY)]
    ]
    text = (
        f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>JOIN THE HOST CHANNEL TO VOTE</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {channel_display}\n"
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>You are voting for:</b> {target_name}\n\n"
        f"<b>1️⃣</b> Tap <b>JOIN HOST CHANNEL</b>\n"
        f"<b>2️⃣</b> Tap <b>VERIFY & VOTE</b>"
    )
    return text, InlineKeyboardMarkup(keyboard)


async def handle_vote_link(update: Update, context: ContextTypes.DEFAULT_TYPE, giveaway_id: str, target_id: int):
    """Step 2 (host channel) + Step 3 (vote) after mandatory channels were already checked."""
    user = update.effective_user
    g = giveaways.get(giveaway_id)

    if not g:
        await context.bot.send_message(chat_id=user.id,
                                       text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>INVALID LINK</b>",
                                       parse_mode="HTML")
        return
    if g.get("ended"):
        await context.bot.send_message(chat_id=user.id,
                                       text=f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> <b>GIVEAWAY ENDED</b>",
                                       parse_mode="HTML")
        return
    if target_id not in g["users"]:
        await context.bot.send_message(chat_id=user.id,
                                       text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Participant not found!</b>",
                                       parse_mode="HTML")
        return

    is_member = (await check_membership(context.bot, g.get("channel_id"), user.id)) is True
    if not is_member:
        link = await get_giveaway_channel_link(context, g)
        text, markup = build_vote_join_prompt(giveaway_id, target_id, g, link)
        await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML", reply_markup=markup)
        return

    extra_missing = await get_extra_missing(context, g, user.id)
    if extra_missing:
        text, markup = build_vote_extra_prompt(giveaway_id, target_id, g, extra_missing)
        await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML", reply_markup=markup)
        return

    ok, msg = await cast_vote(context, user, giveaway_id, target_id)
    await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="HTML")


async def verify_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'VERIFY & VOTE' button after joining the host channel."""
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")   # vchk, gid, target
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("❌ Invalid!", show_alert=True)
        return

    g = giveaways.get(giveaway_id)
    if not g or g.get("ended"):
        await query.answer("❌ Giveaway ended!", show_alert=True)
        return

    # Mandatory channels first (user may have left)
    missing = await get_missing_channels(context.bot, user.id)
    if missing:
        await query.answer()
        await send_force_join_prompt(context, user.id, missing, f"v_{giveaway_id}_{target_id}", query=query)
        return

    if (await check_membership(context.bot, g.get("channel_id"), user.id)) is not True:
        await query.answer("❌ You haven't joined the host channel yet!", show_alert=True)
        return

    extra_missing = await get_extra_missing(context, g, user.id)
    if extra_missing:
        await query.answer("❌ Please join the required channel first!", show_alert=True)
        text, markup = build_vote_extra_prompt(giveaway_id, target_id, g, extra_missing)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
        return

    await query.answer()
    ok, msg = await cast_vote(context, user, giveaway_id, target_id)
    try:
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception:
        await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="HTML")


async def vote_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'Votes: N' button in the channel - shows the current votes in a popup."""
    query = update.callback_query
    parts = query.data.split("_")   # vinfo, gid, uid
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
        g = giveaways[giveaway_id]
        votes = g["vote_counts"].get(target_id, 0)
        name = g["users"].get(target_id, "Participant")
        await query.answer(f"🗳 {name}\nCurrent votes: {votes}\n\nTap 'Vote Now' to vote!", show_alert=False)
    except Exception:
        await query.answer("Giveaway not found!", show_alert=True)


async def legacy_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Old-style vote buttons from previous posts."""
    await update.callback_query.answer("⚠️ Please use the 'Vote Now' button (opens the bot).", show_alert=True)


# ================= JOIN GIVEAWAY LINK =================
def build_join_giveaway(giveaway_id, giveaway, note):
    channel_display = esc(giveaway.get("channel_display", giveaway.get("channel", "Channel")))
    btn_label = "REQUEST TO JOIN" if giveaway.get("mode") == "approve" else "JOIN GIVEAWAY"
    keyboard = [[
        premium_button(btn_label, callback_data=f"join_{giveaway_id}", emoji_id=EMOJI_JOIN,
                       style=BUTTON_STYLE_SUCCESS)
    ]]
    text = (
        f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>EXCLUSIVE GIVEAWAY</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_WINE}'>🍷</tg-emoji> <b>Hosted By:</b> {channel_display}\n"
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Participants:</b> {len(giveaway['users'])}\n\n"
        f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> <b>{note}</b>"
    )
    return text, InlineKeyboardMarkup(keyboard)


def build_membership_required(giveaway_id, giveaway, link, still=False):
    channel_display = esc(giveaway.get("channel_display", giveaway.get("channel", "Channel")))
    title = "STILL NOT A MEMBER" if still else "CHANNEL MEMBERSHIP REQUIRED"
    keyboard = [
        [premium_button("JOIN CHANNEL", url=link, emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("TRY AGAIN", callback_data=f"retry_join_{giveaway_id}", emoji_id=EMOJI_REFRESH,
                        style=BUTTON_STYLE_PRIMARY)]
    ]
    text = (
        f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>{title}</b>\n\n"
        f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {channel_display}\n\n"
        f"<i>You need to join the channel first to participate in this giveaway!</i>\n\n"
        f"<b>Steps to join:</b>\n"
        f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
        f"2️⃣ Join the channel\n"
        f"3️⃣ Click <b>TRY AGAIN</b> to verify membership"
    )
    return text, InlineKeyboardMarkup(keyboard)


async def handle_giveaway_link(update: Update, context: ContextTypes.DEFAULT_TYPE, giveaway_id: str):
    user_id = update.effective_user.id

    if giveaway_id not in giveaways:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>INVALID LINK</b>",
            parse_mode="HTML"
        )
        return

    giveaway = giveaways[giveaway_id]

    if giveaway.get("ended", False):
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> <b>GIVEAWAY ENDED</b>",
            parse_mode="HTML"
        )
        return

    if user_id in giveaway.get("users", {}):
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_STAR}'>🌟</tg-emoji> <b>ALREADY PARTICIPATED!</b>\n\n"
                 f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> <b>Your ID:</b> <code>{user_id}</code>",
            parse_mode="HTML"
        )
        return

    if user_id in giveaway.get("pending", {}):
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⏳</tg-emoji> <b>REQUEST PENDING</b>\n\n"
                 f"<i>Your join request is waiting for the creator's approval.</i>",
            parse_mode="HTML"
        )
        return

    if user_id in giveaway.get("disqualified", []):
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>DISQUALIFIED</b>\n\n"
                 f"<i>You were disqualified from this giveaway.</i>",
            parse_mode="HTML"
        )
        return

    if user_id in giveaway.get("rejected", []):
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>REQUEST REJECTED</b>\n\n"
                 f"<i>The creator rejected your request for this giveaway.</i>",
            parse_mode="HTML"
        )
        return

    is_member = (await check_membership(context.bot, giveaway.get('channel_id'), user_id)) is True

    extra_missing = await get_extra_missing(context, giveaway, user_id) if is_member else None

    if is_member and extra_missing:
        text, markup = build_extra_required(giveaway_id, giveaway, extra_missing)
    elif is_member:
        text, markup = build_join_giveaway(giveaway_id, giveaway, "You are a member of the channel!")
    else:
        link = await get_giveaway_channel_link(context, giveaway)
        text, markup = build_membership_required(giveaway_id, giveaway, link)

    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML", reply_markup=markup)


async def retry_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle retry join callback - checks membership again"""
    query = update.callback_query
    await query.answer()

    giveaway_id = query.data.split("_")[2]
    user_id = query.from_user.id

    if giveaway_id not in giveaways:
        await query.edit_message_text(
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Giveaway not found!</b>",
            parse_mode="HTML"
        )
        return

    giveaway = giveaways[giveaway_id]
    is_member = (await check_membership(context.bot, giveaway.get('channel_id'), user_id)) is True

    extra_missing = await get_extra_missing(context, giveaway, user_id) if is_member else None

    if is_member and extra_missing:
        text, markup = build_extra_required(giveaway_id, giveaway, extra_missing, still=True)
    elif is_member:
        text, markup = build_join_giveaway(giveaway_id, giveaway, "Membership verified! You can now join.")
    else:
        link = await get_giveaway_channel_link(context, giveaway)
        text, markup = build_membership_required(giveaway_id, giveaway, link, still=True)

    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


# ================= CREATE GIVEAWAY =================
async def create_giveaway_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_sessions[user_id] = {"step": "waiting_channel"}
    keyboard = [[premium_button("CANCEL", callback_data="cancel_creation", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)]]
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> CREATE GIVEAWAY</b>\n\n"
             f"<i><tg-emoji emoji-id='{EMOJI_POINTER}'>👈</tg-emoji> Send your channel information:</i>\n\n"
             f"<b>Public:</b> <code>@username</code>\n<b>Private:</b> <code>-1001234567890</code>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]

    await query.edit_message_text(
        text="✅ <b>Cancelled!</b>",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


async def process_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_sessions or user_sessions[user_id].get("step") != "waiting_channel":
        return

    channel_input = update.message.text.strip()
    loading_msg = await update.message.reply_text(
        f"<tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> <b>Verifying...</b>",
        parse_mode="HTML"
    )

    try:
        if channel_input.startswith('@'):
            chat = await context.bot.get_chat(chat_id=channel_input)
            channel_info = {"identifier": channel_input, "display_name": channel_input, "chat_id": chat.id, "type": "public"}
        else:
            chat = await context.bot.get_chat(chat_id=int(channel_input))
            channel_info = {"identifier": str(channel_input), "display_name": chat.title or f"Channel {channel_input}",
                            "chat_id": chat.id, "type": "private"}
    except Exception as e:
        await loading_msg.delete()
        error = str(e).lower()
        if "bot is not a member" in error or "not enough rights" in error:
            await update.message.reply_text(
                f"🤖 <b>Bot is not admin!</b>\n\nPlease add @{BOT_USERNAME} as an admin in the channel first.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Invalid channel!</b>",
                parse_mode="HTML"
            )
        del user_sessions[user_id]
        return

    for gid, gdata in giveaways.items():
        if gdata.get("channel") == channel_info["identifier"] and not gdata.get("ended", False):
            await loading_msg.delete()
            existing_link = f"https://t.me/{BOT_USERNAME}?start={gid}"
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> <b>GIVEAWAY ALREADY ACTIVE!</b>\n\n"
                f"<b>Channel:</b> {esc(channel_info['display_name'])}\n\n"
                f"<b>Active Link:</b>\n<code>{existing_link}</code>",
                parse_mode="HTML"
            )
            del user_sessions[user_id]
            return

    try:
        test_msg = await context.bot.send_message(chat_id=channel_info["chat_id"], text="✅ Bot connected!")
        await test_msg.delete()
    except Exception:
        await loading_msg.delete()
        await update.message.reply_text(
            f"🤖 <b>Bot is not admin!</b>\n\nPlease add @{BOT_USERNAME} as an admin in the channel first.",
            parse_mode="HTML"
        )
        del user_sessions[user_id]
        return

    await loading_msg.delete()

    # Channel is OK -> ask for the giveaway mode (manual / approve)
    user_sessions[user_id] = {"step": "choose_mode", "channel_info": channel_info}
    keyboard = InlineKeyboardMarkup([
        [premium_button("MANUAL", callback_data="gmode_manual", emoji_id=EMOJI_JOIN, style=BUTTON_STYLE_PRIMARY),
         premium_button("APPROVE", callback_data="gmode_approve", emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("CANCEL", callback_data="cancel_creation", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)]
    ])
    await update.message.reply_text(
        f"<b><tg-emoji emoji-id='{EMOJI_SETTINGS}'>⚙️</tg-emoji> CHOOSE GIVEAWAY MODE</b>\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SPEAKER}'>📢</tg-emoji> Channel:</b> {esc(channel_info['display_name'])}\n\n"
        f"<b>MANUAL</b> - users join instantly when they tap JOIN.\n"
        f"<b>APPROVE</b> - every join request comes to you; you <b>approve or reject</b> each user.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


def extra_channel_keyboard():
    return InlineKeyboardMarkup([
        [premium_button("SKIP", callback_data="gextra_skip", emoji_id=EMOJI_RIGHT, style=BUTTON_STYLE_PRIMARY)],
        [premium_button("CANCEL", callback_data="cancel_creation", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)]
    ])


EXTRA_CHANNEL_PROMPT = (
    f"<b><tg-emoji emoji-id='{EMOJI_LOCK}'>🔒</tg-emoji> FORCE JOIN CHANNEL (OPTIONAL)</b>\n\n"
    f"<i>Add <b>1 extra channel</b> that participants and voters must join before they can "
    f"participate or vote in this giveaway.</i>\n\n"
    f"<b>Public:</b> <code>@username</code>\n"
    f"<b>Private:</b> <code>-1001234567890</code>\n"
    f"<b>Private + invite link:</b> <code>-1001234567890 https://t.me/+AbCdEf</code>\n\n"
    f"<i>The bot must be an admin in that channel. Or tap SKIP.</i>"
)


async def choose_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked MANUAL or APPROVE -> ask for the optional extra force-join channel."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mode = "approve" if query.data == "gmode_approve" else "manual"

    session = user_sessions.get(user_id)
    if not session or session.get("step") != "choose_mode":
        await query.edit_message_text("❌ Session expired. Please start again.", parse_mode="HTML",
                                      reply_markup=main_keyboard())
        return

    session["step"] = "waiting_extra_channel"
    session["mode"] = mode
    await query.edit_message_text(EXTRA_CHANNEL_PROMPT, parse_mode="HTML", reply_markup=extra_channel_keyboard())


async def skip_extra_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SKIP pressed -> create the giveaway without an extra channel."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = user_sessions.get(user_id)
    if not session or session.get("step") != "waiting_extra_channel":
        await query.edit_message_text("❌ Session expired. Please start again.", parse_mode="HTML",
                                      reply_markup=main_keyboard())
        return

    del user_sessions[user_id]
    text, markup = await finalize_giveaway(context, user_id, query.from_user.first_name,
                                           session["channel_info"], session["mode"], None)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def process_extra_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creator sent the extra force-join channel -> validate it and create the giveaway."""
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session or session.get("step") != "waiting_extra_channel":
        return

    parts = update.message.text.strip().split()
    if not parts:
        return
    ident = parts[0]
    custom_link = parts[1] if len(parts) > 1 else None

    try:
        chat = await context.bot.get_chat(ident if ident.startswith('@') else int(ident))
    except Exception:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Invalid channel!</b>\n\n"
            f"<i>Send it again, or tap SKIP.</i>",
            parse_mode="HTML", reply_markup=extra_channel_keyboard())
        return

    try:
        me = await context.bot.get_chat_member(chat.id, context.bot.id)
        if me.status not in ("administrator", "creator"):
            raise ValueError("not admin")
    except Exception:
        await update.message.reply_text(
            f"🤖 <b>Bot is not admin!</b>\n\nMake @{BOT_USERNAME} an admin in that channel, then send it again (or tap SKIP).",
            parse_mode="HTML", reply_markup=extra_channel_keyboard())
        return

    if chat.id == session["channel_info"]["chat_id"]:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>This is already your giveaway channel!</b>\n\n"
            f"<i>Send a different channel, or tap SKIP.</i>",
            parse_mode="HTML", reply_markup=extra_channel_keyboard())
        return

    link = custom_link
    if not link:
        if chat.username:
            link = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            link = chat.invite_link
        else:
            try:
                link = await context.bot.export_chat_invite_link(chat.id)
            except Exception:
                link = None
    if not link:
        await update.message.reply_text(
            "❌ Could not create an invite link. Send: <code>-100id https://t.me/+invitelink</code>",
            parse_mode="HTML", reply_markup=extra_channel_keyboard())
        return

    extra = {
        "chat_id": chat.id,
        "identifier": ident,
        "title": chat.title or ident,
        "link": link
    }

    del user_sessions[user_id]
    text, markup = await finalize_giveaway(context, user_id, update.effective_user.first_name,
                                           session["channel_info"], session["mode"], extra)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def finalize_giveaway(context, user_id, user_name, channel_info, mode, extra):
    """Creates the giveaway. Returns (success_text, markup)."""
    giveaway_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    link = f"https://t.me/{BOT_USERNAME}?start={giveaway_id}"

    giveaways[giveaway_id] = {
        "channel": channel_info["identifier"], "channel_display": channel_info["display_name"],
        "channel_id": channel_info["chat_id"], "users": {}, "vote_counts": {}, "voted_users": {}, "vote_msgs": {},
        "mode": mode, "pending": {}, "rejected": [], "disqualified": [], "vote_log": [], "extra_channel": extra,
        "creator": user_id, "creator_name": user_name, "ended": False, "created_at": datetime.now().isoformat()
    }

    update_channel_history(
        channel_identifier=channel_info["identifier"],
        channel_display=channel_info["display_name"],
        channel_id=channel_info["chat_id"],
        user_id=user_id,
        user_name=user_name,
        action="create",
        giveaway_id=giveaway_id
    )

    save_data()

    extra_title = extra["title"] if extra else "None"

    if user_id != OWNER_ID:
        await send_notification_to_owner(context, "🔔 NEW GIVEAWAY CREATED!",
                                         f"👤 {esc(user_name)}\n🆔 <code>{user_id}</code>\n📢 {esc(channel_info['display_name'])}\n"
                                         f"⚙️ Mode: {mode.upper()}\n🔒 Force join: {esc(extra_title)}\n🔗 <code>{link}</code>")

    try:
        await context.bot.send_message(
            chat_id=channel_info["chat_id"],
            text=f"<b><tg-emoji emoji-id='{EMOJI_CONFETTI}'>🎉</tg-emoji> NEW GIVEAWAY STARTED!</b>\n\n"
                 f"<b><tg-emoji emoji-id='{EMOJI_RIGHT}'>➡️</tg-emoji> JOIN HERE:</b>\n{link}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        pass

    success_text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CLOWN}'>✅</tg-emoji> GIVEAWAY CREATED!</b>\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SEARCH}'>🔍</tg-emoji> ID:</b> <code>{giveaway_id}</code>\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SPEAKER}'>📢</tg-emoji> Channel:</b> {esc(channel_info['display_name'])}\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SETTINGS}'>⚙️</tg-emoji> Mode:</b> {mode.upper()}\n"
        f"<b><tg-emoji emoji-id='{EMOJI_LOCK}'>🔒</tg-emoji> Force Join:</b> {esc(extra_title)}\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_LINK}'>🔗</tg-emoji> LINK:</b>\n<code>{link}</code>"
    )

    keyboard = [[
        premium_button("MANAGE", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY),
        premium_button("MAIN MENU", callback_data="main_menu", emoji_id=EMOJI_MAIN_MENU, style=BUTTON_STYLE_PRIMARY)
    ]]

    return success_text, InlineKeyboardMarkup(keyboard)


# ================= MANAGE =================
async def my_giveaways(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    text = f"<b><tg-emoji emoji-id='{EMOJI_CROWN}'>💰</tg-emoji> YOUR GIVEAWAYS</b>\n\n"
    keyboard = []
    found = False

    for gid, gdata in giveaways.items():
        if gdata.get("creator") == user_id and not gdata.get("ended", False):
            found = True
            keyboard.append([premium_button(
                text=f"📢 {gdata.get('channel_display', gdata.get('channel'))}",
                callback_data=f"manage_{gid}",
                emoji_id=EMOJI_MANAGE,
                style=BUTTON_STYLE_PRIMARY
            )])

    if not found:
        text = f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>No active giveaways!</b>"
        keyboard.append([premium_button("CREATE NEW", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY)])

    keyboard.append([premium_button("MAIN MENU", callback_data="main_menu", emoji_id=EMOJI_MAIN_MENU, style=BUTTON_STYLE_PRIMARY)])

    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


def manage_keyboard(giveaway_id, with_back=True):
    keyboard = [
        [
            premium_button("ADD VOTES", callback_data=f"addvotes_{giveaway_id}", emoji_id=EMOJI_ADD_VOTES, style=BUTTON_STYLE_PRIMARY),
            premium_button("REMOVE VOTES", callback_data=f"removevotes_{giveaway_id}", emoji_id=EMOJI_REMOVE_VOTES, style=BUTTON_STYLE_DANGER)
        ],
        [
            premium_button("LEADERBOARD", callback_data=f"leaderboard_{giveaway_id}", emoji_id=EMOJI_LEADERBOARD, style=BUTTON_STYLE_PRIMARY),
            premium_button("REAL VOTES", callback_data=f"realvotes_{giveaway_id}", emoji_id=EMOJI_SEARCH, style=BUTTON_STYLE_PRIMARY)
        ],
        [
            premium_button("PARTICIPANTS", callback_data=f"plist_{giveaway_id}_0", emoji_id=EMOJI_USERS, style=BUTTON_STYLE_PRIMARY)
        ],
        [
            premium_button("END GIVEAWAY", callback_data=f"endgiveaway_{giveaway_id}", emoji_id=EMOJI_END_GIVEAWAY, style=BUTTON_STYLE_DANGER)
        ]
    ]
    if with_back:
        keyboard.append([premium_button("BACK", callback_data="my_giveaways", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)])
    return InlineKeyboardMarkup(keyboard)


async def manage_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    giveaway_id = query.data.split("_")[1]
    if giveaway_id not in giveaways:
        await query.edit_message_text(f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> Not found!", parse_mode="HTML")
        return

    giveaway = giveaways[giveaway_id]
    status = "🟢 ACTIVE" if not giveaway.get("ended") else "🔴 ENDED"

    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_ARROW}'>➡️</tg-emoji> MANAGEMENT PANEL</b>\n\n"
             f"<b>Status:</b> {status}\n"
             f"<b>Mode:</b> {giveaway.get('mode', 'manual').upper()}\n"
             f"<b>Force Join:</b> {esc((giveaway.get('extra_channel') or {}).get('title', 'None'))}\n"
             f"<b>Channel:</b> {esc(giveaway.get('channel_display', giveaway.get('channel')))}\n"
             f"<b>Joined:</b> {len(giveaway.get('users', {}))}\n"
             f"<b>Pending requests:</b> {len(giveaway.get('pending', {}))}",
        parse_mode="HTML",
        reply_markup=manage_keyboard(giveaway_id)
    )


# ================= REAL VOTES (WHO VOTED + TIME) =================
IST = timezone(timedelta(hours=5, minutes=30))   # Indian Standard Time
REAL_VOTES_PER_PAGE = 15                          # participants / voters shown per page


def fmt_time(iso_str):
    """Saved server time -> Indian time (IST)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.astimezone()          # naive = server local time
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M:%S %p") + " IST"
    except Exception:
        return str(iso_str)


def nav_row(prefix, page, total_pages):
    """Prev / Next buttons. prefix example: 'realvotes_<gid>' or 'rvuser_<gid>_<uid>'."""
    row = []
    if page > 0:
        row.append(premium_button("PREV", callback_data=f"{prefix}_{page - 1}",
                                  emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY))
    if page < total_pages - 1:
        row.append(premium_button("NEXT", callback_data=f"{prefix}_{page + 1}",
                                  emoji_id=EMOJI_RIGHT, style=BUTTON_STYLE_PRIMARY))
    return row


async def real_votes_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage -> REAL VOTES: participants with their real (user-cast) votes, paged."""
    query = update.callback_query
    parts = query.data.split("_")   # realvotes, gid, [page]
    giveaway_id = parts[1]
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can see this!", show_alert=True)
        return
    await query.answer()

    counts = defaultdict(int)
    for e in giveaway.get("vote_log", []):
        counts[e.get("target")] += 1

    participants = sorted(giveaway["users"].items(), key=lambda kv: counts.get(kv[0], 0), reverse=True)
    total_pages = max(1, (len(participants) + REAL_VOTES_PER_PAGE - 1) // REAL_VOTES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = participants[page * REAL_VOTES_PER_PAGE:(page + 1) * REAL_VOTES_PER_PAGE]

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_SEARCH}'>🔍</tg-emoji> REAL VOTES</b>\n\n"
        f"<b>Participants:</b> {len(giveaway['users'])}\n"
        f"<b>Total real votes:</b> {len(giveaway.get('vote_log', []))}\n"
        f"<b>Page:</b> {page + 1}/{total_pages}\n\n"
        f"<i>Tap a participant to see who voted for them and when.</i>"
    )
    if not participants:
        text += "\n\n<i>No participants yet.</i>"

    keyboard = []
    for uid, name in chunk:
        keyboard.append([premium_button(f"{str(name)[:22]} — {counts.get(uid, 0)}",
                                        callback_data=f"rvuser_{giveaway_id}_{uid}",
                                        emoji_id=EMOJI_SMILE, style=BUTTON_STYLE_PRIMARY)])
    nav = nav_row(f"realvotes_{giveaway_id}", page, total_pages)
    if nav:
        keyboard.append(nav)
    keyboard.append([premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)])

    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def real_votes_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows who voted for one participant and when (Indian time), paged."""
    query = update.callback_query
    parts = query.data.split("_")   # rvuser, gid, uid, [page]
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await query.answer("Invalid!", show_alert=True)
        return
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can see this!", show_alert=True)
        return
    await query.answer()

    entries = [e for e in giveaway.get("vote_log", []) if e.get("target") == target_id]
    name = giveaway["users"].get(target_id, f"User {target_id}")

    total_pages = max(1, (len(entries) + REAL_VOTES_PER_PAGE - 1) // REAL_VOTES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * REAL_VOTES_PER_PAGE
    chunk = entries[start:start + REAL_VOTES_PER_PAGE]

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <a href=\"tg://user?id={target_id}\">{esc(name)}</a></b>\n"
        f"<b><tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> ID:</b> <code>{target_id}</code>\n"
        f"<b><tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> Real votes:</b> {len(entries)}\n"
        f"<b>Total shown on post:</b> {giveaway['vote_counts'].get(target_id, 0)}\n"
        f"<b>Page:</b> {page + 1}/{total_pages}\n\n"
    )

    if not entries:
        text += "<i>No real votes yet.</i>"
    else:
        for i, e in enumerate(chunk, start + 1):
            voter = e.get("voter")
            uname = all_users.get(str(voter), {}).get("username")
            uname_txt = f" (@{esc(uname)})" if uname else ""
            text += (f"<b>{i}.</b> {esc(e.get('voter_name', 'User'))}{uname_txt}\n"
                     f"     🆔 <a href=\"tg://user?id={voter}\">{voter}</a>\n"
                     f"     🕒 {esc(fmt_time(e.get('time')))}\n\n")

    keyboard = []
    nav = nav_row(f"rvuser_{giveaway_id}_{target_id}", page, total_pages)
    if nav:
        keyboard.append(nav)
    keyboard.append([premium_button("BACK", callback_data=f"realvotes_{giveaway_id}",
                                    emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)])

    await query.edit_message_text(text=text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  disable_web_page_preview=True)


# ================= PARTICIPANTS (OPEN / DISQUALIFY) =================
PARTICIPANTS_PER_PAGE = 15


async def participants_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage -> PARTICIPANTS: all participants, paged. Tap one to open it."""
    query = update.callback_query
    parts = query.data.split("_")   # plist, gid, page
    giveaway_id = parts[1]
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can see this!", show_alert=True)
        return
    await query.answer()

    participants = list(giveaway["users"].items())
    total_pages = max(1, (len(participants) + PARTICIPANTS_PER_PAGE - 1) // PARTICIPANTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = participants[page * PARTICIPANTS_PER_PAGE:(page + 1) * PARTICIPANTS_PER_PAGE]

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_USERS}'>👥</tg-emoji> PARTICIPANTS</b>\n\n"
        f"<b>Total:</b> {len(participants)}\n"
        f"<b>Page:</b> {page + 1}/{total_pages}\n\n"
        f"<i>Tap a participant to open them. You can disqualify from there.</i>"
    )
    if not participants:
        text += "\n\n<i>No participants yet.</i>"

    keyboard = []
    for uid, name in chunk:
        votes = giveaway["vote_counts"].get(uid, 0)
        keyboard.append([premium_button(f"{str(name)[:22]} — {votes}",
                                        callback_data=f"pinfo_{giveaway_id}_{uid}_{page}",
                                        emoji_id=EMOJI_SMILE, style=BUTTON_STYLE_PRIMARY)])
    nav = nav_row(f"plist_{giveaway_id}", page, total_pages)
    if nav:
        keyboard.append(nav)
    keyboard.append([premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)])

    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def participant_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """One participant: details + DISQUALIFY / BACK."""
    query = update.callback_query
    parts = query.data.split("_")   # pinfo, gid, uid, page
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await query.answer("Invalid!", show_alert=True)
        return
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can see this!", show_alert=True)
        return
    await query.answer()

    back_btn = premium_button("BACK", callback_data=f"plist_{giveaway_id}_{page}",
                              emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)

    if target_id not in giveaway["users"]:
        await query.edit_message_text("ℹ️ This participant is no longer in the giveaway.", parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([[back_btn]]))
        return

    name = giveaway["users"][target_id]
    uname = all_users.get(str(target_id), {}).get("username")
    real_votes = sum(1 for e in giveaway.get("vote_log", []) if e.get("target") == target_id)

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <a href=\"tg://user?id={target_id}\">{esc(name)}</a></b>\n"
        f"<b><tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> ID:</b> <a href=\"tg://user?id={target_id}\">{target_id}</a>\n"
        f"📝 <b>Username:</b> @{esc(uname or 'no')}\n"
        f"<b><tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> Votes on post:</b> {giveaway['vote_counts'].get(target_id, 0)}\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SEARCH}'>🔍</tg-emoji> Real votes:</b> {real_votes}"
    )
    keyboard = InlineKeyboardMarkup([
        [premium_button("DISQUALIFY", callback_data=f"pdq_{giveaway_id}_{target_id}_{page}",
                        emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)],
        [back_btn]
    ])
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard,
                                  disable_web_page_preview=True)


async def participant_disqualify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DISQUALIFY pressed: removes the participant, deletes their post, blocks re-joining."""
    query = update.callback_query
    parts = query.data.split("_")   # pdq, gid, uid, page
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await query.answer("Invalid!", show_alert=True)
        return
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can do this!", show_alert=True)
        return

    name = giveaway["users"].get(target_id, str(target_id))
    done = await disqualify_participant(context.bot, giveaway_id, target_id, notify=True)
    await query.answer("🚫 Disqualified!" if done else "Already removed.", show_alert=False)

    text = (f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>DISQUALIFIED</b>\n\n"
            f"{esc(name)} (<code>{target_id}</code>) was removed from the giveaway.")
    await query.edit_message_text(
        text=text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"plist_{giveaway_id}_{page}",
                                                           emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )


# ================= VOTE MANAGEMENT =================
async def add_votes_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "add"
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> ADD VOTES</b>\n\nSend: <code>USER_ID VOTES</code>\nExample: <code>12345678 10</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )


async def remove_votes_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "remove"
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> REMOVE VOTES</b>\n\nSend: <code>USER_ID VOTES</code>\nExample: <code>12345678 5</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )


async def process_vote_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giveaway_id = context.user_data.get("vote_giveaway")
    action = context.user_data.get("vote_action")
    if not giveaway_id or giveaway_id not in giveaways:
        return

    try:
        parts = update.message.text.strip().split()
        target_uid = int(parts[0])
        votes = int(parts[1])
    except Exception:
        await update.message.reply_text(f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> Invalid! Send <code>USER_ID VOTES</code>.", parse_mode="HTML")
        return

    giveaway = giveaways[giveaway_id]
    if target_uid not in giveaway['users']:
        await update.message.reply_text(f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> User not found!", parse_mode="HTML")
        return

    old_votes = giveaway['vote_counts'].get(target_uid, 0)

    if action == "add":
        giveaway['vote_counts'][target_uid] = old_votes + votes
        msg = f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> Added +{votes} votes!"
    else:
        giveaway['vote_counts'][target_uid] = max(0, old_votes - votes)
        msg = f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> Removed {votes} votes!"

    new_votes = giveaway['vote_counts'][target_uid]
    save_data()

    await update_vote_button_in_channel(context, giveaway_id, target_uid, new_votes)

    await update.message.reply_text(
        f"{msg}\n<b>New Total:</b> {new_votes} votes",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )

    context.user_data.pop("vote_giveaway", None)
    context.user_data.pop("vote_action", None)


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.edit_message_text(f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> Not found!", parse_mode="HTML")
        return

    sorted_users = sorted(giveaway['vote_counts'].items(), key=lambda x: x[1], reverse=True)[:10]

    text = f"<b><tg-emoji emoji-id='{EMOJI_CALENDAR}'>🗓</tg-emoji> LEADERBOARD</b>\n\n"
    if not sorted_users:
        text += "<i>No votes yet.</i>"
    else:
        for idx, (uid, votes) in enumerate(sorted_users, 1):
            name = giveaway['users'].get(uid, f"User {uid}")
            text += f"<b>{idx}.</b> {esc(name)} - <b>{votes} votes</b>\n"

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )


async def end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_LOCK}'>⚠️</tg-emoji> End this giveaway?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [premium_button("CONFIRM", callback_data=f"confirm_end_{giveaway_id}", emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_DANGER)],
            [premium_button("CANCEL", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_PRIMARY)]
        ])
    )


async def confirm_end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[2]
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.edit_message_text("❌ Giveaway not found!", parse_mode="HTML")
        return

    giveaway["ended"] = True

    sorted_users = sorted(giveaway['vote_counts'].items(), key=lambda x: x[1], reverse=True)
    winner_text = "No participants."
    if sorted_users:
        w_uid, w_votes = sorted_users[0]
        winner_text = f"🏆 <b>WINNER:</b> {esc(giveaway['users'].get(w_uid, w_uid))} with {w_votes} votes!"

    update_channel_history(
        channel_identifier=giveaway.get("channel"),
        channel_display=giveaway.get("channel_display"),
        channel_id=giveaway.get("channel_id"),
        user_id=giveaway.get("creator"),
        user_name=giveaway.get("creator_name", "Unknown"),
        action="end",
        giveaway_id=giveaway_id
    )

    save_data()

    try:
        await context.bot.send_message(
            chat_id=giveaway['channel_id'],
            text=f"💰 <b>GIVEAWAY ENDED!</b>\n\n{winner_text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await query.edit_message_text(
        text=f"✅ <b>Giveaway ended!</b>\n\n{winner_text}",
        parse_mode="HTML"
    )


# ================= JOIN HANDLER (MANUAL / APPROVE) =================
async def register_participant(context, giveaway_id, user_id, name):
    """Adds the participant and posts their profile (with the 2 buttons) in the channel."""
    giveaway = giveaways[giveaway_id]
    giveaway["users"][user_id] = name
    giveaway["vote_counts"][user_id] = 0
    giveaway["voted_users"][user_id] = set()
    save_data()

    channel_text = (
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Name:</b> {esc(name)}\n"
        f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> <b>ID:</b> <code>{user_id}</code>"
    )

    try:
        sent_msg = await context.bot.send_message(
            chat_id=giveaway['channel_id'],
            text=channel_text,
            parse_mode="HTML",
            reply_markup=participant_markup(giveaway_id, user_id, 0)
        )
        giveaway.setdefault("vote_msgs", {})[user_id] = sent_msg.message_id
        save_data()
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    giveaway_id = query.data.split("_")[1]
    user = query.from_user

    if is_security_banned(user.id):
        await query.answer("🚫 You are banned from this bot.", show_alert=True)
        return

    save_user(user.id, user.username, user.first_name, user.last_name, source="join")
    update_user_stats(user.id, "join")

    if giveaway_id not in giveaways:
        await query.answer("Giveaway not found!", show_alert=True)
        return

    giveaway = giveaways[giveaway_id]

    if giveaway.get("ended"):
        await query.answer("❌ This giveaway has already ended!", show_alert=True)
        return

    if user.id in giveaway["users"]:
        await query.answer("⚠️ Already Joined!", show_alert=True)
        return

    if user.id in giveaway.get("disqualified", []):
        await query.answer("🚫 You were disqualified from this giveaway.", show_alert=True)
        return

    if user.id in giveaway.get("rejected", []):
        await query.answer("❌ The creator rejected your request.", show_alert=True)
        return

    if user.id in giveaway.get("pending", {}):
        await query.answer("⏳ Your request is already pending approval.", show_alert=True)
        return

    # Double-check membership before allowing join
    is_member = (await check_membership(context.bot, giveaway.get('channel_id'), user.id)) is True

    if not is_member:
        await query.answer()
        link = await get_giveaway_channel_link(context, giveaway)
        text, markup = build_membership_required(giveaway_id, giveaway, link)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
        return

    # Creator's extra force-join channel
    extra_missing = await get_extra_missing(context, giveaway, user.id)
    if extra_missing:
        await query.answer()
        text, markup = build_extra_required(giveaway_id, giveaway, extra_missing)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
        return

    display_name = user.full_name or user.first_name

    # ---------- APPROVE MODE: send request to the creator ----------
    if giveaway.get("mode") == "approve" and user.id != giveaway.get("creator"):
        giveaway.setdefault("pending", {})[user.id] = display_name
        save_data()

        await query.answer("📨 Request sent!", show_alert=True)

        req_keyboard = InlineKeyboardMarkup([[
            premium_button("APPROVE", callback_data=f"gapprove_{giveaway_id}_{user.id}",
                           emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_SUCCESS),
            premium_button("REJECT", callback_data=f"greject_{giveaway_id}_{user.id}",
                           emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)
        ]])
        try:
            await context.bot.send_message(
                chat_id=giveaway["creator"],
                text=f"<b><tg-emoji emoji-id='{EMOJI_INBOX}'>📥</tg-emoji> NEW JOIN REQUEST</b>\n\n"
                     f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Name:</b> {esc(display_name)}\n"
                     f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> <b>ID:</b> <code>{user.id}</code>\n"
                     f"📝 <b>Username:</b> @{esc(user.username or 'no')}\n"
                     f"<tg-emoji emoji-id='{EMOJI_SPEAKER}'>📢</tg-emoji> <b>Giveaway:</b> {esc(giveaway.get('channel_display'))}",
                parse_mode="HTML",
                reply_markup=req_keyboard
            )
        except Exception as e:
            logger.error(f"Could not notify creator: {e}")

        try:
            await query.edit_message_text(
                text=f"<tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⏳</tg-emoji> <b>REQUEST SENT!</b>\n\n"
                     f"<i>Waiting for the giveaway creator to approve you. You will be notified here.</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # ---------- MANUAL MODE: join instantly ----------
    await register_participant(context, giveaway_id, user.id, display_name)

    await query.answer("✅ Registration Successful!", show_alert=True)

    await query.edit_message_text(
        text=f"✅ <b>Registration Successful!</b>\n\n"
             f"😎 {esc(display_name)}\n"
             f"💌 <code>{user.id}</code>\n\n"
             f"📥 Profile shared in channel!",
        parse_mode="HTML"
    )


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creator pressed APPROVE / REJECT on a join request."""
    query = update.callback_query
    parts = query.data.split("_")   # gapprove|greject, gid, uid
    approve = parts[0] == "gapprove"
    try:
        giveaway_id = parts[1]
        target_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("Invalid!", show_alert=True)
        return

    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        await query.answer("Giveaway not found!", show_alert=True)
        return
    if not is_manager(query.from_user.id, giveaway):
        await query.answer("❌ Only the creator can do this!", show_alert=True)
        return

    pending = giveaway.get("pending", {})
    if target_id not in pending:
        await query.answer("Already handled.", show_alert=True)
        try:
            await query.edit_message_text("ℹ️ This request was already handled.", parse_mode="HTML")
        except Exception:
            pass
        return

    if giveaway.get("ended"):
        await query.answer("❌ Giveaway already ended!", show_alert=True)
        return

    name = pending.pop(target_id)

    if approve:
        await register_participant(context, giveaway_id, target_id, name)
        await query.answer("✅ Approved!")
        result_text = (f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> <b>APPROVED</b>\n\n"
                       f"{esc(name)} (<code>{target_id}</code>) is now a participant.")
        user_text = (f"<tg-emoji emoji-id='{EMOJI_CELEBRATE}'>🎉</tg-emoji> <b>REQUEST APPROVED!</b>\n\n"
                     f"You are now in the giveaway of <b>{esc(giveaway.get('channel_display'))}</b>.\n"
                     f"📥 Your profile has been shared in the channel!")
    else:
        giveaway.setdefault("rejected", []).append(target_id)
        save_data()
        await query.answer("❌ Rejected!")
        result_text = (f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>REJECTED</b>\n\n"
                       f"{esc(name)} (<code>{target_id}</code>) was rejected.")
        user_text = (f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>REQUEST REJECTED</b>\n\n"
                     f"The creator rejected your request for the giveaway of "
                     f"<b>{esc(giveaway.get('channel_display'))}</b>.")

    save_data()

    try:
        await query.edit_message_text(result_text, parse_mode="HTML")
    except Exception:
        pass
    try:
        await context.bot.send_message(chat_id=target_id, text=user_text, parse_mode="HTML")
    except Exception:
        pass


# ================= BROADCAST ENGINE =================
def get_all_channel_ids():
    """Every channel the bot is connected to (giveaway history + mandatory channels), de-duplicated."""
    ids = []
    seen = set()

    def add(cid):
        if cid and cid not in seen:
            seen.add(cid)
            ids.append(cid)

    for ch in channel_history.values():
        add(ch.get("channel_id"))
    for g in giveaways.values():
        add(g.get("channel_id"))
    for c in required_channels:
        add(c.get("chat_id"))
    return ids


async def send_to_users(context, msg):
    ok = fail = 0
    for uid in list(all_users.keys()):
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="HTML", disable_web_page_preview=True)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


async def send_to_channels(context, msg):
    ok = fail = 0
    ids = get_all_channel_ids()
    for cid in ids:
        try:
            await context.bot.send_message(chat_id=cid, text=msg, parse_mode="HTML", disable_web_page_preview=True)
            ok += 1
        except Exception as e:
            logger.error(f"Failed to send to channel {cid}: {e}")
            fail += 1
        await asyncio.sleep(0.5)
    return ok, fail, len(ids)


async def run_broadcast(context, report_chat_id, target, msg):
    """target: 'users' | 'channels' | 'all'"""
    report = "<b>✅ BROADCAST COMPLETED!</b>\n"
    if target in ("users", "all"):
        ok, fail = await send_to_users(context, msg)
        report += (f"\n<b>📱 USERS:</b>\n   ✅ Sent: <code>{ok}</code>\n   ❌ Failed: <code>{fail}</code>\n"
                   f"   📊 Total: <code>{len(all_users)}</code>\n")
    if target in ("channels", "all"):
        ok, fail, total = await send_to_channels(context, msg)
        report += (f"\n<b>📺 CHANNELS:</b>\n   ✅ Sent: <code>{ok}</code>\n   ❌ Failed: <code>{fail}</code>\n"
                   f"   📊 Total: <code>{total}</code>\n")
    try:
        await context.bot.send_message(chat_id=report_chat_id, text=report, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send broadcast report: {e}")


# ================= ADMIN COMMANDS =================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin - Show all admin commands"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return

    text = """
<b>👑 ADMIN COMMANDS</b>

<code>/admin</code> - Show this help menu
<code>/broadcast</code> - Broadcast menu (Users / Channels)
<code>/broadcast &lt;msg&gt;</code> - Quick send to all users
<code>/bc &lt;msg&gt;</code> - Send message to all channels
<code>/ball &lt;msg&gt;</code> - Send to all users + all channels
<code>/stats</code> - Bot statistics
<code>/users</code> - Recent users list
<code>/channels</code> - Channel history
<code>/backup</code> - Manual backup
<code>/settings</code> - Bot settings
<code>/security</code> - Security status
<code>/ban &lt;user_id&gt; [reason]</code> - Manual ban
<code>/unban &lt;user_id&gt;</code> - Remove ban
<code>/testnotify</code> - Test notification
<code>/clear</code> - Delete all data (keeps mandatory channels)

<b>🔒 MANDATORY JOIN CHANNELS</b>
<code>/addjoin &lt;@username or -100id&gt; [invite_link]</code> - Add mandatory channel
<code>/removejoin &lt;@username or -100id&gt;</code> - Remove mandatory channel
<code>/joinlist</code> - List mandatory channels

<code>/g_management &lt;giveaway_id&gt;</code> - Open giveaway management panel
<code>/add_vote &lt;giveaway_id&gt; &lt;user_id&gt; &lt;votes&gt;</code> - Add votes to user
<code>/remove_vote &lt;giveaway_id&gt; &lt;user_id&gt; &lt;votes&gt;</code> - Remove votes from user

<b>📌 Note:</b> Owner can manage any giveaway secretly.
The bot must be <b>admin</b> in every mandatory channel.
"""
    await update.message.reply_text(text, parse_mode="HTML")


# ---------- Mandatory channel management ----------
async def addjoin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addjoin <@username | -100id> [invite_link]"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /addjoin <@username or -100id> [invite_link]")
        return

    ident = context.args[0]
    custom_link = context.args[1] if len(context.args) > 1 else None

    try:
        chat = await context.bot.get_chat(ident if ident.startswith('@') else int(ident))
    except Exception:
        await update.message.reply_text("❌ Channel not found. Add the bot to the channel as admin first.")
        return

    try:
        me = await context.bot.get_chat_member(chat.id, context.bot.id)
        if me.status not in ("administrator", "creator"):
            raise ValueError("not admin")
    except Exception:
        await update.message.reply_text(f"🤖 Make @{BOT_USERNAME} an <b>admin</b> in that channel first.", parse_mode="HTML")
        return

    if any(c["chat_id"] == chat.id for c in required_channels):
        await update.message.reply_text("⚠️ This channel is already in the mandator
