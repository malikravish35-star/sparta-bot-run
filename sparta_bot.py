#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                       ⚡  S P A R T A - B O T   (SRC)  ⚡                     ║
║          Telegram Channel Search Bot  •  Pyrogram (MTProto)  •  Async        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  LIMITS / PLANS                                                              ║
║    • FREE      ->  20  files per search      (default)                       ║
║    • PREMIUM-1 ->  200 files per search      Rs 100 / month                  ║
║    • PREMIUM-2 ->  350 files per search      Rs 150 / month                  ║
║    • PREMIUM-3 ->  500 files per search      Rs 250 / month                  ║
║    • ADMIN     ->  5000 files (ADMIN_LIMIT se badlo)                         ║
║                                                                              ║
║  SPEED FEATURES                                                              ║
║    • tgcrypto (C encryption) + uvloop  -> fastest possible stack             ║
║    • MongoDB regex/text index          -> search ~10-50 ms                   ║
║    • Mongo na ho to auto JSON store    -> bot kabhi crash nahi               ║
║    • Concurrent result delivery (asyncio.gather + batches)                   ║
║    • Live MTProto channel search fallback (index miss hone par)              ║
║    • /forward ON  -> media seedha copy (real files)                          ║
║    • Per-chat lock + flood guard (double request cancel)                     ║
║                                                                              ║
║  TASK COMPLETE hone par hamesha:  "🙏 THANK YOU FOR CHOOSING SPARTA-BOT!"    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  INSTALL                                                                     ║
║    pip install -U pyrogram tgcrypto motor uvloop                             ║
║    (uvloop sirf Linux/Mac; Windows pe install mat karna)                     ║
║                                                                              ║
║  ENV VARS (ya niche default values me hardcoded kar do)                      ║
║    BOT_TOKEN      123456:ABC-...            (BotFather)                      ║
║    API_ID         1234567                   (my.telegram.org)                ║
║    API_HASH       0123456789abcdef...       (my.telegram.org)                ║
║    ADMIN_ID       123456789                 (apni ID — bot ko /id bhejo)     ║
║    DB_CHANNEL     -1001234567890            (jis channel me files hain)      ║
║    LOG_CHANNEL    -1009876543210            (optional)                       ║
║    MONGO_URI      mongodb+srv://...         (optional — free mongodb.com)    ║
║    DATABASE_NAME  sparta                    (optional)                       ║
║    BOT_NAME       SPARTA-BOT                (optional)                       ║
║    OWNER_NAME     @yourusername             (optional)                       ║
║    PAYMENT_INFO   UPI: sparta@ybl           (optional)                       ║
║    FORCE_SUB      @yourchannel              (optional — join button)         ║
║    MAX_RESULTS    500        ADMIN_LIMIT 5000     AUTO_INDEX 1               ║
║                                                                              ║
║  RUN            python3 sparta_bot.py                                        ║
║                                                                              ║
║  DEPLOY (free)                                                               ║
║    Koyeb / Render / Railway -> worker service, env vars, done                ║
║    Heroku  -> Procfile:  worker: python sparta_bot.py                        ║
║    VPS     -> screen/tmux me:  python3 sparta_bot.py                         ║
║    Docker  -> niche end me Dockerfile diya hai                               ║
║                                                                              ║
║  ADMIN COMMANDS                                                              ║
║    /index /reindex       channel index (re)build                             ║
║    /approve <id> [plan]  premium activate (30 din)                           ║
║    /reject <id>          request reject                                      ║
║    /setplan <id> <200|350|500> [days]                                        ║
║    /removeplan <id>      free tier pe wapas                                   ║
║    /user <id>  /find <name>  /reqs  /usage  /stats  /broadcast <msg>         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import functools
import html
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ── pyrogram import SABSE PEHLE ───────────────────────────────────────────────
# Kyun: pyrogram import ke waqt asyncio.get_event_loop() call karta hai
# (sync.py). Agar uvloop pehle install ho jaye to Python 3.12+ me wo
# RuntimeError deta hai. Isliye pehle pyrogram, fir uvloop.
try:
    from pyrogram import Client, filters, enums, idle
    from pyrogram.errors import (
        FloodWait, UserIsBlocked, PeerIdInvalid, ChatWriteForbidden,
        MessageNotModified, RPCError, UserAlreadyParticipant,
        InviteHashExpired,
    )
    from pyrogram.handlers import MessageHandler, CallbackQueryHandler
    from pyrogram.types import (
        InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message,
    )
except ImportError:
    sys.exit("[!] Pyrogram install nahi hai  ->  pip install -U pyrogram tgcrypto")

# ------------------------------------------------------------------ uvloop ---
try:                                        # Linux/Mac -> ~2x faster loop
    import uvloop
    uvloop.install()                        # asyncio.run() ab uvloop loop banayega
    UVLOOP = True
except Exception:
    UVLOOP = False

# ----------------------------------------------------------------- logging ---
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s :: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("SPARTA")
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ═══════════════════════════════ .ENV LOADER ════════════════════════════════
# Koi extra library nahi chahiye — bot khud .env padh leta hai.
# (python-dotenv installed ho to wo bhi use ho jayega)

def _load_dotenv(path=".env"):
    f = Path(path)
    if not f.exists():
        return False
    loaded = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            loaded += 1
    if loaded:
        log.info("📄 .env loaded (%d vars) from %s", loaded, f.resolve())
    return loaded > 0


try:                                    # optional, agar installed ho
    from dotenv import load_dotenv      # type: ignore
    load_dotenv()
except Exception:
    pass
_load_dotenv()

# ═══════════════════════════════ CONFIG ═════════════════════════════════════

def _get(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default

BOT_TOKEN  = _get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
API_ID     = int(_get("API_ID", 0))
API_HASH   = _get("API_HASH", "PASTE_YOUR_API_HASH_HERE")

ADMIN_ID   = int(_get("ADMIN_ID", 0))
ADMINS     = ({ADMIN_ID} if ADMIN_ID else set()) | {
    int(x) for x in _get("EXTRA_ADMINS", "").replace(",", " ").split() if x.strip().isdigit()}

DB_CHANNEL  = int(_get("DB_CHANNEL", 0))
LOG_CHANNEL = int(_get("LOG_CHANNEL", 0)) or None

MONGO_URI = (_get("MONGO_URI", "") or "").strip()
DB_NAME   = _get("DATABASE_NAME", "sparta")

BOT_NAME     = _get("BOT_NAME", "SPARTA-BOT")
OWNER_NAME   = _get("OWNER_NAME", "@SpartaOwner")
SUPPORT_TXT  = _get("SUPPORT_TXT", OWNER_NAME)
PAYMENT_INFO = _get("PAYMENT_INFO", "UPI / PhonePe / GPay :  sparta@ybl")
FORCE_SUB    = _get("FORCE_SUB", "")

MAX_RESULTS = int(_get("MAX_RESULTS", 500))
ADMIN_LIMIT = int(_get("ADMIN_LIMIT", 5000))
AUTO_INDEX  = _get("AUTO_INDEX", "1") == "1"

FREE_LIMIT   = 20
PREMIUM_DAYS = 30

PLANS = [
    {"key": "P200", "files": 200, "price": 100, "name": "Premium-1", "icon": "🥉"},
    {"key": "P350", "files": 350, "price": 150, "name": "Premium-2", "icon": "🥈"},
    {"key": "P500", "files": 500, "price": 250, "name": "Premium-3", "icon": "🥇"},
]
PLAN_BY_KEY   = {p["key"]: p for p in PLANS}
PLAN_BY_FILES = {p["files"]: p for p in PLANS}

# delivery / speed tuning
RESULT_BATCH     = int(_get("RESULT_BATCH", 20))     # files per message
MAX_BATCH_MSGS   = int(_get("MAX_BATCH_MSGS", 20))   # max result messages per search
SEND_CONCURRENCY = int(_get("SEND_CONCURRENCY", 6))  # parallel sends
FWD_CONCURRENCY  = int(_get("FWD_CONCURRENCY", 3))   # parallel media copies
FWD_DELAY        = float(_get("FWD_DELAY", 0.35))    # ban-safe gap
INDEX_CHUNK      = int(_get("INDEX_CHUNK", 100))
SEARCH_FLOOD_GAP = float(_get("SEARCH_FLOOD_GAP", 2.0))

# ── LINK MODE (kisi bhi group/channel ke link se file nikalna) ──────────────
# Iske liye ek USERBOT session chahiye (aapka Telegram account) kyunki bot
# khud un chats ko access nahi kar sakta jisme wo member nahi hai.
CACHE_CHANNEL  = int(_get("CACHE_CHANNEL", 0)) or None   # private channel (bot admin + userbot member)
SESSION_STRING = _get("SESSION_STRING", "")              # pyrogram v2 string session (userbot)
SESSION_FILE   = _get("SESSION_FILE", "userbot.session")
CLEAN_CACHE    = _get("CLEAN_CACHE", "1") == "1"         # cache se file delete kare?
CACHE_TTL      = int(_get("CACHE_TTL", 300))             # sec
UB_CONCURRENCY = int(_get("USERBOT_CONCURRENCY", 8))   # speed: 4 -> 8 parallel files
UB_DELAY       = float(_get("USERBOT_DELAY", 0.0))     # per-file extra sleep hataya
BOT_SEND_GAP   = float(_get("BOT_SEND_GAP", 0.12))     # global throttle (adaptive, flood-safe)
UB_TRANSMISSIONS = int(_get("UB_TRANSMISSIONS", 12))   # userbot ke parallel DC streams
SEQ_TIMEOUT    = int(_get("SEQ_TIMEOUT", 1800))        # sequence gate max wait (stuck-proof)
PEER_SCAN_MAX  = int(_get("PEER_SCAN_MAX", 90))        # dialogs scan max seconds (hang-proof)
SCAN_NO_HIST   = _get("SCAN_NO_HIST", "0") == "1"      # 1 = history method off
TOPIC_SCAN_MAX = int(os.getenv("TOPIC_SCAN_MAX", "4000"))
FLOOD_MAX_WAIT = int(_get("FLOOD_MAX_WAIT", 900))    # itne sec tak flood = wait + retry
MAX_RANGE      = int(_get("MAX_RANGE", 500))             # t.me/x/10-510 range cap
LINK_MODE      = _get("LINK_MODE", "1") == "1"
DEVICE_NAME    = _get("DEVICE_NAME", "Sparta SRC Server")   # Telegram Devices me yahi naam dikhega

# ── UPTIME / KEEP-ALIVE ──────────────────────────────────────────────────────
# Render/Koyeb jaisi free hosting pe web-service ko ek PORT pe listen karna
# hota hai, warna wo use "crashed" maan ke restart/stop kar deti hai.
# Ye chhota HTTP server bas 200 OK deta hai — UptimeRobot isi ko ping karta hai.
HEALTH_PORT    = int(_get("PORT", _get("HEALTH_PORT", 8080)))
SELF_PING_URL  = _get("SELF_PING_URL", "")          # apna hi public URL (optional)
SELF_PING_EVERY= int(_get("SELF_PING_EVERY", 300))  # sec (5 min)
STALL_SEC      = int(_get("STALL_SEC", 150))        # download itne sec ruka = abort+retry
ASK_COUNT    = _get("ASK_COUNT", "1") != "0"   # link ke baad "kitni files?" poocho
ASK_TTL      = int(_get("ASK_TTL", 600))       # sec — answer ka wait
MAX_FILE_MB  = int(_get("MAX_FILE_MB", 500))   # isse badi file skip (memory safe)

DATA_DIR = Path(_get("DATA_DIR", "sparta_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
JSON_FILE = DATA_DIR / "store.json"

# ═══════════════════════════════ TEXTS ══════════════════════════════════════

def thanks_msg(query, sent, found, limit, tier, start_t):
    return (
        f"🙏 <b>THANK YOU FOR CHOOSING {BOT_NAME}!</b>\n\n"
        f"⚡ <b>Task Complete</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 Query      : <code>{esc(query)[:60]}</code>\n"
        f"📦 Files Sent : <b>{sent}</b> / {found} found\n"
        f"🎯 Your Limit : <b>{limit}</b> ({tier})\n"
        f"⏱️ Time Taken : <b>{time.time() - start_t:.2f}s</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"❤️ Share {BOT_NAME} with your friends!"
    )


def limit_hit_txt(sent, found, limit):
    return (
        f"⛔ <b>LIMIT REACHED!</b>\n\n"
        f"Aapko <b>{sent}</b> files mil gayi (aapka limit <b>{limit}</b>), "
        f"par total <b>{found}</b> files mili thi.\n\n"
        f"🔒 Baaki <b>{found - sent}</b> files ke liye Premium lo:\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🥉 <b>200 files</b> → ₹<b>100</b>/month\n"
        f"🥈 <b>350 files</b> → ₹<b>150</b>/month\n"
        f"🥇 <b>500 files</b> → ₹<b>250</b>/month\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )


def start_txt(u, tguser=None):
    name = html.escape((tguser.first_name if tguser else u.get("name")) or "User")
    return (
        f"⚡ <b>{BOT_NAME}</b> ⚡\n\n"
        f"🙏 Welcome <b>{name}</b>!\n\n"
        "🔎 Main aapke <b>DB Channel</b> me file search karke turant bhej deta hoon — "
        "<b>lightning fast</b> ⚡\n\n"
        "🚀 <b>Kaise use karein?</b>\n"
        "1️⃣ Kisi bhi group/channel ke file post ka <b>link copy</b> karo\n"
        "2️⃣ Yahan <b>paste</b> kar do (ek saath kayi links bhi chalega)\n"
        "3️⃣ File turant aapke chat me aa jayegi 😎⚡\n\n"
        "📥 <b>Example:</b> <code>https://t.me/c/1234567890/45</code>\n"
        + (f"🔎 Search mode bhi hai: /search <i>(DB channel: {'set ✅' if DB_CHANNEL else 'not set'})</i>\n\n"
           if DB_CHANNEL or True else "") +
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎁 Free Limit : <b>{FREE_LIMIT} files</b> / search\n"
        f"👑 Your Plan  : <b>{plan_label(u)}</b>\n"
        f"⚡ Your Limit : <b>{user_limit(u)} files</b> / search\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "💎 Premium lekar limit badhao — sirf ₹100 se!\n"
        f"👤 Owner : {SUPPORT_TXT}"
    )


def plans_txt(u=None):
    rows = ["💎 <b>PREMIUM PLANS</b> 💎", "━━━━━━━━━━━━━━━━━━━"]
    for p in PLANS:
        rows.append(f"{p['icon']} <b>{p['name']}</b>  |  <b>{p['files']} files</b>/search"
                    f"  |  ₹<b>{p['price']}</b>/month")
    rows += [
        "━━━━━━━━━━━━━━━━━━━",
        f"🆓 Free users : <b>{FREE_LIMIT} files</b> per search",
        "",
        "🛒 <b>Kaise kharide?</b>",
        "1️⃣ Niche se apna plan chuno",
        "2️⃣ Payment karo (details niche)",
        "3️⃣ Screenshot / UTR bot ko bhejo",
        "4️⃣ Admin approve karega (5-15 min) ⚡",
        "",
        f"💳 <b>Payment Details</b>\n<code>{html.escape(PAYMENT_INFO)}</code>",
    ]
    if u:
        rows += ["", f"👤 <b>Aapka plan :</b> {plan_label(u)} ({user_limit(u)} files)"]
        if u.get("expiry") and not is_expired(u):
            rows.append(f"⏳ <b>Expiry :</b> {exp_str(u['expiry'])}")
    return "\n".join(rows)


HELP_TXT = (
    f"📖 <b>{BOT_NAME} — Commands</b>\n\n"
    "👤 <b>User Commands</b>\n━━━━━━━━━━━━━━━━━━━\n"
    "/start — bot menu\n"
    "🔗 <b>Koi bhi link bhejo → file turant!</b>\n"
    "/link — link mode help\n"
    "/status — bot ready hai ya nahi\n"
    "/search — file search ⚡\n"
    "   <i>ya seedha bot ko file ka naam bhej do</i>\n"
    "/forward — results ko <b>real file</b> ki tarah bhejo (ON/OFF)\n"
    "/plans — premium plans & prices\n"
    "/buy — plan kharido\n"
    "/myplan — apna plan & expiry\n"
    "/stats — stats\n/ping — speed check\n"
    "/id — apni Telegram ID\n/help — yehi message\n/cancel — chalu search band\n\n"
    "🛡️ <b>Admin Commands</b>\n━━━━━━━━━━━━━━━━━━━\n"
    "/setdb — DB channel set karo (post forward karo)\n"
    "/setcache — CACHE channel set karo (link mode ke liye)\n"
    "/index  /reindex — channel index build\n"
    "/approve &lt;id&gt; [plan] — premium do\n"
    "/reject &lt;id&gt; — request reject\n"
    "/setplan &lt;id&gt; &lt;200|350|500&gt; [days]\n"
    "/removeplan &lt;id&gt; — free pe wapas\n"
    "/user &lt;id&gt;  •  /find &lt;name&gt;\n"
    "/reqs — pending buy requests\n"
    "/usage — premium users + revenue\n"
    "/broadcast &lt;msg&gt; — sabko message\n"
    "/stats — bot stats\n"
)

# ═══════════════════════════════ STORE ══════════════════════════════════════

class JsonStore:
    """Single-file in-memory JSON DB — Mongo na ho tab automatic fallback."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {"users": [], "files": [], "requests": [], "settings": [],
                     "counters": {"searches": 0, "files_sent": 0}}
        self.lock = asyncio.Lock()
        self._dirty = False
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                for k in ("users", "files", "requests", "settings"):
                    self.data.setdefault(k, [])
                self.data.setdefault("counters", {"searches": 0, "files_sent": 0})
                log.info("JsonStore loaded: %d files, %d users",
                         len(self.data["files"]), len(self.data["users"]))
                return
            except Exception as e:
                log.error("JsonStore load fail (%s) -> fresh", e)
        log.info("JsonStore fresh: %s", self.path)

    async def flush(self):
        async with self.lock:
            if not self._dirty:
                return
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
            self._dirty = False

    async def _saver(self):
        while True:
            await asyncio.sleep(5)
            try:
                await self.flush()
            except Exception as e:
                log.warning("flush error: %s", e)

    def _coll(self, name):
        """Collection auto-create — unknown coll pe KeyError na aaye."""
        if name not in self.data or not isinstance(self.data[name], list):
            self.data[name] = []
        return self.data[name]

    @staticmethod
    def _find(coll, key, val):
        for d in coll:
            if d.get(key) == val:
                return d
        return None

    async def upsert(self, coll, key, val, update):
        async with self.lock:
            c = self._coll(coll)
            doc = self._find(c, key, val)
            if doc is None:
                doc = {key: val}
                c.append(doc)
            if update:
                doc.update(update)
                self._dirty = True
            return doc

    async def find_one(self, coll, key, val):
        return self._find(self._coll(coll), key, val)

    async def delete_one(self, coll, key, val):
        async with self.lock:
            before = len(self._coll(coll))
            self.data[coll] = [d for d in self._coll(coll) if d.get(key) != val]
            self._dirty = True
            return before - len(self.data[coll])

    async def all_docs(self, coll):
        return list(self._coll(coll))

    async def count(self, coll):
        return len(self._coll(coll))

    async def insert_many(self, coll, docs):
        async with self.lock:
            self._coll(coll).extend(docs)
            self._dirty = True

    async def drop(self, coll):
        async with self.lock:
            self.data[coll] = []
            self._dirty = True

    async def inc_counter(self, key, amount=1):
        async with self.lock:
            self.data["counters"][key] = self.data["counters"].get(key, 0) + amount
            self._dirty = True

    async def get_counters(self):
        return dict(self.data["counters"])

    async def search_files_any(self, words, limit):
        """OR search — koi ek word match ho jaye (fallback ke liye)."""
        need = limit * 4
        out = []
        for d in self.data["files"]:
            t = d.get("title_lc", "")
            for w in words:
                if w in t:
                    out.append(d)
                    break
            if len(out) >= need:
                break
        return out

    async def search_files(self, words, limit):
        """words = lowercase word list. Pehle C-speed substring scan (bahut tez),
        phir chhote candidate set pe regex confirm."""
        need = limit * 4
        pool = self.data["files"]
        if not words:
            return pool[:need]
        # sabse lamba word pehle -> candidates sabse kam
        cand = [d for d in pool if words[0] in d.get("title_lc", "")]
        for w in words[1:]:
            cand = [d for d in cand if w in d.get("title_lc", "")]
            if not cand:
                break
        return cand[:need]


class MongoStore:
    """Motor (async MongoDB) — same API as JsonStore, super fast search."""

    def __init__(self, uri, dbname):
        from motor.motor_asyncio import AsyncIOMotorClient
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
        self.db = self.client[dbname]
        self.users, self.files = self.db["users"], self.db["files"]
        self.requests, self.counters = self.db["requests"], self.db["counters"]

    async def setup(self):
        await self.files.create_index([("title_lc", 1)])
        await self.files.create_index([("title", "text")])
        await self.files.create_index([("chat_id", 1), ("msg_id", 1)], unique=True)
        await self.users.create_index("user_id", unique=True)
        await self.requests.create_index("user_id", unique=True)

    async def upsert(self, coll, key, val, update):
        c = getattr(self, coll)
        ops = {"$set": update} if update else {"$setOnInsert": {key: val}}
        r = await c.find_one_and_update({key: val}, ops, upsert=True)
        return r or {key: val, **(update or {})}

    async def find_one(self, coll, key, val):
        return await getattr(self, coll).find_one({key: val})

    async def delete_one(self, coll, key, val):
        r = await getattr(self, coll).delete_many({key: val})
        return r.deleted_count

    async def all_docs(self, coll):
        return await getattr(self, coll).find().to_list(length=None)

    async def count(self, coll):
        return await getattr(self, coll).estimated_document_count() \
            if coll == "files" else await getattr(self, coll).count_documents({})

    async def insert_many(self, coll, docs):
        if docs:
            await getattr(self, coll).insert_many(docs, ordered=False)

    async def drop(self, coll):
        await getattr(self, coll).delete_many({})

    async def inc_counter(self, key, amount=1):
        await self.counters.update_one({"_id": "global"}, {"$inc": {key: amount}}, upsert=True)

    async def get_counters(self):
        d = await self.counters.find_one({"_id": "global"}) or {}
        d.pop("_id", None)
        return d

    async def search_files_any(self, words, limit):
        need = limit * 4
        if not words:
            return []
        cur = self.files.find(
            {"$or": [{"title_lc": {"$regex": re.escape(w)}} for w in words]},
            {"_id": 0, "title": 1, "title_lc": 1, "chat_id": 1, "msg_id": 1,
             "size": 1, "type": 1},
        ).limit(need)
        return await cur.to_list(length=need)

    async def search_files(self, words, limit):
        """words = lowercase word list. Mongo pe sirf sabse selective word ka regex
        (tezi ke liye), baaki words python me filter."""
        need = limit * 4
        if not words:
            return await self.files.find(
                {}, {"_id": 0, "title": 1, "chat_id": 1, "msg_id": 1, "size": 1, "type": 1}
            ).limit(need).to_list(length=need)
        anchor = max(words, key=len)                      # sabse lamba = sabse selective
        cur = self.files.find(
            {"title_lc": {"$regex": re.escape(anchor)}},
            {"_id": 0, "title": 1, "chat_id": 1, "msg_id": 1, "size": 1, "type": 1},
        ).limit(need * 3)
        docs = await cur.to_list(length=need * 3)
        rest = [w for w in words if w != anchor]
        if rest:
            docs = [d for d in docs
                    if all(w in (d.get("title_lc") or d.get("title", "").lower()) for w in rest)]
        return docs[:need]


async def build_store():
    if MONGO_URI:
        try:
            s = MongoStore(MONGO_URI, DB_NAME)
            await s.setup()
            log.info("✅ MongoDB connected -> %s", DB_NAME)
            return s, "MongoDB"
        except Exception as e:
            log.error("MongoDB fail (%s) -> JSON fallback", e)
    s = JsonStore(JSON_FILE)
    asyncio.create_task(s._saver())
    log.info("✅ JsonStore ready -> %s", JSON_FILE)
    return s, "JSON"

# ═══════════════════════════════ HELPERS ════════════════════════════════════

STORE, STORE_KIND = None, "JSON"
CLIENT: Client = None
USERBOT: Client = None
USERBOT_OK = False
USERBOT_ME = None
SEM_UB = asyncio.Semaphore(UB_CONCURRENCY)
BIG_MB = int(_get("BIG_MB", 150))                   # isse bari = "big file"
SEM_BIG = asyncio.Semaphore(int(_get("BIG_CONCURRENCY", 2)))  # bari files 2-at-a-time


# ── ADAPTIVE SEND THROTTLE ────────────────────────────────────────────────
# Har bot-send ke beech minimum gap. Normal me chhota (fast), flood aate hi
# khud badh jaata hai, fir dheere-dheere wapas fast ho jaata hai.
_GAP = {"cur": BOT_SEND_GAP, "last": 0.0}
_GAP_LOCK = asyncio.Lock()


async def send_throttle():
    """Global pacing — semaphore slot block kiye bina."""
    async with _GAP_LOCK:
        wait = _GAP["cur"] - (time.time() - _GAP["last"])
        if wait > 0:
            await asyncio.sleep(wait)
        _GAP["last"] = time.time()
    # har safe send ke baad gap thoda kam (wapas full speed ki taraf)
    if _GAP["cur"] > BOT_SEND_GAP:
        _GAP["cur"] = max(BOT_SEND_GAP, _GAP["cur"] * 0.9)


def throttle_backoff(wait_s):
    """FloodWait mila -> gap badha do (max 2s)."""
    _GAP["cur"] = min(2.0, max(_GAP["cur"] * 2, 0.4))
PEER_OK = set()          # jin chats ka access hash mil chuka
PEER_BAD = {}            # id -> ts (member nahi / resolve fail; 10 min yaad rakho)
WARM_DIALOGS = int(_get("WARM_DIALOGS", 5000))
INDEX_STATE = {"running": False, "count": 0, "last": 0}
BUSY, LAST_SEARCH = set(), {}
BUSY_INFO = {}        # chat_id -> {"task","uid","ts"} — cancel button ke liye
BUSY_STALE = int(_get("BUSY_STALE", 1800))   # 30 min purani BUSY = auto-clear


def busy_add(chat_id, uid):
    BUSY.add(chat_id)
    try:
        task = asyncio.current_task()
    except Exception:
        task = None
    BUSY_INFO[chat_id] = {"task": task, "uid": uid, "ts": time.time()}


def busy_del(chat_id):
    BUSY.discard(chat_id)
    BUSY_INFO.pop(chat_id, None)
ASK_PENDING = {}        # chat_id -> {uid, pairs, ts}  ("kitni files?" ka wait)
DL_PROG = {}            # (chat,mid) -> [downloaded, total]  (live MB progress)
SEM_SEND = asyncio.Semaphore(SEND_CONCURRENCY)
SEM_FWD = asyncio.Semaphore(FWD_CONCURRENCY)


def persist_env(updates: dict):
    """Runtime change ko .env me bhi save karo — restart pe bhi bana rahe."""
    try:
        f = Path(os.environ.get("ENV_FILE", ".env"))
        lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
        out, done = [], set()
        for ln in lines:
            st = ln.strip()
            if st and not st.startswith("#") and "=" in st:
                k = st.split("=", 1)[0].strip()
                if k in updates:
                    out.append(f"{k}={updates[k]}")
                    done.add(k)
                    continue
            out.append(ln)
        for k, v in updates.items():
            if k not in done:
                out.append(f"{k}={v}")
            os.environ[k] = str(v)
        f.write_text("\n".join(out) + "\n", encoding="utf-8")
        log.info("💾 .env updated: %s", ", ".join(updates))
        return True
    except Exception as e:
        log.warning("env persist fail: %s", e)
        return False


def esc(t):
    return html.escape(str(t if t is not None else ""))


def exp_str(ts):
    if not ts:
        return ""
    try:
        return datetime.utcfromtimestamp(ts).strftime("%d-%b-%Y %H:%M UTC")
    except Exception:
        return ""


def is_expired(u):
    exp = u.get("expiry")
    return (not exp) or time.time() > exp


def plan_label(u):
    if u.get("user_id") in ADMINS:
        return "🛡️ ADMIN"
    p = PLAN_BY_KEY.get(u.get("plan"))
    if p and not is_expired(u):
        return f"👑 {p['name']}"
    return "🆓 FREE"


def user_limit(u):
    if u.get("user_id") in ADMINS:
        return ADMIN_LIMIT
    if u.get("plan") and not is_expired(u):
        return min(int(u.get("limit") or FREE_LIMIT), MAX_RESULTS)
    return FREE_LIMIT


def clean_title(m):
    """Message -> best display name."""
    if getattr(m, "document", None) and m.document.file_name:
        return m.document.file_name.strip()
    for a in ("video", "audio", "animation", "photo", "voice", "sticker"):
        o = getattr(m, a, None)
        if o is not None and getattr(o, "file_name", None):
            return o.file_name.strip()
    cap = re.sub(r"<[^>]+>", "", (m.caption or m.text or ""))
    cap = re.sub(r"https?://\S+", "", cap).strip()
    first = cap.splitlines()[0] if cap else ""
    return (first or "Untitled File")[:120]


def media_type(m):
    if getattr(m, "video", None):
        return "video"
    if getattr(m, "document", None):
        return "document"
    if getattr(m, "audio", None) or getattr(m, "voice", None):
        return "audio"
    if getattr(m, "photo", None):
        return "photo"
    return "other"


def msg_size(m):
    for a in ("video", "document", "audio", "voice", "animation"):
        o = getattr(m, a, None)
        if o is not None:
            return getattr(o, "size", 0) or getattr(o, "file_size", 0) or 0
    return 0


def hsize(b):
    if not b:
        return ""
    b = float(b)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{int(b)}B" if u == "B" else f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}PB"


def public_link(chat_id, msg_id):
    cid = str(chat_id)
    return f"https://t.me/c/{cid[4:] if cid.startswith('-100') else cid}/{msg_id}"


def username_link(u):
    if getattr(u, "username", None):
        return f"@{u.username}"
    return f"<a href='tg://user?id={u.id}'>{esc(getattr(u, 'first_name', '') or u.id)}</a>"


def regex_from_query(q):
    """MongoDB/Python-safe regex: har word kahin bhi match ho (flexible SRC)."""
    parts = [re.escape(p) for p in re.split(r"\s+", q.strip()) if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "(?=.*" + ")(?=.*".join(parts) + ")"


def rank(results, query):
    """Best matches pehle: exact > prefix > contains > zyada words match > chhota naam."""
    q = query.lower().strip()
    words = [w for w in re.split(r"\s+", q) if w]

    def score(r):
        t = (r.get("title") or "").lower()
        s = 0
        if t == q:
            s += 10000
        if t.startswith(q):
            s += 5000
        if q in t:
            s += 2500
        hits = 0
        for i, w in enumerate(words):
            if w in t:
                hits += 1
                s += 100 - i * 5
                if t.startswith(w):
                    s += 60 - i * 5
        s += hits * 200                     # jitne zyada words match, utna upar
        s += max(0, 30 - len(t) // 12)      # chhote (saaf) naam upar
        return s

    return sorted(results, key=score, reverse=True)


def dedupe(results):
    seen, out = set(), []
    for r in results:
        k = (r.get("chat_id"), r.get("msg_id"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

# ═══════════════════════════════ USER LAYER ═════════════════════════════════

async def get_user(user, chat_id=None):
    uid = user.id if hasattr(user, "id") else int(user)
    doc = await STORE.find_one("users", "user_id", uid)
    upd = {"last_seen": time.time()}

    if doc is None:
        upd.update({
            "user_id": uid,
            "name": getattr(user, "first_name", "") or "",
            "username": getattr(user, "username", None),
            "chat_id": chat_id or uid,
            "plan": None, "limit": FREE_LIMIT, "expiry": 0, "forward": 0,
            "joined": time.time(), "searches": 0, "files_got": 0,
        })
        doc = await STORE.upsert("users", "user_id", uid, upd)
        doc = dict(doc or {}, **upd)
        if LOG_CHANNEL:
            try:
                await CLIENT.send_message(
                    LOG_CHANNEL,
                    f"🆕 <b>New User</b>\n👤 {username_link(user)}\n🔗 <code>{uid}</code>",
                    disable_web_page_preview=True)
            except Exception:
                pass
    else:
        doc = dict(doc)
        if getattr(user, "username", None):
            upd["username"] = user.username
        if getattr(user, "first_name", None):
            upd["name"] = user.first_name
        if doc.get("plan") and doc.get("expiry") and time.time() > doc["expiry"]:
            upd.update({"plan": None, "limit": FREE_LIMIT, "expiry": 0})
            try:
                await CLIENT.send_message(
                    doc.get("chat_id") or uid,
                    f"⏰ <b>Aapka Premium plan EXPIRE ho gaya!</b>\n\n"
                    f"Ab aap <b>FREE ({FREE_LIMIT} files)</b> par ho.\n"
                    f"💎 Renew: /plans")
            except Exception:
                pass
        await STORE.upsert("users", "user_id", uid, upd)
        doc.update(upd)

    if doc.get("plan") and is_expired(doc):
        doc.update({"plan": None, "limit": FREE_LIMIT, "expiry": 0})
    return doc


async def bump_usage(uid, chat_id, nfiles):
    doc = await STORE.find_one("users", "user_id", uid) or {}
    await STORE.upsert("users", "user_id", uid, {
        "searches": int(doc.get("searches") or 0) + 1,
        "files_got": int(doc.get("files_got") or 0) + nfiles,
        "last_search": time.time(), "chat_id": chat_id,
    })
    await STORE.inc_counter("searches", 1)
    await STORE.inc_counter("files_sent", nfiles)

# ═══════════════════════════════ SEARCH ═════════════════════════════════════

def query_words(q):
    """Query -> lowercase words (lambe word pehle = fast filtering)."""
    w = [re.sub(r"[^\w\-.+ ]", "", x).lower() for x in re.split(r"\s+", q.strip())]
    w = [x for x in w if x]
    return sorted(set(w), key=len, reverse=True)


def _slim(d):
    return {"title": d.get("title"), "chat_id": d.get("chat_id"), "msg_id": d.get("msg_id"),
            "size": d.get("size"), "type": d.get("type")}


async def search_index(query, limit):
    """Pehle AND (saare words) — kam result mile to OR (koi ek word) fallback,
    taaki user ko kabhi bhi '0 results' na mile jab tak kuch bhi related hai."""
    words = query_words(query)
    if not words:
        return []
    try:
        docs = await STORE.search_files(words, limit)
        mode = "and"
        if len(docs) < max(3, limit // 5) and len(words) > 1:
            extra = await STORE.search_files_any(words, limit)
            if extra:
                docs = dedupe([_slim(d) for d in docs] + [_slim(d) for d in extra])
                mode = "and+or"
                return docs
        return [_slim(d) for d in docs]
    except Exception as e:
        log.error("index search error: %s", e)
        return []


async def search_live(query, limit):
    """Index me na mile to channel me live MTProto search."""
    if not DB_CHANNEL:
        return []
    out = []
    try:
        async for m in CLIENT.search_messages(chat_id=DB_CHANNEL, query=query,
                                              filter=enums.MessagesFilter.EMPTY,
                                              limit=limit + 100):
            if getattr(m, "empty", False):
                continue
            out.append({"title": clean_title(m), "chat_id": m.chat.id, "msg_id": m.id,
                        "size": msg_size(m), "type": media_type(m)})
            if len(out) >= limit:
                break
    except Exception as e:
        log.warning("live search: %s", e)
    return out


async def do_search(query, limit):
    """Returns (capped_results, total_found, source)."""
    cap = max(limit, MAX_RESULTS)
    res = await search_index(query, cap)
    src = "index"
    if len(res) < max(3, limit // 5):
        live = await search_live(query, cap)
        if live:
            res = dedupe(res + live)
            src = "index+live" if res else "live"
    res = dedupe(rank(res, query))
    return res[:limit], len(res), src

# ═══════════════════════════════ LINK MODE ══════════════════════════════════
#  User kisi bhi group/channel ka link bhejta hai -> bot file nikal ke deta hai.
#  Flow:  userbot -> CACHE_CHANNEL (server-side copy) -> bot -> user
#  (bot khud un chats ko nahi padh sakta jisme wo member nahi, isliye userbot)

LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(c/)?"
    r"([A-Za-z0-9_+.\-]+)"
    r"((?:/\d+(?:[-\u2013]\d+)?)+)?"
    r"(\?single)?",
    re.I,
)
BARE_RE = re.compile(r"(?<!\d)(-100\d{6,})(?:[\s/:]+)(\d{1,9})(?![\d])")


TOPIC_OF = {}     # (chat, msg_id) -> topic_id   (forum topic links ke liye)


def parse_links(text):
    """Text se saare (chat, msg_id) pairs nikalo. Duplicates hata deta hai.

    Support:
      https://t.me/c/1234567890/45            single message
      t.me/channelname/45                     public channel
      t.me/c/1234567890/45-60                 range (45..60)
      t.me/c/1234567890/45/60?single          multi-select range
      t.me/c/1234567890/77/100                ★ TOPIC link (77=topic, 100=msg)
      t.me/c/1234567890/77/100/120?single     topic multi-select (100..120)
      -1001234567890 45                       bare pair
    """
    out, seen = [], set()

    for m in LINK_RE.finditer(text or ""):
        is_c, ident, tail, qsingle = m.group(1), m.group(2), m.group(3), m.group(4)
        if not tail:
            continue
        if ident.lower() in ("s", "c", "proxy", "socks", "addstickers", "setlanguage",
                             "share", "confirmphone", "login", "iv", "bg", "invoice"):
            continue
        if is_c or ident.lstrip("-").isdigit():
            digits = ident.lstrip("-")
            chat = int(digits) if ident.startswith("-100") else int(f"-100{digits}")
        else:
            chat = ident

        nums, dash = [], False
        for seg in tail.strip("/").split("/"):
            if not seg:
                continue
            if re.search(r"[-\u2013]", seg):
                dash = True
            for x in re.split(r"[-\u2013]", seg):
                if x.isdigit():
                    nums.append(int(x))
        if not nums:
            continue

        if len(nums) == 1:
            ids = list(nums)                          # single message
        elif len(nums) == 2 and not qsingle and not dash:
            ids = [nums[1]]                           # ★ TOPIC: /<topic>/<msg>
            # topic id yaad rakho -> scan sirf isi topic ke andar hoga
            TOPIC_OF[(chat, nums[1])] = nums[0]
        else:
            a2, b2 = sorted(nums[-2:])                # range (last 2 numbers)
            ids = list(range(a2, min(b2, a2 + MAX_RANGE - 1) + 1))

        for i in ids:
            k = (chat, i)
            if k not in seen:
                seen.add(k)
                out.append(k)

    for m in BARE_RE.finditer(text or ""):
        k = (int(m.group(1)), int(m.group(2)))
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


async def ensure_peer(chat_id) -> bool:
    """Channel/group ka access hash pakka karo.

    Telegram private chats ke liye access hash chahiye hota hai jo sirf tab
    milta hai jab account uska member ho aur dialogs/participants fetch hue hon.
    Fresh (in-memory) session me ye cache khali hota hai -> PEER_ID_INVALID.
    Isliye: pehle try, fail ho to dialogs scan karke dhundo.
    """
    if isinstance(chat_id, str):
        return True                      # username khud resolve ho jata hai
    if chat_id in PEER_OK:
        return True
    if time.time() - PEER_BAD.get(chat_id, 0) < 120:
        return False
    for _fn in ("get_chat", "resolve_peer"):
        try:
            await getattr(USERBOT, _fn)(chat_id)
            PEER_OK.add(chat_id)
            return True
        except Exception:
            pass
    for attempt in range(2):
        try:
            n = 0
            t_start = time.time()
            async for d in USERBOT.get_dialogs():
                n += 1
                if d.chat.id == chat_id:
                    PEER_OK.add(chat_id)
                    log.info("🔑 peer resolve via dialogs: %s (%s)", chat_id, d.chat.title)
                    return True
                if n >= 5000 or time.time() - t_start > PEER_SCAN_MAX:
                    log.warning("peer scan timeout: %s dialogs %.0fs", n, time.time() - t_start)
                    break
            break
        except Exception as e:
            log.warning("peer scan fail: %s", e)
            if "AUTH_KEY" in str(e).upper() and attempt == 0:
                await asyncio.sleep(4)     # doosri session ka conflict — ruk ke retry
                continue
            break
    PEER_BAD[chat_id] = time.time()
    return False


async def userbot_watchdog():
    """Userbot mar jaye (session conflict / network) to khud reconnect karo.

    Render deploy switch ke waqt 2-4 sec purani+nayi instance dono same session
    use karti hain -> AUTH_KEY_DUPLICATED -> naya userbot fail. Watchdog use
    45 sec me khud thik kar deta hai.
    """
    while True:
        await asyncio.sleep(45)
        try:
            alive = USERBOT_OK and USERBOT is not None and getattr(USERBOT, "is_connected", False)
        except Exception:
            alive = False
        if alive:
            continue
        log.info("🔁 watchdog: userbot down hai — reconnect kar raha hoon…")
        try:
            if await start_userbot():
                asyncio.create_task(warm_peer_cache())
                log.info("🔁 watchdog: userbot wapas online ✅")
        except Exception as e:
            log.warning("watchdog retry fail: %s", e)


async def warm_peer_cache():
    """Startup pe dialogs fetch karke access hashes cache karo (fast links)."""
    if not USERBOT_OK:
        return
    try:
        n = 0
        async for d in USERBOT.get_dialogs():
            PEER_OK.add(d.chat.id)
            n += 1
            if n >= WARM_DIALOGS:
                break
        log.info("🔑 peer cache warm: %d chats", n)
        try:
            await USERBOT.get_chat(CACHE_CHANNEL)
            log.info("🗄️ post-warm cache channel OK: %s", CACHE_CHANNEL)
        except Exception as e:
            log.warning("post-warm cache check fail: %s", e)
    except Exception as e:
        log.warning("warm cache fail: %s", e)


async def ub_ready():
    return bool(USERBOT_OK and USERBOT and CACHE_CHANNEL)


async def link_error_msg():
    if not USERBOT_OK:
        return (
            "⚠️ <b>Link mode abhi ready nahi hai</b>\n\n"
            "Kisi bhi group/channel ke link se file nikalne ke liye bot ke paas "
            "<b>userbot session</b> hona chahiye (bot khud un chats ko access nahi "
            "kar sakta jisme wo member nahi hai).\n\n"
            f"👉 Admin ({SUPPORT_TXT}) se bolo setup complete karne ko.")
    if not CACHE_CHANNEL:
        return (
            "⚠️ <b>CACHE_CHANNEL set nahi hai</b>\n\n"
            "Admin ko ek <b>private channel</b> bana ke usme bot ko admin banana hoga, "
            "fir us channel ka post forward karke <code>/setcache</code> bhejna hoga.")
    return None


SPIN = "⠋⠙⠸⠴⠧⠏"          # smooth braille spinner


def pbar(done, total, width=15):
    """Clean loading bar: [████████⚡░░░░░░░]  / complete: [███████████████]"""
    total = max(1, total)
    filled = round(done / total * width)
    if done >= total:
        return "█" * width
    return "█" * filled + "⚡" + "░" * (width - filled - 1)


def spin():
    return SPIN[int(time.time() * 10) % len(SPIN)]


def kb_ask_single(limit):
    """Single link ke liye: 1 = sirf ye file, ya neeche ki N files."""
    rows = [[InlineKeyboardButton("1 📄 (sirf ye file)", callback_data="ask:1")]]
    row = []
    for o in (10, 25, 50, 100, 200):
        if o > limit:
            break
        row.append(InlineKeyboardButton(f"{o} 📄", callback_data=f"ask:{o}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="ask:cancel")])
    return InlineKeyboardMarkup(rows)


def kb_ask(mx):
    """'Kitni files chahiye?' ke buttons."""
    opts = [o for o in (5, 10, 20, 50, 100) if o < mx]
    rows, row = [], []
    for o in opts:
        row.append(InlineKeyboardButton(f"{o} 📄", callback_data=f"ask:{o}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(f"📚 ALL {mx} files", callback_data=f"ask:{mx}")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="ask:cancel")])
    return InlineKeyboardMarkup(rows)


async def scan_topic(chat, topic_id, start_id, need, on_progress=None):
    """Forum TOPIC ke andar hi media dhoondo (id-range scan ki jagah).

    Topic ke messages chat me bikhre hote hain — beech me doosre topics ke
    messages aate hain. Isliye id+1, id+2... scan karna galat hai.
    `get_discussion_replies` (RPC messages.GetReplies) sirf usi topic ke
    messages deta hai, aur ye flood-limited bhi nahi hai.
    """
    got, seen_n, all_ids, sample = [], 0, [], []
    try:
        async for mm in USERBOT.get_discussion_replies(chat, topic_id):
            seen_n += 1
            if mm and not getattr(mm, "empty", False):
                all_ids.append(mm.id)
                if len(sample) < 5:
                    sample.append("%s:%s" % (mm.id, getattr(mm, "media", None)))
                if _has_media(mm):
                    got.append(mm.id)
            if seen_n % 200 == 0:
                if on_progress:
                    try:
                        await on_progress(0, mm.id if mm else start_id)
                    except Exception:
                        pass
                await asyncio.sleep(0)
            if seen_n >= TOPIC_SCAN_MAX:
                break
    except FloodWait as fe:
        w = int(getattr(fe, "value", 30) or 30)
        log.warning("⏳ topic scan FloodWait %ss", w)
        if w <= 60:
            await asyncio.sleep(w + 2)
            return await scan_topic(chat, topic_id, start_id, need, on_progress)
        return None
    except Exception as e:
        log.warning("topic scan fail (topic=%s): %s", topic_id, e)
        return None

    got = sorted(set(got))
    all_ids = sorted(set(all_ids))
    log.info("scan_topic: topic=%s me %s media / %s msgs (scanned=%s) sample=%s",
             topic_id, len(got), len(all_ids), seen_n, ",".join(sample))

    # GetReplies kabhi-kabhi adhoore Message objects deta hai (media field khali).
    # Us case me sirf IDs le kar full messages fetch karo — ye 1-2 RPC call hai.
    if not got and all_ids:
        log.info("scan_topic: inline media 0 — %s ids full-fetch kar rahe", len(all_ids))
        for i in range(0, len(all_ids), 100):
            chunk = all_ids[i:i + 100]
            for _a in range(3):
                try:
                    full = await USERBOT.get_messages(chat, chunk)
                    if not isinstance(full, (list, tuple)):
                        full = [full]
                    for fm in full:
                        if fm and not getattr(fm, "empty", False) and _has_media(fm):
                            got.append(fm.id)
                    break
                except FloodWait as fe:
                    w = int(getattr(fe, "value", 30) or 30)
                    log.warning("⏳ topic full-fetch FloodWait %ss", w)
                    if w > 300:
                        break
                    if on_progress:
                        try:
                            await on_progress(len(got), chunk[0], w)
                        except Exception:
                            pass
                    await asyncio.sleep(w + 2)
                except Exception as e:
                    log.warning("topic full-fetch fail: %s", e)
                    break
        got = sorted(set(got))
        log.info("scan_topic: full-fetch ke baad %s media mile", len(got))

    if not got:
        return None
    fwd = [i for i in got if i >= start_id]
    if not fwd:
        # link topic ke aakhir me tha -> poore topic ki files de do
        log.info("scan_topic: %s ke aage kuch nahi, poora topic use kar rahe", start_id)
        fwd = got
    return [(chat, i) for i in fwd[:need]]


async def scan_forward(chat, start_id, need, cap=5000, on_progress=None,
                       topic=None):
    """Ek message id se SHURU karke neeche ki files collect karo.

    Topic/channel me files lagatar hoti hain — user sirf pehla link deta hai,
    bot aage badh kar `need` files nikal leta hai (100-100 batch me, fast).
    Video/PDF/photo — sab media count hota hai; text messages skip.
    """
    # ★ Agar topic link hai to pehle topic-scan (sahi + fast + flood-free)
    if topic:
        tp = await scan_topic(chat, topic, start_id, need, on_progress)
        if tp:
            return tp
        log.info("topic scan se kuch nahi — id-range scan pe fallback")

    out = []
    cid = start_id
    end = start_id + cap
    empty_rounds = 0
    while len(out) < need and cid <= end:
        batch = list(range(cid, min(cid + 100, end + 1)))
        msgs = None
        # PEHLE history method (messages.GetHistory) — ye alag RPC hai aur
        # channels.GetMessages jaisa flood-limited nahi hota. Isse scan
        # tab bhi chalta hai jab GetMessages pe 30s ka rate-limit laga ho.
        if not SCAN_NO_HIST:
            try:
                hist = []
                async for _mm in USERBOT.get_chat_history(
                        chat, limit=len(batch), offset_id=batch[-1] + 1):
                    if _mm and _mm.id < batch[0]:
                        break
                    hist.append(_mm)
                if hist:
                    msgs = hist
            except FloodWait as fe:
                w = int(getattr(fe, "value", 30) or 30)
                log.warning("⏳ history FloodWait %ss — GetMessages pe switch", w)
            except Exception as e:
                log.warning("history scan fail (%s) — GetMessages pe switch", e)
        for _a in range(3 if msgs is None else 0):   # fallback: GetMessages
            try:
                msgs = await USERBOT.get_messages(chat, batch)
                break
            except FloodWait as fe:
                w = int(getattr(fe, "value", 30) or 30)
                log.warning("⏳ scan FloodWait %ss (ids %s-%s) — wait karke retry",
                            w, batch[0], batch[-1])
                if w > 300:
                    return out[:need]
                await asyncio.sleep(w + 2)
                if on_progress:
                    try:
                        await on_progress(len(out), cid, w)
                    except Exception:
                        pass
            except Exception as e:
                log.warning("scan_forward get_messages fail (ids %s-%s): %s",
                            batch[0], batch[-1], e)
                break
        if msgs is None:
            break
        if not isinstance(msgs, (list, tuple)):
            msgs = [msgs]
        alive = 0
        for mm in msgs:
            if mm and not getattr(mm, "empty", False):
                alive += 1
                if _has_media(mm):
                    out.append((chat, mm.id))
        if alive == 0:
            empty_rounds += 1
            if empty_rounds >= 3:      # 300 messages tak kuch nahi = khatam
                log.info("scan_forward: %s ke baad koi message nahi", cid)
                break
        else:
            empty_rounds = 0
        cid = batch[-1] + 1
        if on_progress:
            try:
                await on_progress(len(out), cid)
            except Exception:
                pass
    return out[:need]


# ye "media" nahi hain — inhe file nahi maana jayega
_SKIP_MEDIA = {"WEB_PAGE", "POLL", "CONTACT", "LOCATION", "VENUE",
               "DICE", "GAME", "STORY", "GIVEAWAY", "GIVEAWAY_WINNERS"}


def _media_kind(mm):
    """Message me kis type ka media hai -> naam (ya '' agar koi nahi)."""
    if not mm:
        return ""
    for attr in ("document", "video", "audio", "photo", "voice",
                 "animation", "video_note", "sticker"):
        if getattr(mm, attr, None):
            return attr
    # koi naya/unknown media type bhi pakdo (pyrogram ka media enum)
    md = getattr(mm, "media", None)
    if md:
        nm = (getattr(md, "name", None) or str(md).split(".")[-1] or "").upper()
        if nm and nm not in _SKIP_MEDIA:
            return nm.lower()
    return ""


def _has_media(mm):
    return bool(_media_kind(mm))


async def scan_media(pairs):
    """Sirf wo (chat, mid) pairs jitme asli media/file hai.

    Returns (media_pairs, access_fail, scan_fail) taaki galat error message na aaye.
    """
    by_chat = {}
    for chat, mid in pairs:
        by_chat.setdefault(chat, []).append(mid)
    out, access_fail, scan_fail = [], False, False
    for chat, ids in by_chat.items():
        if not await ensure_peer(chat):
            access_fail = True
            continue
        msgs = None
        for attempt in range(2):
            try:
                msgs = await USERBOT.get_messages(chat, ids)
                break
            except Exception as e:
                if "AUTH_KEY" in str(e).upper() and attempt == 0:
                    await asyncio.sleep(3)      # session conflict — ek beat ruko
                    continue
                scan_fail = True
        if msgs is None:
            continue
        if not isinstance(msgs, (list, tuple)):
            msgs = [msgs]
        got = {mm.id: mm for mm in msgs if mm and not getattr(mm, "empty", False)}
        for mid in ids:
            if _has_media(got.get(mid)):
                out.append((chat, mid))   # web_page preview count nahi hoga
    return out, access_fail, scan_fail


def _media_size(src):
    for attr in ("document", "video", "animation", "audio", "voice", "photo"):
        sz = getattr(getattr(src, attr, None), "file_size", 0)
        if sz:
            return sz
    return 0


async def _grab_thumb(src):
    """Source message ki ORIGINAL thumbnail download karo -> file path.

    Video/document/audio/animation sab pe thumbs list hoti hai; sabse badi
    lete hain taaki quality achhi rahe. Fail ho to None (koi crash nahi).
    """
    for attr in ("video", "document", "audio", "animation", "video_note"):
        o = getattr(src, attr, None)
        thumbs = getattr(o, "thumbs", None) if o else None
        if thumbs:
            try:
                return await USERBOT.download_media(
                    thumbs[-1].file_id,
                    file_name=os.path.join(THUMB_DIR_TMP,
                                           f"th_{src.id}_{int(time.time()*1000)}.jpg"))
            except Exception as e:
                log.warning("thumb download fail: %s", e)
            return None
    return None


async def _reupload_via_download(src, msg_id):
    """Noforwards channel se file: DISK pe download -> cache me fresh upload.

    Bari files (>BIG_MB) SEM_BIG se ek-ek chalti hain taaki poori bandwidth
    ek file ko mile aur wo jaldi complete ho (progress bar zinda rehti hai).
    """
    size = _media_size(src)
    if size and size > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"file {size // (1024 * 1024)}MB hai — limit {MAX_FILE_MB}MB")
    try:
        stv = os.statvfs("/tmp")
        free_mb = (stv.f_bavail * stv.f_frsize) // 1048576
        if size and size > (free_mb - 150) * 1048576:
            raise ValueError(
                f"file {size // 1048576}MB hai par server disk me sirf {free_mb}MB khaali — "
                "itni bari file abhi nahi utar sakti")
    except OSError:
        pass
    tmp = tempfile.mkstemp(suffix=".media", dir="/tmp")[1]
    log.info("⬇️ download shuru: msg %s (%.1fMB)", msg_id, size / 1048576)
    dlkey = (getattr(src.chat, "id", 0), msg_id)
    DL_PROG[dlkey] = [0, size, time.time()]

    async def _dl_cb(cur, tot, *a):
        rec = DL_PROG.get(dlkey)
        t0 = rec[2] if rec and len(rec) > 2 else time.time()
        DL_PROG[dlkey] = [cur, tot or size, t0]

    dl_timeout = 600 + (size // 1048576) * 2      # bari file = zyada waqt
    sem = SEM_BIG if size > BIG_MB * 1048576 else SEM_UB
    async with sem:                              # bari file = poori bandwidth
        try:
            # ★ STALL WATCHDOG: agar download STALL_SEC tak 1 byte bhi aage
            # na badhe to connection mar chuka hai -> abort karke retry.
            # (pehle ye poore dl_timeout tak latka rehta tha = "file beech
            #  me ruk gayi")
            dl_task = asyncio.ensure_future(
                USERBOT.download_media(src, file_name=tmp, progress=_dl_cb))

            async def _stall_guard():
                last, last_t = -1, time.time()
                while not dl_task.done():
                    await asyncio.sleep(10)
                    rec = DL_PROG.get(dlkey) or [0, 0, 0]
                    if rec[0] != last:
                        last, last_t = rec[0], time.time()
                    elif time.time() - last_t > STALL_SEC:
                        log.warning("🧊 download STALL (%ss koi progress nahi) "
                                    "msg %s — abort", STALL_SEC, msg_id)
                        dl_task.cancel()
                        return

            guard = asyncio.ensure_future(_stall_guard())
            try:
                path = await asyncio.wait_for(dl_task, timeout=dl_timeout)
            except asyncio.CancelledError:
                raise TimeoutError("download stall — dobara koshish")
            finally:
                guard.cancel()
            if not path:
                return None
            log.info("⬆️ download complete, upload to cache: msg %s", msg_id)
            name = (getattr(getattr(src, "document", None), "file_name", None)
                    or getattr(getattr(src, "video", None), "file_name", None)
                    or getattr(getattr(src, "animation", None), "file_name", None)
                    or getattr(getattr(src, "audio", None), "file_name", None)
                    or f"file_{msg_id}")
            ck = dict(caption=src.caption or None,
                      caption_entities=src.caption_entities or None)
            # ★ ORIGINAL THUMBNAIL: re-upload me Telegram apne aap thumb nahi
            # rakhta (kaali screen aa jaati hai). Isliye source ki thumb
            # download karke saath bhejte hain + video ke attributes bhi.
            thp = await _grab_thumb(src)
            try:
                if src.video:
                    v = src.video
                    return await USERBOT.send_video(
                        CACHE_CHANNEL, path, file_name=name, thumb=thp,
                        duration=v.duration or 0, width=v.width or 0,
                        height=v.height or 0, supports_streaming=True, **ck)
                if src.photo:
                    return await USERBOT.send_photo(CACHE_CHANNEL, path, **ck)
                if src.audio:
                    a = src.audio
                    return await USERBOT.send_audio(
                        CACHE_CHANNEL, path, file_name=name, thumb=thp,
                        duration=a.duration or 0, performer=a.performer,
                        title=a.title, **ck)
                if src.voice:
                    return await USERBOT.send_voice(CACHE_CHANNEL, path, **ck)
                if src.animation:
                    an = src.animation
                    return await USERBOT.send_animation(
                        CACHE_CHANNEL, path, file_name=name, thumb=thp,
                        duration=an.duration or 0, width=an.width or 0,
                        height=an.height or 0, **ck)
                if src.video_note:
                    return await USERBOT.send_video_note(CACHE_CHANNEL, path,
                                                         thumb=thp)
                return await USERBOT.send_document(CACHE_CHANNEL, path,
                                                   file_name=name, thumb=thp,
                                                   **ck)
            finally:
                if thp:
                    try:
                        os.remove(thp)
                    except Exception:
                        pass
        finally:
            DL_PROG.pop(dlkey, None)
            try:
                os.remove(tmp)
            except Exception:
                pass


# ══════════════════ CUSTOM THUMBNAIL + CAPTION ENGINE ════════════════════
USER_SET   = {}        # uid -> settings dict (memory cache)
THUMB_DIR  = "/tmp/thumbs"
THUMB_DIR_TMP = "/tmp/srcthumbs"
os.makedirs(THUMB_DIR_TMP, exist_ok=True)
SET_WAIT   = {}        # uid -> "caption" | "cut" | "prefix" | "suffix" | "rename"

DEFAULT_SET = {
    "thumb": None,          # thumbnail file path
    "caption": None,        # custom caption template (None = original)
    "cut": [],              # original caption se ye words/lines HATAO
    "prefix": "",           # caption ke aage
    "suffix": "",           # caption ke peeche
    "keep_orig": True,      # original caption base rakho
    "sequence": True,       # files ORDER me bheji jaayein
}


async def get_set(uid):
    """User ki thumb/caption settings (store se, cache ke saath)."""
    if uid in USER_SET:
        return USER_SET[uid]
    doc = await STORE.find_one("settings", "user_id", uid) or {}
    st = dict(DEFAULT_SET)
    for k in DEFAULT_SET:
        if k in doc and doc[k] is not None:
            st[k] = doc[k]
    USER_SET[uid] = st
    return st


async def save_set(uid, **kw):
    st = await get_set(uid)
    st.update(kw)
    USER_SET[uid] = st
    try:
        await STORE.upsert("settings", "user_id", uid, dict(st, user_id=uid))
    except Exception:
        log.exception("save_set fail uid=%s", uid)
    return st


def apply_caption(orig, st, filename=""):
    """Original caption pe user ke rules lagao -> final caption."""
    txt = orig or ""

    # 1) CUT — jo parts user nahi chahta
    for bad in (st.get("cut") or []):
        if not bad:
            continue
        try:
            if bad.startswith("re:"):                     # regex cut
                txt = re.sub(bad[3:], "", txt, flags=re.I)
            else:                                         # plain text cut
                txt = re.sub(re.escape(bad), "", txt, flags=re.I)
        except re.error:
            txt = txt.replace(bad, "")

    # khali lines / extra spaces saaf
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()

    # 2) TEMPLATE — custom caption (placeholders ke saath)
    tpl = st.get("caption")
    if tpl:
        txt = (tpl.replace("{original}", txt)
                  .replace("{caption}", txt)
                  .replace("{filename}", filename or "")
                  .replace("{file_name}", filename or ""))
    elif not st.get("keep_orig", True):
        txt = ""

    # 3) PREFIX / SUFFIX
    pre, suf = st.get("prefix") or "", st.get("suffix") or ""
    if pre:
        txt = f"{pre}\n{txt}" if txt else pre
    if suf:
        txt = f"{txt}\n{suf}" if txt else suf

    return txt.strip()[:1024] or None


def _fname(msg):
    for a in ("document", "video", "audio", "animation"):
        o = getattr(msg, a, None)
        if o is not None and getattr(o, "file_name", None):
            return o.file_name
    return ""


async def send_by_file_id(client, dest_chat, msg, st=None):
    """Cache message ko file_id se DIRECT bhejo — sabse fast path.

    st = user settings (custom thumbnail + caption rules).
    """
    if st:
        cap = apply_caption(msg.caption or "", st, _fname(msg))
        ck = dict(caption=cap)                  # custom caption = entities drop
        if cap == (msg.caption or None):
            ck["caption_entities"] = msg.caption_entities or None
    else:
        ck = dict(caption=msg.caption or None,
                  caption_entities=msg.caption_entities or None)

    thumb = (st or {}).get("thumb")
    if thumb and not os.path.exists(thumb):
        thumb = None

    if msg.document:
        return await client.send_document(dest_chat, msg.document.file_id,
                                          thumb=thumb, **ck)
    if msg.video:
        return await client.send_video(dest_chat, msg.video.file_id,
                                       thumb=thumb, **ck)
    if msg.audio:
        return await client.send_audio(dest_chat, msg.audio.file_id, **ck)
    if msg.photo:
        return await client.send_photo(dest_chat, msg.photo.file_id, **ck)
    if msg.animation:
        return await client.send_animation(dest_chat, msg.animation.file_id, **ck)
    if msg.voice:
        return await client.send_voice(dest_chat, msg.voice.file_id, **ck)
    if msg.video_note:
        return await client.send_video_note(dest_chat, msg.video_note.file_id)
    if msg.sticker:
        return await client.send_sticker(dest_chat, msg.sticker.file_id)
    return None


async def fetch_one(chat, msg_id, dest_chat, stats, st=None):
    """Ek file: userbot -> cache -> user. FloodWait pe wait karke 1 retry —
    taaki Telegram ke temporary ban me bot ATKE nahi, khud resume ho."""
    for attempt in range(2):
        try:
            return await _fetch_one_try(chat, msg_id, dest_chat, stats, st)
        except FloodWait as e:
            wait = int(getattr(e, "value", 5) or 5)
            stats["flood"] = max(stats.get("flood", 0), wait)
            throttle_backoff(wait)
            if attempt == 0 and wait <= FLOOD_MAX_WAIT:
                log.warning("⏳ FloodWait %ss (msg %s) — wait karke 1 retry", wait, msg_id)
                await asyncio.sleep(wait + 1)
                continue
            return False, "", f"telegram ne {wait}s ka wait diya (flood)"


async def _fetch_one_try(chat, msg_id, dest_chat, stats, st=None):
    async with SEM_UB:
        cached_id = None
        try:
            if not await ensure_peer(chat):
                return (False, "",
                        "aap is group/channel me member nahi ho "
                        "(ya chat private hai) — pehle join karo")
            if not await ensure_peer(CACHE_CHANNEL):
                return False, "", "cache channel access nahi (warm-up pending)"
            src = await USERBOT.get_messages(chat, msg_id)
            if not src or getattr(src, "empty", False) or src.id is None:
                return False, "", "message nahi mila (deleted/private)"
            if not _has_media(src):
                _md = getattr(src, "media", None)
                _why = (getattr(_md, "name", None) or str(_md)) if _md else (
                    "sirf text" if (src.text or src.caption) else "khali/service msg")
                log.info("no-media msg %s in %s -> %s", msg_id, chat, _why)
                return False, clean_title(src), f"file nahi hai ({_why})"
            title = clean_title(src)

            try:
                # src pehle hi fetch ho chuka hai -> src.copy() use karo.
                # copy_message() andar se dobara GetMessages maarta hai, jo
                # flood-limited RPC hai (har file pe 2 calls = double flood).
                ids = await src.copy(CACHE_CHANNEL)
            except RPCError as ce:
                if "CHAT_FORWARDS_RESTRICTED" in str(ce):
                    # channel me "restrict saving content" ON hai -> copy blocked.
                    # Workaround: file DOWNLOAD karke fresh upload karo.
                    ids = await _reupload_via_download(src, msg_id)
                else:
                    raise
            cached_id = getattr(ids, "id", None) or (ids[0] if isinstance(ids, (list, tuple)) else None)
            if not cached_id:
                return False, title, "cache copy fail"

            cached_msg = await USERBOT.get_messages(CACHE_CHANNEL, cached_id)
            await send_throttle()          # flood-safe pacing (adaptive)
            delivered = None
            if cached_msg:
                try:
                    delivered = await send_by_file_id(CLIENT, dest_chat, cached_msg, st)
                except Exception as fe:
                    log.warning("file_id send fail (%s) -> copy fallback", fe)
            if delivered is None:
                for attempt in range(6):
                    try:
                        _cap = (apply_caption(cached_msg.caption or "", st,
                                              _fname(cached_msg))
                                if (st and cached_msg) else None)
                        await CLIENT.copy_message(dest_chat, CACHE_CHANNEL,
                                                  cached_id, caption=_cap)
                        break
                    except (ValueError, RPCError, KeyError) as e2:
                        txt2 = str(e2).upper()
                        if ("PEER_ID" in txt2 or "ID NOT FOUND" in txt2) and attempt < 5:
                            await asyncio.sleep(0.6 * (attempt + 1))
                            continue
                        raise
            if UB_DELAY:
                await asyncio.sleep(UB_DELAY)
            stats["ok"] += 1
            return True, title, ""
        except RPCError as e:
            txt = str(e)
            log.exception("fetch_one RPCError chat=%s msg=%s", chat, msg_id)
            if "CHANNEL_PRIVATE" in txt or "CHAT_WRITE_FORBIDDEN" in txt or "USER_NOT_PARTICIPANT" in txt:
                return False, "", "chat access nahi hai (userbot us group me nahi hai)"
            if "MSG_ID_INVALID" in txt or "MESSAGE_ID_EMPTY" in txt or "MESSAGE_DELETE_SKIP" in txt:
                return False, "", "message invalid/deleted"
            return False, "", txt[:90]
        except Exception as e:
            log.exception("fetch_one Exception chat=%s msg=%s", chat, msg_id)
            return False, "", str(e)[:90]
        finally:
            if CLEAN_CACHE and cached_id:
                try:
                    asyncio.get_event_loop().call_later(
                        CACHE_TTL,
                        lambda cid=cached_id: asyncio.ensure_future(_del_cached(cid)))
                except Exception:
                    pass


async def _del_cached(cid):
    try:
        await USERBOT.delete_messages(CACHE_CHANNEL, [cid])
    except Exception:
        pass


async def handle_links(m: Message, pairs, _from_ask=False, _user=None, _total=None):
    """Link mode ka main flow — limit check, fetch, progress, thank-you."""
    who = _user or m.from_user
    chat_id, uid, t0 = m.chat.id, who.id, time.time()

    # ── TURANT ACK ── kisi bhi slow kaam se PEHLE, taaki user ko chuppi na mile
    ack = None
    if not _from_ask:
        try:
            ack = await asyncio.wait_for(
                m.reply_text("🔗 <b>Link mila!</b> 🔍 check kar raha hoon…"),
                timeout=20)
        except Exception as _e:
            log.warning("⚠️ ACK send fail/slow: %s", _e)

    st = await get_set(uid)          # custom thumb / caption / sequence
    if chat_id in BUSY:
        info = BUSY_INFO.get(chat_id) or {}
        task = info.get("task")
        age = time.time() - info.get("ts", time.time())
        if task is None or task.done() or age > BUSY_STALE:
            if task and not task.done():
                task.cancel()
            busy_del(chat_id)
            log.warning("⚠️ BUSY stale-clear: chat=%s age=%.0fs", chat_id, age)
        else:
            return await m.reply_text(
                "⏳ <b>Ek request pehle se chal rahi hai</b> "
                "(shayad badi video download ho rahi hai).\n"
                f"🕐 <b>{int(age // 60)} min {int(age % 60)}s</b> se chal rahi hai.\n\n"
                "👇 Naya link bhejna ho to pehle purani request <b>cancel</b> karo:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Purani request CANCEL karo",
                                           callback_data="cancelreq")]]))
    if not _from_ask and time.time() - LAST_SEARCH.get(chat_id, 0) < SEARCH_FLOOD_GAP:
        await m.reply_text("⏳ Ek second ruko… fir bhejo.")
        return
    LAST_SEARCH[chat_id] = time.time()
    busy_add(chat_id, uid)

    err = await link_error_msg()
    if err:
        busy_del(chat_id)
        return await m.reply_text(err)

    u = await get_user(who, chat_id)
    limit, tier = user_limit(u), plan_label(u)

    # ── "KITNI FILES CHAHIYE?" — scan + question ─────────────────────────
    if ASK_COUNT and not _from_ask and len(pairs) == 1:
        chat, start = pairs[0]
        try:
            _ok = await asyncio.wait_for(ensure_peer(chat), timeout=PEER_SCAN_MAX + 20)
        except asyncio.TimeoutError:
            log.warning("ensure_peer TIMEOUT chat=%s", chat)
            _ok = False
        except Exception as e:
            log.warning("ensure_peer error chat=%s: %s", chat, e)
            _ok = False
        if not _ok:
            busy_del(chat_id)
            _t = (f"🔒 <b>IS CHAT TAK ACCESS NAHI</b>\n"
                  f"━━━━━━━━━━━━━━━━━━━\n"
                  f"🆔 <code>{chat}</code>\n\n"
                  f"❗ Main (<b>@{(USERBOT_ME.username if USERBOT_ME else 'userbot')}</b>) "
                  f"is group/channel ka <b>member nahi hoon</b>.\n\n"
                  f"✅ <b>2 me se koi ek karo:</b>\n"
                  f"1️⃣ Us group ka <b>invite link</b> yahan bhejo\n"
                  f"    (<code>t.me/+xxxxx</code>) — main khud join kar lunga ⚡\n"
                  f"2️⃣ Ya mujhe us group me <b>add</b> kar do\n\n"
                  f"📌 Uske baad post link dobara bhejo 🫧")
            if ack:
                try:
                    return await ack.edit_text(_t)
                except Exception:
                    pass
            return await m.reply_text(_t)
        ASK_PENDING[chat_id] = {"uid": uid, "mode": "fwd", "chat": chat,
                                "start": start, "ts": time.time(),
                                "topic": TOPIC_OF.get((chat, start))}
        busy_del(chat_id)
        _q = (
            f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄✨\n"
            f"🔗 <b>LINK MILA!</b>\n"
            f"📚 Is link se <b>NEECHE ki files</b> bhi nikaal sakte ho\n\n"
            f"🎛️ <b>KITNI FILES CHAHIYE?</b>\n"
            f"👇 Button dabao ya number likho (1–{limit})\n"
            f"💡 <code>1</code> = sirf ye file • <code>150</code> = neeche ki 150 files\n"
            f"🎞️ Video • 📕 PDF • 🖼️ Photo — sab media count; 💬 text auto-skip\n"
            f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄✨")
        if ack:
            try:
                return await ack.edit_text(_q, reply_markup=kb_ask_single(limit))
            except Exception:
                pass
        return await m.reply_text(_q, reply_markup=kb_ask_single(limit))

    if ASK_COUNT and not _from_ask and len(pairs) > 1:
        scan = await m.reply_text("🔍 Link scan kar raha hoon — kitni files hain dekhta hoon…")
        media, access_fail, scan_fail = await scan_media(pairs)
        if not media:
            busy_del(chat_id)
            if access_fail:
                return await scan.edit_text(
                    "🔒 <b>Is chat tak access nahi mila!</b>\n\n"
                    "Aap is group/channel me <b>member nahi ho</b> (ya chat bahut purani hai).\n"
                    "📌 Pehle join karo, fir link dobara bhejo.")
            if scan_fail:
                return await scan.edit_text(
                    "⚠️ Scan me <b>temporary dikkat</b> aayi (server session conflict).\n\n"
                    "📌 Link ko <b>ek baar dobara</b> bhejo — chal jayega.")
            return await scan.edit_text(
                "⚠️ Is link me <b>koi file nahi mili</b> — sirf text messages hain.\n\n"
                "📌 File wale post ka link bhejo (ya range do).")
        if len(media) > 1:
            mx = min(len(media), limit)
            ASK_PENDING[chat_id] = {"uid": uid, "mode": "multi", "pairs": media,
                                    "ts": time.time()}
            busy_del(chat_id)
            qtxt = (f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n"
                    f"🔍 <b>LINK SCAN COMPLETE!</b>\n"
                    f"📚 Is link me <b>{len(media)} files</b> mili hain!\n\n"
                    f"🎛️ <b>KITNI FILES CHAHIYE?</b>\n"
                    f"👇 Button dabao ya number likho (1–{mx})\n"
                    f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨")
            try:
                return await scan.edit_text(qtxt, reply_markup=kb_ask(mx))
            except Exception as e:
                log.warning("question edit fail (%s) -> naya message bheja", e)
                return await m.reply_text(qtxt, reply_markup=kb_ask(mx))
        try:
            await scan.delete()
        except Exception:
            pass
        pairs = media

    total_links = _total or len(pairs)
    allowed = pairs[:limit]
    locked = max(0, total_links - len(allowed))

    status = await m.reply_text(
        f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n"
        f"{spin()} <b>FILES NIKAL RAHA HOON… 0%</b>\n"
        f"<code>[{pbar(0, len(allowed))}]</code> 0/{len(allowed)}\n\n"
        f"🔗 Links : <b>{total_links}</b> • 🎯 Limit : <b>{limit}</b> ({tier})\n"
        f"🚀 SPARTA SPEED MODE ON\n"
        f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨")

    stats = {"ok": 0, "fail": 0, "errs": {}}
    done = 0
    last_edit = [0.0]
    lock = asyncio.Lock()

    async def _ticker():
        """Bari file download hote waqt bar ko zinda rakho (MB progress)."""
        while True:
            await asyncio.sleep(2.5)
            items = [v for v in DL_PROG.values() if v and v[1] and len(v) > 2]
            if not items:
                continue
            cur, tot, t0dl = max(items, key=lambda v: v[0] / max(1, v[1]))
            pct = min(99, int(cur * 100 / max(1, tot)))
            el = max(1.0, time.time() - t0dl)
            speed = cur / el
            eta = (tot - cur) / speed if speed > 1024 else 0
            try:
                await status.edit_text(
                    f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n"
                    f"{spin()} <b>BARI FILE DOWNLOAD HO RAHI HAI…</b>\n"
                    f"<code>[{pbar(cur, tot)}]</code> {pct}%\n\n"
                    f"⬇️ <b>{cur // 1048576} / {tot // 1048576} MB</b>\n"
                    f"⚡ {speed / 1048576:.1f} MB/s • "
                    + (f"⏳ ETA ~{int(eta // 60)}m {int(eta % 60):02d}s\n" if eta else "⏳ bas thoda sa…\n")
                    + f"📥 <b>{stats['ok']}/{len(allowed)}</b> aayi • 💔 {stats['fail']} fail\n"
                    + (f"⏳ Telegram wait {stats['flood']}s — apne aap resume hoga\n" if stats.get("flood") else "")
                    + f"🍿 bari files ek-ek karke full speed pe\n"
                    f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄✨")
            except Exception:
                pass

    async def _seq_fetch(chat, mid, idx):
        """Apni baari aane par hi deliver karo (order guarantee)."""
        try:
            await asyncio.wait_for(_gates[idx].wait(), timeout=SEQ_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("⏭️ sequence gate timeout idx=%s — aage badha", idx)
        try:
            return await fetch_one(chat, mid, chat_id, stats, st)
        finally:
            if idx + 1 < len(_gates):
                _gates[idx + 1].set()

    # ── SEQUENCE MODE ──
    # Files parallel fetch hoti hain (speed), par user ko ORDER me jaati hain.
    # Har worker apni baari ka intezaar karta hai: slot i ka gate tabhi khulta
    # hai jab slot i-1 deliver ho chuka ho. Speed barkarar — sirf send ordered.
    _gates = ([asyncio.Event() for _ in allowed] if st.get("sequence", True)
              else None)
    if _gates:
        _gates[0].set()

    async def one(chat, mid, _idx=0):
        nonlocal done
        if _gates:
            # download/cache-copy sab parallel; sirf FINAL send ordered ho
            ok, title, why = await _seq_fetch(chat, mid, _idx)
        else:
            ok, title, why = await fetch_one(chat, mid, chat_id, stats, st)
        async with lock:
            done += 1
            if not ok:
                stats["fail"] += 1
                stats["errs"][why or "unknown"] = stats["errs"].get(why or "unknown", 0) + 1
            now = time.time()
            if done == len(allowed) or now - last_edit[0] >= 2.0:
                last_edit[0] = now
                pct = done * 100 // max(1, len(allowed))
                try:
                    await status.edit_text(
                        f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n"
                        f"{spin()} <b>LOADING… {pct}%</b>\n"
                        f"<code>[{pbar(done, len(allowed))}]</code> <b>{stats['ok']}/{len(allowed)}</b>\n\n"
                        f"📥 <b>{stats['ok']}</b> aayi • ⏳ <b>{max(0, len(allowed) - done)}</b> baaki • 💔 {stats['fail']} fail\n"
                        + (f"⏳ Telegram ne {stats['flood']}s wait diya — apne aap resume hoga 🫧\n" if stats.get("flood") else "")
                        + f"⏱️ {now - t0:.1f}s • 🚀 SPARTA SPEED\n"
                        + f"🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨")
                except Exception:
                    pass

    tick = asyncio.create_task(_ticker())
    try:
        await asyncio.gather(*[one(c, i, n) for n, (c, i) in enumerate(allowed)])
    except asyncio.CancelledError:
        try:
            await status.edit_text(
                "❌ <b>Request cancel kar di gayi.</b>\n\n"
                f"📥 {stats['ok']} files aayi thi • 💔 {stats['fail']} fail\n"
                "✅ Ab naya link bhej sakte ho 🫧")
        except Exception:
            pass
        busy_del(chat_id)
        raise
    finally:
        tick.cancel()
    sent = stats["ok"]
    await bump_usage(uid, chat_id, sent)

    # ── THANK YOU / LIMIT message ──
    body = thanks_msg("link mode", sent, total_links, limit, tier, t0)
    body = body.replace("🔎 Query      : <code>link mode</code>",
                        f"🔗 Links       : <b>{total_links}</b>")
    kb = None
    if locked > 0:
        body = (f"⛔ <b>LIMIT REACHED!</b>\n\n"
                f"Aapne <b>{total_links}</b> links bheje, par aapka limit <b>{limit}</b> hai.\n"
                f"🔒 <b>{locked} files</b> process nahi hui.\n\n"
                f"💎 Premium lo — ek baar me zyada files:\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🥉 <b>200 files</b> → ₹<b>100</b>/month\n"
                f"🥈 <b>350 files</b> → ₹<b>150</b>/month\n"
                f"🥇 <b>500 files</b> → ₹<b>250</b>/month\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n" + body)
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💎 UPGRADE PLAN", callback_data="menu:plans"),
              InlineKeyboardButton("🛒 BUY NOW", callback_data="menu:buy")]])
    elif limit == FREE_LIMIT and uid not in ADMINS:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💎 Premium lo → 500 files/time", callback_data="menu:plans")]])

    if stats["errs"]:
        top = sorted(stats["errs"].items(), key=lambda x: -x[1])[:3]
        body += "\n\n⚠️ <b>Fail reasons:</b>\n" + "\n".join(
            f"• {esc(k)} — {v} files" for k, v in top)

    try:
        await status.edit_text(body, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await m.reply_text(body, reply_markup=kb, disable_web_page_preview=True)

    log.info("LINKS uid=%s total=%s sent=%s fail=%s %.2fs",
             uid, total_links, sent, stats["fail"], time.time() - t0)
    if LOG_CHANNEL:
        try:
            await CLIENT.send_message(
                LOG_CHANNEL,
                f"🔗 <b>Link request</b>\n👤 {username_link(m.from_user)} (<code>{uid}</code>)\n"
                f"📥 {total_links} links • ✅ {sent} sent • ❌ {stats['fail']} fail\n"
                f"⏱️ {time.time() - t0:.2f}s • {tier}")
        except Exception:
            pass
    busy_del(chat_id)


# ═══════════════════════════════ INDEXING ═══════════════════════════════════

async def _push_index(batch):
    if STORE_KIND == "MongoDB":
        try:
            await STORE.files.insert_many(batch, ordered=False)
        except Exception as e:
            if "duplicate" not in str(e).lower():
                log.warning("mongo insert: %s", e)
    else:
        existing = {(d["chat_id"], d["msg_id"]) for d in STORE.data["files"]}
        new = [d for d in batch if (d["chat_id"], d["msg_id"]) not in existing]
        if new:
            await STORE.insert_many("files", new)


async def run_index(rebuild=False, progress_msg=None):
    if INDEX_STATE["running"]:
        return False, "⏳ Indexing already chal rahi hai — thoda ruko."
    if not DB_CHANNEL:
        return False, "❌ DB_CHANNEL set nahi hai!"

    INDEX_STATE.update({"running": True, "count": 0})
    if rebuild:
        await STORE.drop("files")

    t0, batch, seen, last_edit = time.time(), [], set(), 0.0
    try:
        async for m in CLIENT.get_chat_history(DB_CHANNEL, limit=None):
            if getattr(m, "empty", False):
                continue
            if not (m.document or m.video or m.audio or m.voice or m.photo
                    or m.animation or m.caption or m.text):
                continue
            key = (m.chat.id, m.id)
            if key in seen:
                continue
            seen.add(key)
            title = clean_title(m)
            batch.append({"chat_id": m.chat.id, "msg_id": m.id, "title": title,
                          "title_lc": title.lower(), "type": media_type(m),
                          "size": msg_size(m), "date": m.date})
            if len(batch) >= INDEX_CHUNK:
                await _push_index(batch)
                batch = []
                INDEX_STATE["count"] = len(seen)
                if progress_msg and time.time() - last_edit > 2.5:
                    last_edit = time.time()
                    try:
                        await progress_msg.edit_text(
                            f"🔄 <b>Indexing…</b>\n\n📥 Scanned : <b>{len(seen)}</b> messages\n"
                            f"⏱️ Time : {time.time() - t0:.1f}s\n"
                            f"⚡ Speed : {len(seen) / max(time.time() - t0, .01):.0f} msg/s\n\n"
                            f"<i>Ruko mat, tezi se chal raha hai ⚡</i>")
                    except Exception:
                        pass
        if batch:
            await _push_index(batch)
    except Exception as e:
        INDEX_STATE["running"] = False
        log.exception("index error")
        return False, f"❌ Index error: <code>{esc(e)[:300]}</code>"

    took = time.time() - t0
    INDEX_STATE.update({"running": False, "last": time.time(), "count": len(seen)})
    log.info("Index done: %d msgs in %.1fs", len(seen), took)
    return True, (f"✅ <b>INDEX COMPLETE!</b>\n\n"
                  f"📦 Total Files : <b>{len(seen)}</b>\n"
                  f"⏱️ Time Taken  : <b>{took:.1f}s</b>\n"
                  f"⚡ Speed       : <b>{len(seen) / max(took, .001):.0f} msg/sec</b>\n"
                  f"🗄️ Store       : {STORE_KIND}")

# ═══════════════════════════════ DELIVERY ═══════════════════════════════════

async def send_result_batches(chat_id, results, query):
    """Link-list mode (default) — sabse fast delivery."""
    chunks = [results[i:i + RESULT_BATCH] for i in range(0, len(results), RESULT_BATCH)]
    chunks = chunks[:MAX_BATCH_MSGS]
    sent_msgs, failed = 0, 0
    lock = asyncio.Lock()

    async def one(idx, chunk):
        nonlocal sent_msgs, failed
        base = idx * RESULT_BATCH
        lines = [f"🔎 <b>{esc(query)}</b> — part {idx + 1}/{len(chunks)} ⚡",
                 "━━━━━━━━━━━━━━━━━━━"]
        for j, r in enumerate(chunk, start=1):
            size = f" <i>({hsize(r.get('size'))})</i>" if r.get("size") else ""
            lines.append(f"{base + j}. <a href='{public_link(r['chat_id'], r['msg_id'])}'>"
                         f"{esc(r['title'])}</a>{size}")
        lines += ["━━━━━━━━━━━━━━━━━━━",
                  "👉 Link pe click karo — file turant khulegi.\n"
                  f"🙏 Thank you for choosing {BOT_NAME}!"]
        async with SEM_SEND:
            for attempt in range(3):
                try:
                    await CLIENT.send_message(chat_id, "\n".join(lines),
                                              disable_web_page_preview=True)
                    async with lock:
                        sent_msgs += 1
                    return
                except FloodWait as e:
                    await asyncio.sleep(min(e.value, 20) + .2)
                except (UserIsBlocked, PeerIdInvalid, ChatWriteForbidden):
                    async with lock:
                        failed += 1
                    return
                except Exception as e:
                    if attempt == 2:
                        log.warning("batch send fail: %s", e)
                        async with lock:
                            failed += 1
                    else:
                        await asyncio.sleep(1.0)

    await asyncio.gather(*[one(i, c) for i, c in enumerate(chunks)])
    return sent_msgs, failed


async def forward_files(chat_id, results, status_msg=None):
    """Forward mode — real files seedha chat me (slower, save-friendly)."""
    done, lock = 0, asyncio.Lock()

    async def one(r):
        nonlocal done
        async with SEM_FWD:
            for _ in range(2):
                try:
                    await CLIENT.copy_message(chat_id=chat_id, from_chat_id=r["chat_id"],
                                              message_id=r["msg_id"])
                    async with lock:
                        done += 1
                        d = done
                    if status_msg and d % 10 == 0:
                        try:
                            await status_msg.edit_text(
                                f"📤 <b>Sending files…</b> {d}/{len(results)} ⚡")
                        except Exception:
                            pass
                    await asyncio.sleep(FWD_DELAY)
                    return
                except FloodWait as e:
                    await asyncio.sleep(min(e.value, 30))
                except RPCError as e:
                    log.debug("copy fail: %s", e)
                    return
    await asyncio.gather(*[one(r) for r in results])
    return done, len(results) - done

# ═══════════════════════════════ KEYBOARDS ══════════════════════════════════

def join_row():
    if not FORCE_SUB:
        return []
    t = FORCE_SUB if str(FORCE_SUB).startswith(("@", "-")) else f"@{FORCE_SUB}"
    url = (f"https://t.me/{t.lstrip('@')}" if t.startswith("@")
           else f"https://t.me/c/{str(t).replace('-100', '')}/1")
    return [InlineKeyboardButton("📢 JOIN CHANNEL (required)", url=url)]


def back_row(extra=None):
    row = [InlineKeyboardButton("🔙 Back", callback_data="menu:start")]
    return [extra + row] if extra else [row]


def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 SEARCH FILES", callback_data="menu:search")],
        [InlineKeyboardButton("⚙️ SETTINGS", callback_data="menu:settings")],
        [InlineKeyboardButton("💎 PLANS", callback_data="menu:plans"),
         InlineKeyboardButton("🛒 BUY PREMIUM", callback_data="menu:buy")],
        [InlineKeyboardButton("👤 MY PLAN", callback_data="menu:myplan"),
         InlineKeyboardButton("📊 STATS", callback_data="menu:stats")],
        [InlineKeyboardButton("❓ HELP", callback_data="menu:help"),
         InlineKeyboardButton("👑 OWNER", url=f"https://t.me/{SUPPORT_TXT.lstrip('@')}")],
    ] + join_row())


def kb_plans():
    rows = [[InlineKeyboardButton(f"🛒 {p['name']} • {p['files']} files • ₹{p['price']}/mo",
                                  callback_data=f"buy:{p['key']}")] for p in PLANS]
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="menu:start")])
    return InlineKeyboardMarkup(rows)


def kb_admin(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve 30d", callback_data=f"admap:{uid}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"admrej:{uid}")],
        [InlineKeyboardButton("👤 Info", callback_data=f"adminfo:{uid}"),
         InlineKeyboardButton("🗑️ Free", callback_data=f"admrm:{uid}")],
    ])

# ═══════════════════════════════ BOT CLIENT ═════════════════════════════════

# ⚠️ Client ko module-level pe create MAT karo!
# Pyrogram Client.__init__ (aur uska Dispatcher) us waqt ka event loop capture
# kar leta hai. Import-time pe banaya client asyncio.run() wale loop se alag
# loop pakad leta hai -> bot online dikhta hai par messages ka reply NAHI karta.
# Isliye client main() ke andar banta hai.
CLIENT: Client = None


def build_client() -> Client:
    return Client(
        name="sparta_src",
        bot_token=BOT_TOKEN,
        api_id=API_ID,
        api_hash=API_HASH,
        workers=64,
        max_concurrent_transmissions=16,
        sleep_threshold=25,
        in_memory=True,
    )


HANDLERS = []          # (filter, handler, kind, group)
SEEN_UPD = {}          # duplicate-update guard


def handler(flt, kind="message", group=0):
    """Decorator: handler register karo + crash-proof banao.

    group < 0 = pehle chalega (settings-input jaise handlers ke liye).
    """
    def deco(fn):
        @functools.wraps(fn)
        async def wrapped(client, update, *a, **kw):
            try:
                # DUPLICATE update guard — Telegram kabhi-kabhi same update
                # do baar bhejta hai (reconnect ke baad); dono chalen to
                # BUSY clash hota hai aur bot atka hua lagta hai.
                try:
                    _k = None
                    if getattr(update, "id", None) and getattr(update, "chat", None):
                        _k = ("m", update.chat.id, update.id)
                    elif getattr(update, "data", None):
                        _k = ("c", getattr(update, "id", ""))
                    if _k:
                        _now = time.time()
                        if _now - SEEN_UPD.get(_k, 0) < 15:
                            log.info("⏭️ duplicate update skip: %s", _k)
                            return
                        SEEN_UPD[_k] = _now
                        if len(SEEN_UPD) > 500:
                            for _o in [k for k, v in SEEN_UPD.items()
                                       if _now - v > 60][:300]:
                                SEEN_UPD.pop(_o, None)
                except Exception:
                    pass
                # SLOW watchdog — 15s me handler khatam na ho to stack chhapo
                _slow = None
                try:
                    _self_task = asyncio.current_task()

                    async def _slow_watch():
                        try:
                            await asyncio.sleep(15)
                            log.warning("🐌 SLOW handler %s — 15s se chal raha, stack:",
                                        fn.__name__)
                            _self_task.print_stack(limit=18)
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            pass

                    _slow = asyncio.create_task(_slow_watch())
                except Exception:
                    pass
                try:                                  # incoming visibility
                    _t = (getattr(update, "text", None)
                          or getattr(update, "data", None)
                          or ("[media]" if getattr(update, "media", None) else ""))
                    _u = getattr(update, "from_user", None)
                    log.info("📩 IN %s | %s | %s", fn.__name__,
                             getattr(_u, "id", "?"), str(_t)[:60])
                except Exception:
                    pass
                try:
                    return await fn(client, update, *a, **kw)
                finally:
                    if _slow:
                        _slow.cancel()
            except FloodWait as e:
                log.warning("FloodWait %ss in %s", getattr(e, "value", "?"), fn.__name__)
                await asyncio.sleep(min(int(getattr(e, "value", 5)), 60))
            except MessageNotModified:
                pass
            except Exception as e:
                log.exception("handler error in %s", fn.__name__)
                try:
                    chat = getattr(update, "chat", None) or getattr(
                        getattr(update, "message", None), "chat", None)
                    if chat:
                        await client.send_message(
                            chat.id, f"⚠️ Kuch gadbad: <code>{esc(e)[:220]}</code>\n"
                                     f"Dobara try karo.")
                except Exception:
                    pass
                if LOG_CHANNEL:
                    try:
                        await client.send_message(
                            LOG_CHANNEL,
                            f"⚠️ <b>Error</b> in <code>{fn.__name__}</code>\n<code>{esc(e)[:800]}</code>")
                    except Exception:
                        pass
        HANDLERS.append((flt, wrapped, kind, group))
        return wrapped
    return deco


is_admin = filters.user(list(ADMINS)) if ADMINS else filters.create(lambda *_: False)

CMD_BLOCK = ["start", "help", "id", "search", "plans", "buy", "myplan", "stats", "setdb",
             "setcache", "link", "status",
             "forward", "cancel", "index", "reindex", "approve", "reject", "setplan",
             "removeplan", "user", "find", "reqs", "usage", "broadcast", "del", "ping",
             "settings", "setting", "custom", "raw"]

# ─────────────────────────────── USER: start / help / id ────────────────────

@handler(filters.command("start") & filters.private)
async def cmd_start(c, m: Message):
    u = await get_user(m.from_user, m.chat.id)
    await m.reply_text(start_txt(u, m.from_user), reply_markup=kb_main(),
                       disable_web_page_preview=True)


@handler(filters.command("help") & filters.private)
async def cmd_help(c, m: Message):
    await m.reply_text(HELP_TXT, disable_web_page_preview=True)


@handler(filters.command("id"))
async def cmd_id(c, m: Message):
    r = m.reply_to_message
    txt = (f"🆔 <b>Your ID :</b> <code>{m.from_user.id}</code>\n"
           f"💬 <b>Chat ID :</b> <code>{m.chat.id}</code>\n")
    if r and r.from_user:
        txt += f"👤 <b>Replied User :</b> <code>{r.from_user.id}</code>\n"
    if r and getattr(r, "forward_from_chat", None):
        txt += f"📢 <b>Channel ID :</b> <code>{r.forward_from_chat.id}</code>\n"
    txt += (f"🗄️ <b>DB Channel :</b> <code>{DB_CHANNEL or 'not set'}</code>\n"
            f"🛡️ <b>Admin?</b> {'YES' if m.from_user.id in ADMINS else 'NO'}")
    await m.reply_text(txt)


@handler(filters.command("ping") & filters.private)
async def cmd_ping(c, m: Message):
    t = time.time()
    msg = await m.reply_text("🏓 Pinging…")
    await msg.edit_text(f"⚡ <b>Pong!</b>  <code>{(time.time() - t) * 1000:.0f} ms</code>\n"
                        f"🗄️ Store: {STORE_KIND} | Loop: {'uvloop' if UVLOOP else 'asyncio'}")

# ─────────────────────────────── USER: search ───────────────────────────────

@handler(filters.command("search") & filters.private)
async def cmd_search(c, m: Message):
    parts = m.text.split(None, 1)
    q = parts[1].strip() if len(parts) > 1 else ""
    if q:
        await handle_search(m, q)
        return
    u = await get_user(m.from_user, m.chat.id)
    await m.reply_text(
        "🔎 <b>SEARCH MODE ON</b>\n\nAb apni file ka naam type karo 👇\n"
        "<i>Example:</i> <code>avengers endgame</code>\n\n"
        f"🎯 Aapka limit: <b>{user_limit(u)} files</b>\n❌ Cancel: /cancel",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💎 Upgrade Limit", callback_data="menu:plans")]]))


@handler(filters.command("cancel") & filters.private)
async def cmd_cancel(c, m: Message):
    info = BUSY_INFO.pop(m.chat.id, None)
    BUSY.discard(m.chat.id)
    task = (info or {}).get("task")
    if task and not task.done() and task is not asyncio.current_task():
        task.cancel()
        await m.reply_text(
            "❌ <b>Chal rahi request CANCEL kar di.</b>\n\n"
            "✅ Ab naya link/search bhej sakte ho 🫧")
    else:
        await m.reply_text(
            "✅ Cancelled — koi request chal nahi rahi thi.\nNaya link/search bhejo 🫧")


async def _detect_channel(m: Message):
    """Message/reply se channel ID nikalo (forwarded channel post se)."""
    for msg in (m, getattr(m, "reply_to_message", None)):
        if not msg:
            continue
        fwd = getattr(msg, "forward_from_chat", None)
        if fwd and getattr(fwd, "type", None) in ("channel", None):
            return fwd.id, (getattr(fwd, "title", None) or getattr(fwd, "username", None) or "?")
    return None, None


async def set_db_channel(m: Message, cid: int, title: str = ""):
    """DB_CHANNEL set karo (runtime + .env) aur index ka option do."""
    global DB_CHANNEL
    try:
        chat = await CLIENT.get_chat(cid)
        title = getattr(chat, "title", None) or getattr(chat, "username", None) or title or str(cid)
        ctype = str(getattr(chat, "type", "?"))
    except Exception as e:
        await m.reply_text(
            f"❌ Ye channel read nahi kar paya: <code>{esc(e)[:200]}</code>\n\n"
            f"👉 Bot ko us channel me <b>ADMIN</b> banao (Read messages on), fir dobara try karo.")
        return
    DB_CHANNEL = cid
    persist_env({"DB_CHANNEL": cid})
    await m.reply_text(
        f"✅ <b>DB CHANNEL SET!</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Channel : <b>{esc(title)}</b>\n"
        f"🔗 ID      : <code>{cid}</code>\n"
        f"📝 Type    : {esc(ctype)}\n"
        f"💾 .env    : saved (restart pe bhi rahega)\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ Zaroori: bot ko is channel me <b>ADMIN</b> banana (Read messages on).\n\n"
        f"👇 Ab index bana lo — search chalu hone ke liye zaroori hai:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 INDEX NOW (recommended)", callback_data="adminidx:1")],
             [InlineKeyboardButton("⏭️ Baad me karunga", callback_data="adminidx:0")]]))


async def _admin_fwd_trigger(_, __, m: Message):
    if m.from_user and m.from_user.id in ADMINS:
        cid, _t = await _detect_channel(m)
        return cid is not None
    return False


@handler(filters.private & filters.create(_admin_fwd_trigger))
async def admin_forward_detect(c, m: Message):
    """Admin ne channel ka post forward kiya -> pooch lo DB banana hai ya CACHE."""
    cid, title = await _detect_channel(m)
    await m.reply_text(
        f"📢 <b>Channel detect ho gaya!</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 ID : <code>{cid}</code>\n"
        f"📛 Name : {esc(title or '?')}\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ise <b>kya</b> banana hai?\n\n"
        f"🔗 <b>CACHE CHANNEL</b> — link mode ke liye (kisi bhi group ke link se "
        f"file nikalna). <i>Ye chahiye aapko.</i>\n\n"
        f"📢 <b>DB CHANNEL</b> — search mode ke liye (ek fixed channel me naam se "
        f"search).",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗄️ CACHE banao (link mode)", callback_data=f"setascache:{cid}")],
            [InlineKeyboardButton("📢 DB banao (search mode)", callback_data=f"setasdb:{cid}")],
        ]), disable_web_page_preview=True)


@handler(filters.regex(r"^setas(db|cache):"), kind="callback")
async def cb_set_channel(c, q: CallbackQuery):
    if q.from_user.id not in ADMINS:
        return await q.answer("⛔ Admin only!")
    kind, cid = q.data.split(":")[0][6:], int(q.data.split(":")[1])
    await q.answer()
    if kind == "db":
        await set_db_channel(q.message, cid)
    else:
        await set_cache_channel(q.message, cid)


async def set_cache_channel(m: Message, cid: int):
    """CACHE_CHANNEL set karo (runtime + .env) — link mode ke liye."""
    global CACHE_CHANNEL
    title, bot_ok, ub_ok, ub_err = str(cid), True, USERBOT_OK, ""
    try:
        ch = await CLIENT.get_chat(cid)
        title = getattr(ch, "title", None) or getattr(ch, "username", None) or str(cid)
    except Exception as e:
        bot_ok = False
        await m.reply_text(
            f"❌ <b>BOT</b> is channel ko access nahi kar paya:\n<code>{esc(e)[:200]}</code>\n\n"
            f"👉 Channel me @{CLIENT.me.username if CLIENT.me else 'bot'} ko <b>ADMIN</b> banao "
            f"(Post messages on), fir dobara forward karo.")
        return
    if USERBOT_OK:
        try:
            await USERBOT.get_chat(cid)
        except Exception as e:
            ub_ok = False
            ub_err = str(e)[:160]
    CACHE_CHANNEL = cid
    persist_env({"CACHE_CHANNEL": cid})
    ready = USERBOT_OK and ub_ok
    await m.reply_text(
        f"✅ <b>CACHE CHANNEL SET!</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"🗄️ Channel : <b>{esc(title)}</b>\n"
        f"🔗 ID : <code>{cid}</code>\n"
        f"🤖 Bot access : ✅\n"
        f"👤 Userbot access : {'✅' if ub_ok else '❌ ' + esc(ub_err)}\n"
        f"💾 .env : saved\n━━━━━━━━━━━━━━━━━━━\n\n"
        + ("🎉 <b>LINK MODE READY!</b> Ab koi bhi group/channel ka link bhejo — "
           "file turant mil jayegi ⚡\n\n🧪 Test karo: kisi file post ka link bhejo."
           if ready else
           "⚠️ Abhi <b>userbot session</b> chahiye link mode ke liye:\n"
           "<code>python3 userbot_login.py send +91XXXXXXXXXX</code>\n"
           "fir OTP se session banao. Uske baad link mode chalu ✅"),
        disable_web_page_preview=True)


@handler(filters.command("setdb") & is_admin)
async def cmd_setdb(c, m: Message):
    """Usage: /setdb -1001234567890  |  ya channel post forward/reply karke /setdb"""
    new = None
    for a in m.text.split()[1:]:
        if re.fullmatch(r"-?\d{5,}", a.strip()):
            new = int(a.strip())
    if not new:
        new, title = await _detect_channel(m)
    else:
        title = ""
    if not new:
        await m.reply_text(
            "📢 <b>DB CHANNEL SET KARO</b>\n\n3 tarike hain:\n"
            "1️⃣ Channel ka koi post bot ko <b>forward</b> karo (auto detect)\n"
            "2️⃣ Kisi forwarded post ka <b>reply</b> karke <code>/setdb</code>\n"
            "3️⃣ Direct ID: <code>/setdb -1001234567890</code>\n\n"
            f"📌 Abhi set hai: <code>{DB_CHANNEL or 'kuch nahi'}</code>")
        return
    await set_db_channel(m, new, title or "")


@handler(filters.private & filters.text & ~filters.command(CMD_BLOCK, prefixes="/"))
async def on_plain_text(c, m: Message):
    # ★ INVITE LINK -> userbot ko group me join karao (warna us group se
    # files nikal hi nahi sakte). t.me/+hash ya t.me/joinchat/hash
    _inv = re.search(r"(?:t\.me/\+|t\.me/joinchat/)([\w-]+)", m.text or "")
    if _inv and USERBOT_OK:
        _w = await m.reply_text("🔗 Invite link mila — join kar raha hoon… 🫧")
        try:
            _ch = await USERBOT.join_chat(m.text.strip().split()[0])
            PEER_OK.add(_ch.id)
            return await _w.edit_text(
                f"✅ <b>JOIN HO GAYA!</b>\n📛 {_ch.title}\n\n"
                f"Ab is group ka koi bhi <b>post link</b> bhejo — file nikal dunga ⚡")
        except UserAlreadyParticipant:
            return await _w.edit_text("✅ Is group me pehle se joined hoon — "
                                      "seedha post ka link bhejo 🫧")
        except InviteHashExpired:
            return await _w.edit_text("❌ Ye invite link <b>expire</b> ho gaya — naya bhejo")
        except Exception as _e:
            return await _w.edit_text(f"❌ Join nahi ho paya: <code>{_e}</code>")

    """Seedha text = search query. Pending buy ho to payment proof samjho."""
    txt = (m.text or "").strip()
    uid = m.from_user.id

    pend = await STORE.find_one("requests", "user_id", uid)
    if pend and pend.get("status") == "pending" and pend.get("awaiting_proof") \
            and (time.time() - pend.get("ts", 0)) < 1800:
        p = PLAN_BY_KEY.get(pend.get("plan"), {})
        await STORE.upsert("requests", "user_id", uid,
                           {"proof_text": txt[:500], "awaiting_proof": 0, "ts": time.time()})
        await m.reply_text(
            f"✅ <b>Payment proof received!</b>\n\n"
            f"🧾 UTR / Note : <code>{esc(txt[:80])}</code>\n"
            f"📦 Plan : <b>{p.get('name', 'Premium')} ({p.get('files', '?')} files)</b>\n"
            f"💰 Amount : <b>₹{p.get('price', '?')}</b>\n\n"
            f"⏳ Admin approve karte hi plan <b>{PREMIUM_DAYS} din</b> ke liye active ho jayega — "
            f"notification turant milegi ⚡")
        await notify_admin_request(m, pend, txt)
        return

    # ── LINK MODE: text me telegram link ho to files nikalo ──
    if LINK_MODE:
        st = ASK_PENDING.get(m.chat.id)
        if st and st["uid"] == uid and time.time() - st["ts"] < ASK_TTL:
            low = txt.lower()
            if low in ("cancel", "no", "x"):
                ASK_PENDING.pop(m.chat.id, None)
                return await m.reply_text("❌ Cancel kar diya. Dobara link bhejo.")
            if txt.isdigit():
                u = await get_user(m.from_user, m.chat.id)
                lim = user_limit(u)
                n = max(1, min(int(txt), lim))
                ASK_PENDING.pop(m.chat.id, None)
                if st.get("mode") == "fwd":
                    if n == 1:
                        # exact message me file na ho (topic header / text) to
                        # usi jagah se neeche pehli file utha lo
                        sel = await scan_forward(st["chat"], st["start"], 1,
                                                 topic=st.get("topic"))
                        if not sel:
                            sel = [(st["chat"], st["start"])]
                    else:
                        probe = await m.reply_text(
                            f"🔍 Link ke neeche scan kar raha hoon… ⏳\n"
                            f"📚 Mili: <b>0/{n}</b> files")

                        async def _pf(found, upto, flood=0):
                            try:
                                await probe.edit_text(
                                    f"🔍 Link ke neeche scan chal raha hai… ⏳\n"
                                    f"📚 Mili: <b>{found}/{n}</b> files\n"
                                    f"💬 Check hue: {max(0, upto - st['start'])} messages"
                                    + (f"\n⏳ Telegram ne {flood}s wait diya — "
                                       f"apne aap resume hoga 🫧" if flood else ""))
                            except Exception:
                                pass

                        sel = await scan_forward(st["chat"], st["start"], n,
                                                 topic=st.get("topic"),
                                                 on_progress=_pf)
                        try:
                            await probe.delete()
                        except Exception:
                            pass
                        if not sel:
                            return await m.reply_text(
                                "⚠️ Is link ke neeche <b>koi file nahi mili</b>.")
                    return await handle_links(m, sel, _from_ask=True, _total=n)
                sel = st["pairs"][:n]
                return await handle_links(m, sel, _from_ask=True)
            if not parse_links(txt):
                return await m.reply_text(
                    "🔢 Button dabao ya number likho (kitni files chahiye).\n"
                    "❌ Cancel karna ho to <code>cancel</code> likho.")
            ASK_PENDING.pop(m.chat.id, None)   # naya link aa gaya -> purana question khatam
        pairs = parse_links(txt)
        if pairs:
            return await handle_links(m, pairs)

    if len(txt) < 2:
        await m.reply_text("🔎 Kam se kam 2 letters likho, ya /help dabao.")
        return
    if len(txt) > 120:
        await m.reply_text("⚠️ Query bahut lambi hai — chhoti likho (max 120 chars).")
        return
    if not DB_CHANNEL:
        await m.reply_text(
            "🔗 <b>LINK BHEJO — FILE TURANT MILEGI!</b>\n\n"
            "Kisi bhi group/channel ke file post ka <b>link copy</b> karke yahan bhej do:\n"
            "<code>https://t.me/c/1234567890/45</code>\n\n"
            "📌 Ek saath <b>multiple links</b> bhi bhej sakte ho (free = "
            f"{FREE_LIMIT} files per message).\n"
            "💎 Premium: 200/350/500 files ek baar me — /plans")
        return
    await handle_search(m, txt)


async def handle_search(m: Message, query: str):
    chat_id, uid, t0 = m.chat.id, m.from_user.id, time.time()

    if chat_id in BUSY:                      # double request block
        info = BUSY_INFO.get(chat_id) or {}
        task = info.get("task")
        if task is None or task.done() \
                or time.time() - info.get("ts", time.time()) > BUSY_STALE:
            if task and not task.done():
                task.cancel()
            busy_del(chat_id)
        else:
            return await m.reply_text(
                "⏳ <b>Ek request pehle se chal rahi hai.</b>\n"
                "👇 Naya search bhejna ho to purani cancel karo:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Purani request CANCEL karo",
                                           callback_data="cancelreq")]]))
    if time.time() - LAST_SEARCH.get(chat_id, 0) < SEARCH_FLOOD_GAP:
        await m.reply_text("⏳ Ek second ruko… fir bhejo.")
        return
    LAST_SEARCH[chat_id] = time.time()
    busy_add(chat_id, uid)

    u = await get_user(m.from_user, chat_id)
    limit, tier = user_limit(u), plan_label(u)

    status = await m.reply_text(
        f"⚡ <b>Searching…</b>\n\n🔎 Query : <code>{esc(query)}</code>\n"
        f"🎯 Limit : <b>{limit}</b> files ({tier})\n\n<i>Turant result aayega…</i>")

    try:
        results, total, src = await do_search(query, limit)

        if not results:
            await status.edit_text(
                f"❌ <b>No Results Found</b>\n\n🔎 Query : <code>{esc(query)}</code>\n\n"
                "🤔 Ye try karo:\n• spelling check karo\n"
                "• chhoti query likho (<code>avengers</code> instead of "
                "<code>avengers endgame 1080p hindi</code>)\n"
                f"• admin se /index chalwao\n\n🙏 Thank you for choosing {BOT_NAME}!")
            return

        fwd = bool(u.get("forward"))
        if fwd:
            await status.edit_text(f"📤 <b>Sending {len(results)} files…</b> ⚡")
            sent, failed = await forward_files(chat_id, results, status)
            try:
                await status.delete()
                status = None
            except Exception:
                pass
        else:
            msgs, failed = await send_result_batches(chat_id, results, query)
            sent = len(results) if msgs else 0

        await bump_usage(uid, chat_id, sent)

        # ────────── TASK COMPLETE → THANK YOU ──────────
        body = thanks_msg(query, sent, total, limit, tier, t0)
        kb = None
        if total > sent:
            body = limit_hit_txt(sent, total, limit) + "\n\n" + body
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 UPGRADE PLAN", callback_data="menu:plans"),
                  InlineKeyboardButton("🛒 BUY NOW", callback_data="menu:buy")]])
        elif limit == FREE_LIMIT and uid not in ADMINS:
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Premium lo → 500 files", callback_data="menu:plans")]])

        if status is not None:
            try:
                await status.edit_text(body, reply_markup=kb, disable_web_page_preview=True)
            except Exception:
                await m.reply_text(body, reply_markup=kb, disable_web_page_preview=True)
        else:
            await m.reply_text(body, reply_markup=kb, disable_web_page_preview=True)

        log.info("SEARCH uid=%s q=%r sent=%s/%s %.2fs src=%s",
                 uid, query[:30], sent, total, time.time() - t0, src)
        if LOG_CHANNEL:
            try:
                await CLIENT.send_message(
                    LOG_CHANNEL,
                    f"🔎 <b>Search</b>\n👤 {username_link(m.from_user)} (<code>{uid}</code>)\n"
                    f"📝 <code>{esc(query)}</code>\n📦 {sent}/{total} files • {tier}\n"
                    f"⏱️ {time.time() - t0:.2f}s • src={src}")
            except Exception:
                pass
    finally:
        busy_del(chat_id)


@handler(filters.command("link") & filters.private)
async def cmd_link(c, m: Message):
    parts = m.text.split(None, 1)
    pairs = parse_links(parts[1] if len(parts) > 1 else "")
    if not pairs and m.reply_to_message:
        pairs = parse_links(m.reply_to_message.text or m.reply_to_message.caption or "")
    if pairs:
        return await handle_links(m, pairs)
    u = await get_user(m.from_user, m.chat.id)
    await m.reply_text(
        f"🔗 <b>LINK SE FILE NIKALO</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"Kisi bhi group/channel ke post ka link yahan bhejo — file turant milegi ⚡\n\n"
        f"📥 <b>Example:</b>\n<code>https://t.me/c/1234567890/45</code>\n\n"
        f"🗂️ <b>Ek saath kitne?</b>\n"
        f"• Free      : <b>{FREE_LIMIT} files</b>\n"
        f"• Premium-1 : <b>200 files</b> (₹100/mo)\n"
        f"• Premium-2 : <b>350 files</b> (₹150/mo)\n"
        f"• Premium-3 : <b>500 files</b> (₹250/mo)\n\n"
        f"🎯 <b>Aapka limit : {user_limit(u)} files</b> ({plan_label(u)})\n\n"
        f"💡 Range bhi chalega: <code>t.me/c/123456/10-30</code>\n"
        f"💡 Link post pe <b>right click → Copy Link</b> (ya share → copy)")


@handler(filters.command("raw") & is_admin)
async def cmd_raw(c, m: Message):
    """/raw <link>  -> Telegram ne us message pe EXACTLY kya bheja, wo dikhao."""
    pairs = parse_links(m.text or "")
    if not pairs:
        return await m.reply_text("Use: <code>/raw &lt;post link&gt;</code>")
    chat, mid = pairs[0]
    await ensure_peer(chat)
    out = [f"<b>RAW DEBUG</b>\nchat=<code>{chat}</code> id=<code>{mid}</code>"]

    # 1) pyrogram parsed
    try:
        msg = await USERBOT.get_messages(chat, mid)
        out.append(f"\n<b>pyrogram:</b> empty={getattr(msg,'empty',None)} "
                   f"media={getattr(msg,'media',None)} "
                   f"service={getattr(msg,'service',None)}")
        keys = [k for k in ("document","video","audio","photo","voice","animation",
                            "video_note","sticker","text","caption")
                if getattr(msg, k, None)]
        out.append(f"fields: {keys or 'KUCH NAHI'}")
    except Exception as e:
        out.append(f"\npyrogram fail: <code>{e}</code>")

    # 2) RAW MTProto — pyrogram parse na kar paye to bhi asli sach yahan
    try:
        from pyrogram.raw.functions.channels import GetMessages as RawGet
        from pyrogram.raw.types import InputMessageID
        peer = await USERBOT.resolve_peer(chat)
        r = await USERBOT.invoke(RawGet(channel=peer, id=[InputMessageID(id=mid)]))
        for mm in getattr(r, "messages", [])[:1]:
            out.append(f"\n<b>RAW:</b> {type(mm).__name__}")
            md = getattr(mm, "media", None)
            out.append(f"raw media: <code>{type(md).__name__ if md else None}</code>")
            if md is not None:
                out.append(f"<code>{str(md)[:400]}</code>")
    except Exception as e:
        out.append(f"\nraw fail: <code>{e}</code>")
    await m.reply_text("\n".join(out)[:4000])


@handler(filters.command("setcache") & is_admin)
async def cmd_setcache(c, m: Message):
    """CACHE_CHANNEL: us channel ka post forward karo, ya /setcache -100xxxx"""
    cid, title = None, ""
    for a in m.text.split()[1:]:
        if re.fullmatch(r"-?\d{5,}", a.strip()):
            cid = int(a.strip())
    if not cid:
        cid, title = await _detect_channel(m)
    if not cid:
        await m.reply_text(
            "🗄️ <b>CACHE CHANNEL SET KARO</b>\n\n"
            "Ye wo <b>private channel</b> hai jisme userbot files temporary rakhta hai, "
            "fir bot wahan se user ko bhejta hai (Telegram = free unlimited storage).\n\n"
            "<b>Tarika:</b>\n"
            "1️⃣ Ek <b>private channel</b> banao (jaise <i>Sparta Cache</i>)\n"
            "2️⃣ Usme bot ko <b>ADMIN</b> banao\n"
            "3️⃣ Us channel ka koi post bot ko <b>forward</b> karo\n"
            "4️⃣ Ya ID se: <code>/setcache -1001234567890</code>\n\n"
            f"📌 Abhi set: <code>{CACHE_CHANNEL or 'kuch nahi'}</code>")
        return
    await set_cache_channel(m, cid)


@handler(filters.command("status") & filters.private)
async def cmd_status(c, m: Message):
    admin = m.from_user.id in ADMINS
    lines = [
        f"🩺 <b>{BOT_NAME} STATUS</b>", "━━━━━━━━━━━━━━━━━━━",
        f"🤖 Bot        : ✅ <b>@{CLIENT.me.username if CLIENT.me else '?'}</b>",
        f"👤 Userbot    : {'✅ <b>' + (USERBOT_ME.first_name if USERBOT_ME else 'connected') + '</b>' if USERBOT_OK else '❌ <b>not connected</b>'}",
        f"🗄️ Cache ch.  : {'✅ <code>' + str(CACHE_CHANNEL) + '</code>' if CACHE_CHANNEL else '❌ not set'}",
        f"📢 DB channel : {'✅ <code>' + str(DB_CHANNEL) + '</code>' if DB_CHANNEL else '— (search mode off)'}",
        f"📦 Index files: {await STORE.count('files')}",
        f"🔗 Link mode  : {'✅ ON' if LINK_MODE else '❌ OFF'}",
        f"⚡ uvloop     : {'ON' if UVLOOP else 'OFF'}  |  store: {STORE_KIND}",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    ready = await ub_ready()
    lines.append("🎯 <b>LINK MODE:</b> " + ("✅ READY — link bhejo!" if ready else "⚠️ setup baaki hai"))
    if not ready and admin:
        miss = []
        if not USERBOT_OK:
            miss.append("userbot session (userbot_login.py chalao)")
        if not CACHE_CHANNEL:
            miss.append("CACHE_CHANNEL (/setcache)")
        lines.append("👉 Baaki: " + ", ".join(miss))
    u = await get_user(m.from_user, m.chat.id)
    lines += ["", f"🎯 Aapka limit : <b>{user_limit(u)} files</b> ({plan_label(u)})"]
    await m.reply_text("\n".join(lines), disable_web_page_preview=True)


@handler(filters.command("forward") & filters.private)
async def cmd_forward(c, m: Message):
    u = await get_user(m.from_user, m.chat.id)
    new = 0 if u.get("forward") else 1
    await STORE.upsert("users", "user_id", m.from_user.id, {"forward": new})
    await m.reply_text(
        f"📤 <b>Forward Mode : {'ON ✅' if new else 'OFF ❌'}</b>\n\n"
        + ("Ab results <b>real files</b> ki tarah seedha aayengi (chat me save ho jayengi, "
           "thoda time lagega).\n" if new else
           "Ab results <b>fast link list</b> me aayenge — sabse tez ⚡\n")
        + "\n👉 /search karke dekho.")

# ─────────────────────────────── USER: plans / buy / myplan / stats ─────────

@handler(filters.command("plans") & filters.private)
async def cmd_plans(c, m: Message):
    u = await get_user(m.from_user, m.chat.id)
    await m.reply_text(plans_txt(u), reply_markup=kb_plans(), disable_web_page_preview=True)


@handler(filters.command("buy") & filters.private)
async def cmd_buy(c, m: Message):
    await m.reply_text("🛒 <b>BUY PREMIUM</b>\n\nNiche se apna plan chuno 👇",
                       reply_markup=kb_plans(), disable_web_page_preview=True)


@handler(filters.command("myplan") & filters.private)
async def cmd_myplan(c, m: Message):
    u = await get_user(m.from_user, m.chat.id)
    left = ""
    if u.get("expiry") and u["expiry"] > time.time():
        d = u["expiry"] - time.time()
        left = f"  ({int(d // 86400)}d {int((d % 86400) // 3600)}h left)"
    await m.reply_text(
        f"👑 <b>YOUR PLAN</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Plan      : <b>{plan_label(u)}</b>\n"
        f"⚡ Limit     : <b>{user_limit(u)} files</b> / search\n"
        f"📅 Expiry    : {exp_str(u.get('expiry')) or '—'}{left}\n"
        f"🔎 Searches  : {u.get('searches', 0)}\n"
        f"📦 Files Got : {u.get('files_got', 0)}\n"
        f"📤 Forward   : {'ON' if u.get('forward') else 'OFF'}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆓 Free limit: {FREE_LIMIT} files  •  💎 Upgrade: /plans",
        reply_markup=None if u["user_id"] in ADMINS else kb_plans(),
        disable_web_page_preview=True)


@handler(filters.command("stats") & filters.private)
async def cmd_stats(c, m: Message):
    u = await get_user(m.from_user, m.chat.id)
    cnt = await STORE.get_counters()
    await m.reply_text(
        f"📊 <b>{BOT_NAME} STATS</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Users         : <b>{await STORE.count('users')}</b>\n"
        f"📦 Indexed Files : <b>{await STORE.count('files')}</b>\n"
        f"🔎 Total Searches: <b>{cnt.get('searches', 0)}</b>\n"
        f"📤 Files Sent    : <b>{cnt.get('files_sent', 0)}</b>\n"
        f"🗄️ Store         : {STORE_KIND}\n"
        f"⚡ Event Loop    : {'uvloop' if UVLOOP else 'asyncio'}\n"
        f"🕒 Last Index    : {exp_str(INDEX_STATE['last']) or 'never'}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Your Stats</b>\n"
        f"• Searches : {u.get('searches', 0)}\n"
        f"• Files Got: {u.get('files_got', 0)}\n"
        f"• Limit    : <b>{user_limit(u)}</b> ({plan_label(u)})\n\n"
        f"🙏 Thank you for choosing {BOT_NAME}!")

# ─────────────────────────────── ADMIN: index ───────────────────────────────

@handler(filters.command(["index", "reindex"]) & is_admin)
async def cmd_index(c, m: Message):
    rebuild = m.command[0].lower() == "reindex"
    msg = await m.reply_text(
        f"🔄 <b>{'Re' if rebuild else ''}Indexing start…</b>\n\n"
        f"📢 Channel : <code>{DB_CHANNEL}</code>\n<i>Progress yahan dikhega ⚡</i>")
    ok, out = await run_index(rebuild=rebuild, progress_msg=msg)
    try:
        await msg.edit_text(out)
    except Exception:
        await m.reply_text(out)

# ─────────────────────────────── ADMIN: premium ─────────────────────────────

async def activate_plan(uid, plan_key, days=PREMIUM_DAYS, chat_id=None):
    p = PLAN_BY_KEY.get(str(plan_key).upper())
    if not p and str(plan_key).isdigit():
        p = PLAN_BY_FILES.get(int(plan_key))
    if not p:
        return None
    exp = int(time.time() + days * 86400)
    doc = await STORE.find_one("users", "user_id", uid) or {}
    await STORE.upsert("users", "user_id", uid, {
        "plan": p["key"], "limit": p["files"], "expiry": exp,
        "activated": time.time(), "days": days, "price": p["price"]})
    try:
        await CLIENT.send_message(
            chat_id or doc.get("chat_id") or uid,
            f"🎉 <b>PREMIUM ACTIVATED!</b>\n━━━━━━━━━━━━━━━━━━━\n"
            f"👑 Plan   : <b>{p['name']}</b>\n"
            f"⚡ Limit  : <b>{p['files']} files</b> per search\n"
            f"📅 Valid  : <b>{days} days</b>\n"
            f"⏰ Expiry : {exp_str(exp)}\n━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔎 Ab /search karke mazza lo!\n🙏 Thank you for choosing {BOT_NAME}!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔎 SEARCH NOW", callback_data="menu:search")]]))
    except Exception as e:
        log.warning("notify user fail: %s", e)
    return p


def _parse_uid(args, m):
    """args me se user-id nikalo (plan numbers 200/350/500 ko ignore karta hai)."""
    uid = None
    r = getattr(m, "reply_to_message", None)
    if r and getattr(r, "from_user", None):
        uid = r.from_user.id
    for a in args:
        a = a.strip()
        if not a.isdigit():
            continue
        if int(a) in PLAN_BY_FILES or a.upper() in PLAN_BY_KEY:
            continue                      # ye plan hai, user-id nahi
        uid = int(a)
    return uid


@handler(filters.command("approve") & is_admin)
async def cmd_approve(c, m: Message):
    args = m.text.split()[1:]
    uid = _parse_uid(args, m)
    if not uid:
        await m.reply_text("❌ Usage: <code>/approve 123456789 P500</code>\n"
                           "<i>ya kisi user ke message ka reply do</i>")
        return
    plan, days = None, PREMIUM_DAYS
    for a in args:
        up = a.upper()
        if up in PLAN_BY_KEY:
            plan = up
        elif a.isdigit() and int(a) in PLAN_BY_FILES:
            plan = PLAN_BY_FILES[int(a)]["key"]
        elif a.isdigit() and uid and int(a) != uid and 0 < int(a) <= 3650 \
                and int(a) not in PLAN_BY_FILES:
            days = int(a)                     # user-id ko days mat samajh lo
    p = await activate_plan(uid, plan or "P500", days)
    if not p:
        await m.reply_text(f"❌ Plan nahi mila: <code>{esc(plan)}</code>")
        return
    await STORE.upsert("requests", "user_id", uid, {"status": "approved", "ts": time.time()})
    await m.reply_text(
        f"✅ <b>APPROVED!</b>\n\n👤 User : <code>{uid}</code>\n"
        f"👑 Plan : <b>{p['name']}</b> ({p['files']} files)\n"
        f"💰 Paid : ₹{p['price']}\n📅 Days : <b>{days}</b>\n"
        f"⏰ Expiry : {exp_str(int(time.time() + days * 86400))}")


@handler(filters.command("reject") & is_admin)
async def cmd_reject(c, m: Message):
    uid = _parse_uid(m.text.split()[1:], m)
    if not uid:
        await m.reply_text("❌ Usage: <code>/reject 123456789</code>")
        return
    await STORE.upsert("requests", "user_id", uid, {"status": "rejected", "ts": time.time()})
    try:
        await CLIENT.send_message(
            uid, "❌ <b>Request Rejected</b>\n\nPayment proof verify nahi hua.\n"
                 f"Dobara /buy try karo ya {SUPPORT_TXT} se baat karo.")
    except Exception:
        pass
    await m.reply_text(f"🗑️ Rejected: <code>{uid}</code>")


@handler(filters.command("setplan") & is_admin)
async def cmd_setplan(c, m: Message):
    args = m.text.split()[1:]
    if len(args) < 2:
        await m.reply_text("❌ Usage: <code>/setplan 123456789 350 30</code>\n"
                           "<i>(user_id, files 200/350/500, days)</i>")
        return
    uid = int(args[0]) if args[0].lstrip("-").isdigit() else 0
    files = int(args[1]) if args[1].isdigit() else 0
    days = int(args[2]) if len(args) > 2 and args[2].isdigit() else PREMIUM_DAYS
    if files not in PLAN_BY_FILES:
        await m.reply_text("❌ Files sirf <b>200 / 350 / 500</b> ho sakti hain.")
        return
    p = await activate_plan(uid, PLAN_BY_FILES[files]["key"], days)
    await m.reply_text(f"✅ <code>{uid}</code> → <b>{p['name']}</b> "
                       f"({p['files']} files, {days} din)")


@handler(filters.command("removeplan") & is_admin)
async def cmd_removeplan(c, m: Message):
    uid = _parse_uid(m.text.split()[1:], m)
    if not uid:
        await m.reply_text("❌ Usage: <code>/removeplan 123456789</code>")
        return
    await STORE.upsert("users", "user_id", uid,
                       {"plan": None, "limit": FREE_LIMIT, "expiry": 0})
    try:
        await CLIENT.send_message(
            uid, f"ℹ️ Aapka plan hata diya gaya. Ab aap FREE ({FREE_LIMIT} files) par ho.")
    except Exception:
        pass
    await m.reply_text(f"🗑️ <code>{uid}</code> → FREE ({FREE_LIMIT} files)")


@handler(filters.command("user") & is_admin)
async def cmd_user(c, m: Message):
    args = m.text.split()[1:]
    uid = int(args[0]) if args and args[0].lstrip("-").isdigit() else None
    if not uid:
        uid = m.reply_to_message.from_user.id if m.reply_to_message else None
    if not uid:
        await m.reply_text("❌ Usage: <code>/user 123456789</code>")
        return
    u = await STORE.find_one("users", "user_id", uid)
    if not u:
        await m.reply_text(f"❌ User <code>{uid}</code> DB me nahi mila.")
        return
    await m.reply_text(
        f"👤 <b>USER DETAILS</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID      : <code>{u['user_id']}</code>\n"
        f"📛 Name    : {esc(u.get('name'))}\n"
        f"🔗 Username: {esc(u.get('username') or '—')}\n"
        f"👑 Plan    : <b>{plan_label(u)}</b>\n"
        f"⚡ Limit   : <b>{user_limit(u)}</b> files\n"
        f"📅 Expiry  : {exp_str(u.get('expiry')) or '—'}\n"
        f"🔎 Searches: {u.get('searches', 0)}\n"
        f"📦 Files   : {u.get('files_got', 0)}\n"
        f"📤 Forward : {'ON' if u.get('forward') else 'OFF'}\n"
        f"🕒 Joined  : {exp_str(u.get('joined'))}\n"
        f"🕒 Last    : {exp_str(u.get('last_seen'))}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{p['icon']} {p['files']}", callback_data=f"admap:{uid}:{p['key']}")
             for p in PLANS],
            [InlineKeyboardButton("🗑️ Remove Plan", callback_data=f"admrm:{uid}")],
        ]))


@handler(filters.command("find") & is_admin)
async def cmd_find(c, m: Message):
    parts = m.text.split(None, 1)
    q = parts[1].lower().strip() if len(parts) > 1 else ""
    if not q:
        await m.reply_text("❌ Usage: <code>/find rahul</code>")
        return
    users = await STORE.all_docs("users")
    hits = [u for u in users if q in (u.get("name") or "").lower()
            or q in (u.get("username") or "").lower() or q == str(u.get("user_id"))]
    if not hits:
        await m.reply_text("❌ Koi user nahi mila.")
        return
    lines = [f"🔎 <b>{len(hits)} users mile</b>", "━━━━━━━━━━━━━━━━━━━"]
    for u in hits[:30]:
        lines.append(f"• <code>{u['user_id']}</code> — {esc(u.get('name'))[:20]} | {plan_label(u)}")
    await m.reply_text("\n".join(lines))


@handler(filters.command("reqs") & is_admin)
async def cmd_reqs(c, m: Message):
    reqs = await STORE.all_docs("requests")
    pend = [r for r in reqs if r.get("status") == "pending"]
    if not pend:
        await m.reply_text("✅ Koi pending request nahi.")
        return
    lines = [f"🛒 <b>{len(pend)} PENDING REQUESTS</b>", "━━━━━━━━━━━━━━━━━━━"]
    for r in sorted(pend, key=lambda x: x.get("ts", 0), reverse=True)[:20]:
        p = PLAN_BY_KEY.get(r.get("plan"), {})
        proof = r.get("proof_text") or ("⏳ proof ka wait" if r.get("awaiting_proof") else "—")
        lines.append(f"• <code>{r['user_id']}</code> — {p.get('name', '?')} "
                     f"({p.get('files', '?')} files) ₹{p.get('price', '?')}\n"
                     f"   🧾 <code>{esc(proof)[:45]}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ Approve: <code>/approve &lt;id&gt; P500</code>")
    await m.reply_text("\n".join(lines))


@handler(filters.command("usage") & is_admin)
async def cmd_usage(c, m: Message):
    users = await STORE.all_docs("users")
    prem = [u for u in users if u.get("plan") and not is_expired(u)]
    lines = [f"💎 <b>{len(prem)} ACTIVE PREMIUM</b>", "━━━━━━━━━━━━━━━━━━━"]
    for u in sorted(prem, key=lambda x: x.get("expiry") or 0)[:40]:
        p = PLAN_BY_KEY.get(u.get("plan"), {})
        left = int(((u.get("expiry") or 0) - time.time()) // 86400)
        lines.append(f"• <code>{u['user_id']}</code> — {p.get('name', '?')} | {left}d left")
    rev = sum(PLAN_BY_KEY.get(u.get("plan"), {}).get("price", 0) for u in prem)
    lines += ["━━━━━━━━━━━━━━━━━━━",
              f"💰 Approx monthly revenue : <b>₹{rev}</b>",
              f"👥 Total users : {len(users)} | 🆓 Free : {len(users) - len(prem)}"]
    await m.reply_text("\n".join(lines))


@handler(filters.command("broadcast") & is_admin)
async def cmd_broadcast(c, m: Message):
    parts = m.text.split(None, 1)
    txt = parts[1] if len(parts) > 1 else None
    rep = m.reply_to_message
    if not txt and not rep:
        await m.reply_text("❌ Usage: <code>/broadcast message</code> ya kisi message ka reply do.")
        return
    users = await STORE.all_docs("users")
    ok = fail = 0
    st = await m.reply_text(f"📣 Broadcast start… {len(users)} users")
    for u in users:
        try:
            if txt:
                await CLIENT.send_message(u["user_id"], txt, disable_web_page_preview=True)
            else:
                await rep.copy(u["user_id"])
            ok += 1
        except FloodWait as e:
            await asyncio.sleep(min(e.value, 30))
        except Exception:
            fail += 1
        if (ok + fail) % 25 == 0:
            try:
                await st.edit_text(f"📣 Broadcast… ✅{ok} ❌{fail} / {len(users)}")
            except Exception:
                pass
        await asyncio.sleep(0.06)
    await st.edit_text(f"✅ <b>Broadcast Done</b>\n\n📤 Sent : {ok}\n❌ Failed : {fail}\n"
                       f"👥 Total : {len(users)}")


@handler(filters.command("del") & is_admin)
async def cmd_del(c, m: Message):
    if m.reply_to_message:
        try:
            await m.reply_to_message.delete()
            await m.delete()
        except Exception as e:
            await m.reply_text(f"❌ {esc(e)}")

# ═══════════════════════════════ CALLBACKS ══════════════════════════════════

# ═════════════════ /settings — THUMBNAIL + CAPTION UI ════════════════════

def _set_kb(st):
    on = lambda b: "✅" if b else "❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🖼️ Thumbnail : {'LAGA HAI ✅' if st.get('thumb') else 'nahi ❌'}",
            callback_data="set:thumbinfo")],
        [InlineKeyboardButton("➕ Thumbnail set", callback_data="set:thumbhow"),
         InlineKeyboardButton("🗑️ Thumb hatao", callback_data="set:thumbdel")],
        [InlineKeyboardButton(
            f"📝 Caption : {'CUSTOM ✅' if st.get('caption') else 'original'}",
            callback_data="set:capinfo")],
        [InlineKeyboardButton("✏️ Caption likho", callback_data="set:cap"),
         InlineKeyboardButton("🗑️ Caption reset", callback_data="set:capdel")],
        [InlineKeyboardButton(
            f"✂️ Caption se KAATO ({len(st.get('cut') or [])})",
            callback_data="set:cutlist")],
        [InlineKeyboardButton("➕ Cut add", callback_data="set:cut"),
         InlineKeyboardButton("🗑️ Cut clear", callback_data="set:cutdel")],
        [InlineKeyboardButton("🔝 Prefix", callback_data="set:prefix"),
         InlineKeyboardButton("🔚 Suffix", callback_data="set:suffix")],
        [InlineKeyboardButton(
            f"🔢 Sequence (order me) : {on(st.get('sequence', True))}",
            callback_data="set:seq")],
        [InlineKeyboardButton("👁️ PREVIEW dekho", callback_data="set:preview")],
        [InlineKeyboardButton("♻️ Sab reset", callback_data="set:reset")],
    ])


def _set_txt(st):
    cut = st.get("cut") or []
    return (
        "🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n"
        "⚙️ <b>SPARTA SETTINGS</b>\n"
        "🫧 ✨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄✨\n\n"
        f"🖼️ <b>Thumbnail</b> : {'set hai ✅' if st.get('thumb') else 'nahi ❌'}\n"
        f"📝 <b>Caption</b>   : {'custom ✅' if st.get('caption') else 'original rakhega'}\n"
        f"✂️ <b>Cut list</b>  : <b>{len(cut)}</b> item"
        + (f" — <code>{esc(', '.join(cut[:4]))}</code>" if cut else "") + "\n"
        f"🔝 <b>Prefix</b>    : {esc(st.get('prefix') or '—')}\n"
        f"🔚 <b>Suffix</b>    : {esc(st.get('suffix') or '—')}\n"
        f"🔢 <b>Sequence</b>  : {'ON ✅ (files order me)' if st.get('sequence', True) else 'OFF'}\n\n"
        "<i>Neeche buttons se set karo 👇</i>")


@handler(filters.command(["settings", "setting", "custom"]) & filters.private)
async def cmd_settings(c, m: Message):
    st = await get_set(m.from_user.id)
    await m.reply_text(_set_txt(st), reply_markup=_set_kb(st))


@handler(filters.photo & filters.private)
async def catch_thumb(c, m: Message):
    """Photo bheji = thumbnail set (agar user ne thumb mode chalu kiya ho)."""
    uid = m.from_user.id
    if SET_WAIT.get(uid) != "thumb":
        return
    SET_WAIT.pop(uid, None)
    os.makedirs(THUMB_DIR, exist_ok=True)
    path = os.path.join(THUMB_DIR, f"{uid}.jpg")
    try:
        await c.download_media(m, file_name=path)
        await save_set(uid, thumb=path)
        st = await get_set(uid)
        await m.reply_text(
            "✅ <b>Thumbnail set ho gaya!</b>\n\n"
            "Ab jo bhi video/document aayega, usme yahi thumbnail lagega 🖼️",
            reply_markup=_set_kb(st))
    except Exception as e:
        await m.reply_text(f"❌ Thumbnail save fail: <code>{esc(str(e)[:80])}</code>")


@handler(filters.text & filters.private & filters.create(
    lambda _f, _c, msg: SET_WAIT.get(getattr(msg.from_user, "id", 0)) in
    ("caption", "cut", "prefix", "suffix")), group=-1)
async def catch_set_text(c, m: Message):
    """Caption / cut / prefix / suffix ka text input."""
    uid = m.from_user.id
    mode = SET_WAIT.pop(uid, None)
    txt = (m.text or "").strip()
    if txt.lower() in ("/cancel", "cancel", "band"):
        st = await get_set(uid)
        return await m.reply_text("✅ Theek hai, kuch nahi badla.",
                                  reply_markup=_set_kb(st))

    if mode == "caption":
        await save_set(uid, caption=txt)
        msg = "✅ <b>Custom caption set!</b>"
    elif mode == "cut":
        st = await get_set(uid)
        cuts = list(st.get("cut") or [])
        for line in txt.split("\n"):
            line = line.strip()
            if line and line not in cuts:
                cuts.append(line)
        await save_set(uid, cut=cuts[:50])
        msg = f"✅ <b>Cut list update</b> — ab <b>{len(cuts[:50])}</b> item hain."
    elif mode == "prefix":
        await save_set(uid, prefix=txt)
        msg = "✅ <b>Prefix set!</b>"
    else:
        await save_set(uid, suffix=txt)
        msg = "✅ <b>Suffix set!</b>"

    st = await get_set(uid)
    demo = apply_caption(
        "🎬 Physics Lecture 01 - NEET 2025\n📚 @SomeOtherChannel\njoin fast",
        st, "Physics_L01.mp4")
    await m.reply_text(
        f"{msg}\n\n👁️ <b>Preview</b>:\n<code>{esc(demo or '(khali)')}</code>",
        reply_markup=_set_kb(st))


@handler(filters.regex(r"^set:"), kind="callback")
async def cb_settings(c, q: CallbackQuery):
    uid = q.from_user.id
    act = q.data.split(":", 1)[1]
    st = await get_set(uid)

    async def _refresh(note=None):
        s2 = await get_set(uid)
        try:
            await q.message.edit_text(_set_txt(s2), reply_markup=_set_kb(s2))
        except Exception:
            pass
        if note:
            await q.answer(note)

    if act == "thumbhow":
        SET_WAIT[uid] = "thumb"
        await q.answer()
        return await q.message.reply_text(
            "🖼️ <b>Ab ek PHOTO bhejo</b> — wahi thumbnail ban jayegi.\n\n"
            "<i>Cancel karna ho to /settings dobara bhejo.</i>")
    if act == "thumbdel":
        t = st.get("thumb")
        if t and os.path.exists(t):
            try:
                os.remove(t)
            except Exception:
                pass
        await save_set(uid, thumb=None)
        return await _refresh("Thumbnail hata diya 🗑️")
    if act == "thumbinfo":
        return await q.answer(
            "Video/document pe apni photo thumbnail lagegi." if st.get("thumb")
            else "Abhi original thumbnail hi jaata hai.", show_alert=True)

    if act == "cap":
        SET_WAIT[uid] = "caption"
        await q.answer()
        return await q.message.reply_text(
            "✏️ <b>Caption likh ke bhejo.</b>\n\n"
            "Placeholders use kar sakte ho:\n"
            "• <code>{original}</code> — original caption (cut lagne ke baad)\n"
            "• <code>{filename}</code> — file ka naam\n\n"
            "<b>Example:</b>\n"
            "<code>🎬 {filename}\n\n{original}\n\n👑 @THE_SPARTAN_300</code>\n\n"
            "<i>Cancel = /cancel</i>")
    if act == "capdel":
        await save_set(uid, caption=None)
        return await _refresh("Caption reset — original aayega ✅")
    if act == "capinfo":
        return await q.answer((st.get("caption") or "Original caption jaata hai")[:190],
                              show_alert=True)

    if act == "cut":
        SET_WAIT[uid] = "cut"
        await q.answer()
        return await q.message.reply_text(
            "✂️ <b>Kya-kya KAATNA hai?</b> Ek line me ek cheez bhejo:\n\n"
            "<code>@OtherChannel\njoin fast\nt.me/spam</code>\n\n"
            "Ye sab original caption se hat jayega.\n"
            "🧠 Advanced: <code>re:</code> se regex — jaise "
            "<code>re:@\\w+</code> (saare @tags udao) ya "
            "<code>re:https?://\\S+</code> (saare links udao)\n\n"
            "<i>Cancel = /cancel</i>")
    if act == "cutdel":
        await save_set(uid, cut=[])
        return await _refresh("Cut list khali ✅")
    if act == "cutlist":
        cut = st.get("cut") or []
        return await q.answer("\n".join(f"• {x}" for x in cut[:10]) or
                              "Cut list khali hai.", show_alert=True)

    if act in ("prefix", "suffix"):
        SET_WAIT[uid] = act
        await q.answer()
        return await q.message.reply_text(
            f"{'🔝 Prefix' if act == 'prefix' else '🔚 Suffix'} "
            f"ka text bhejo — ye har caption ke "
            f"{'upar' if act == 'prefix' else 'neeche'} lagega.\n\n"
            "<i>Cancel = /cancel</i>")

    if act == "seq":
        await save_set(uid, sequence=not st.get("sequence", True))
        s2 = await get_set(uid)
        return await _refresh("Sequence ON — files order me aayengi 🔢"
                              if s2["sequence"] else "Sequence OFF — max speed ⚡")

    if act == "preview":
        demo = apply_caption(
            "🎬 Physics Lecture 01 - NEET 2025\n📚 @SomeOtherChannel\njoin fast\n"
            "https://t.me/spamlink", st, "Physics_L01.mp4")
        return await q.answer(
            f"Aisa caption jayega:\n\n{demo or '(khali caption)'}"[:195],
            show_alert=True)

    if act == "reset":
        t = st.get("thumb")
        if t and os.path.exists(t):
            try:
                os.remove(t)
            except Exception:
                pass
        await save_set(uid, **DEFAULT_SET)
        return await _refresh("Sab reset ✅")

    await q.answer()


@handler(filters.regex(r"^cancelreq$"), kind="callback")
async def cb_cancel_req(c, q: CallbackQuery):
    """'❌ Purani request CANCEL karo' button ka handler."""
    chat_id = q.message.chat.id
    uid = q.from_user.id
    info = BUSY_INFO.get(chat_id)
    if chat_id not in BUSY or not info:
        await q.answer("Koi request chal hi nahi rahi ✅")
        try:
            await q.message.edit_text(
                "✅ <b>Koi request pending nahi</b> — naya link bhej sakte ho! 🫧")
        except Exception:
            pass
        return
    if info.get("uid") != uid and uid not in ADMINS:
        return await q.answer("Sirf request bhejne wala hi cancel kar sakta hai.",
                              show_alert=True)
    task = info.get("task")
    busy_del(chat_id)
    if task and not task.done() and task is not asyncio.current_task():
        task.cancel()
        log.info("❌ user-cancel: chat=%s task cancel kiya", chat_id)
    await q.answer("❌ Cancel kar diya!")
    try:
        await q.message.edit_text(
            "❌ <b>Purani request cancel kar di gayi.</b>\n\n"
            "✅ Ab naya link bhejo — turant process hoga! 🫧")
    except Exception:
        pass


@handler(filters.regex(r"^menu:settings$"), kind="callback", group=-1)
async def cb_menu_settings(c, q: CallbackQuery):
    st = await get_set(q.from_user.id)
    await q.answer()
    try:
        await q.message.edit_text(_set_txt(st), reply_markup=_set_kb(st))
    except Exception:
        await q.message.reply_text(_set_txt(st), reply_markup=_set_kb(st))


@handler(filters.regex(r"^menu:"), kind="callback")
@handler(filters.regex(r"^ask:"), kind="callback")
async def cb_ask(c, q: CallbackQuery):
    """'Kitni files chahiye?' ke buttons ka jawab."""
    chat_id = q.message.chat.id
    st = ASK_PENDING.get(chat_id)
    if not st or st["uid"] != q.from_user.id or time.time() - st["ts"] > ASK_TTL:
        ASK_PENDING.pop(chat_id, None)
        return await q.answer("⌛ Time out ho gaya — link dobara bhejo.", show_alert=True)
    act = q.data.split(":", 1)[1]
    if act == "cancel":
        ASK_PENDING.pop(chat_id, None)
        await q.answer()
        return await q.message.edit_text("❌ Cancel kar diya. Dobara link bhejo.")
    try:
        n = int(act)
    except ValueError:
        return await q.answer()
    ASK_PENDING.pop(chat_id, None)
    if st.get("mode") == "fwd":
        u2 = await get_user(q.from_user, chat_id)
        n = max(1, min(n, user_limit(u2)))
        if n == 1:
            sel = await scan_forward(st["chat"], st["start"], 1,
                                                 topic=st.get("topic"))
            if not sel:
                sel = [(st["chat"], st["start"])]
        else:
            await q.answer(f"🔍 {n} files dhundh raha hoon…")
            try:
                await q.message.edit_text(
                    f"🔍 Link ke neeche scan kar raha hoon… ⏳\n"
                    f"📚 Mili: <b>0/{n}</b> files")
            except Exception:
                pass

            async def _pf2(found, upto, flood=0):
                try:
                    await q.message.edit_text(
                        f"🔍 Link ke neeche scan chal raha hai… ⏳\n"
                        f"📚 Mili: <b>{found}/{n}</b> files\n"
                        f"💬 Check hue: {max(0, upto - st['start'])} messages"
                        + (f"\n⏳ Telegram ne {flood}s wait diya — "
                           f"apne aap resume hoga 🫧" if flood else ""))
                except Exception:
                    pass

            sel = await scan_forward(st["chat"], st["start"], n,
                                                 topic=st.get("topic"), on_progress=_pf2)
            if not sel:
                return await q.message.reply_text(
                    "⚠️ Is link ke neeche <b>koi file nahi mili</b>.")
        await handle_links(q.message, sel, _from_ask=True, _user=q.from_user, _total=n)
        return
    pairs = st["pairs"][:n]
    await q.answer(f"📥 {len(pairs)} files load ho rahi hain…")
    try:
        await q.message.edit_text(f"📥 <b>{len(pairs)} files</b> select ki — loading shuru! ⏳")
    except Exception:
        pass
    await handle_links(q.message, pairs, _from_ask=True, _user=q.from_user)


async def cb_menu(c, q: CallbackQuery):
    act = q.data.split(":", 1)[1]
    u = await get_user(q.from_user, q.message.chat.id)
    msg = q.message

    if act == "start":
        await msg.edit_text(start_txt(u, q.from_user), reply_markup=kb_main(),
                            disable_web_page_preview=True)
    elif act == "search":
        await msg.edit_text(
            "🔎 <b>SEARCH MODE ON</b>\n\nAb file ka naam type karo 👇\n"
            f"🎯 Aapka limit : <b>{user_limit(u)} files</b>\n\n❌ /cancel",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Upgrade Limit", callback_data="menu:plans"),
                  InlineKeyboardButton("🔙 Back", callback_data="menu:start")]]))
    elif act == "plans":
        await msg.edit_text(plans_txt(u), reply_markup=kb_plans(),
                            disable_web_page_preview=True)
    elif act == "buy":
        await msg.edit_text(
            "🛒 <b>BUY PREMIUM</b>\n\nApna plan chuno 👇\n\n"
            f"💳 Payment : <code>{esc(PAYMENT_INFO)}</code>",
            reply_markup=kb_plans(), disable_web_page_preview=True)
    elif act == "myplan":
        left = ""
        if u.get("expiry") and u["expiry"] > time.time():
            d = u["expiry"] - time.time()
            left = f" ({int(d // 86400)}d {int((d % 86400) // 3600)}h left)"
        await msg.edit_text(
            f"👑 <b>MY PLAN</b>\n━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Plan   : <b>{plan_label(u)}</b>\n"
            f"⚡ Limit  : <b>{user_limit(u)} files</b>/search\n"
            f"📅 Expiry : {exp_str(u.get('expiry')) or '—'}{left}\n"
            f"🔎 Searches : {u.get('searches', 0)}\n"
            f"📦 Files Got: {u.get('files_got', 0)}\n"
            f"📤 Forward  : {'ON' if u.get('forward') else 'OFF'}\n"
            f"━━━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Upgrade", callback_data="menu:plans"),
                  InlineKeyboardButton("🔙 Back", callback_data="menu:start")]]))
    elif act == "stats":
        cnt = await STORE.get_counters()
        await msg.edit_text(
            f"📊 <b>STATS</b>\n━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Users : {await STORE.count('users')}\n"
            f"📦 Files : {await STORE.count('files')}\n"
            f"🔎 Searches : {cnt.get('searches', 0)}\n"
            f"📤 Files Sent : {cnt.get('files_sent', 0)}\n"
            f"🗄️ Store : {STORE_KIND}\n"
            f"⚡ Loop : {'uvloop' if UVLOOP else 'asyncio'}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="menu:start")]]))
    elif act == "help":
        await msg.edit_text(HELP_TXT, disable_web_page_preview=True,
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("🔙 Back", callback_data="menu:start")]]))
    await q.answer()


@handler(filters.regex(r"^buy:"), kind="callback")
async def cb_buy(c, q: CallbackQuery):
    p = PLAN_BY_KEY.get(q.data.split(":", 1)[1])
    if not p:
        return await q.answer("❌ Invalid plan")
    uid = q.from_user.id
    u = await get_user(q.from_user, q.message.chat.id)
    await STORE.upsert("requests", "user_id", uid, {
        "user_id": uid, "plan": p["key"], "plan_files": p["files"], "plan_price": p["price"],
        "status": "pending", "awaiting_proof": 1, "ts": time.time(),
        "name": u.get("name"), "username": u.get("username")})

    await q.message.edit_text(
        f"🛒 <b>{p['name']}</b> selected!\n━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Limit  : <b>{p['files']} files</b> per search\n"
        f"💰 Price  : <b>₹{p['price']} / month</b>\n"
        f"📅 Valid  : <b>{PREMIUM_DAYS} days</b>\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 <b>Payment karo:</b>\n<code>{esc(PAYMENT_INFO)}</code>\n\n"
        f"📸 Payment ke baad <b>screenshot ya UTR</b> isi bot ko bhej do.\n"
        f"Admin approve karte hi plan <b>instantly</b> active ⚡\n\n📞 Help: {SUPPORT_TXT}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Plans", callback_data="menu:plans")]]),
        disable_web_page_preview=True)

    for target in filter(None, [ADMIN_ID, LOG_CHANNEL]):
        try:
            await CLIENT.send_message(
                target,
                f"🛒 <b>New Buy Request</b>\n👤 {username_link(q.from_user)}\n"
                f"🆔 <code>{uid}</code>\n👑 Plan : <b>{p['name']} ({p['files']} files)</b>\n"
                f"💰 ₹{p['price']}/month\n\n<i>Payment proof ka wait hai…</i>",
                reply_markup=kb_admin(uid) if target == ADMIN_ID else None)
        except Exception:
            pass
    await q.answer("✅ Plan selected — payment karo!")


async def notify_admin_request(m: Message, pend: dict, proof: str):
    p = PLAN_BY_KEY.get(pend.get("plan"), {})
    txt = (f"💰 <b>PAYMENT PROOF RECEIVED</b>\n━━━━━━━━━━━━━━━━━━━\n"
           f"👤 User  : {username_link(m.from_user)}\n"
           f"🆔 ID    : <code>{m.from_user.id}</code>\n"
           f"👑 Plan  : <b>{p.get('name', '?')} ({p.get('files', '?')} files)</b>\n"
           f"💰 Amount: <b>₹{p.get('price', '?')}</b>\n"
           f"🧾 Proof : <code>{esc(proof)[:200]}</code>\n━━━━━━━━━━━━━━━━━━━\n\n"
           f"✅ <code>/approve {m.from_user.id} {p.get('key', 'P500')}</code>\n"
           f"❌ <code>/reject {m.from_user.id}</code>")
    for target in filter(None, [LOG_CHANNEL, ADMIN_ID]):
        try:
            await CLIENT.send_message(target, txt,
                                      reply_markup=kb_admin(m.from_user.id) if target == ADMIN_ID else None)
        except Exception:
            pass
    if m.photo or m.document:
        for target in filter(None, [LOG_CHANNEL, ADMIN_ID]):
            try:
                await m.copy(target)
            except Exception:
                pass


@handler(filters.regex(r"^adminidx:"), kind="callback")
async def cb_admin_index(c, q: CallbackQuery):
    if q.from_user.id not in ADMINS:
        return await q.answer("⛔ Admin only!")
    if q.data.split(":")[1] == "0":
        await q.answer("⏭️ Theek hai")
        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await q.message.reply_text(
            "👍 Baad me /index bhej dena. Tab tak search kaam nahi karegi.")
    await q.answer("🔄 Indexing start!")
    if not DB_CHANNEL:
        return await q.message.reply_text("❌ DB_CHANNEL set nahi — pehle /setdb karo.")
    msg = await q.message.reply_text(
        f"🔄 <b>Indexing start…</b>\n📢 <code>{DB_CHANNEL}</code>\n<i>Progress yahan dikhega ⚡</i>")
    ok, out = await run_index(rebuild=True, progress_msg=msg)
    try:
        await msg.edit_text(out)
    except Exception:
        await q.message.reply_text(out)


@handler(filters.regex(r"^adm(ap|rej|info|rm):"), kind="callback")
async def cb_admin(c, q: CallbackQuery):
    if q.from_user.id not in ADMINS:
        return await q.answer("⛔ Admin only!")
    parts = q.data.split(":")
    act, uid = parts[0][3:], int(parts[1])
    plan = parts[2] if len(parts) > 2 else None

    if act == "ap":
        p = await activate_plan(uid, plan or "P500")
        await STORE.upsert("requests", "user_id", uid, {"status": "approved", "ts": time.time()})
        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.answer(f"✅ Approved {p['name']}" if p else "❌ fail")
        try:
            await q.message.reply_text(
                f"✅ <b>APPROVED</b> → <code>{uid}</code>\n"
                f"👑 {p['name']} • {p['files']} files • {PREMIUM_DAYS} days")
        except Exception:
            pass
    elif act == "rej":
        await STORE.upsert("requests", "user_id", uid, {"status": "rejected", "ts": time.time()})
        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.answer("🗑️ Rejected")
    elif act == "rm":
        await STORE.upsert("users", "user_id", uid,
                           {"plan": None, "limit": FREE_LIMIT, "expiry": 0})
        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.answer(f"🗑️ {uid} → FREE")
    elif act == "info":
        u = await STORE.find_one("users", "user_id", uid)
        if not u:
            return await q.answer("❌ User not found")
        await q.answer()
        await q.message.reply_text(
            f"👤 <code>{uid}</code>\n📛 {esc(u.get('name'))}\n👑 {plan_label(u)}\n"
            f"⚡ {user_limit(u)} files\n📅 {exp_str(u.get('expiry')) or '—'}\n"
            f"🔎 {u.get('searches', 0)} searches")

# ───────────────────────── group search + media proof ───────────────────────

async def _group_trigger(_, __, m: Message):
    t = (m.text or "")
    if re.match(r"^/search(@\w+)?(\s|$)", t, re.I):
        return True
    for e in (getattr(m, "entities", None) or []):
        if getattr(e, "type", None) in ("mention", "text_mention"):
            return True
    return False


@handler(filters.group & filters.create(_group_trigger))
async def group_search(c, m: Message):
    parts = (m.text or "").split(None, 1)
    q = parts[1].strip() if len(parts) > 1 else ""
    q = re.sub(r"^@\w+\s*", "", q).strip()
    if not q:
        await m.reply_text("🔎 Usage: <code>/search file ka naam</code>")
        return
    await handle_search(m, q)


@handler(filters.private & (filters.photo | filters.document))
async def on_media(c, m: Message):
    pend = await STORE.find_one("requests", "user_id", m.from_user.id)
    if pend and pend.get("status") == "pending" and (time.time() - pend.get("ts", 0)) < 1800:
        await STORE.upsert("requests", "user_id", m.from_user.id,
                           {"awaiting_proof": 0, "ts": time.time(),
                            "proof_text": (m.caption or "📸 screenshot sent")[:300]})
        await m.reply_text(
            "✅ <b>Payment proof mil gaya!</b>\n\n"
            f"⏳ Admin verify karke plan activate kar dega ({PREMIUM_DAYS} din). "
            "Activate hote hi message aayega ⚡")
        await notify_admin_request(m, pend, m.caption or "📸 screenshot")
        return
    await m.reply_text("📸 Screenshot sirf premium buy karte waqt bhejo.\n\n"
                       "🔎 File search ke liye bas <b>naam type karo</b> ya /search dabao.")

# ═══════════════════════════════ STARTUP ════════════════════════════════════

async def start_userbot():
    """Userbot (aapka account) start karo — link mode ke liye zaroori."""
    global USERBOT, USERBOT_OK, USERBOT_ME
    if not (SESSION_STRING or Path(SESSION_FILE).exists()):
        log.warning("🔗 Link mode: userbot session nahi mila -> userbot_login.py chalao")
        return False
    try:
        kwargs = dict(api_id=API_ID, api_hash=API_HASH, workers=32,
                      max_concurrent_transmissions=UB_TRANSMISSIONS,
                      sleep_threshold=25,
                      # Telegram me session ka naam clean dikhe (default "CPython 3.x" hota hai)
                      device_model=DEVICE_NAME, system_version="Ubuntu 22.04",
                      app_version=f"{BOT_NAME} 1.0")
        if USERBOT is not None:
            try:
                await USERBOT.stop()
            except Exception:
                pass
        sess_file = Path(SESSION_FILE)
        if sess_file.exists():
            # FILE session prefer karo — isme peer/access-hash cache persist hota
            # hai, warna har restart pe private chats PEER_ID_INVALID deti hain.
            USERBOT = Client(name=sess_file.with_suffix("").name, **kwargs)
            log.info("👤 userbot session: file (%s)", sess_file)
        elif SESSION_STRING:
            USERBOT = Client(name="sparta_ub", session_string=SESSION_STRING,
                             in_memory=True, **kwargs)
            log.info("👤 userbot session: string (in-memory)")
        else:
            log.warning("🔗 Link mode: userbot session nahi mila -> userbot_login.py chalao")
            return False
        await USERBOT.start()
        USERBOT_ME = await USERBOT.get_me()
        USERBOT_OK = True
        log.info("👤 Userbot connected: %s (id=%s)", USERBOT_ME.first_name, USERBOT_ME.id)
        if CACHE_CHANNEL:
            try:
                await USERBOT.get_chat(CACHE_CHANNEL)
                log.info("🗄️ Userbot cache channel OK: %s", CACHE_CHANNEL)
            except Exception as e:
                log.warning("⚠️ Userbot cache channel access fail: %s", e)
        return True
    except Exception as e:
        USERBOT_OK = False
        log.error("❌ Userbot start fail: %s", e)
        if ADMIN_ID:
            try:
                await CLIENT.send_message(
                    ADMIN_ID,
                    f"❌ <b>Userbot start nahi hua</b>\n<code>{esc(e)[:300]}</code>\n\n"
                    f"👉 Session expire ho gaya ho sakta hai — <code>userbot_login.py</code> "
                    f"dobara chalao.")
            except Exception:
                pass
        return False


class _HealthHandler(BaseHTTPRequestHandler):
    """Uptime/health endpoint — UptimeRobot yahan ping karega."""
    def do_GET(self):
        body = json.dumps({"ok": True, "bot": BOT_NAME,
                           "uvloop": UVLOOP, "link_mode": LINK_MODE}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a):
        pass


def start_health_server():
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", HEALTH_PORT), _HealthHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info("🩺 health/uptime server: http://0.0.0.0:%d/  (200 OK)", HEALTH_PORT)
        return srv
    except OSError as e:
        log.warning("health server port %s busy/fail: %s", HEALTH_PORT, e)
        return None


async def self_ping_loop():
    """Apne hi public URL ko har kuch minute me ping karo (free-tier sleep rokne ke liye)."""
    if not SELF_PING_URL:
        return
    import urllib.request
    log.info("🔁 self-ping ON: %s (har %ds)", SELF_PING_URL, SELF_PING_EVERY)
    while True:
        await asyncio.sleep(SELF_PING_EVERY)
        try:
            def _get_url():
                with urllib.request.urlopen(SELF_PING_URL, timeout=15) as r:
                    return r.status
            st = await asyncio.get_event_loop().run_in_executor(None, _get_url)
            log.info("🔁 self-ping ok (%s)", st)
        except Exception as e:
            log.warning("🔁 self-ping fail: %s", e)


async def bot_warm_cache_peer():
    """Bot ke storage me cache channel ka access hash warm karo (retry ke saath)."""
    if not CACHE_CHANNEL:
        return
    for i in range(8):
        try:
            await CLIENT.get_chat(CACHE_CHANNEL)
            log.info("🤖 bot cache peer OK: %s", CACHE_CHANNEL)
            return
        except Exception:
            await asyncio.sleep(2)
    log.warning("bot cache peer warm fail — fetch retries sambhal lenge")


async def startup_tasks():
    global STORE, STORE_KIND
    STORE, STORE_KIND = await build_store()
    log.info("🚀 %s online (uvloop=%s, store=%s)", BOT_NAME, UVLOOP, STORE_KIND)

    if AUTO_INDEX and DB_CHANNEL:
        total = await STORE.count("files")
        if total == 0:
            log.info("Auto-index start (DB empty)…")
            asyncio.create_task(run_index(rebuild=False))
        else:
            log.info("Index me %d files hain (auto-index skip; /reindex se refresh)", total)

    if LINK_MODE:
        if await start_userbot():
            asyncio.create_task(warm_peer_cache())
        asyncio.create_task(userbot_watchdog())
    if SELF_PING_URL:
        asyncio.create_task(self_ping_loop())
    if CACHE_CHANNEL:
        asyncio.create_task(bot_warm_cache_peer())

    for target in filter(None, [ADMIN_ID, LOG_CHANNEL]):
        try:
            await CLIENT.send_message(
                target,
                f"✅ <b>{BOT_NAME} ONLINE!</b>\n\n"
                f"🔗 Link mode : {'✅ READY' if await ub_ready() else '⚠️ setup baaki (/status dekho)'}\n"
                f"👤 Userbot   : {'✅ ' + (USERBOT_ME.first_name if USERBOT_ME else '') if USERBOT_OK else '❌ session nahi'}\n"
                f"🗄️ Cache ch. : {CACHE_CHANNEL or '❌ not set'}\n"
                f"🗄️ Store : {STORE_KIND}\n"
                f"📦 Files : {await STORE.count('files')}\n"
                f"👥 Users : {await STORE.count('users')}\n"
                f"⚡ uvloop : {'ON' if UVLOOP else 'OFF'}\n"
                f"🆓 Free limit : {FREE_LIMIT} files\n"
                f"💎 Plans : 200/₹100 • 350/₹150 • 500/₹250\n\n"
                f"🛡️ Admin commands: /index /approve /setplan /reqs /usage /stats")
        except Exception as e:
            log.warning("startup notify fail (%s): %s", target, e)


async def shutdown_tasks():
    try:
        if STORE_KIND == "JSON" and STORE is not None:
            await STORE.flush()
    except Exception:
        pass
    try:
        if USERBOT_OK and USERBOT is not None:
            await USERBOT.stop()
            log.info("👤 Userbot stopped")
    except Exception:
        pass


def register_handlers():
    for flt, fn, kind, grp in sorted(HANDLERS, key=lambda h: h[3]):
        if kind == "callback":
            CLIENT.add_handler(CallbackQueryHandler(fn, flt), grp)
        else:
            CLIENT.add_handler(MessageHandler(fn, flt), grp)
    log.info("🔧 %d handlers registered", len(HANDLERS))


def preflight():
    problems = []
    if not BOT_TOKEN or "PASTE" in BOT_TOKEN:
        problems.append("BOT_TOKEN set nahi (BotFather se lo)")
    if not API_ID or not API_HASH or "PASTE" in str(API_HASH):
        problems.append("API_ID / API_HASH set nahi (my.telegram.org se lo)")
    if not ADMIN_ID:
        problems.append("ADMIN_ID set nahi (bot ko /id bhej ke ID lo)")
    if not DB_CHANNEL and not CACHE_CHANNEL:
        problems.append("DB_CHANNEL / CACHE_CHANNEL dono set nahi — link mode ke liye /setcache, "
                        "search mode ke liye /setdb karo")
    if not MONGO_URI:
        problems.append("[info] MONGO_URI nahi hai -> JSON store use hoga (chalega, par Mongo better)")
    return problems


async def main():
    global CLIENT
    for p in preflight():
        log.warning("CONFIG :: %s", p)
    start_health_server()            # uptime/keep-alive ke liye (PORT pe 200 OK)
    CLIENT = build_client()          # running loop ke andar banao (zaroori!)
    # ── FLOOD-SAFE BOT LOGIN ──
    # Bar-bar restart hone pe Telegram sign_in pe FloodWait deta hai. Crash hoke
    # turant restart = flood aur badhta hai. Isliye yahin wait karke retry karo.
    for _try in range(12):
        try:
            await CLIENT.start()
            break
        except FloodWait as _fw:
            _w = int(getattr(_fw, "value", 60) or 60)
            log.warning("⏳ Bot login FloodWait %ss — wait karke retry (%d/12) "
                        "[restart mat karo, khud resume hoga]", _w, _try + 1)
            await asyncio.sleep(_w + 5)
        except Exception as _e:
            log.error("❌ Bot login fail: %s — 20s me retry", _e)
            await asyncio.sleep(20)
    else:
        log.error("❌ Bot login baar-baar fail — process exit")
        raise SystemExit(1)
    me = await CLIENT.get_me()
    log.info("🤖 Logged in as @%s (id=%s)", me.username, me.id)
    register_handlers()
    await startup_tasks()
    print(f"\n⚡ {BOT_NAME} chal raha hai… Ctrl+C se band karo.\n")
    await idle()
    await shutdown_tasks()
    await CLIENT.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Bot stopped. 🙏 THANK YOU FOR CHOOSING %s", BOT_NAME)

# ═══════════════════════════════ DEPLOY NOTES ═══════════════════════════════
#  Dockerfile:
#    FROM python:3.11-slim
#    WORKDIR /app
#    RUN pip install -U pyrogram tgcrypto motor uvloop
#    COPY sparta_bot.py .
#    CMD ["python", "sparta_bot.py"]
#
#  Procfile (Heroku):     worker: python sparta_bot.py
#  Koyeb / Render / Railway:  start command -> python sparta_bot.py
#
#  requirements.txt:
#    pyrogram==2.0.106
#    tgcrypto
#    motor
#    uvloop ; sys_platform != 'win32'
# ════════════════════════════════════════════════════════════════════════════
