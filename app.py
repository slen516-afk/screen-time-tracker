import os
import sys
import time
import sqlite3
import datetime
import threading
import subprocess
import webbrowser
from flask import Flask, jsonify, request, render_template

# Make sure tracker is importable
from tracker import run_tracker, DB_PATH, init_db

app = Flask(__name__, template_folder="templates", static_folder="static")

# Globals to manage background tasks
tracker_thread = None
stop_event = threading.Event()
widget_process = None

# --- Helpers ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def is_widget_active():
    global widget_process
    if widget_process is None:
        return False
    if widget_process.poll() is None:
        return True
    widget_process = None
    return False

# --- UI Routing ---
@app.route("/")
def index():
    return render_template("index.html")

# --- API Routing ---

# 1. Summary Stats
@app.route("/api/stats/summary", methods=["GET"])
def get_summary():
    try:
        range_val = request.args.get("range", "today")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date conditions based on selected range
        if range_val == "yesterday":
            date_cond = "date(start_time) = date('now', '-1 day', 'localtime')"
            prev_date_cond = "date(start_time) = date('now', '-2 days', 'localtime')"
        elif range_val == "7days":
            date_cond = "date(start_time) >= date('now', '-6 days', 'localtime')"
            prev_date_cond = "date(start_time) >= date('now', '-13 days', 'localtime') AND date(start_time) < date('now', '-6 days', 'localtime')"
        elif range_val == "30days":
            date_cond = "date(start_time) >= date('now', '-29 days', 'localtime')"
            prev_date_cond = "date(start_time) >= date('now', '-59 days', 'localtime') AND date(start_time) < date('now', '-29 days', 'localtime')"
        else: # today
            date_cond = "date(start_time) = date('now', 'localtime')"
            prev_date_cond = "date(start_time) = date('now', '-1 day', 'localtime')"

        # Current total duration in selected range
        cursor.execute(f"SELECT SUM(duration) FROM window_logs WHERE {date_cond}")
        row_today = cursor.fetchone()
        total_today = row_today[0] if row_today and row_today[0] is not None else 0
        
        # Previous total duration for trend comparison
        cursor.execute(f"SELECT SUM(duration) FROM window_logs WHERE {prev_date_cond}")
        row_yesterday = cursor.fetchone()
        total_yesterday = row_yesterday[0] if row_yesterday and row_yesterday[0] is not None else 0
        
        # Percentage Change
        pct_change = 0.0
        if total_yesterday > 0:
            pct_change = round(((total_today - total_yesterday) / total_yesterday) * 100, 1)
        elif total_today > 0:
            pct_change = 100.0
            
        # Category Breakdown for selected range
        cursor.execute(f"""
        SELECT COALESCE(l.category, c.category) as category, SUM(l.duration) as cat_duration
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE {date_cond}
        GROUP BY COALESCE(l.category, c.category)
        ORDER BY cat_duration DESC
        """)
        rows_categories = cursor.fetchall()
        category_data = {row["category"]: row["cat_duration"] for row in rows_categories}
        
        # Default empty categories to 0 if not tracked
        all_categories = ["Browsers", "Developer Tools", "Social & Communication", 
                          "Entertainment & Media", "Productivity & Office", "System", "學習", "Others"]
        for cat in all_categories:
            if cat not in category_data:
                category_data[cat] = 0
                
        conn.close()
        
        return jsonify({
            "success": True,
            "total_today": total_today,
            "total_yesterday": total_yesterday,
            "percentage_change": pct_change,
            "categories": category_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 2. Chart Stats (Hourly breakdown for today/yesterday, Daily for 7/30 days)
@app.route("/api/stats/chart", methods=["GET"])
def get_chart_data():
    try:
        range_val = request.args.get("range", "today")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if range_val in ["today", "yesterday"]:
            # Hourly breakdown
            hourly_data = [0] * 24
            labels = [f"{i}點" for i in range(24)]
            
            if range_val == "yesterday":
                date_cond = "date(start_time) = date('now', '-1 day', 'localtime')"
            else:
                date_cond = "date(start_time) = date('now', 'localtime')"
                
            cursor.execute(f"""
            SELECT strftime('%H', start_time) as hr, SUM(duration) as hr_duration
            FROM window_logs
            WHERE {date_cond}
            GROUP BY hr
            """)
            
            rows = cursor.fetchall()
            for row in rows:
                hour_idx = int(row["hr"])
                if 0 <= hour_idx < 24:
                    hourly_data[hour_idx] = row["hr_duration"]
            data_val = hourly_data
            
        else:
            # Daily breakdown (7 days or 30 days)
            days_count = 7 if range_val == "7days" else 30
            
            # Generate the list of dates for the last N days (ascending order)
            dates_list = []
            labels = []
            for i in reversed(range(days_count)):
                cursor.execute(f"SELECT date('now', '-{i} day', 'localtime')")
                dt = cursor.fetchone()[0]
                dates_list.append(dt)
                # Formatted label: e.g. "5/30"
                parts = dt.split("-")
                labels.append(f"{int(parts[1])}/{int(parts[2])}")
                
            daily_data = [0] * days_count
            date_cond = f"date(start_time) >= date('now', '-{days_count - 1} days', 'localtime')"
            
            cursor.execute(f"""
            SELECT date(start_time) as dt, SUM(duration) as day_duration
            FROM window_logs
            WHERE {date_cond}
            GROUP BY dt
            """)
            
            rows = cursor.fetchall()
            date_to_duration = {row["dt"]: row["day_duration"] for row in rows}
            
            for idx, dt in enumerate(dates_list):
                daily_data[idx] = date_to_duration.get(dt, 0)
                
            data_val = daily_data
            
        conn.close()
        return jsonify({
            "success": True,
            "chart_data": data_val,
            "labels": labels
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 3. Application List
@app.route("/api/stats/apps", methods=["GET"])
def get_apps_data():
    try:
        range_val = request.args.get("range", "today")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date conditions based on selected range
        if range_val == "yesterday":
            date_cond = "date(l.start_time) = date('now', '-1 day', 'localtime')"
            sub_date_cond = "date(start_time) = date('now', '-1 day', 'localtime')"
        elif range_val == "7days":
            date_cond = "date(l.start_time) >= date('now', '-6 days', 'localtime')"
            sub_date_cond = "date(start_time) >= date('now', '-6 days', 'localtime')"
        elif range_val == "30days":
            date_cond = "date(l.start_time) >= date('now', '-29 days', 'localtime')"
            sub_date_cond = "date(start_time) >= date('now', '-29 days', 'localtime')"
        else: # today
            date_cond = "date(l.start_time) = date('now', 'localtime')"
            sub_date_cond = "date(start_time) = date('now', 'localtime')"
        
        # Get overall applications and their duration in this range
        cursor.execute(f"""
        SELECT l.app_name, c.display_name, c.category, SUM(l.duration) as app_duration
        FROM window_logs l
        JOIN app_categories c ON l.app_name = c.app_name
        WHERE {date_cond}
        GROUP BY l.app_name
        ORDER BY app_duration DESC
        """)
        
        app_rows = cursor.fetchall()
        apps_list = []
        
        for row in app_rows:
            app_name = row["app_name"]
            
            # Fetch limit details
            cursor.execute("SELECT limit_seconds FROM daily_limits WHERE target = ?", (app_name,))
            lim_row = cursor.fetchone()
            limit = lim_row["limit_seconds"] if lim_row else None
            
            # Fetch category limit if specific limit not set
            if limit is None:
                cursor.execute("SELECT limit_seconds FROM daily_limits WHERE target = ?", (f"category:{row['category']}",))
                cat_lim_row = cursor.fetchone()
                limit = cat_lim_row["limit_seconds"] if cat_lim_row else None
                
            # Fetch top window titles/subtasks for this app in this range
            cursor.execute(f"""
            SELECT window_title, SUM(duration) as win_duration
            FROM window_logs
            WHERE app_name = ? AND {sub_date_cond} AND window_title != ''
            GROUP BY window_title
            ORDER BY win_duration DESC
            LIMIT 8
            """, (app_name,))
            win_rows = cursor.fetchall()
            window_details = [{"title": w["window_title"], "duration": w["win_duration"]} for w in win_rows]
            
            apps_list.append({
                "app_name": app_name,
                "display_name": row["display_name"],
                "category": row["category"],
                "duration": row["app_duration"],
                "limit": limit,
                "sub_details": window_details
            })
            
        conn.close()
        
        return jsonify({
            "success": True,
            "apps": apps_list
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 4. Chronological Timeline
@app.route("/api/stats/timeline", methods=["GET"])
def get_timeline():
    try:
        range_val = request.args.get("range", "today")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date conditions based on selected range
        if range_val == "yesterday":
            date_cond = "date(l.start_time) = date('now', '-1 day', 'localtime')"
        elif range_val == "7days":
            date_cond = "date(l.start_time) >= date('now', '-6 days', 'localtime')"
        elif range_val == "30days":
            date_cond = "date(l.start_time) >= date('now', '-29 days', 'localtime')"
        else: # today
            date_cond = "date(l.start_time) = date('now', 'localtime')"
        
        # Get last 50 events today where duration was significant (>= 3 seconds)
        cursor.execute(f"""
        SELECT l.app_name, c.display_name, COALESCE(l.category, c.category) as category, l.window_title, l.start_time, l.end_time, l.duration
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE {date_cond} AND l.duration >= 3
        ORDER BY l.start_time DESC
        LIMIT 50
        """)
        
        rows = cursor.fetchall()
        timeline_list = [{
            "app_name": row["app_name"],
            "display_name": row["display_name"],
            "category": row["category"],
            "window_title": row["window_title"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "duration": row["duration"]
        } for row in rows]
        
        conn.close()
        
        return jsonify({
            "success": True,
            "timeline": timeline_list
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 5. Get/Set/Delete Application Limits
@app.route("/api/limits", methods=["GET", "POST", "DELETE"])
def handle_limits():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == "GET":
            cursor.execute("SELECT target, limit_seconds FROM daily_limits")
            rows = cursor.fetchall()
            limits_data = []
            
            for row in rows:
                target = row["target"]
                limit_seconds = row["limit_seconds"]
                usage_seconds = 0
                
                if target.startswith("category:"):
                    cat_name = target.replace("category:", "")
                    cursor.execute("""
                    SELECT SUM(l.duration) 
                    FROM window_logs l
                    LEFT JOIN app_categories c ON l.app_name = c.app_name
                    WHERE COALESCE(l.category, c.category) = ? AND date(l.start_time) = date('now', 'localtime')
                    """, (cat_name,))
                    u_row = cursor.fetchone()
                    usage_seconds = u_row[0] if u_row and u_row[0] is not None else 0
                    
                elif target.startswith("site:"):
                    site_kw = target.replace("site:", "").lower()
                    cursor.execute("""
                    SELECT SUM(duration) 
                    FROM window_logs 
                    WHERE date(start_time) = date('now', 'localtime') AND LOWER(window_title) LIKE ?
                    """, (f"%{site_kw}%",))
                    u_row = cursor.fetchone()
                    usage_seconds = u_row[0] if u_row and u_row[0] is not None else 0
                    
                else:
                    cursor.execute("""
                    SELECT SUM(duration) 
                    FROM window_logs 
                    WHERE app_name = ? AND date(start_time) = date('now', 'localtime')
                    """, (target,))
                    u_row = cursor.fetchone()
                    usage_seconds = u_row[0] if u_row and u_row[0] is not None else 0
                    
                limits_data.append({
                    "target": target,
                    "limit_seconds": limit_seconds,
                    "usage_seconds": usage_seconds
                })
                
            conn.close()
            return jsonify({"success": True, "limits": limits_data})
            
        elif request.method == "POST":
            data = request.get_json()
            target = data.get("target")
            limit_seconds = int(data.get("limit_seconds", 0))
            
            if not target or limit_seconds <= 0:
                return jsonify({"success": False, "error": "Invalid target or limit time"}), 400
                
            cursor.execute("""
            INSERT OR REPLACE INTO daily_limits (target, limit_seconds, notified)
            VALUES (?, ?, 0)
            """, (target, limit_seconds))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Limit set successfully"})
            
        elif request.method == "DELETE":
            data = request.get_json()
            target = data.get("target")
            
            if not target:
                return jsonify({"success": False, "error": "Invalid target"}), 400
                
            cursor.execute("DELETE FROM daily_limits WHERE target = ?", (target,))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Limit deleted successfully"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 6. Customize Application Display Names and Categories
@app.route("/api/apps/configure", methods=["POST"])
def configure_app():
    try:
        data = request.get_json()
        app_name = data.get("app_name")
        display_name = data.get("display_name")
        category = data.get("category")
        
        if not app_name or not display_name or not category:
            return jsonify({"success": False, "error": "Missing parameters"}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO app_categories (app_name, display_name, category)
        VALUES (?, ?, ?)
        """, (app_name, display_name, category))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "App configuration saved"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 7. Get/Set Active Idle Threshold and Gemini API Key
@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == "GET":
            cursor.execute("SELECT value FROM settings WHERE key = 'idle_threshold'")
            row = cursor.fetchone()
            idle_threshold = float(row[0]) if row else 60.0
            
            # Query Gemini API key if present
            cursor.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'")
            row_key = cursor.fetchone()
            gemini_api_key = row_key[0] if row_key else ""
            
            # Query auto-start widget setting
            cursor.execute("SELECT value FROM settings WHERE key = 'auto_start_widget'")
            row_widget = cursor.fetchone()
            auto_start_widget = (row_widget[0] == "true") if row_widget else False
            
            # Also return list of all unique categories in system
            cursor.execute("SELECT DISTINCT category FROM app_categories")
            cats = [r["category"] for r in cursor.fetchall()]
            
            conn.close()
            return jsonify({
                "success": True, 
                "idle_threshold": idle_threshold,
                "gemini_api_key": gemini_api_key,
                "auto_start_widget": auto_start_widget,
                "available_categories": cats
            })
            
        elif request.method == "POST":
            data = request.get_json()
            idle_threshold = data.get("idle_threshold")
            gemini_api_key = data.get("gemini_api_key")
            auto_start_widget = data.get("auto_start_widget")
            
            if idle_threshold is not None:
                if float(idle_threshold) <= 0:
                    return jsonify({"success": False, "error": "Invalid idle threshold"}), 400
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('idle_threshold', ?)", (str(idle_threshold),))
                
            if gemini_api_key is not None:
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gemini_api_key', ?)", (str(gemini_api_key),))
                
            if auto_start_widget is not None:
                val = "true" if auto_start_widget else "false"
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_start_widget', ?)", (val,))
                
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Settings updated"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 7.5 Silent Startup Toggle Manager (Registry Run Key + project VBS launch)
@app.route("/api/settings/startup", methods=["GET", "POST"])
def handle_startup_toggle():
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    project_dir = os.path.dirname(os.path.abspath(__file__))
    vbs_path = os.path.join(project_dir, "screentime_startup.vbs")
    
    # Old Startup folder path for cleanup
    old_startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    old_vbs_path = os.path.join(old_startup_dir, "screentime_startup.vbs")
    
    try:
        if request.method == "GET":
            is_enabled = False
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                winreg.QueryValueEx(key, "ScreenTimePC")
                winreg.CloseKey(key)
                is_enabled = os.path.exists(vbs_path)
            except FileNotFoundError:
                pass
            return jsonify({"success": True, "enabled": is_enabled})
            
        elif request.method == "POST":
            data = request.get_json() or {}
            enable = data.get("enable", False)
            
            # Clean up old Startup folder script to avoid double-boot conflicts
            if os.path.exists(old_vbs_path):
                try:
                    os.remove(old_vbs_path)
                except Exception:
                    pass
            
            if enable:
                run_bat_path = os.path.join(project_dir, "run.bat")
                vbs_content = (
                    'Set WshShell = CreateObject("WScript.Shell")\n'
                    f'WshShell.Run Chr(34) & "{run_bat_path}" & Chr(34), 0\n'
                    'Set WshShell = Nothing\n'
                )
                with open(vbs_path, "w", encoding="utf-8") as f:
                    f.write(vbs_content)
                
                # Register in HKEY_CURRENT_USER Run Key
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                value = f'wscript.exe "{vbs_path}"'
                winreg.SetValueEx(key, "ScreenTimePC", 0, winreg.REG_SZ, value)
                winreg.CloseKey(key)
                return jsonify({"success": True, "enabled": True, "message": "已啟用開機自動背景啟動 (登錄檔方式)"})
            else:
                # Remove from Registry
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                    winreg.DeleteValue(key, "ScreenTimePC")
                    winreg.CloseKey(key)
                except FileNotFoundError:
                    pass
                
                # Delete VBS file from project folder
                if os.path.exists(vbs_path):
                    os.remove(vbs_path)
                return jsonify({"success": True, "enabled": False, "message": "已關閉開機自動背景啟動"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 8. Manage Floating Desktop Widget Process
@app.route("/api/widget/status", methods=["GET"])
def get_widget_status():
    return jsonify({
        "success": True,
        "is_active": is_widget_active()
    })

@app.route("/api/widget/toggle", methods=["POST"])
def toggle_widget():
    global widget_process
    try:
        if is_widget_active():
            # Kill process
            widget_process.terminate()
            widget_process.wait()
            widget_process = None
            active = False
            msg = "Desktop widget closed"
        else:
            # Start process using same Python executable
            widget_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.py")
            # Start it detatched / in background so Flask doesn't block
            if sys.platform == "win32":
                # DETACHED_PROCESS = 0x00000008, prevents showing command window
                widget_process = subprocess.Popen(
                    [sys.executable, widget_script],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                widget_process = subprocess.Popen([sys.executable, widget_script])
            active = True
            msg = "Desktop widget launched"
            
        return jsonify({
            "success": True,
            "is_active": active,
            "message": msg
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 9. Get Gamified Digital Avatar Stats (30-day feedback system)
@app.route("/api/character", methods=["GET"])
def get_character_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query total duration for 學習 in past 30 days
        cursor.execute("""
        SELECT SUM(l.duration) 
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE COALESCE(l.category, c.category) = '學習' 
          AND date(l.start_time) >= date('now', '-30 days', 'localtime')
        """)
        row_edu = cursor.fetchone()
        edu_seconds = row_edu[0] if row_edu and row_edu[0] is not None else 0
        edu_hours = edu_seconds / 3600.0
        
        # Query total duration for Entertainment & Media in past 30 days
        cursor.execute("""
        SELECT SUM(l.duration) 
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE COALESCE(l.category, c.category) = 'Entertainment & Media' 
          AND date(l.start_time) >= date('now', '-30 days', 'localtime')
        """)
        row_ent = cursor.fetchone()
        ent_seconds = row_ent[0] if row_ent and row_ent[0] is not None else 0
        ent_hours = ent_seconds / 3600.0
        
        conn.close()
        
        # Evolution Logic based on Education hours
        # Levels: 1 to 5
        level = 1
        stage_title = "初階使用者"
        description = "已建立螢幕時間管理基礎，建議透過增加教育學習與開發時間來提升分身狀態。"
        next_threshold = 5.0
        prev_threshold = 0.0
        
        if edu_hours >= 100.0:
            level = 5
            stage_title = "卓越時間管理大師"
            description = "時間管理的典範，高度平衡學習與效率，將自律轉化為日常習慣，達成極佳的數位生產力目標。"
            next_threshold = 100.0
            prev_threshold = 100.0
        elif edu_hours >= 50.0:
            level = 4
            stage_title = "深度專注專家"
            description = "展現高強度的自律性，能長時間維持高度集中的專注狀態，系統性地累積深度的知識技能。"
            next_threshold = 100.0
            prev_threshold = 50.0
        elif edu_hours >= 20.0:
            level = 3
            stage_title = "效率實踐者"
            description = "擁有良好的專注度與時間分配能力，在學習、程式開發或辦公生產力上展現出優異的執行力。"
            next_threshold = 50.0
            prev_threshold = 20.0
        elif edu_hours >= 5.0:
            level = 2
            stage_title = "自主學習者"
            description = "已具備基本的學習規律與自我要求，能持續穩定地累積教育與技術開發時間。"
            next_threshold = 20.0
            prev_threshold = 5.0
            
        # EXP percent to next level
        if level == 5:
            exp_percent = 100
        else:
            range_h = next_threshold - prev_threshold
            progress_h = edu_hours - prev_threshold
            exp_percent = min(100, max(0, int((progress_h / range_h) * 100)))
            
        # Fatigue Level based on Entertainment hours (30 hours = 100% fatigue)
        fatigue_percent = min(100, int((ent_hours / 30.0) * 100))
        
        # Weakened State check
        # Entertainment > 30 hours OR Entertainment > 1.5 * Education (and entertainment > 3 hours)
        is_weakened = False
        if ent_hours > 30.0 or (ent_hours > 3.0 and ent_hours > 1.5 * edu_hours):
            is_weakened = True
            
        # Output values
        status = "normal"
        image_name = f"avatar_stage{level}.png"
        
        if is_weakened:
            status = "weakened"
            stage_title = "過度娛樂 (注意偏離)"
            description = "檢測到近期娛樂與社群時數偏高。適度的放鬆有助於恢復專注，但建議安排適當的學習或工作時間以重新激活分身狀態。"
            image_name = "avatar_weakened.png"
        elif level >= 4:
            status = "strong"
            
        return jsonify({
            "success": True,
            "edu_hours": round(edu_hours, 1),
            "ent_hours": round(ent_hours, 1),
            "level": level,
            "stage_title": stage_title,
            "description": description,
            "exp_percent": exp_percent,
            "fatigue_percent": fatigue_percent,
            "status": status,
            "image_url": f"/static/images/{image_name}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Ensure database is set up
    init_db()
    
    # 1. Start background tracker thread
    stop_event.clear()
    tracker_thread = threading.Thread(target=run_tracker, args=(stop_event,), daemon=True)
    tracker_thread.start()
    
    # 2.5 Auto-start desktop widget if setting is enabled
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'auto_start_widget'")
        row_widget = cursor.fetchone()
        conn.close()
        if row_widget and row_widget[0] == "true":
            print("Auto-starting desktop widget...")
            widget_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.py")
            if sys.platform == "win32":
                widget_process = subprocess.Popen(
                    [sys.executable, widget_script],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                widget_process = subprocess.Popen([sys.executable, widget_script])
    except Exception as e:
        print(f"Error auto-starting desktop widget: {e}")
        
    # 3. Start Flask app
    try:
        app.run(host="127.0.0.1", port=5000, debug=False)
    finally:
        # Signal tracker to stop on shutdown
        print("Shutting down tracker background thread...")
        stop_event.set()
        if tracker_thread:
            tracker_thread.join(timeout=3.0)
            
        # Clean up widget if running
        if widget_process and widget_process.poll() is None:
            print("Closing desktop widget...")
            widget_process.terminate()
            widget_process.wait()
