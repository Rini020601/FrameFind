"""
Daemon Service Manager for Screenrecord Manager
Allows installing, running, and managing the background auto-renaming daemon
as a native macOS LaunchAgent (so it runs silently in the background on startup).

Usage:
    python daemon.py start      # Run the background auto-renamer in terminal
    python daemon.py install    # Install macOS LaunchAgent (runs automatically on login)
    python daemon.py uninstall  # Remove macOS LaunchAgent
    python daemon.py status     # Check background daemon status
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

from core.auto_renamer import ScreenrecordDaemon

LAUNCH_AGENT_LABEL = "com.screenrecord.manager"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LAUNCH_AGENT_LABEL}.plist"


def get_project_paths():
    project_dir = Path(__file__).resolve().parent
    venv_python = project_dir / ".venv" / "bin" / "python3"
    python_exe = venv_python if venv_python.exists() else Path(sys.executable)
    daemon_script = project_dir / "daemon.py"
    log_dir = project_dir / ".data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return project_dir, python_exe, daemon_script, log_dir


def generate_plist_content() -> str:
    project_dir, python_exe, daemon_script, log_dir = get_project_paths()
    stdout_log = log_dir / "daemon.stdout.log"
    stderr_log = log_dir / "daemon.stderr.log"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>{daemon_script}</string>
        <string>start</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_log}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_log}</string>
</dict>
</plist>
"""


def install_launch_agent():
    """Install and register a native macOS LaunchAgent."""
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist_content = generate_plist_content()

    with open(PLIST_PATH, "w", encoding="utf-8") as f:
        f.write(plist_content)

    # Load launch agent with launchctl
    try:
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
        subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
        print("✅ macOS Background Service successfully installed!")
        print(f"   LaunchAgent Plist: {PLIST_PATH}")
        print("\n⚡ From now on, whenever you screen record on macOS:")
        print("   1. You record via Cmd+Shift+5.")
        print("   2. macOS saves it to Desktop / Recents.")
        print("   3. This background service automatically renames it in Finder to match its content.")
        print("   4. Runs automatically on startup / login.")
    except Exception as e:
        print(f"⚠️ Error registering with launchctl: {e}")


def uninstall_launch_agent():
    """Unload and remove the LaunchAgent."""
    if PLIST_PATH.exists():
        try:
            subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, check=False)
        except Exception:
            pass
        PLIST_PATH.unlink(missing_ok=True)
        print("✅ macOS Background Service uninstalled.")
    else:
        print("Service is not currently installed.")


def status_launch_agent():
    """Check if the LaunchAgent is installed and running."""
    is_installed = PLIST_PATH.exists()
    print(f"• LaunchAgent Plist Installed: {'YES' if is_installed else 'NO'}")
    if is_installed:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        is_running = LAUNCH_AGENT_LABEL in res.stdout
        print(f"• Service Running in Background: {'🟢 ACTIVE' if is_running else '🔴 STOPPED'}")
    else:
        print("• Service Running in Background: 🔴 NOT INSTALLED")


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "start":
        daemon = ScreenrecordDaemon()
        daemon.start(blocking=True)
    elif sys.argv[1] == "install":
        install_launch_agent()
    elif sys.argv[1] == "uninstall":
        uninstall_launch_agent()
    elif sys.argv[1] == "status":
        status_launch_agent()
    else:
        print("Usage: python daemon.py [start|install|uninstall|status]")


if __name__ == "__main__":
    main()
