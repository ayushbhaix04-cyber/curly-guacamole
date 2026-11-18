#!/usr/bin/env python3
"""
ARJUN VOTE GIVEAWAY BOT
Requires: python-telegram-bot >= 20.7
Install: pip install -U python-telegram-bot
Run:
  export BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
  python arjun_vote_bot.py

IMPORTANT:
- Revoke any token previously posted publicly using @BotFather.
- Add the bot as an administrator in giveaway channels and required channels.
- For required-channel leave detection, enable chat_member updates (done below)
  and make the bot an administrator in each required channel.
"""

import os
import json
import html
import logging
import random
import string
import asyncio
from datetime import datetime
from collections import defaultdict, deque

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ChatMemberHandler, ContextTypes, filters
)
from telegram.error import TelegramError

# ---------------- CONFIG ----------------

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "arjunvotebot").lstrip("@")
OWNER_ID = int(os.getenv("OWNER_ID", "8413435583"))
DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- DATABASE ----------------

giveaways = {}
all_users = {}
channel_history = {}
mandatory_channels = {}  # key: str(chat_id), value: {id, title, link}
vote_messages = {}       # runtime-only message IDs
user_sessions = {}
admin_sessions = {}

banned_users = set()
suspicious_scores = defaultdict(int)
vote_activity = defaultdict(deque)

VOTE_WINDOW_SECONDS = 30
MAX_VOTES_IN_WINDOW = 8
MAX_TARGETS_IN_WINDOW = 6
SUSPICIOUS_SCORE_LIMIT = 3

ABUSE_WORDS = {
    "fuck", "fucking", "fucker", "shit", "bitch", "bastard", "asshole",
    "dick", "cunt", "whore", "slut", "idiot", "stupid", "gaand", "gand",
    "chutiya", "chutiye", "madarchod", "bhosdike", "bhosdi", "behenchod",
    "bhenchod", "randi", "harami", "kamina", "kamine"
}
ADULT_WORDS = {
    "porn", "porno", "pornography", "xxx", "nsfw", "nudes", "nude",
    "sexcam", "sexvideo", "onlyfans"
}


def json_safe(value):
    if isinstance(value, set):
        return list(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def load_data():
    global giveaways, all_users, channel_history, mandatory_channels
    if not os.path.exists(DATA_FILE):
        giveaways, all_users, channel_history, mandatory_channels = {}, {}, {}, {}
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        giveaways = data.get("giveaways", {})
        all_users = data.get("all_users", {})
        channel_history = data.get("channel_history", {})
        mandatory_channels = data.get("mandatory_channels", {})

        for gid, g in giveaways.items():
            g["users"] = {int(k): v for k, v in g.get("users", {}).items()}
            g["vote_counts"] = {
                int(k): int(v) for k, v in g.get("vote_counts", {}).items()
            }
            g["voted_users"] = {
                int(k): set(int(x) for x in v)
                for k, v in g.get("voted_users", {}).items()
            }
            vote_messages.setdefault(gid, {})
        for uid, info in all_users.items():
            if info.get("security_banned"):
                banned_users.add(int(uid))
        logger.info("Loaded %d giveaways and %d users", len(giveaways), len(all_users))
    except Exception:
        logger.exception("Could not load database")
        giveaways, all_users, channel_history, mandatory_channels = {}, {}, {}, {}


def save_data():
    data = {
        "giveaways": giveaways,
        "all_users": all_users,
        "channel_history": channel_history,
        "mandatory_channels": mandatory_channels,
        "last_saved": datetime.now().isoformat()
    }
    temp_file = DATA_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(json_safe(data), f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DATA_FILE)
    except Exception:
        logger.exception("Could not save database")


def save_user(user):
    if not user:
        return
    key = str(user.id)
    now = datetime.now().isoformat()
    record = all_users.setdefault(key, {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "joined_at": now,
        "total_votes_given": 0,
        "total_giveaways_joined": 0
    })
    record.update({
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "last_active": now
    })
    save_data()


def is_owner(user_id):
    return int(user_id) == OWNER_ID


def esc(value):
    return html.escape(str(value or ""))


def button(label, callback=None, url=None):
    if url:
        return InlineKeyboardButton(label, url=url)
    return InlineKeyboardButton(label, callback_data=callback)


async def notify_owner(context, title, message):
    try:
        await context.bot.send_message(
            OWNER_ID, f"<b>{esc(title)}</b>\n\n{message}", parse_mode="HTML"
        )
    except TelegramError:
        logger.exception("Owner notification failed")


# ---------------- REQUIRED CHANNELS ----------------

def is_member_status(member):
    status = member.status
    return (
        status in ("member", "administrator", "creator")
        or (status == "restricted" and getattr(member, "is_member", False))
    )


async def check_required_channels(user_id, context):
    missing = []
    for channel in mandatory_channels.values():
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if not is_member_status(member):
                missing.append(channel)
        except TelegramError as exc:
            logger.warning("Required channel check failed for %s: %s", channel.get("id"), exc)
            missing.append(channel)
    return missing


async def require_channels_message(target, missing):
    rows = []
    for channel in missing:
        link = channel.get("link")
        if link:
            rows.append([button(f"Join {channel.get('title', 'channel')}", url=link)])
    rows.append([button("I JOINED — VERIFY", callback="verify_required")])
    markup = InlineKeyboardMarkup(rows)
    text = (
        "<b>CHANNEL MEMBERSHIP REQUIRED</b>\n\n"
        "Join all channels below, then press VERIFY to use the bot."
    )
    if hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except TelegramError:
            pass
    await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def gate_user(update, context):
    user = update.effective_user
    if not user or is_owner(user.id) or not mandatory_channels:
        return False
    missing = await check_required_channels(user.id, context)
    if missing:
        if update.callback_query:
            await require_channels_message(update.callback_query, missing)
        elif update.effective_message:
            await require_channels_message(update.effective_message, missing)
        return True
    return False


async def add_required_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Owner only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addrequired @channel")
        return
    identifier = context.args[0]
    try:
        chat = await context.bot.get_chat(identifier)
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await update.message.reply_text(
                "Please make the bot an administrator in that channel first."
            )
            return
        link = chat.invite_link
        if chat.username:
            link = f"https://t.me/{chat.username}"
        if not link:
            invite = await context.bot.create_chat_invite_link(chat.id)
            link = invite.invite_link
        mandatory_channels[str(chat.id)] = {
            "id": chat.id, "title": chat.title or chat.username or str(chat.id),
            "link": link
        }
        save_data()
        await update.message.reply_text(
            f"Added required channel: <b>{esc(chat.title or identifier)}</b>",
            parse_mode="HTML"
        )
    except TelegramError as exc:
        await update.message.reply_text(
            f"Could not add channel. Check the channel ID/username and bot admin rights.\n{esc(exc)}",
            parse_mode="HTML"
        )


async def remove_required_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Owner only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removerequired CHANNEL_ID")
        return
    key = context.args[0]
    if key not in mandatory_channels:
        await update.message.reply_text("That channel is not in the required list.")
        return
    removed = mandatory_channels.pop(key)
    save_data()
    await update.message.reply_text(f"Removed: {esc(removed.get('title', key))}")


async def list_required_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Owner only.")
        return
    if not mandatory_channels:
        await update.message.reply_text("No mandatory channels configured.")
        return
    lines = ["<b>MANDATORY CHANNELS</b>"]
    for channel in mandatory_channels.values():
        lines.append(
            f"• {esc(channel.get('title'))} — <code>{channel.get('id')}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def verify_required_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    missing = await check_required_channels(query.from_user.id, context)
    if missing:
        await query.answer("You have not joined every required channel yet.", show_alert=True)
        await require_channels_message(query, missing)
    else:
        await query.answer("Membership verified!")
        await query.edit_message_text(
            "Membership verified. Send /start to open the bot.",
            parse_mode="HTML"
        )


async def required_channel_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When someone leaves a required channel, remove their votes everywhere."""
    event = update.chat_member
    if not event:
        return
    channel_key = str(event.chat.id)
    if channel_key not in mandatory_channels:
        return
    new_member = event.new_chat_member
    user_id = new_member.user.id
    if user_id == context.bot.id or is_member_status(new_member):
        return

    removed_votes = 0
    affected = []
    for gid, giveaway in giveaways.items():
        if giveaway.get("ended"):
            continue
        for target_id, voters in giveaway.get("voted_users", {}).items():
            if user_id in voters:
                voters.remove(user_id)
                giveaway["vote_counts"][target_id] = max(
                    0, int(giveaway["vote_counts"].get(target_id, 0)) - 1
                )
                removed_votes += 1
                affected.append((gid, target_id, giveaway["vote_counts"][target_id]))
    if removed_votes:
        save_data()
        for gid, target_id, count in affected:
            await update_vote_button_in_channel(context, gid, target_id, count)
        await notify_owner(
            context, "REQUIRED CHANNEL LEFT",
            f"User <code>{user_id}</code> left {esc(mandatory_channels[channel_key].get('title'))}.\n"
            f"Removed votes: <b>{removed_votes}</b>"
        )


# ---------------- SECURITY ----------------

def normalize_text(text):
    text = (text or "").lower()
    for old, new in {"@": "a", "4": "a", "3": "e", "1": "i", "!": "i",
                     "0": "o", "$": "s", "5": "s"}.items():
        text = text.replace(old, new)
    return "".join(ch if ch.isalnum() else " " for ch in text).strip()


def contains_banned_content(text):
    normalized = normalize_text(text)
    words = set(normalized.split())
    compact = normalized.replace(" ", "")
    if words & ABUSE_WORDS:
        return True
    if words & ADULT_WORDS:
        return True
    return any(len(term) >= 5 and term in compact for term in ABUSE_WORDS | ADULT_WORDS)


def security_ban_user(user_id, reason):
    uid = int(user_id)
    banned_users.add(uid)
    record = all_users.setdefault(str(uid), {"user_id": uid})
    record["security_banned"] = True
    record["security_ban_reason"] = reason
    record["security_banned_at"] = datetime.now().isoformat()
    save_data()


def vote_rate_check(voter_id, target_id):
    now = asyncio.get_running_loop().time()
    q = vote_activity[int(voter_id)]
    q.append((now, int(target_id)))
    while q and now - q[0][0] > VOTE_WINDOW_SECONDS:
        q.popleft()
    count = len(q)
    targets = len({target for _, target in q})
    return count > MAX_VOTES_IN_WINDOW or targets > MAX_TARGETS_IN_WINDOW, count, targets


async def security_gate(update, context, text=""):
    user = update.effective_user
    if not user or is_owner(user.id):
        return False
    if user.id in banned_users:
        if update.callback_query:
            await update.callback_query.answer("You are banned.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("You are banned from using this bot.")
        return True
    profile = " ".join(filter(None, [user.username, user.first_name, user.last_name]))
    if contains_banned_content(profile) or contains_banned_content(text):
        security_ban_user(user.id, "profile or message contained prohibited text")
        await notify_owner(context, "SECURITY AUTO-BAN", f"User ID: <code>{user.id}</code>")
        if update.callback_query:
            await update.callback_query.answer("Access blocked.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("Your access has been blocked.")
        return True
    return False


# ---------------- GIVEAWAY HELPERS ----------------

async def update_vote_button_in_channel(context, giveaway_id, target_id, new_votes):
    message_id = vote_messages.get(giveaway_id, {}).get(target_id)
    giveaway = giveaways.get(giveaway_id)
    if not message_id or not giveaway:
        return False
    try:
        keyboard = [[button(
            f"Vote — {new_votes}",
            callback=f"vote_{giveaway_id}_{target_id}"
        )]]
        await context.bot.edit_message_reply_markup(
            chat_id=giveaway["channel_id"], message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True
    except TelegramError:
        logger.exception("Could not update vote button")
        return False


async def channel_membership(context, channel_id, user_id):
    try:
        member = await context.bot.get_chat_member(channel_id, user_id)
        return is_member_status(member)
    except TelegramError:
        return False


def record_channel_history(channel, user, giveaway_id, action):
    key = str(channel["identifier"])
    entry = channel_history.setdefault(key, {
        "channel_identifier": channel["identifier"],
        "channel_display": channel["display"],
        "channel_id": channel["id"],
        "created_by": user.id,
        "created_by_name": user.first_name,
        "total_giveaways": 0,
        "giveaways": []
    })
    if action == "create":
        entry["total_giveaways"] += 1
        entry["giveaways"].append({
            "giveaway_id": giveaway_id, "status": "active",
            "created_at": datetime.now().isoformat()
        })
    elif action == "end":
        for item in entry["giveaways"]:
            if item.get("giveaway_id") == giveaway_id:
                item["status"] = "ended"
                item["ended_at"] = datetime.now().isoformat()
    save_data()


# ---------------- USER COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await security_gate(update, context):
        return
    if await gate_user(update, context):
        return
    save_user(user)

    if context.args:
        await handle_giveaway_link(update, context, context.args[0])
        return

    keyboard = [
        [button("CONNECT BOT TO CHANNEL", url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages")],
        [button("CREATE", callback="create_giveaway"),
         button("MANAGE", callback="my_giveaways")]
    ]
    await update.message.reply_text(
        "<b>WELCOME TO ARJUN VOTE GIVEAWAY BOT</b>\n\n"
        "Create vote giveaways, manage participants, and view live vote counts.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_giveaway_link(update, context, giveaway_id):
    giveaway = giveaways.get(giveaway_id)
    if not giveaway or giveaway.get("ended"):
        await update.effective_message.reply_text("This giveaway is invalid or has ended.")
        return
    user_id = update.effective_user.id
    channel_id = giveaway.get("channel_id")
    if not await channel_membership(context, channel_id, user_id):
        identifier = giveaway.get("channel", "")
        link = (f"https://t.me/{identifier[1:]}" if identifier.startswith("@")
                else f"https://t.me/{BOT_USERNAME}")
        keyboard = [
            [button("JOIN CHANNEL", url=link)],
            [button("TRY AGAIN", callback=f"retry_join_{giveaway_id}")]
        ]
        await update.effective_message.reply_text(
            "You must join the giveaway channel before participating.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if user_id in giveaway["users"]:
        await update.effective_message.reply_text("You have already joined this giveaway.")
        return
    keyboard = [[button("JOIN GIVEAWAY", callback=f"join_{giveaway_id}")]]
    await update.effective_message.reply_text(
        f"<b>GIVEAWAY</b>\nHost: {esc(giveaway.get('channel_display'))}\n"
        f"Participants: {len(giveaway['users'])}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def create_giveaway_flow(update, context):
    query = update.callback_query
    await query.answer()
    if await gate_user(update, context):
        return
    user_sessions[query.from_user.id] = {"step": "waiting_channel"}
    await query.edit_message_text(
        "Send the channel username (for example @mychannel) or numeric channel ID.\n"
        "The bot must be an administrator there.",
        reply_markup=InlineKeyboardMarkup([[button("CANCEL", callback="cancel_creation")]])
    )


async def cancel_creation(update, context):
    query = update.callback_query
    await query.answer()
    user_sessions.pop(query.from_user.id, None)
    await query.edit_message_text("Creation cancelled. Send /start to return to the menu.")


async def process_channel(update, context):
    user = update.effective_user
    value = update.message.text.strip()
    try:
        chat = await context.bot.get_chat(value if value.startswith("@") else int(value))
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            raise ValueError("Bot is not an administrator in that channel.")
        await context.bot.send_message(chat.id, "ARJUN VOTE BOT connected.")
    except Exception as exc:
        user_sessions.pop(user.id, None)
        await update.message.reply_text(f"Could not verify channel: {esc(exc)}", parse_mode="HTML")
        return

    for gid, old in giveaways.items():
        if old.get("channel_id") == chat.id and not old.get("ended"):
            user_sessions.pop(user.id, None)
            await update.message.reply_text(f"An active giveaway already exists: https://t.me/{BOT_USERNAME}?start={gid}")
            return

    gid = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    identifier = f"@{chat.username}" if chat.username else str(chat.id)
    channel = {"identifier": identifier, "display": chat.title or identifier, "id": chat.id}
    giveaways[gid] = {
        "channel": identifier, "channel_display": channel["display"], "channel_id": chat.id,
        "users": {}, "vote_counts": {}, "voted_users": {},
        "creator": user.id, "creator_name": user.first_name,
        "ended": False, "created_at": datetime.now().isoformat()
    }
    vote_messages[gid] = {}
    record_channel_history(channel, user, gid, "create")
    save_data()
    link = f"https://t.me/{BOT_USERNAME}?start={gid}"
    try:
        await context.bot.send_message(
            chat.id, f"<b>NEW GIVEAWAY STARTED</b>\nJoin here: {link}",
            parse_mode="HTML", disable_web_page_preview=True
        )
    except TelegramError:
        logger.exception("Could not post giveaway link")
    user_sessions.pop(user.id, None)
    await update.message.reply_text(
        f"<b>Giveaway created!</b>\nID: <code>{gid}</code>\nLink:\n{link}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[button("MANAGE", callback=f"manage_{gid}")]])
    )
    if user.id != OWNER_ID:
        await notify_owner(context, "NEW GIVEAWAY", f"{esc(user.first_name)} created {esc(gid)} in {esc(channel['display'])}")


async def retry_join(update, context):
    query = update.callback_query
    await query.answer()
    gid = query.data[len("retry_join_"):]
    await handle_giveaway_link_from_query(query, context, gid)


async def handle_giveaway_link_from_query(query, context, gid):
    giveaway = giveaways.get(gid)
    if not giveaway or giveaway.get("ended"):
        await query.edit_message_text("Giveaway not found or ended.")
        return
    if not await channel_membership(context, giveaway["channel_id"], query.from_user.id):
        await query.answer("Join the giveaway channel first.", show_alert=True)
        return
    await query.edit_message_text(
        f"Membership verified for {esc(giveaway.get('channel_display'))}.",
        reply_markup=InlineKeyboardMarkup([[button("JOIN GIVEAWAY", callback=f"join_{gid}")]]),
        parse_mode="HTML"
    )


async def handle_join(update, context):
    query = update.callback_query
    await query.answer()
    if await security_gate(update, context) or await gate_user(update, context):
        return
    gid = query.data[len("join_"):]
    giveaway = giveaways.get(gid)
    user = query.from_user
    if not giveaway or giveaway.get("ended"):
        await query.answer("Giveaway not available.", show_alert=True)
        return
    if user.id in giveaway["users"]:
        await query.answer("You already joined.", show_alert=True)
        return
    if not await channel_membership(context, giveaway["channel_id"], user.id):
        await query.answer("Join the giveaway channel first.", show_alert=True)
        return
    save_user(user)
    giveaway["users"][user.id] = user.full_name
    giveaway["vote_counts"][user.id] = 0
    giveaway["voted_users"][user.id] = set()
    all_users[str(user.id)]["total_giveaways_joined"] = all_users[str(user.id)].get("total_giveaways_joined", 0) + 1
    save_data()
    text = f"<b>Name:</b> {esc(user.full_name)}\n<b>ID:</b> <code>{user.id}</code>"
    markup = InlineKeyboardMarkup([[button("Vote — 0", callback=f"vote_{gid}_{user.id}")]])
    try:
        msg = await context.bot.send_message(
            giveaway["channel_id"], text, parse_mode="HTML", reply_markup=markup
        )
        vote_messages.setdefault(gid, {})[user.id] = msg.message_id
    except TelegramError:
        logger.exception("Could not post participant to channel")
    await query.edit_message_text("You have successfully joined the giveaway!")


async def handle_vote(update, context):
    query = update.callback_query
    await query.answer()
    if await security_gate(update, context) or await gate_user(update, context):
        return
    parts = query.data.split("_")
    if len(parts) != 3:
        return
    gid, target_raw = parts[1], parts[2]
    target_id = int(target_raw)
    voter = query.from_user
    giveaway = giveaways.get(gid)
    if not giveaway or giveaway.get("ended"):
        await query.answer("Giveaway ended or not found.", show_alert=True)
        return
    if target_id not in giveaway["users"]:
        await query.answer("Participant not found.", show_alert=True)
        return
    if not await channel_membership(context, giveaway["channel_id"], voter.id):
        await query.answer("Only channel members can vote.", show_alert=True)
        return
    too_fast, count, targets = vote_rate_check(voter.id, target_id)
    if too_fast:
        suspicious_scores[voter.id] += 1
        if suspicious_scores[voter.id] >= SUSPICIOUS_SCORE_LIMIT:
            security_ban_user(voter.id, "suspicious voting activity")
            await notify_owner(context, "VOTING SECURITY BAN", f"User <code>{voter.id}</code>")
            await query.answer("Voting access blocked.", show_alert=True)
        else:
            await query.answer("Please slow down.", show_alert=True)
        return
    voters = giveaway["voted_users"].setdefault(target_id, set())
    if voter.id in voters:
        await query.answer("You have already voted for this participant.", show_alert=True)
        return
    voters.add(voter.id)
    giveaway["vote_counts"][target_id] = giveaway["vote_counts"].get(target_id, 0) + 1
    save_user(voter)
    all_users[str(voter.id)]["total_votes_given"] = all_users[str(voter.id)].get("total_votes_given", 0) + 1
    save_data()
    await update_vote_button_in_channel(context, gid, target_id, giveaway["vote_counts"][target_id])
    await query.answer("Vote recorded!")


# ---------------- MANAGEMENT ----------------

async def my_giveaways(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    rows = []
    for gid, g in giveaways.items():
        if g.get("creator") == uid and not g.get("ended"):
            rows.append([button(g.get("channel_display", gid), callback=f"manage_{gid}")])
    rows.append([button("MAIN MENU", callback="main_menu")])
    await query.edit_message_text(
        "YOUR ACTIVE GIVEAWAYS" if len(rows) > 1 else "No active giveaways.",
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def manage_giveaway(update, context):
    query = update.callback_query
    await query.answer()
    gid = query.data[len("manage_"):]
    g = giveaways.get(gid)
    if not g:
        await query.edit_message_text("Giveaway not found.")
        return
    if not is_owner(query.from_user.id) and g.get("creator") != query.from_user.id:
        await query.answer("Not your giveaway.", show_alert=True)
        return
    rows = [
        [button("LEADERBOARD", callback=f"leaderboard_{gid}")],
        [button("END GIVEAWAY", callback=f"endgiveaway_{gid}")],
        [button("BACK", callback="my_giveaways")]
    ]
    await query.edit_message_text(
        f"<b>MANAGEMENT PANEL</b>\nChannel: {esc(g.get('channel_display'))}\n"
        f"Participants: {len(g.get('users', {}))}\n"
        f"Votes: {sum(g.get('vote_counts', {}).values())}",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
    )


async def show_leaderboard(update, context):
    query = update.callback_query
    await query.answer()
    gid = query.data[len("leaderboard_"):]
    g = giveaways.get(gid)
    if not g:
        await query.edit_message_text("Giveaway not found.")
        return
    ranked = sorted(g["vote_counts"].items(), key=lambda item: item[1], reverse=True)[:20]
    lines = ["<b>LEADERBOARD</b>"]
    if not ranked:
        lines.append("No votes yet.")
    for index, (uid, votes) in enumerate(ranked, 1):
        lines.append(f"{index}. {esc(g['users'].get(uid, uid))} — <b>{votes}</b>")
    await query.edit_message_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[button("BACK", callback=f"manage_{gid}")]])
    )


async def end_giveaway(update, context):
    query = update.callback_query
    await query.answer()
    gid = query.data[len("endgiveaway_"):]
    if gid not in giveaways:
        await query.edit_message_text("Giveaway not found.")
        return
    await query.edit_message_text(
        "End this giveaway?",
        reply_markup=InlineKeyboardMarkup([
            [button("CONFIRM", callback=f"confirm_end_{gid}")],
            [button("CANCEL", callback=f"manage_{gid}")]
        ])
    )


async def confirm_end_giveaway(update, context):
    query = update.callback_query
    await query.answer()
    gid = query.data[len("confirm_end_"):]
    g = giveaways.get(gid)
    if not g:
        await query.edit_message_text("Giveaway not found.")
        return
    if not is_owner(query.from_user.id) and g.get("creator") != query.from_user.id:
        await query.answer("Not authorized.", show_alert=True)
        return
    g["ended"] = True
    ranked = sorted(g["vote_counts"].items(), key=lambda item: item[1], reverse=True)
    winner = "No participants."
    if ranked:
        uid, votes = ranked[0]
        winner = f"Winner: {esc(g['users'].get(uid, uid))} — {votes} votes"
    for entry in channel_history.values():
        for item in entry.get("giveaways", []):
            if item.get("giveaway_id") == gid:
                item["status"] = "ended"
                item["ended_at"] = datetime.now().isoformat()
    save_data()
    vote_messages.pop(gid, None)
    try:
        await context.bot.send_message(g["channel_id"], f"<b>GIVEAWAY ENDED</b>\n{winner}", parse_mode="HTML")
    except TelegramError:
        pass
    await query.edit_message_text(f"Giveaway ended.\n\n{winner}", parse_mode="HTML")


# ---------------- OWNER COMMANDS ----------------

async def owner_only(update):
    if not is_owner(update.effective_user.id):
        await update.effective_message.reply_text("Owner only.")
        return False
    return True


async def admin_command(update, context):
    if not await owner_only(update):
        return
    await update.message.reply_text(
        "<b>OWNER COMMANDS</b>\n"
        "/addrequired @channel — require channel membership\n"
        "/removerequired CHANNEL_ID — remove required channel\n"
        "/requiredchannels — list required channels\n"
        "/stats — bot statistics\n"
        "/users — recent users\n"
        "/channels — channel history\n"
        "/backup — save database\n"
        "/broadcast message — message all known users\n"
        "/bc message — message active giveaway channels\n"
        "/add_vote ID USER_ID COUNT — add votes\n"
        "/remove_vote ID USER_ID COUNT — remove votes\n"
        "/ban USER_ID [reason] — ban user\n"
        "/unban USER_ID — unban user\n"
        "/clear — clear all bot data",
        parse_mode="HTML"
    )


async def stats_command(update, context):
    if not await owner_only(update):
        return
    active = sum(not g.get("ended") for g in giveaways.values())
    participants = sum(len(g.get("users", {})) for g in giveaways.values())
    votes = sum(sum(g.get("vote_counts", {}).values()) for g in giveaways.values())
    await update.message.reply_text(
        f"<b>BOT STATS</b>\nUsers: {len(all_users)}\nGiveaways: {len(giveaways)}\n"
        f"Active: {active}\nParticipants: {participants}\nVotes: {votes}\n"
        f"Required channels: {len(mandatory_channels)}",
        parse_mode="HTML"
    )


async def users_command(update, context):
    if not await owner_only(update):
        return
    recent = list(all_users.values())[-20:][::-1]
    lines = ["<b>RECENT USERS</b>"]
    for item in recent:
        lines.append(
            f"{esc(item.get('first_name'))} — <code>{item.get('user_id')}</code> "
            f"@{esc(item.get('username') or 'none')}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def channels_command(update, context):
    if not await owner_only(update):
        return
    lines = ["<b>CHANNEL HISTORY</b>"]
    for item in channel_history.values():
        active = sum(x.get("status") == "active" for x in item.get("giveaways", []))
        lines.append(f"{esc(item.get('channel_display'))} — active giveaways: {active}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def backup_command(update, context):
    if not await owner_only(update):
        return
    save_data()
    await update.message.reply_text(f"Database saved to {esc(DATA_FILE)}.")


async def broadcast_command(update, context):
    if not await owner_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast your message")
        return
    msg = " ".join(context.args)
    sent = failed = 0
    for uid in list(all_users):
        try:
            await context.bot.send_message(int(uid), msg, parse_mode="HTML")
            sent += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.04)
    await update.message.reply_text(f"Broadcast complete. Sent: {sent}, failed: {failed}")


async def bc_command(update, context):
    if not await owner_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /bc your message")
        return
    msg = " ".join(context.args)
    sent = failed = 0
    channel_ids = {g.get("channel_id") for g in giveaways.values() if not g.get("ended")}
    for chat_id in channel_ids:
        if not chat_id:
            continue
        try:
            await context.bot.send_message(chat_id, msg, parse_mode="HTML")
            sent += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.3)
    await update.message.reply_text(f"Channel broadcast complete. Sent: {sent}, failed: {failed}")


async def change_votes_command(update, context, add=True):
    if not await owner_only(update):
        return
    if len(context.args) != 3:
        command = "/add_vote" if add else "/remove_vote"
        await update.message.reply_text(f"Usage: {command} GIVEAWAY_ID USER_ID COUNT")
        return
    gid, uid_raw, count_raw = context.args
    try:
        uid, count = int(uid_raw), int(count_raw)
        if count < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("USER_ID and COUNT must be valid non-negative integers.")
        return
    g = giveaways.get(gid)
    if not g or uid not in g.get("users", {}):
        await update.message.reply_text("Giveaway or participant not found.")
        return
    old = g["vote_counts"].get(uid, 0)
    g["vote_counts"][uid] = old + count if add else max(0, old - count)
    save_data()
    await update_vote_button_in_channel(context, gid, uid, g["vote_counts"][uid])
    await update.message.reply_text(f"New vote total: {g['vote_counts'][uid]}")


async def add_vote_command(update, context):
    await change_votes_command(update, context, True)


async def remove_vote_command(update, context):
    await change_votes_command(update, context, False)


async def ban_command(update, context):
    if not await owner_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban USER_ID [reason]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    security_ban_user(uid, " ".join(context.args[1:]) or "owner ban")
    await update.message.reply_text(f"User {uid} banned.")


async def unban_command(update, context):
    if not await owner_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban USER_ID")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    banned_users.discard(uid)
    if str(uid) in all_users:
        all_users[str(uid)]["security_banned"] = False
    save_data()
    await update.message.reply_text(f"User {uid} unbanned.")


async def clear_command(update, context):
    if not await owner_only(update):
        return
    await update.message.reply_text(
        "This permanently clears users, giveaways, channel history, and required channels. "
        "Type /confirmclear to proceed."
    )


async def confirm_clear_command(update, context):
    global giveaways, all_users, channel_history, mandatory_channels, vote_messages
    if not await owner_only(update):
        return
    giveaways, all_users, channel_history, mandatory_channels, vote_messages = {}, {}, {}, {}, {}
    banned_users.clear()
    save_data()
    await update.message.reply_text("All bot data cleared.")


# ---------------- ROUTING ----------------

async def button_handler(update, context):
    query = update.callback_query
    data = query.data or ""
    if await security_gate(update, context):
        return
    if data != "verify_required" and await gate_user(update, context):
        return
    if data == "verify_required":
        await verify_required_callback(update, context)
    elif data == "create_giveaway":
        await create_giveaway_flow(update, context)
    elif data == "cancel_creation":
        await cancel_creation(update, context)
    elif data == "my_giveaways":
        await my_giveaways(update, context)
    elif data == "main_menu":
        await query.answer()
        await query.edit_message_text(
            "ARJUN VOTE GIVEAWAY BOT",
            reply_markup=InlineKeyboardMarkup([
                [button("CREATE", callback="create_giveaway"),
                 button("MANAGE", callback="my_giveaways")]
            ])
        )
    elif data.startswith("retry_join_"):
        await retry_join(update, context)
    elif data.startswith("manage_"):
        await manage_giveaway(update, context)
    elif data.startswith("leaderboard_"):
        await show_leaderboard(update, context)
    elif data.startswith("endgiveaway_"):
        await end_giveaway(update, context)
    elif data.startswith("confirm_end_"):
        await confirm_end_giveaway(update, context)
    elif data.startswith("join_"):
        await handle_join(update, context)
    elif data.startswith("vote_"):
        await handle_vote(update, context)
    else:
        await query.answer("Unknown action.", show_alert=True)


async def handle_message(update, context):
    user = update.effective_user
    if not user:
        return
    if await security_gate(update, context, update.message.text or ""):
        return
    if await gate_user(update, context):
        return
    if user.id in user_sessions and user_sessions[user.id].get("step") == "waiting_channel":
        await process_channel(update, context)


def main():
    load_data()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addrequired", add_required_channel))
    app.add_handler(CommandHandler("removerequired", remove_required_channel))
    app.add_handler(CommandHandler("requiredchannels", list_required_channels))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("channels", channels_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("bc", bc_command))
    app.add_handler(CommandHandler("add_vote", add_vote_command))
    app.add_handler(CommandHandler("remove_vote", remove_vote_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("confirmclear", confirm_clear_command))

    app.add_handler(ChatMemberHandler(
        required_channel_member_update, ChatMemberHandler.CHAT_MEMBER
    ))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("ARJUN VOTE GIVEAWAY BOT is running as @%s", BOT_USERNAME)
    app.run_polling(allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    main()
