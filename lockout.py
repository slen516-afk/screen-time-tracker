import os
import sys
import tkinter as tk

# Parse command line arguments
app_name = sys.argv[1] if len(sys.argv) > 1 else "unknown.exe"
display_name = sys.argv[2] if len(sys.argv) > 2 else "應用程式"

class LockoutWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("時間限制已達")
        
        # Borderless and always on top
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        
        # Centered on Screen
        self.width = 460
        self.height = 290
        
        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - self.width) // 2
            y = (screen_height - self.height) // 2
        except Exception:
            x, y = 300, 300
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        # Styling Colors (Premium iOS Dark Theme)
        self.bg_color = "#1C1C1E"       # Dark charcoal
        self.border_color = "#2C2C2E"   # Border
        self.accent_color = "#007AFF"   # Blue Accent
        self.amber_glow = "#FF9F0A"     # Amber Hourglass
        self.text_primary = "#FFFFFF"   # White text
        self.text_secondary = "#AEAEB2" # M muted grey
        self.btn_bg = "#2C2C2E"         # Button dark grey
        
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
        
        # 1. Giant Hourglass Icon
        self.lbl_icon = tk.Label(
            self.card, 
            text="⏳", 
            font=("Segoe UI", 36), 
            bg=self.bg_color, 
            fg=self.amber_glow
        )
        self.lbl_icon.pack(pady=(25, 5))
        
        # 2. Main Blocker Title
        self.lbl_title = tk.Label(
            self.card, 
            text="時間限制已達", 
            font=("Segoe UI Semibold", 20), 
            bg=self.bg_color, 
            fg=self.text_primary
        )
        self.lbl_title.pack(pady=5)
        
        # 3. Blocker Subtext
        self.lbl_desc = tk.Label(
            self.card, 
            text=f"您今天使用「{display_name}」的時間已達到上限。", 
            font=("Segoe UI", 11), 
            bg=self.bg_color, 
            fg=self.text_secondary,
            wraplength=400,
            justify=tk.CENTER
        )
        self.lbl_desc.pack(pady=(5, 25))
        
        # 4. Action Buttons Container
        self.btn_frame = tk.Frame(self.card, bg=self.bg_color)
        self.btn_frame.pack(fill=tk.X, padx=30)
        
        # Left: One More Minute
        self.btn_minute = tk.Button(
            self.btn_frame,
            text="再使用 1 分鐘",
            font=("Segoe UI", 10, "bold"),
            bg=self.btn_bg,
            fg=self.accent_color,
            activebackground=self.accent_color,
            activeforeground=self.text_primary,
            bd=0,
            cursor="hand2",
            padx=15,
            pady=8,
            command=self.one_more_minute
        )
        self.btn_minute.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Center: OK (Minimize)
        self.btn_ok = tk.Button(
            self.btn_frame,
            text="確定 (關閉)",
            font=("Segoe UI", 10, "bold"),
            bg=self.accent_color,
            fg=self.text_primary,
            activebackground="#0056B3",
            activeforeground=self.text_primary,
            bd=0,
            cursor="hand2",
            padx=15,
            pady=8,
            command=self.confirm_lock
        )
        self.btn_ok.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Right: Ignore for Today
        self.btn_ignore = tk.Button(
            self.btn_frame,
            text="今日忽略限制",
            font=("Segoe UI", 10),
            bg=self.btn_bg,
            fg=self.text_secondary,
            activebackground=self.btn_bg,
            activeforeground=self.text_primary,
            bd=0,
            cursor="hand2",
            padx=15,
            pady=8,
            command=self.ignore_today
        )
        self.btn_ignore.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

    def confirm_lock(self):
        # Exit with code 0: standard OK / Minimize
        self.root.destroy()
        sys.exit(0)
        
    def one_more_minute(self):
        # Exit with code 1: One More Minute
        self.root.destroy()
        sys.exit(1)
        
    def ignore_today(self):
        # Exit with code 2: Ignore for Today
        self.root.destroy()
        sys.exit(2)
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = LockoutWindow()
    app.run()
