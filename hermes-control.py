#!/usr/bin/env python3
"""
Hermes Control - System Tray App
A compact GTK system tray application for controlling Hermes
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, GLib, Gdk, AppIndicator3
import cairo
import math
import threading
import urllib.request
import json
import os
import sys

# -----------------------------------------
# Config
# -----------------------------------------
POLL_INTERVAL = 3000  # ms
STATS_PORT = 8099
N8N_PORT = 5678
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 560

COLORS = {
    "bg":         (0.05, 0.05, 0.05),
    "bg_card":    (0.08, 0.08, 0.08),
    "cyan":       (0.0,  0.87, 0.87),
    "green":      (0.0,  0.87, 0.25),
    "red":        (0.87, 0.15, 0.15),
    "yellow":     (0.87, 0.65, 0.0),
    "dim":        (0.35, 0.35, 0.35),
    "text":       (0.85, 0.85, 0.85),
    "text_dim":   (0.45, 0.45, 0.45),
}


# -----------------------------------------
# Autostart
# -----------------------------------------
AUTOSTART_DIR  = os.path.expanduser('~/.config/autostart')
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, 'hermes-control.desktop')

def autostart_is_enabled():
    return os.path.exists(AUTOSTART_FILE)

def autostart_enable():
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    main_py = os.path.abspath(__file__)
    python  = sys.executable
    desktop = f"""[Desktop Entry]
Type=Application
Name=Hermes Control
Comment=Hermes travel automation control panel
Exec={python} {main_py}
Icon=network-wireless-symbolic
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
    with open(AUTOSTART_FILE, 'w') as f:
        f.write(desktop)

def autostart_disable():
    if os.path.exists(AUTOSTART_FILE):
        os.remove(AUTOSTART_FILE)

# -----------------------------------------
# State
# -----------------------------------------
state = {
    "connected": False,
    "hermes_ip": "",
    "stats": None,
    "error": None,
}

# -----------------------------------------
# API
# -----------------------------------------
def fetch_stats(ip):
    try:
        url = f"http://{ip}:{STATS_PORT}/stats"
        req = urllib.request.urlopen(url, timeout=3)
        return json.loads(req.read().decode())
    except Exception as e:
        return None

def fire_webhook(ip, path):
    try:
        url = f"http://{ip}:{N8N_PORT}/webhook/{path}"
        data = b"{}"
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
        return True
    except:
        return False

# -----------------------------------------
# Dial widget
# -----------------------------------------
class Dial(Gtk.DrawingArea):
    def __init__(self, label, unit, color, max_val=100):
        super().__init__()
        self.label = label
        self.unit = unit
        self.color = color
        self.max_val = max_val
        self.value = 0
        self.set_size_request(55, 55)
        self.connect("draw", self.on_draw)

    def set_value(self, val):
        self.value = val
        self.queue_draw()

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 4

        # Background
        cr.set_source_rgb(*COLORS["bg_card"])
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

        # Track
        cr.set_source_rgb(*COLORS["dim"])
        cr.set_line_width(4)
        cr.arc(cx, cy, r - 2, math.pi * 0.75, math.pi * 2.25)
        cr.stroke()

        # Value arc
        pct = min(self.value / self.max_val, 1.0)
        end_angle = math.pi * 0.75 + pct * math.pi * 1.5
        cr.set_source_rgb(*self.color)
        cr.set_line_width(4)
        cr.arc(cx, cy, r - 2, math.pi * 0.75, end_angle)
        cr.stroke()

        # Value text
        cr.set_source_rgb(*COLORS["text"])
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(9)
        val_str = str(int(self.value))
        ext = cr.text_extents(val_str)
        cr.move_to(cx - ext.width / 2, cy + ext.height / 2)
        cr.show_text(val_str)

        # Unit text
        cr.set_source_rgb(*COLORS["text_dim"])
        cr.set_font_size(7)
        unit_ext = cr.text_extents(self.unit)
        cr.move_to(cx - unit_ext.width / 2, cy + ext.height / 2 + 9)
        cr.show_text(self.unit)

        # Label
        cr.set_source_rgb(*COLORS["text_dim"])
        cr.set_font_size(7)
        lext = cr.text_extents(self.label)
        cr.move_to(cx - lext.width / 2, h - 2)
        cr.show_text(self.label)

# -----------------------------------------
# Main window
# -----------------------------------------
class HermesPanel(Gtk.Window):
    def __init__(self):
        super().__init__(title="Hermes Control")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_decorated(True)
        self.set_skip_taskbar_hint(True)

        # Dark theme
        css = b"""
        window { background-color: #0d0d0d; }
        button {
            background: #1a1a1a;
            color: #dddddd;
            border: 1px solid #333;
            border-radius: 4px;
            font-family: monospace;
            font-size: 22px;
            padding: 4px 8px;
            min-height: 0;
        }
        button:hover { background: #252525; border-color: #00dddd; }
        button.recall { border-color: #dd2222; color: #dd2222; }
        button.recall:hover { background: #1a0000; }
        button.security { border-color: #ddaa00; color: #ddaa00; }
        button.security:hover { background: #1a1000; }
        button.reconnect { border-color: #00dd40; color: #00dd40; }
        button.reconnect:hover { background: #001a08; }
        entry {
            background: #1a1a1a;
            color: #dddddd;
            border: 1px solid #333;
            border-radius: 4px;
            font-family: monospace;
            font-size: 22px;
        }
        label { color: #dddddd; font-family: monospace; }
        .dim { color: #555555; }
        .title { color: #00dddd; font-weight: bold; font-size: 26px; }
        .section { color: #00dddd; font-size: 18px; }
        .connected { color: #00dd40; }
        .disconnected { color: #dd2222; }
        separator { background: #222222; }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.showing_connect = True
        self.build_ui()

    def build_ui(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.main_box.set_margin_top(8)
        self.main_box.set_margin_bottom(8)
        self.add(self.main_box)

        self.show_connect_screen()

    def clear_main(self):
        for child in self.main_box.get_children():
            self.main_box.remove(child)

    # -----------------------------------------
    # Connect screen
    # -----------------------------------------
    def show_connect_screen(self):
        self.clear_main()
        self.showing_connect = True

        # Title
        title = Gtk.Label(label="⚡ HERMES")
        title.get_style_context().add_class("title")
        title.set_margin_bottom(4)
        self.main_box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label="Control Panel")
        subtitle.get_style_context().add_class("dim")
        subtitle.set_margin_bottom(16)
        self.main_box.pack_start(subtitle, False, False, 0)

        sep = Gtk.Separator()
        sep.set_margin_bottom(16)
        self.main_box.pack_start(sep, False, False, 0)

        # IP entry
        ip_label = Gtk.Label(label="Hermes IP Address")
        ip_label.set_halign(Gtk.Align.START)
        ip_label.get_style_context().add_class("section")
        ip_label.set_margin_bottom(4)
        self.main_box.pack_start(ip_label, False, False, 0)

        self.ip_entry = Gtk.Entry()
        self.ip_entry.set_placeholder_text("192.168.x.x")
        saved_ip = self.load_saved_ip()
        if saved_ip:
            self.ip_entry.set_text(saved_ip)
        self.ip_entry.set_margin_bottom(12)
        self.main_box.pack_start(self.ip_entry, False, False, 0)

        # Connect button
        connect_btn = Gtk.Button(label="CONNECT")
        connect_btn.get_style_context().add_class("reconnect")
        connect_btn.connect("clicked", self.on_connect)
        self.main_box.pack_start(connect_btn, False, False, 0)

        self.connect_status = Gtk.Label(label="")
        self.connect_status.get_style_context().add_class("dim")
        self.connect_status.set_margin_top(8)
        self.main_box.pack_start(self.connect_status, False, False, 0)

        self.show_all()

    def on_connect(self, btn):
        ip = self.ip_entry.get_text().strip()
        if not ip:
            self.connect_status.set_text("Enter an IP address")
            return
        self.connect_status.set_text("Connecting...")
        self.save_ip(ip)

        def try_connect():
            stats = fetch_stats(ip)
            GLib.idle_add(self.handle_connect_result, ip, stats)

        threading.Thread(target=try_connect, daemon=True).start()

    def handle_connect_result(self, ip, stats):
        if stats:
            state["connected"] = True
            state["hermes_ip"] = ip
            state["stats"] = stats
            self.show_panel()
        else:
            self.connect_status.set_text("Could not connect — check IP")
        return False

    # -----------------------------------------
    # Main panel
    # -----------------------------------------
    def show_panel(self):
        self.clear_main()
        self.showing_connect = False

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label="⚡ HERMES")
        title.get_style_context().add_class("title")
        header.pack_start(title, True, True, 0)

        self.status_dot = Gtk.Label(label="● Connected")
        self.status_dot.get_style_context().add_class("connected")
        header.pack_end(self.status_dot, False, False, 0)
        self.main_box.pack_start(header, False, False, 0)

        ip_lbl = Gtk.Label(label=state["hermes_ip"])
        ip_lbl.get_style_context().add_class("dim")
        ip_lbl.set_halign(Gtk.Align.START)
        ip_lbl.set_margin_bottom(6)
        self.main_box.pack_start(ip_lbl, False, False, 0)

        sep = Gtk.Separator()
        sep.set_margin_bottom(8)
        self.main_box.pack_start(sep, False, False, 0)

        # Dials
        dials_label = Gtk.Label(label="SYSTEM")
        dials_label.get_style_context().add_class("section")
        dials_label.set_halign(Gtk.Align.START)
        dials_label.set_margin_bottom(6)
        self.main_box.pack_start(dials_label, False, False, 0)

        dials_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dials_row1.set_homogeneous(True)

        self.cpu_dial = Dial("CPU", "%", COLORS["cyan"])
        self.temp_dial = Dial("TEMP", "°C", COLORS["yellow"], max_val=85)
        self.mem_dial = Dial("MEM", "%", COLORS["green"])

        dials_row1.pack_start(self.cpu_dial, True, True, 0)
        dials_row1.pack_start(self.temp_dial, True, True, 0)
        dials_row1.pack_start(self.mem_dial, True, True, 0)
        dials_row1.set_margin_bottom(6)
        self.main_box.pack_start(dials_row1, False, False, 0)

        # Uptime
        uptime_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        uptime_lbl = Gtk.Label(label="UPTIME")
        uptime_lbl.get_style_context().add_class("dim")
        uptime_box.pack_start(uptime_lbl, False, False, 0)
        self.uptime_val = Gtk.Label(label="--")
        self.uptime_val.set_halign(Gtk.Align.END)
        uptime_box.pack_end(self.uptime_val, False, False, 0)
        uptime_box.set_margin_bottom(8)
        self.main_box.pack_start(uptime_box, False, False, 0)

        sep2 = Gtk.Separator()
        sep2.set_margin_bottom(8)
        self.main_box.pack_start(sep2, False, False, 0)

        # Services
        svc_label = Gtk.Label(label="SERVICES")
        svc_label.get_style_context().add_class("section")
        svc_label.set_halign(Gtk.Align.START)
        svc_label.set_margin_bottom(4)
        self.main_box.pack_start(svc_label, False, False, 0)

        svc_grid = Gtk.Grid()
        svc_grid.set_column_spacing(6)
        svc_grid.set_row_spacing(2)
        svc_grid.set_margin_bottom(8)

        self.svc_labels = {}
        svcs = [
            ("homeassistant", "HA", 0, 0),
            ("music-assistant", "MA", 1, 0),
            ("n8n", "n8n", 0, 1),
            ("sendspin", "AUD", 1, 1),
        ]
        for key, display, col, row in svcs:
            lbl = Gtk.Label(label=f"● {display}")
            lbl.set_halign(Gtk.Align.START)
            self.svc_labels[key] = lbl
            svc_grid.attach(lbl, col, row, 1, 1)

        self.main_box.pack_start(svc_grid, False, False, 0)

        sep3 = Gtk.Separator()
        sep3.set_margin_bottom(8)
        self.main_box.pack_start(sep3, False, False, 0)

        # Mode
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        mode_lbl = Gtk.Label(label="MODE")
        mode_lbl.get_style_context().add_class("dim")
        mode_box.pack_start(mode_lbl, False, False, 0)
        self.mode_val = Gtk.Label(label="ACTIVE")
        self.mode_val.set_halign(Gtk.Align.END)
        mode_box.pack_end(self.mode_val, False, False, 0)
        mode_box.set_margin_bottom(8)
        self.main_box.pack_start(mode_box, False, False, 0)

        sep4 = Gtk.Separator()
        sep4.set_margin_bottom(8)
        self.main_box.pack_start(sep4, False, False, 0)

        # Controls
        ctrl_label = Gtk.Label(label="CONTROLS")
        ctrl_label.get_style_context().add_class("section")
        ctrl_label.set_halign(Gtk.Align.START)
        ctrl_label.set_margin_bottom(6)
        self.main_box.pack_start(ctrl_label, False, False, 0)

        recall_btn = Gtk.Button(label="⏻  RECALL")
        recall_btn.get_style_context().add_class("recall")
        recall_btn.connect("clicked", self.on_recall)
        recall_btn.set_margin_bottom(4)
        self.main_box.pack_start(recall_btn, False, False, 0)

        self.security_btn = Gtk.Button(label="🔒  SECURITY ON")
        self.security_btn.get_style_context().add_class("security")
        self.security_btn.connect("clicked", self.on_security)
        self.security_btn.set_margin_bottom(4)
        self.main_box.pack_start(self.security_btn, False, False, 0)

        reconnect_btn = Gtk.Button(label="⟳  RECONNECT")
        reconnect_btn.get_style_context().add_class("reconnect")
        reconnect_btn.connect("clicked", self.on_reconnect)
        self.main_box.pack_start(reconnect_btn, False, False, 0)

        self.show_all()
        self.update_stats(state["stats"])
        GLib.timeout_add(POLL_INTERVAL, self.poll_stats)

    def update_stats(self, stats):
        if not stats:
            self.status_dot.set_text("● Disconnected")
            self.status_dot.get_style_context().remove_class("connected")
            self.status_dot.get_style_context().add_class("disconnected")
            return

        self.status_dot.set_text("● Connected")
        self.status_dot.get_style_context().remove_class("disconnected")
        self.status_dot.get_style_context().add_class("connected")

        self.cpu_dial.set_value(stats.get("cpu", 0))
        self.temp_dial.set_value(stats.get("temp", 0))
        mem = stats.get("memory", {})
        self.mem_dial.set_value(mem.get("percent", 0))
        self.uptime_val.set_text(stats.get("uptime", "--"))

        services = stats.get("services", {})
        for key, lbl in self.svc_labels.items():
            status = services.get(key, "unknown")
            short = {"homeassistant": "HA", "music-assistant": "MA",
                     "n8n": "n8n", "sendspin": "AUD"}[key]
            lbl.set_text(f"● {short}")
            ctx = lbl.get_style_context()
            ctx.remove_class("connected")
            ctx.remove_class("disconnected")
            if status == "running":
                ctx.add_class("connected")
            else:
                ctx.add_class("disconnected")

        mode = stats.get("mode", "active").upper()
        self.mode_val.set_text(mode)

    def poll_stats(self):
        if self.showing_connect:
            return False
        ip = state["hermes_ip"]

        def fetch():
            s = fetch_stats(ip)
            GLib.idle_add(self.handle_poll, s)

        threading.Thread(target=fetch, daemon=True).start()
        return True

    def handle_poll(self, stats):
        if stats:
            state["stats"] = stats
            self.update_stats(stats)
        else:
            self.update_stats(None)
        return False

    # -----------------------------------------
    # Control actions
    # -----------------------------------------
    def on_recall(self, btn):
        ip = state["hermes_ip"]
        threading.Thread(
            target=lambda: fire_webhook(ip, "hermes-recall"),
            daemon=True
        ).start()

    def on_security(self, btn):
        ip = state["hermes_ip"]
        mode = state.get("stats", {}).get("mode", "active")
        if mode == "security":
            threading.Thread(
                target=lambda: fire_webhook(ip, "hermes-security-off"),
                daemon=True
            ).start()
            self.security_btn.set_label("🔒  SECURITY ON")
        else:
            threading.Thread(
                target=lambda: fire_webhook(ip, "hermes-security-on"),
                daemon=True
            ).start()
            self.security_btn.set_label("🔓  SECURITY OFF")

    def on_reconnect(self, btn):
        ip = state["hermes_ip"]
        def try_reconnect():
            stats = fetch_stats(ip)
            GLib.idle_add(self.handle_poll, stats)
        threading.Thread(target=try_reconnect, daemon=True).start()

    # -----------------------------------------
    # IP persistence
    # -----------------------------------------
    def save_ip(self, ip):
        try:
            config_dir = os.path.expanduser("~/.config/hermes-control")
            os.makedirs(config_dir, exist_ok=True)
            with open(os.path.join(config_dir, "last_ip"), "w") as f:
                f.write(ip)
        except:
            pass

    def load_saved_ip(self):
        try:
            path = os.path.expanduser("~/.config/hermes-control/last_ip")
            with open(path) as f:
                return f.read().strip()
        except:
            return ""

# -----------------------------------------
# System tray
# -----------------------------------------
class HermesControl:
    def __init__(self):
        self.panel = None
        self.indicator = AppIndicator3.Indicator.new(
            "hermes-control",
            "network-wireless-symbolic",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

    def build_menu(self):
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label="Open Hermes Control")
        show_item.connect("activate", self.toggle_panel)
        menu.append(show_item)

        menu.append(Gtk.SeparatorMenuItem())

        autostart_label = "Disable Autostart" if autostart_is_enabled() else "Enable Autostart"
        self.autostart_item = Gtk.MenuItem(label=autostart_label)
        self.autostart_item.connect("activate", self.toggle_autostart)
        menu.append(self.autostart_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    def toggle_panel(self, source=None):
        if self.panel is None or not self.panel.get_visible():
            self.panel = HermesPanel()
            self.panel.connect("delete-event", lambda w, e: w.hide() or True)
            self.panel.show_all()
            screen = Gdk.Screen.get_default()
            screen_w = screen.get_width()
            self.panel.move(screen_w - WINDOW_WIDTH - 10, 40)
        else:
            self.panel.hide()

    def toggle_autostart(self, source=None):
        if autostart_is_enabled():
            autostart_disable()
            self.autostart_item.set_label("Enable Autostart")
        else:
            autostart_enable()
            self.autostart_item.set_label("Disable Autostart")

# -----------------------------------------
# Entry point
# -----------------------------------------
if __name__ == "__main__":
    app = HermesControl()
    Gtk.main()
