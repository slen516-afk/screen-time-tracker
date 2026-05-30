import os
import sys
import time
import sqlite3
import datetime
import webbrowser
import tkinter as tk
from tkinter import messagebox

# Paths
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screentime.db")

class DesktopWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Screen Time Widget")
        
        # Borderless & Always-on-top by default
        self.root.overrideredirect(True)
        self.is_topmost = True
        self.root.wm_attributes("-topmost", True)
        
        # Set opacity (default 85%)
        self.opacity = 0.85
        self.root.wm_attributes("-alpha", self.opacity)
        
        # UI Dimensions
        self.width = 230
        self.height = 95
        
        # Position in bottom-right corner of primary monitor
        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = screen_width - self.width - 30
            y = screen_height - self.height - 60
        except Exception:
            x, y = 100, 100
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        # Styling Colors (Premium iOS Dark Theme)
        self.bg_color = "#1C1C1E"       # Dark Card
        self.border_color = "#2C2C2E"   # Border
        self.accent_color = "#007AFF"   # Blue Accent
        self.cyan_glow = "#00E5FF"     # Glowing Info
        self.text_primary = "#FFFFFF"   # White text
        self.text_secondary = "#8E8E93" # Muted grey
        self.active_green = "#30D158"   # Active indicator green
        
        self.root.configure(bg=self.bg_color)
        
        # Outer Card Border
        self.card = tk.Frame(
            self.root, 
            bg=self.bg_color, 
            highlightbackground=self.border_color, 
            highlightthickness=1,
            bd=0
        )
        self.card.pack(fill=tk.BOTH, expand=True)
        
        # 1. Header / Control Bar
        self.header_frame = tk.Frame(self.card, bg=self.bg_color)
        self.header_frame.pack(fill=tk.X, padx=10, pady=(6, 0))
        
        self.lbl_title = tk.Label(
            self.header_frame, 
            text="螢幕使用時間", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.bg_color, 
            fg=self.text_secondary
        )
        self.lbl_title.pack(side=tk.LEFT)
        
        # Category/Status Hint Label
        self.lbl_hint = tk.Label(
            self.header_frame, 
            text="", 
            font=("Segoe UI", 8, "bold"), 
            bg=self.bg_color, 
            fg=self.text_secondary
        )
        self.lbl_hint.pack(side=tk.LEFT, padx=(10, 0))
        
        self.lbl_pin = tk.Label(
            self.header_frame, 
            text="📌 釘選", 
            font=("Segoe UI", 8), 
            bg=self.bg_color, 
            fg=self.accent_color
        )
        self.lbl_pin.pack(side=tk.RIGHT)
        
        # 2. Main Stats (Large screen time display)
        self.lbl_time = tk.Label(
            self.card, 
            text="0h 00m", 
            font=("Segoe UI Semibold", 20), 
            bg=self.bg_color, 
            fg=self.cyan_glow
        )
        self.lbl_time.pack(anchor=tk.W, padx=10, pady=(2, 2))
        
        # 3. Active App Subtext
        self.lbl_app = tk.Label(
            self.card, 
            text="● 載入中...", 
            font=("Segoe UI", 9), 
            bg=self.bg_color, 
            fg=self.active_green,
            anchor=tk.W,
            justify=tk.LEFT
        )
        self.lbl_app.pack(fill=tk.X, padx=10, pady=(0, 6))
        
        # --- Dragging Mechanics ---
        self.root.bind("<Button-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.do_drag)
        
        # --- Context Menu & Double Click ---
        self.root.bind("<Button-3>", self.show_context_menu)
        self.root.bind("<Double-Button-1>", lambda e: self.open_dashboard())
        
        # Context Menu Creation
        self.menu = tk.Menu(self.root, tearoff=0, bg=self.bg_color, fg=self.text_primary, activebackground=self.accent_color)
        self.menu.add_command(label="📌 切換釘選 (置頂)", command=self.toggle_pin)
        
        self.opacity_menu = tk.Menu(self.menu, tearoff=0, bg=self.bg_color, fg=self.text_primary, activebackground=self.accent_color)
        self.opacity_menu.add_command(label="30%", command=lambda: self.set_opacity(0.3))
        self.opacity_menu.add_command(label="50%", command=lambda: self.set_opacity(0.5))
        self.opacity_menu.add_command(label="75%", command=lambda: self.set_opacity(0.75))
        self.opacity_menu.add_command(label="85% (預設)", command=lambda: self.set_opacity(0.85))
        self.opacity_menu.add_command(label="100%", command=lambda: self.set_opacity(1.0))
        self.menu.add_cascade(label="🌗 調整透明度", menu=self.opacity_menu)
        
        self.menu.add_command(label="📊 開啟儀表板", command=self.open_dashboard)
        self.menu.add_separator()
        self.menu.add_command(label="❌ 關閉小工具", command=self.quit_widget)
        
        # Start Live Update Poll
        self.update_data()
        
    def start_drag(self, event):
        self.x = event.x
        self.y = event.y

    def do_drag(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
        
    def show_context_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
            
    def toggle_pin(self):
        self.is_topmost = not self.is_topmost
        self.root.wm_attributes("-topmost", self.is_topmost)
        self.lbl_pin.configure(
            text="📌 釘選" if self.is_topmost else "🔓 浮動", 
            fg=self.accent_color if self.is_topmost else self.text_secondary
        )
        
    def set_opacity(self, value):
        self.opacity = value
        self.root.wm_attributes("-alpha", self.opacity)
        
    def open_dashboard(self):
        webbrowser.open("http://127.0.0.1:5000")
        
    def quit_widget(self):
        self.root.destroy()
        
    def get_todays_stats(self):
        if not os.path.exists(DB_PATH):
            return 0, "無資料", 0, "Others"
            
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Today's total duration
            cursor.execute("""
            SELECT SUM(duration) 
            FROM window_logs 
            WHERE date(start_time) = date('now', 'localtime')
            """)
            total_sec_row = cursor.fetchone()
            total_seconds = total_sec_row[0] if total_sec_row and total_sec_row[0] is not None else 0
            
            # Latest active application session (including category)
            cursor.execute("""
            SELECT app_name, window_title, category 
            FROM window_logs 
            ORDER BY id DESC LIMIT 1
            """)
            last_app_row = cursor.fetchone()
            
            if last_app_row:
                active_app = last_app_row[0]
                category = last_app_row[2] or "Others"
                
                # Check if this app was active recently (within last 15 seconds) to ensure it's "currently active"
                # If the tracker is offline or we are idle, show "Idle/Away"
                cursor.execute("""
                SELECT end_time 
                FROM window_logs 
                ORDER BY id DESC LIMIT 1
                """)
                end_time_row = cursor.fetchone()
                
                is_currently_active = False
                if end_time_row:
                    end_t = datetime.datetime.fromisoformat(end_time_row[0])
                    time_diff = (datetime.datetime.now() - end_t).total_seconds()
                    if time_diff <= 15:
                        is_currently_active = True
                        
                if not is_currently_active:
                    conn.close()
                    return total_seconds, "暫停中 (閒置/鎖定)", 0, "Others"
                
                # Get human readable display name
                cursor.execute("SELECT display_name FROM app_categories WHERE app_name = ?", (active_app,))
                d_row = cursor.fetchone()
                display_name = d_row[0] if d_row else active_app.replace(".exe", "").capitalize()
                
                # Get today's total for this active app
                cursor.execute("""
                SELECT SUM(duration) 
                FROM window_logs 
                WHERE app_name = ? AND date(start_time) = date('now', 'localtime')
                """, (active_app,))
                app_total_row = cursor.fetchone()
                app_total_seconds = app_total_row[0] if app_total_row and app_total_row[0] is not None else 0
                
                conn.close()
                return total_seconds, display_name, app_total_seconds, category
            else:
                conn.close()
                return total_seconds, "無活動", 0, "Others"
        except Exception as e:
            print(f"Widget DB error: {e}", file=sys.stderr)
            return 0, "錯誤", 0, "Others"

    def update_data(self):
        total_sec, active_app, app_sec, category = self.get_todays_stats()
        
        # Format total time
        total_hours = total_sec // 3600
        total_mins = (total_sec % 3600) // 60
        self.lbl_time.configure(text=f"{total_hours}h {total_mins:02d}m")
        
        # Format active app detail
        if active_app in ["暫停中 (閒置/鎖定)", "無活動", "錯誤"]:
            self.lbl_app.configure(text=f"● {active_app}", fg=self.text_secondary)
            self.lbl_hint.configure(text="[💤 閒置]", fg=self.text_secondary)
        else:
            app_hours = app_sec // 3600
            app_mins = (app_sec % 3600) // 60
            app_time_str = f"{app_hours}h {app_mins}m" if app_hours > 0 else f"{app_mins}m"
            
            # Shorten app display name if it's too long
            if len(active_app) > 15:
                active_app = active_app[:13] + "..."
                
            self.lbl_app.configure(text=f"● 正在使用 {active_app} ({app_time_str})", fg=self.active_green)
            
            # Update category status hint
            if category == "Education":
                self.lbl_hint.configure(text="[🎓 教育]", fg="#64D2FF")  # Neon Cyan
            elif category == "Entertainment & Media":
                self.lbl_hint.configure(text="[🎮 娛樂]", fg="#FF453A")  # Neon Red
            else:
                self.lbl_hint.configure(text="[⚙️ 其他]", fg="#AEAEB2")  # Muted Grey
            
        # Poll again in 1 second
        self.root.after(1000, self.update_data)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = DesktopWidget()
    app.run()
