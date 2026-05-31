import os
import sys
import time
import datetime
import sqlite3
import ctypes
import psutil
from plyer import notification

# Constants
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screentime.db")
DEFAULT_IDLE_THRESHOLD = 60.0  # seconds

# Default category mappings for common Windows applications
DEFAULT_CATEGORIES = {
    "chrome.exe": ("Google Chrome", "Browsers"),
    "msedge.exe": ("Microsoft Edge", "Browsers"),
    "firefox.exe": ("Mozilla Firefox", "Browsers"),
    "brave.exe": ("Brave", "Browsers"),
    "code.exe": ("VS Code", "Developer Tools"),
    "devenv.exe": ("Visual Studio", "Developer Tools"),
    "idea64.exe": ("IntelliJ IDEA", "Developer Tools"),
    "pycharm64.exe": ("PyCharm", "Developer Tools"),
    "discord.exe": ("Discord", "Social & Communication"),
    "slack.exe": ("Slack", "Social & Communication"),
    "teams.exe": ("Microsoft Teams", "Social & Communication"),
    "whatsapp.exe": ("WhatsApp", "Social & Communication"),
    "tg.exe": ("Telegram", "Social & Communication"),
    "spotify.exe": ("Spotify", "Entertainment & Media"),
    "vlc.exe": ("VLC Player", "Entertainment & Media"),
    "netflix.exe": ("Netflix", "Entertainment & Media"),
    "excel.exe": ("Microsoft Excel", "Productivity & Office"),
    "winword.exe": ("Microsoft Word", "Productivity & Office"),
    "powerpnt.exe": ("Microsoft PowerPoint", "Productivity & Office"),
    "notepad.exe": ("Notepad", "Productivity & Office"),
    "explorer.exe": ("Windows Explorer", "System"),
    "cmd.exe": ("Command Prompt", "System"),
    "powershell.exe": ("PowerShell", "System"),
    "wt.exe": ("Windows Terminal", "System")
}

# --- Database Initialization ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. window_logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS window_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_name TEXT,
        window_title TEXT,
        start_time TEXT,
        end_time TEXT,
        duration INTEGER,
        category TEXT
    )
    """)
    
    # Migration: Add category column to window_logs if it doesn't exist
    try:
        cursor.execute("ALTER TABLE window_logs ADD COLUMN category TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    # 2. app_categories
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_categories (
        app_name TEXT PRIMARY KEY,
        display_name TEXT,
        category TEXT
    )
    """)
    
    # Populate default categories if they don't exist
    for app, (display_name, category) in DEFAULT_CATEGORIES.items():
        cursor.execute("""
        INSERT OR IGNORE INTO app_categories (app_name, display_name, category)
        VALUES (?, ?, ?)
        """, (app, display_name, category))
        
    # 3. daily_limits
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_limits (
        target TEXT PRIMARY KEY,
        limit_seconds INTEGER,
        notified INTEGER DEFAULT 0
    )
    """)
    
    # 4. settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # 5. title_classifications (AI Classification Cache)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS title_classifications (
        title TEXT PRIMARY KEY,
        category TEXT
    )
    """)
    
    # Default idle threshold
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('idle_threshold', ?)", (str(DEFAULT_IDLE_THRESHOLD),))
    
    # Database Migration: Update 'Education' category to '學習'
    try:
        cursor.execute("UPDATE app_categories SET category = '學習' WHERE category = 'Education'")
        cursor.execute("UPDATE window_logs SET category = '學習' WHERE category = 'Education'")
        cursor.execute("UPDATE daily_limits SET target = 'category:學習' WHERE target = 'category:Education'")
    except Exception as e:
        print(f"Database migration error: {e}", file=sys.stderr)
        
    conn.commit()
    conn.close()

# --- Settings Helper ---
def get_setting(key, default):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default

LAST_GEMINI_ERROR_TIME = 0.0

# --- Gemini AI Classification Helper ---
def classify_with_gemini(title, api_key):
    global LAST_GEMINI_ERROR_TIME
    import urllib.request
    import urllib.error
    import json
    import sys
    import time
    
    current_time = time.time()
    if current_time - LAST_GEMINI_ERROR_TIME < 60:
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = (
        "You are a professional video and webpage classifier. Classify the following title into exactly one of these categories:\n"
        "- '學習' (Educational channels, tutorials, study, coding, programming, learning languages, physics, calculus, lecture notes, science, design tutorials, art sketching/painting process)\n"
        "- 'Entertainment & Media' (Gaming streams, netflix, anime, music videos, pop songs, vlogs, entertainment, entertainment shows)\n"
        "- 'Productivity & Office' (Notion tutorials, excel/word office skills, time management, scheduling)\n"
        "- 'Others' (Generic search pages, blank pages, generic sites)\n\n"
        f"Title: \"{title}\"\n\n"
        "Return ONLY the exact category string from: '學習', 'Entertainment & Media', 'Productivity & Office', 'Others'. "
        "Do not include any explanation, punctuation, or extra spaces. Keep it as a simple string."
    )
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            candidate = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            candidate_clean = candidate.replace("'", "").replace('"', "").strip()
            
            valid_categories = ["學習", "Entertainment & Media", "Productivity & Office", "Others"]
            for cat in valid_categories:
                if cat.lower() in candidate_clean.lower():
                    return cat
                    
            if "學習" in candidate_clean or "learn" in candidate_clean.lower() or "edu" in candidate_clean.lower():
                return "學習"
            elif "entertainment" in candidate_clean.lower() or "media" in candidate_clean.lower() or "music" in candidate_clean.lower() or "game" in candidate_clean.lower():
                return "Entertainment & Media"
            elif "productivity" in candidate_clean.lower() or "office" in candidate_clean.lower():
                return "Productivity & Office"
                
            return None
    except urllib.error.HTTPError as e:
        LAST_GEMINI_ERROR_TIME = current_time
        err_msg = ""
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("error", {}).get("message", "")
        except Exception:
            pass
            
        if e.code == 404:
            print(f"[Gemini AI] 錯誤 404: 找不到此模型或金鑰不支援此模型。已自動冷卻 60 秒。({err_msg})", file=sys.stderr)
        elif e.code == 429:
            print(f"[Gemini AI] 錯誤 429: 額度已達上限/超出限制 (Quota Exceeded)。請至 Google AI Studio 申請免費金鑰，或檢查帳單設定。已自動冷卻 60 秒。({err_msg})", file=sys.stderr)
        elif e.code == 403:
            print(f"[Gemini AI] 錯誤 403: 權限不足或 API 金鑰無效。請確認金鑰正確性。已自動冷卻 60 秒。({err_msg})", file=sys.stderr)
        else:
            print(f"[Gemini AI] 錯誤 {e.code}: {e.reason}。已自動冷卻 60 秒。({err_msg})", file=sys.stderr)
        return None
    except Exception as e:
        LAST_GEMINI_ERROR_TIME = current_time
        print(f"[Gemini AI] 分類失敗: {e}。已自動冷卻 60 秒。", file=sys.stderr)
        return None


# --- Windows API Functions ---
def get_foreground_window():
    return ctypes.windll.user32.GetForegroundWindow()

def get_process_info(hwnd):
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return None, None
    try:
        proc = psutil.Process(pid.value)
        return proc.name(), proc.pid
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None, None

def get_window_title(hwnd):
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_system_idle_time():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("dwTime", ctypes.c_uint)
        ]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        tick_count = ctypes.windll.kernel32.GetTickCount()
        idle_ms = tick_count - lii.dwTime
        return idle_ms / 1000.0
    return 0.0

# --- App Helper to Auto-categorize Unknown Apps ---
def get_app_metadata(app_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, category FROM app_categories WHERE app_name = ?", (app_name,))
    row = cursor.fetchone()
    
    if not row:
        # Create a default display name and category
        display_name = app_name.replace(".exe", "").capitalize()
        category = "Others"
        cursor.execute("""
        INSERT INTO app_categories (app_name, display_name, category)
        VALUES (?, ?, ?)
        """, (app_name, display_name, category))
        conn.commit()
    else:
        display_name, category = row
        
    conn.close()
    return display_name, category

# --- Content Classification (學習/Education vs Entertainment) ---
def classify_content(app_name, window_title):
    title_lower = window_title.lower()
    app_lower = app_name.lower()
    
    # Match local development URLs, dashboard titles, or GitHub activities
    if "localhost" in title_lower or "127.0.0.1" in title_lower or "螢幕使用時間" in title_lower or "screentime" in title_lower or "github" in title_lower or "github" in app_lower:
        return "學習"
        
    # Specific known applications take absolute priority
    if app_lower in ["code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe", "antigravity ide.exe", "wsl.exe", "windows terminal.exe", "python.exe", "pythonw.exe"]:
        return "學習"
        
    if app_lower in ["spotify.exe", "vlc.exe", "netflix.exe", "steam.exe"]:
        return "Entertainment & Media"
        
    if app_lower in ["discord.exe", "slack.exe", "teams.exe", "whatsapp.exe", "tg.exe"]:
        return "Social & Communication"
        
    if app_lower in ["excel.exe", "winword.exe", "powerpnt.exe", "notepad.exe"]:
        return "Productivity & Office"
        
    # --- Special Fine-Grained Classification for Social Platforms ---
    # Detects if browsing Facebook, Instagram, or Pinterest
    is_social_platform = False
    matched_platform = None
    
    for platform in ["facebook", "instagram", "pinterest", "fb.com", "ig.com"]:
        if platform in title_lower or platform in app_lower:
            is_social_platform = True
            matched_platform = platform
            break
            
    # Also support boundary matched short-forms "fb" or "ig" in browser titles
    if not is_social_platform:
        import re
        if re.search(r'\b(fb|ig)\b', title_lower):
            is_social_platform = True
            matched_platform = "facebook" if "fb" in title_lower else "instagram"
            
    if is_social_platform:
        # Fine-grained educational, art/drawing, or artwork/creations keywords for social platforms
        social_edu_keywords = [
            "教學", "學習", "課程", "教育", "知識", "科普", "研究", "程式", "開發", "演算法", "技術",
            "畫畫", "繪畫", "插畫", "速寫", "素描", "水彩", "油畫", "電繪", "塗鴉", "手繪", "動漫教學", 
            "漫畫教學", "藝術", "設計", "筆記", "論文", "歷史", "科學", "物理", "化學", "生物", "英文", 
            "數學", "微積分", "寫生", "美工", "臨摹", "勾線", "上色", "配色", "透視", "人體結構", "厚塗",
            "作品", "創作", "畫作", "畫集", "作品集", "畫廊", "插圖", "原創", "同人", "二創", "草稿", 
            "線稿", "落書", "板繪", "繪師", "插畫家", "藝術家", "畫師", "設計師",
            "education", "tutorial", "lecture", "course", "learn", "study", "class", "classroom",
            "art", "paint", "drawing", "sketch", "illustration", "design", "watercolor", "acrylic",
            "oil painting", "digital art", "doodle", "procreate", "photoshop", "illustrator",
            "clip studio", "krita", "anatomy", "perspective", "shading", "speedpaint", "speed drawing",
            "portfolio", "artwork", "gallery", "fanart", "creation", "creative", "artist", "designer",
            "painting", "drawings", "paintings", "illustrations", "concept art", "character design",
            "charadesign", "cg"
        ]
        
        has_edu_content = False
        for kw in social_edu_keywords:
            if kw in title_lower:
                has_edu_content = True
                break
                
        if has_edu_content:
            return "學習"
        else:
            # Fallback to non-education categories
            if matched_platform in ["facebook", "fb.com"]:
                return "Social & Communication"
            elif matched_platform in ["instagram", "ig.com"]:
                return "Social & Communication"
            elif matched_platform in ["pinterest"]:
                return "Entertainment & Media"
            return "Social & Communication"

    # --- Special Fine-Grained Classification for Video Platforms (YouTube, Bilibili) ---
    is_video_platform = False
    if "youtube" in title_lower or "bilibili" in title_lower:
        is_video_platform = True
        
    if is_video_platform:
        # --- Gemini AI Title Classification with local SQLite Cache ---
        api_key = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] and row[0].strip():
                api_key = row[0].strip()
        except Exception:
            pass
            
        if api_key:
            # Clean title of browser suffixes for higher AI classification accuracy
            clean_title = window_title
            for suffix in [" - YouTube", " - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Brave"]:
                clean_title = clean_title.replace(suffix, "")
            clean_title = clean_title.strip()
            
            # Check SQLite Cache first
            cached_category = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT category FROM title_classifications WHERE title = ?", (clean_title,))
                row_cache = cursor.fetchone()
                conn.close()
                if row_cache:
                    cached_category = row_cache[0]
            except Exception:
                pass
                
            if cached_category:
                return cached_category
                
            # Query Gemini API
            ai_category = classify_with_gemini(clean_title, api_key)
            if ai_category:
                # Save to Cache
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR REPLACE INTO title_classifications (title, category) VALUES (?, ?)", (clean_title, ai_category))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                return ai_category

        # --- Rule-Based Fallback ---
        # 1. Check for Productivity & Office keywords (excel, word, notion, productivity hacks, etc.)
        video_productivity_keywords = [
            "excel", "word", "powerpoint", "ppt", "notion", "outlook", "office", "productivity", 
            "生產力", "工作效率", "時間管理", "工作法", "筆記術", "整理術", "試算表", "簡報", "排程"
        ]
        for kw in video_productivity_keywords:
            if kw in title_lower:
                return "Productivity & Office"
                
        # 2. Check for Education keywords (drawing, art, tutorials, science, calculus, languages, coding, etc.)
        video_education_keywords = [
            "教學", "學習", "課程", "教育", "知識", "科普", "研究", "程式", "開發", "演算法", "技術",
            "畫畫", "繪畫", "插畫", "速寫", "素描", "水彩", "油畫", "電繪", "塗鴉", "手繪", "動漫教學", 
            "漫畫教學", "藝術", "設計", "筆記", "論文", "歷史", "科學", "物理", "化學", "生物", "英文", 
            "數學", "微積分", "寫生", "美工", "臨摹", "勾線", "上色", "配色", "透視", "人體結構", "厚塗",
            "作品", "創作", "畫作", "畫集", "作品集", "畫廊", "插圖", "原創", "同人", "二創", "草稿", 
            "線稿", "落書", "板繪", "繪師", "插畫家", "藝術家", "畫師", "設計師",
            "education", "tutorial", "lecture", "course", "learn", "study", "class", "classroom",
            "art", "paint", "drawing", "sketch", "illustration", "design", "watercolor", "acrylic",
            "oil painting", "digital art", "doodle", "procreate", "photoshop", "illustrator",
            "clip studio", "krita", "anatomy", "perspective", "shading", "speedpaint", "speed drawing",
            "portfolio", "artwork", "how to draw", "how to paint", "programming", "coding",
            "calculator", "math", "english learning", "history", "science", "ted", "tedx",
            "crash course", "lecture", "class", "python", "javascript", "c++", "java", "html",
            "css", "rust", "sql", "github", "vscode", "git", "leetcode", "compiler"
        ]
        for kw in video_education_keywords:
            if kw in title_lower:
                return "學習"
                
        # 3. Default fallback for general video browsing is Entertainment & Media
        return "Entertainment & Media"

    # Education Keywords (教育) - Cleaned for exact matching in window titles
    education_keywords = [
        "education", "tutorial", "lecture", "course", "learn", "study", "class", 
        "wikipedia", "github", "stackoverflow", "medium", "notion", "classroom", 
        "duolingo", "coursera", "edx", "udemy", "khan academy", "docs", "document", 
        "w3schools", "leetcode", "mdn", "python", "javascript", "c++", "java", 
        "教學", "學習", "課程", "歷史", "科學", "知識", "百科", "圖書館", "線上課",
        "筆記", "研究", "論文", "研討會", "程式", "演算法", "機器學習", "開發", "programming", "教授",
        "english", "物理", "化學", "地質", "天文", "生物", "電機", "國文", "英文", "微積分",
        "清大", "交大", "成大", "中央", "中山", "中正", "中興", 
        "gemini", "lovable", "openai", "chatgpt", "claude",
        # Art/Drawing & Creations
        "畫畫", "繪畫", "插畫", "速寫", "素描", "水彩", "油畫", "電繪", "塗鴉", "手繪", "動漫教學", 
        "漫畫教學", "藝術", "設計", "寫生", "美工", "臨摹", "勾線", "上色", "配色", "透視", "人體結構", 
        "厚塗", "繪畫過程", "繪製", "畫作", "插圖", "原創", "草稿", "線稿", "落書", "板繪", 
        "繪師", "插畫家", "藝術家", "畫師", "設計師", "作品集",
        "art", "paint", "drawing", "sketch", "illustration", "design", "watercolor", "acrylic",
        "oil painting", "digital art", "doodle", "procreate", "photoshop", "illustrator",
        "clip studio", "krita", "anatomy", "perspective", "shading", "speedpaint", "speed drawing",
        "portfolio", "artwork"
    ]
    
    # Entertainment Keywords (娛樂)
    entertainment_keywords = [
        "netflix", "youtube", "twitch", "spotify", "disney", "anime", "manga", 
        "game", "play", "steam", "bilibili", "reddit", 
        "twitter", "baha", "gamer", "vlc", "music", "pop", "rock", "song", "video", 
        "娛樂", "影音", "遊戲", "動漫", "漫畫", "音樂", "電影", "追劇", "巴哈姆特",
        "直播", "實況", "社群", "臉書", "推特", "抖音", "tiktok"
    ]
    
    is_browser = app_lower in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]
    
    # Check keywords for browser tabs and any other general apps (like unknown PWAs or browsers)
    if is_browser or not app_lower or app_lower in ["explorer.exe", "applicationframehost.exe"]:
        # Check educational keywords first
        for kw in education_keywords:
            if kw in title_lower:
                return "學習"
        # Check entertainment keywords next
        for kw in entertainment_keywords:
            if kw in title_lower:
                return "Entertainment & Media"
        if is_browser:
            return "Browsers"
            
    # Fallback to general category in db
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT category FROM app_categories WHERE app_name = ?", (app_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
        
    return "Others"

# --- App Lockout & Bypasses System (iOS Style Blocker) ---
bypasses_ignore_today = set()
bypasses_one_more_minute = {}  # target -> expiration timestamp
active_lockouts = set()         # Prevent multiple overlapping lockout popups, tracking active popups

def is_target_locked(app_name, category, window_title):
    global active_lockouts
    if app_name in active_lockouts:
        return True
    if f"category:{category}" in active_lockouts:
        return True
    # Check all active site lockouts against window_title
    for locked in active_lockouts:
        if locked.startswith("site:"):
            site_kw = locked.replace("site:", "").lower()
            if site_kw in window_title.lower():
                return True
    return False

def get_todays_usage(target):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        usage_seconds = 0
        if target.startswith("category:"):
            cat_name = target.replace("category:", "")
            cursor.execute("""
            SELECT SUM(l.duration) 
            FROM window_logs l
            LEFT JOIN app_categories c ON l.app_name = c.app_name
            WHERE COALESCE(l.category, c.category) = ? AND date(l.start_time) = date('now', 'localtime')
            """, (cat_name,))
            row = cursor.fetchone()
            usage_seconds = row[0] if row and row[0] is not None else 0
        elif target.startswith("site:"):
            site_kw = target.replace("site:", "").lower()
            cursor.execute("""
            SELECT SUM(duration) 
            FROM window_logs 
            WHERE date(start_time) = date('now', 'localtime') AND LOWER(window_title) LIKE ?
            """, (f"%{site_kw}%",))
            row = cursor.fetchone()
            usage_seconds = row[0] if row and row[0] is not None else 0
        else:
            cursor.execute("""
            SELECT SUM(duration) 
            FROM window_logs 
            WHERE app_name = ? AND date(start_time) = date('now', 'localtime')
            """, (target,))
            row = cursor.fetchone()
            usage_seconds = row[0] if row and row[0] is not None else 0
        conn.close()
        return usage_seconds
    except Exception:
        return 0

def check_app_lockout(hwnd, app_name, window_title):
    global bypasses_ignore_today, bypasses_one_more_minute, active_lockouts
    
    if not app_name:
        return
        
    try:
        # Get dynamic category of active app and window
        category = classify_content(app_name, window_title)
        display_name, _ = get_app_metadata(app_name)
        
        # Check if this app/category is already undergoing a lockout popup
        if is_target_locked(app_name, category, window_title):
            # Just minimize again immediately to enforce lock
            ctypes.windll.user32.ShowWindow(hwnd, 6) # SW_MINIMIZE = 6
            return
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Find if there are limits set for this app, its category, or site keywords
        cursor.execute("""
        SELECT target, limit_seconds 
        FROM daily_limits 
        WHERE target = ? OR target = ? OR target LIKE 'site:%'
        """, (app_name, f"category:{category}"))
        
        limits = cursor.fetchall()
        conn.close()
        
        import subprocess
        
        for target, limit_seconds in limits:
            # Check if ignored today
            if target in bypasses_ignore_today:
                continue
                
            # Check if one more minute is active and not expired
            if target in bypasses_one_more_minute:
                if time.time() < bypasses_one_more_minute[target]:
                    continue
                    
            # For site-specific limits, only enforce if the current window title matches
            if target.startswith("site:"):
                site_kw = target.replace("site:", "").lower()
                if site_kw not in window_title.lower():
                    continue
                    
            # Check usage today
            usage_seconds = get_todays_usage(target)
            
            if usage_seconds >= limit_seconds:
                # Limit Exceeded!
                # 1. Minimize the window immediately
                ctypes.windll.user32.ShowWindow(hwnd, 6) # SW_MINIMIZE = 6
                
                # 2. Spawn lockout popup asynchronously in a separate thread
                target_display = display_name if not target.startswith("category:") else category
                if target.startswith("site:"):
                    target_display = f"網站 {target.replace('site:', '')}"
                
                def run_lockout_async(t_val, t_disp, app_n):
                    global active_lockouts, bypasses_one_more_minute, bypasses_ignore_today
                    active_lockouts.add(t_val)
                    print(f"Lockout popup spawned for {t_val}")
                    
                    lockout_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lockout.py")
                    try:
                        res = subprocess.run([
                            sys.executable, lockout_script, app_n, t_disp
                        ], capture_output=True, text=True)
                        
                        code = res.returncode
                        if code == 1:
                            # "One More Minute": bypass for 60 seconds
                            bypasses_one_more_minute[t_val] = time.time() + 60.0
                            print(f"Bypassed {t_val} for 1 minute.")
                        elif code == 2:
                            # "Ignore for Today"
                            bypasses_ignore_today.add(t_val)
                            print(f"Bypassed {t_val} for today.")
                        else:
                            # OK / Cancel: just minimize it again
                            print(f"Lockout confirmed for {t_val}.")
                    except Exception as le:
                        print(f"Error running lockout popup: {le}", file=sys.stderr)
                    finally:
                        active_lockouts.discard(t_val)
                        print(f"Lockout popup closed for {t_val}")
                
                import threading
                threading.Thread(target=run_lockout_async, args=(target, target_display, app_name), daemon=True).start()
                
                break
                
    except Exception as ex:
        print(f"Error in check_app_lockout: {ex}", file=sys.stderr)

# --- Notification System ---
def check_limits_and_notify():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Reset notified status if it is a new day
        today_str = datetime.date.today().isoformat()
        
        cursor.execute("SELECT key, value FROM settings WHERE key = 'last_reset_date'")
        row = cursor.fetchone()
        if not row or row[1] != today_str:
            cursor.execute("UPDATE daily_limits SET notified = 0")
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_reset_date', ?)", (today_str,))
            conn.commit()
            
        # Select all limits
        cursor.execute("SELECT target, limit_seconds, notified FROM daily_limits WHERE notified = 0")
        active_limits = cursor.fetchall()
        
        for target, limit_seconds, notified in active_limits:
            usage_seconds = 0
            display_name = target
            
            if target.startswith("category:"):
                cat_name = target.replace("category:", "")
                display_name = cat_name
                cursor.execute("""
                SELECT SUM(l.duration) 
                FROM window_logs l
                LEFT JOIN app_categories c ON l.app_name = c.app_name
                WHERE COALESCE(l.category, c.category) = ? AND date(l.start_time) = date('now', 'localtime')
                """, (cat_name,))
                row = cursor.fetchone()
                usage_seconds = row[0] if row and row[0] is not None else 0
            elif target.startswith("site:"):
                site_kw = target.replace("site:", "")
                display_name = f"網站 {site_kw}"
                cursor.execute("""
                SELECT SUM(duration) 
                FROM window_logs 
                WHERE date(start_time) = date('now', 'localtime') AND LOWER(window_title) LIKE ?
                """, (f"%{site_kw.lower()}%",))
                row = cursor.fetchone()
                usage_seconds = row[0] if row and row[0] is not None else 0
            else:
                cursor.execute("""
                SELECT SUM(duration) 
                FROM window_logs 
                WHERE app_name = ? AND date(start_time) = date('now', 'localtime')
                """, (target,))
                row = cursor.fetchone()
                usage_seconds = row[0] if row and row[0] is not None else 0
                
                # Get neat display name
                cursor.execute("SELECT display_name FROM app_categories WHERE app_name = ?", (target,))
                d_row = cursor.fetchone()
                if d_row:
                    display_name = d_row[0]
                    
            if usage_seconds >= limit_seconds:
                # Trigger notification
                limit_mins = limit_seconds // 60
                limit_hours = limit_mins // 60
                limit_mins_rem = limit_mins % 60
                limit_str = f"{limit_hours}小時" if limit_hours > 0 else ""
                limit_str += f"{limit_mins_rem}分鐘" if limit_mins_rem > 0 or not limit_str else ""
                
                try:
                    notification.notify(
                        title="螢幕使用時間限制已達",
                        message=f"您今天使用「{display_name}」的時間已達到上限 {limit_str}！",
                        app_name="Screen Time PC",
                        timeout=10
                    )
                except Exception as ne:
                    print(f"Error showing notification: {ne}", file=sys.stderr)
                    
                # Mark as notified
                cursor.execute("UPDATE daily_limits SET notified = 1 WHERE target = ?", (target,))
                conn.commit()
                
        conn.close()
    except Exception as e:
        print(f"Error checking limits: {e}", file=sys.stderr)

# --- Audio Playback Detection Helpers ---
def ensure_audiocheck_exe():
    import os
    import subprocess
    import sys
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(project_dir, "audiocheck.exe")
    cs_path = os.path.join(project_dir, "audiocheck.cs")
    
    if os.path.exists(exe_path):
        return True
        
    cs_code = """using System;
using System.Runtime.InteropServices;

namespace AudioDetection {
    class Program {
        static void Main(string[] args) {
            try {
                var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
                IMMDevice speakers = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia);
                IAudioMeterInformation meter = (IAudioMeterInformation)speakers.Activate(typeof(IAudioMeterInformation).GUID, 0, IntPtr.Zero);
                float peak = meter.GetPeakValue();
                if (peak > 1E-08) {
                    Console.WriteLine("True");
                } else {
                    Console.WriteLine("False");
                }
            } catch {
                Console.WriteLine("False");
            }
        }

        [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] private class MMDeviceEnumerator { }
        private enum EDataFlow { eRender, eCapture, eAll }
        private enum ERole { eConsole, eMultimedia, eCommunications }

        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
        private interface IMMDeviceEnumerator {
            void NotNeeded();
            IMMDevice GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role);
        }

        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("D666063F-1587-4E43-81F1-B948E807363F")]
        private interface IMMDevice {
            [return: MarshalAs(UnmanagedType.IUnknown)]
            object Activate([MarshalAs(UnmanagedType.LPStruct)] Guid iid, int dwClsCtx, IntPtr pActivationParams);
        }

        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064")]
        private interface IAudioMeterInformation {
            float GetPeakValue();
        }
    }
}
"""
    try:
        with open(cs_path, "w", encoding="utf-8") as f:
            f.write(cs_code)
            
        compilers = [
            r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
            r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
        ]
        
        compiled = False
        for csc in compilers:
            if os.path.exists(csc):
                startupinfo = None
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                res = subprocess.run([csc, "/nologo", f"/out:{exe_path}", cs_path], capture_output=True, text=True, startupinfo=startupinfo)
                if res.returncode == 0:
                    compiled = True
                    break
                    
        if os.path.exists(cs_path):
            os.remove(cs_path)
            
        return compiled
    except Exception:
        return False

def check_audio_playing():
    import os
    import subprocess
    import sys
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(project_dir, "audiocheck.exe")
    if not os.path.exists(exe_path):
        return False
        
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        res = subprocess.run(
            [exe_path],
            capture_output=True,
            text=True,
            timeout=2,
            startupinfo=startupinfo
        )
        return "True" in res.stdout
    except Exception:
        return False


# --- Active Window Tracking Engine ---
def run_tracker(stop_event=None):
    print("Screen Time Tracking Engine started...")
    init_db()
    ensure_audiocheck_exe()
    
    current_session_id = None
    last_app = None
    last_title = None
    last_time = time.time()
    
    # Keep track of when we last checked notifications
    last_limit_check = 0.0
    
    while stop_event is None or not stop_event.is_set():
        try:
            # 1. Fetch current settings (e.g. idle threshold)
            idle_threshold = float(get_setting("idle_threshold", DEFAULT_IDLE_THRESHOLD))
            
            # 2. Get active window information first
            hwnd = get_foreground_window()
            app_name = None
            window_title = ""
            
            if hwnd != 0:
                app_name, pid = get_process_info(hwnd)
                if app_name:
                    window_title = get_window_title(hwnd) or ""
            
            # 3. Check system idle state
            idle_time = get_system_idle_time()
            
            # 4. Determine if active window is a video/media playback window
            is_video = False
            if app_name:
                app_lower = app_name.lower()
                title_lower = window_title.lower()
                
                # Known media player apps
                video_apps = [
                    "vlc.exe", "potplayer.exe", "netflix.exe", "kmplayer.exe", 
                    "mpc-hc.exe", "powerdvd.exe", "gomp.exe"
                ]
                
                # Browser video platform titles
                video_title_keywords = [
                    " - youtube", "youtube", "哔哩哔哩", "bilibili", 
                    "netflix", "disney+", "巴哈姆特動畫瘋", "動畫瘋", 
                    "twitch", "vimeo", "iqiyi", "愛奇藝"
                ]
                
                if app_lower in video_apps:
                    is_video = True
                elif app_lower in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
                    for kw in video_title_keywords:
                        if kw in title_lower:
                            is_video = True
                            break
            
            # 5. Calculate idle state with dynamic threshold (check audio output when physically idle)
            if is_video:
                if idle_time >= idle_threshold:
                    if check_audio_playing():
                        is_idle = False  # Bypassed because video is actively outputting sound!
                    else:
                        is_idle = True   # Video is paused, user is idle!
                else:
                    is_idle = False      # Physical user is active
            else:
                is_idle = idle_time >= idle_threshold
                
            # 6. Skip tracking if active window is our own widget or lockout window
            if hwnd != 0 and not is_idle and app_name:
                title_lower_temp = window_title.lower()
                if "screen time widget" in title_lower_temp or "lockout.py" in title_lower_temp:
                    time.sleep(1.0)
                    continue
                # Check and enforce app limit lockouts
                check_app_lockout(hwnd, app_name, window_title)
                    
            # 4. Handle State Transitions
            now = time.time()
            now_iso = datetime.datetime.now().isoformat()
            
            # If the user is idle or lock screen or no window is active
            if not app_name or is_idle:
                if current_session_id is not None:
                    # Close current session
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("SELECT start_time FROM window_logs WHERE id = ?", (current_session_id,))
                    row = cursor.fetchone()
                    if row:
                        start_t = datetime.datetime.fromisoformat(row[0])
                        duration = int((datetime.datetime.now() - start_t).total_seconds())
                        cursor.execute("""
                        UPDATE window_logs 
                        SET end_time = ?, duration = ? 
                        WHERE id = ?
                        """, (now_iso, max(0, duration), current_session_id))
                        conn.commit()
                    conn.close()
                    
                    print(f"Session ended (User Idle/Away). Last App: {last_app}")
                    current_session_id = None
                    last_app = None
                    last_title = None
                    
            # If a window is active and user is active
            else:
                # Ensure the app metadata exists in DB
                get_app_metadata(app_name)
                
                # Check if it is a window switch or new session
                if current_session_id is None or app_name != last_app or window_title != last_title:
                    # Close the previous session if any
                    if current_session_id is not None:
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute("SELECT start_time FROM window_logs WHERE id = ?", (current_session_id,))
                        row = cursor.fetchone()
                        if row:
                            start_t = datetime.datetime.fromisoformat(row[0])
                            duration = int((datetime.datetime.now() - start_t).total_seconds())
                            cursor.execute("""
                            UPDATE window_logs 
                            SET end_time = ?, duration = ? 
                            WHERE id = ?
                            """, (now_iso, max(0, duration), current_session_id))
                            conn.commit()
                        conn.close()
                        
                    # Create new session with dynamic category
                    category = classify_content(app_name, window_title)
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("""
                    INSERT INTO window_logs (app_name, window_title, start_time, end_time, duration, category)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (app_name, window_title, now_iso, now_iso, 0, category))
                    current_session_id = cursor.lastrowid
                    conn.commit()
                    conn.close()
                    
                    print(f"New Session started: {app_name} - {window_title[:40]}")
                    last_app = app_name
                    last_title = window_title
                    
                # If same app/window continues, update the end time and duration continuously
                else:
                    # Update database every 5 seconds to reduce write frequency while maintaining high-fidelity stats
                    if now - last_time >= 5.0:
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute("SELECT start_time FROM window_logs WHERE id = ?", (current_session_id,))
                        row = cursor.fetchone()
                        if row:
                            start_t = datetime.datetime.fromisoformat(row[0])
                            duration = int((datetime.datetime.now() - start_t).total_seconds())
                            # Re-classify in case window title/tab changed
                            category = classify_content(app_name, window_title)
                            cursor.execute("""
                            UPDATE window_logs 
                            SET end_time = ?, duration = ?, category = ? 
                            WHERE id = ?
                            """, (now_iso, max(0, duration), category, current_session_id))
                            conn.commit()
                        conn.close()
                        last_time = now
                        
            # 5. Periodically check limits (every 5 seconds)
            if now - last_limit_check >= 5.0:
                check_limits_and_notify()
                last_limit_check = now
                
        except Exception as ex:
            print(f"Error in tracking loop: {ex}", file=sys.stderr)
            
        time.sleep(1.0)

if __name__ == "__main__":
    init_db()
    try:
        run_tracker()
    except KeyboardInterrupt:
        print("Screen Time Tracking Engine stopped manually.")
        sys.exit(0)
