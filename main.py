#!/usr/bin/env python3
"""
Screenrecord Manager — Intelligent OCR, Video Indexing & Privacy Redaction for macOS.

Usage:
    python main.py                  # Launch the Native Desktop GUI
    python main.py --gui            # Launch the Native Desktop GUI
    python main.py index <path>     # Index a video, screenshot, or directory
    python main.py search "<query>" # Full-text search across indexed media
    python main.py watch            # Run the background filesystem watcher daemon
    python main.py stats            # Display indexed library statistics
"""

import os
import sys
import argparse
from typing import List

from core.database import SearchDatabase
from core.indexer import IndexerPipeline
from core.watcher import CaptureWatcher
from core.namer import SmartNamer
from core.auto_renamer import ScreenrecordDaemon


def cli_index(paths: List[str], auto_rename: bool = True):
    db = SearchDatabase()
    pipeline = IndexerPipeline(db=db, auto_rename=auto_rename)

    target_files = []
    for p in paths:
        if os.path.isfile(p):
            target_files.append(p)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(('.mov', '.mp4', '.png', '.jpg', '.jpeg')):
                        target_files.append(os.path.join(root, f))

    if not target_files:
        print("❌ No supported media files (.mov, .mp4, .png, .jpg) found.")
        return

    print(f"🚀 Indexing {len(target_files)} media file(s) with Apple Vision OCR...")
    for i, file_path in enumerate(target_files, 1):
        def on_progress(pct, msg):
            print(f"  [{i}/{len(target_files)}] ({int(pct*100)}%) {msg}")

        rec_id = pipeline.index_file(file_path, progress_cb=on_progress)
        if rec_id:
            print(f"  ✅ Completed: {os.path.basename(file_path)} (ID: {rec_id})\n")
        else:
            print(f"  ⚠️ Skipped / Failed: {os.path.basename(file_path)}\n")


def cli_search(query: str):
    db = SearchDatabase()
    print(f"🔍 Searching for: '{query}'\n" + "—" * 60)
    results = db.search(query)
    if not results:
        print("No matches found.")
        return

    print(f"Found {len(results)} match(es):\n")
    for r in results:
        sec = r.get("timestamp_sec", 0.0)
        mins = int(sec // 60)
        secs = int(sec % 60)
        time_str = f"{mins:02d}:{secs:02d}" if r.get("file_type") == "video" else "Screenshot"
        snippet = (r.get("ocr_snippet") or "").replace("<mark>", ">>").replace("</mark>", "<<")

        print(f"📁 {r.get('file_name')} [{r.get('category', 'General')}]")
        print(f"   ⏱ Timestamp: {time_str}")
        print(f"   💬 Snippet: {snippet}")
        print(f"   📍 Path: {r.get('file_path')}")
        print("—" * 60)


def cli_watch():
    print("👀 Starting Background Auto-Renamer Daemon...")
    print("Captures saved to Desktop/Finder will be automatically renamed based on their content.\n")
    daemon = ScreenrecordDaemon()
    daemon.start(blocking=True)


def cli_rename(target: str):
    db = SearchDatabase()
    rec = None
    if target.isdigit():
        rec = db.get_record(int(target))
    else:
        abs_path = os.path.abspath(target)
        for r in db.get_recent_records(limit=200):
            if os.path.abspath(r["file_path"]) == abs_path or r["file_name"] == os.path.basename(target):
                rec = r
                break

    if not rec:
        print(f"❌ Recording '{target}' not found in database. Index it first.")
        return

    events = db.get_record_events(rec["id"])
    all_text = [e.get("ocr_text", "") for e in events]
    suggested = SmartNamer.generate_title(all_text, rec.get("app_name", "macOS"), rec.get("category", "General"), rec["file_path"])

    print(f"Current Name:   {rec['file_name']}")
    print(f"Suggested Name: {suggested}")
    try:
        new_path = SmartNamer.rename_recording_file(rec["file_path"], suggested)
        new_name = os.path.basename(new_path)
        db.update_record_file_path(rec["id"], new_path, new_name)
        print(f"✅ Renamed on disk to: {new_name}")
    except Exception as e:
        print(f"❌ Failed to rename: {e}")


def cli_stats():
    db = SearchDatabase()
    stats = db.get_stats()
    hrs = round(stats.get("total_duration_sec", 0.0) / 3600.0, 2)
    mb = round(stats.get("total_size_bytes", 0) / (1024 * 1024), 1)

    print("📊 Screenrecord Manager Library Stats:")
    print(f"  • Total Videos Indexed:      {stats.get('total_videos', 0)}")
    print(f"  • Total Screenshots Indexed: {stats.get('total_screenshots', 0)}")
    print(f"  • Total Indexed Events:      {stats.get('total_indexed_events', 0)}")
    print(f"  • Total Video Duration:      {hrs} hours")
    print(f"  • Total Media Size:          {mb} MB")


def main():
    parser = argparse.ArgumentParser(description="Screenrecord Manager — Intelligent OCR & Video Indexer")
    parser.add_argument("--gui", action="store_true", help="Launch the Desktop GUI")
    
    subparsers = parser.add_subparsers(dest="command")

    # index command
    idx_p = subparsers.add_parser("index", help="Index media files or folder")
    idx_p.add_argument("paths", nargs="+", help="Files or directories to index")
    idx_p.add_argument("--no-auto-rename", action="store_true", help="Disable automatic content-based renaming")

    # rename command
    ren_p = subparsers.add_parser("rename", help="Smart-rename a recording based on its OCR content")
    ren_p.add_argument("target", help="File path or record ID to rename")

    # search command
    srch_p = subparsers.add_parser("search", help="Search indexed media")
    srch_p.add_argument("query", help="Text/query to search")

    # watch command
    subparsers.add_parser("watch", help="Run background auto-renamer daemon")

    # daemon command
    d_p = subparsers.add_parser("daemon", help="Manage background LaunchAgent service")
    d_p.add_argument("action", choices=["start", "install", "uninstall", "status"], help="Daemon action")

    # stats command
    subparsers.add_parser("stats", help="Show library statistics")

    args = parser.parse_args()

    if args.command == "index":
        cli_index(args.paths, auto_rename=not args.no_auto_rename)
    elif args.command == "rename":
        cli_rename(args.target)
    elif args.command == "search":
        cli_search(args.query)
    elif args.command == "watch":
        cli_watch()
    elif args.command == "daemon":
        from daemon import install_launch_agent, uninstall_launch_agent, status_launch_agent
        if args.action == "start":
            cli_watch()
        elif args.action == "install":
            install_launch_agent()
        elif args.action == "uninstall":
            uninstall_launch_agent()
        elif args.action == "status":
            status_launch_agent()
    elif args.command == "stats":
        cli_stats()
    else:
        # Default action: Launch Desktop GUI
        from gui.app import run_gui
        run_gui()


if __name__ == "__main__":
    main()
