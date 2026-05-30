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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Today's total duration
        cursor.execute("""
        SELECT SUM(duration) 
        FROM window_logs 
        WHERE date(start_time) = date('now', 'localtime')
        """)
        row_today = cursor.fetchone()
        total_today = row_today[0] if row_today and row_today[0] is not None else 0
        
        # Yesterday's total duration
        cursor.execute("""
        SELECT SUM(duration) 
        FROM window_logs 
        WHERE date(start_time) = date('now', '-1 day', 'localtime')
        """)
        row_yesterday = cursor.fetchone()
        total_yesterday = row_yesterday[0] if row_yesterday and row_yesterday[0] is not None else 0
        
        # Percentage Change
        pct_change = 0.0
        if total_yesterday > 0:
            pct_change = round(((total_today - total_yesterday) / total_yesterday) * 100, 1)
        elif total_today > 0:
            pct_change = 100.0
            
        # Category Breakdown for today
        cursor.execute("""
        SELECT COALESCE(l.category, c.category) as category, SUM(l.duration) as cat_duration
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE date(l.start_time) = date('now', 'localtime')
        GROUP BY COALESCE(l.category, c.category)
        ORDER BY cat_duration DESC
        """)
        rows_categories = cursor.fetchall()
        category_data = {row["category"]: row["cat_duration"] for row in rows_categories}
        
        # Default empty categories to 0 if not tracked
        all_categories = ["Browsers", "Developer Tools", "Social & Communication", 
                          "Entertainment & Media", "Productivity & Office", "System", "Education", "Others"]
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

# 2. Chart Stats (Hourly breakdown for today)
@app.route("/api/stats/chart", methods=["GET"])
def get_chart_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Initialize 24 hours to 0
        hourly_data = [0] * 24
        
        cursor.execute("""
        SELECT strftime('%H', start_time) as hr, SUM(duration) as hr_duration
        FROM window_logs
        WHERE date(start_time) = date('now', 'localtime')
        GROUP BY hr
        """)
        
        rows = cursor.fetchall()
        for row in rows:
            hour_idx = int(row["hr"])
            if 0 <= hour_idx < 24:
                hourly_data[hour_idx] = row["hr_duration"]
                
        conn.close()
        
        return jsonify({
            "success": True,
            "chart_data": hourly_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 3. Application List
@app.route("/api/stats/apps", methods=["GET"])
def get_apps_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get overall applications and their today's duration
        cursor.execute("""
        SELECT l.app_name, c.display_name, c.category, SUM(l.duration) as app_duration
        FROM window_logs l
        JOIN app_categories c ON l.app_name = c.app_name
        WHERE date(l.start_time) = date('now', 'localtime')
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
                
            # Fetch top window titles/subtasks for this app today
            cursor.execute("""
            SELECT window_title, SUM(duration) as win_duration
            FROM window_logs
            WHERE app_name = ? AND date(start_time) = date('now', 'localtime') AND window_title != ''
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get last 50 events today where duration was significant (>= 3 seconds)
        cursor.execute("""
        SELECT l.app_name, c.display_name, COALESCE(l.category, c.category) as category, l.window_title, l.start_time, l.end_time, l.duration
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE date(l.start_time) = date('now', 'localtime') AND l.duration >= 3
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
            limits_data = [{"target": row["target"], "limit_seconds": row["limit_seconds"]} for row in rows]
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

# 7. Get/Set Active Idle Threshold
@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == "GET":
            cursor.execute("SELECT value FROM settings WHERE key = 'idle_threshold'")
            row = cursor.fetchone()
            idle_threshold = float(row[0]) if row else 60.0
            
            # Also return list of all unique categories in system
            cursor.execute("SELECT DISTINCT category FROM app_categories")
            cats = [r["category"] for r in cursor.fetchall()]
            
            conn.close()
            return jsonify({
                "success": True, 
                "idle_threshold": idle_threshold,
                "available_categories": cats
            })
            
        elif request.method == "POST":
            data = request.get_json()
            idle_threshold = data.get("idle_threshold")
            
            if idle_threshold is None or float(idle_threshold) <= 0:
                return jsonify({"success": False, "error": "Invalid idle threshold"}), 400
                
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('idle_threshold', ?)", (str(idle_threshold),))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Settings updated"})
            
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
        
        # Query total duration for Education in past 30 days
        cursor.execute("""
        SELECT SUM(l.duration) 
        FROM window_logs l
        LEFT JOIN app_categories c ON l.app_name = c.app_name
        WHERE COALESCE(l.category, c.category) = 'Education' 
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
        stage_title = "初階數碼蛋"
        description = "剛出生的初階數位分身，充滿對新事物的渴望，需要多進行教育學習或寫程式來進化。"
        next_threshold = 5.0
        prev_threshold = 0.0
        
        if edu_hours >= 100.0:
            level = 5
            stage_title = "終極數位真神"
            description = "超越肉體凡胎，化身為掌控網絡底層架構的至高數位真神，智慧之光普照整個網絡世界。"
            next_threshold = 100.0
            prev_threshold = 100.0
        elif edu_hours >= 50.0:
            level = 4
            stage_title = "星際科技賢者"
            description = "大腦已與量子雲端進行神經連結，能隨意編織星雲般的代碼，通曉數據演變的大道法則。"
            next_threshold = 100.0
            prev_threshold = 50.0
        elif edu_hours >= 20.0:
            level = 3
            stage_title = "數據編譯大法師"
            description = "能夠流暢編寫各類程式，操縱多維度虛擬程式面板，對演算法的理解達到爐火純青的境界。"
            next_threshold = 50.0
            prev_threshold = 20.0
        elif edu_hours >= 5.0:
            level = 2
            stage_title = "自學機器人"
            description = "已經開始吸收大量基礎知識，手臂裝備了初階編譯器，眼神中透露著智慧的光芒。"
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
            stage_title = "沙發土豆 (萎靡狀態)"
            description = "過度影音娛樂！分身正癱在沙發上吃洋芋片看劇，雙眼失神、數據嚴重溢出...快去進行教育學習來喚醒他！"
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

# --- Auto Browser Launch Thread ---
def launch_browser():
    time.sleep(1.5)  # Wait for Flask to boot up
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    # Ensure database is set up
    init_db()
    
    # 1. Start background tracker thread
    stop_event.clear()
    tracker_thread = threading.Thread(target=run_tracker, args=(stop_event,), daemon=True)
    tracker_thread.start()
    
    # 2. Trigger auto-browser open in a thread
    browser_thread = threading.Thread(target=launch_browser, daemon=True)
    browser_thread.start()
    
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
