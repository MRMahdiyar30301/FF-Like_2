import sqlite3
import time

DB = "bot.db"

def init():
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        bonus INTEGER DEFAULT 0,
        last_like REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        ref_by INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE
    )""")
    con.commit()
    for ch in ["@ZorenixStudio", "@ZorenixFF"]:
        c.execute("INSERT OR IGNORE INTO channels(username) VALUES(?)", (ch,))
    con.commit()
    con.close()

def get_user(uid):
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    con.close()
    if row:
        keys = ["user_id","username","bonus","last_like","referrals","ref_by","banned","is_admin"]
        return dict(zip(keys, row))
    return None

def add_user(uid, username, ref_by=0):
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT 1 FROM users WHERE user_id=?", (uid,))
    exists = c.fetchone()
    c.execute("INSERT OR IGNORE INTO users(user_id, username, ref_by) VALUES(?,?,?)",
              (uid, username, ref_by))
    if ref_by and not exists:
        c.execute("UPDATE users SET referrals=referrals+1, bonus=bonus+1 WHERE user_id=?", (ref_by,))
    con.commit()
    con.close()

def can_like(user):
    remaining = user["last_like"] + 24*3600 - time.time()
    if user["bonus"] > 0:
        return True, 0
    if remaining <= 0:
        return True, 0
    return False, int(remaining)

def consume_like(user):
    con = sqlite3.connect(DB)
    c = con.cursor()
    if user["bonus"] > 0:
        c.execute("UPDATE users SET bonus=bonus-1 WHERE user_id=?", (user["user_id"],))
    else:
        c.execute("UPDATE users SET last_like=? WHERE user_id=?", (time.time(), user["user_id"]))
    con.commit(); con.close()

def set_admin(uid, val):
    con = sqlite3.connect(DB); con.execute("UPDATE users SET is_admin=? WHERE user_id=?", (val, uid)); con.commit(); con.close()

def ban(uid, val):
    con = sqlite3.connect(DB); con.execute("UPDATE users SET banned=? WHERE user_id=?", (val, uid)); con.commit(); con.close()

def reset_cooldown(uid):
    con = sqlite3.connect(DB); con.execute("UPDATE users SET last_like=0 WHERE user_id=?", (uid,)); con.commit(); con.close()

def add_bonus(uid, n=1):
    con = sqlite3.connect(DB)
    con.execute("UPDATE users SET bonus=bonus+? WHERE user_id=?", (n, uid))
    con.commit(); con.close()

def all_uids():
    con = sqlite3.connect(DB)
    r = [x[0] for x in con.execute("SELECT user_id FROM users").fetchall()]
    con.close()
    return r

def stats():
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT COUNT(*) FROM users"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE last_like > ?", (time.time()-86400,)); today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE banned=1"); banned = c.fetchone()[0]
    con.close()
    return total, today, banned

# ---------- کانال‌های جوین اجباری ----------

def get_channels():
    con = sqlite3.connect(DB)
    r = [x[0] for x in con.execute("SELECT username FROM channels").fetchall()]
    con.close()
    return r

def add_channel(ch):
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("INSERT OR IGNORE INTO channels(username) VALUES(?)", (ch,))
    added = c.rowcount > 0
    con.commit(); con.close()
    return added

def del_channel(ch):
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("DELETE FROM channels WHERE username=?", (ch,))
    ok = c.rowcount > 0
    con.commit(); con.close()
    return ok