"""
Database Module for Screenrecord Manager
SQLite FTS5 full-text search index for video keyframes and screenshots.
"""

import os
import json
import sqlite3
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_DIR = os.environ.get(
    "SCREENRECORD_DATA_DIR",
    os.path.join(PROJECT_ROOT, ".data")
)
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "library.db")


class SearchDatabase:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self.conn:
            # 1. Records table (each screen recording or screenshot)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL, -- 'video' or 'screenshot'
                    duration_sec REAL DEFAULT 0.0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    file_size_bytes INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    app_name TEXT DEFAULT 'Unknown',
                    category TEXT DEFAULT 'General', -- 'Code & Terminal', 'Slides & Presentation', etc.
                    thumbnail_path TEXT
                )
            """)

            # 2. Events table (per-timestamp OCR / audio transcript / keyframe)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id INTEGER NOT NULL,
                    timestamp_sec REAL NOT NULL,
                    frame_idx INTEGER DEFAULT 0,
                    ocr_text TEXT DEFAULT '',
                    audio_text TEXT DEFAULT '',
                    bounding_boxes TEXT DEFAULT '[]', -- JSON array of [{text, box: [x,y,w,h], confidence}]
                    is_keyframe INTEGER DEFAULT 1,
                    frame_thumb_path TEXT,
                    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
                )
            """)

            # 3. Full-Text Search 5 (FTS5) standalone virtual table
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    ocr_text,
                    audio_text,
                    file_name,
                    category,
                    tokenize='porter unicode61'
                )
            """)

            # Indexes for faster joins & filtering
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_record_id ON events(record_id);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp_sec);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON records(file_type);")

    def insert_or_update_record(self, data: Dict[str, Any]) -> int:
        """Insert a new recording or screenshot metadata record, or return existing ID."""
        with self.conn:
            cur = self.conn.execute(
                "SELECT id FROM records WHERE file_path = ?", (data["file_path"],)
            )
            row = cur.fetchone()
            if row:
                record_id = row["id"]
                self.conn.execute("""
                    UPDATE records SET
                        file_name = ?, file_type = ?, duration_sec = ?,
                        width = ?, height = ?, file_size_bytes = ?,
                        indexed_at = CURRENT_TIMESTAMP, app_name = ?,
                        category = ?, thumbnail_path = ?
                    WHERE id = ?
                """, (
                    data["file_name"], data["file_type"], data.get("duration_sec", 0.0),
                    data.get("width", 0), data.get("height", 0), data.get("file_size_bytes", 0),
                    data.get("app_name", "Unknown"), data.get("category", "General"),
                    data.get("thumbnail_path", ""), record_id
                ))
                # Delete old events from FTS and events table
                self.conn.execute("""
                    DELETE FROM events_fts WHERE rowid IN (
                        SELECT id FROM events WHERE record_id = ?
                    )
                """, (record_id,))
                self.conn.execute("DELETE FROM events WHERE record_id = ?", (record_id,))
                return record_id
            else:
                cur = self.conn.execute("""
                    INSERT INTO records (
                        file_path, file_name, file_type, duration_sec,
                        width, height, file_size_bytes, app_name,
                        category, thumbnail_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["file_path"], data["file_name"], data["file_type"],
                    data.get("duration_sec", 0.0), data.get("width", 0),
                    data.get("height", 0), data.get("file_size_bytes", 0),
                    data.get("app_name", "Unknown"), data.get("category", "General"),
                    data.get("thumbnail_path", "")
                ))
                return cur.lastrowid

    def insert_event(self, event_data: Dict[str, Any]) -> int:
        """Insert a timestamped OCR/Audio keyframe event and sync with FTS5."""
        boxes = event_data.get("bounding_boxes", [])
        if isinstance(boxes, (list, dict)):
            boxes_json = json.dumps(boxes)
        else:
            boxes_json = str(boxes)

        with self.conn:
            cur = self.conn.execute("""
                INSERT INTO events (
                    record_id, timestamp_sec, frame_idx, ocr_text,
                    audio_text, bounding_boxes, is_keyframe, frame_thumb_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data["record_id"],
                event_data.get("timestamp_sec", 0.0),
                event_data.get("frame_idx", 0),
                event_data.get("ocr_text", ""),
                event_data.get("audio_text", ""),
                boxes_json,
                event_data.get("is_keyframe", 1),
                event_data.get("frame_thumb_path", "")
            ))
            event_id = cur.lastrowid

            # Fetch record metadata to index in FTS5
            r_cur = self.conn.execute(
                "SELECT file_name, category FROM records WHERE id = ?", (event_data["record_id"],)
            )
            r_row = r_cur.fetchone()
            file_name = r_row["file_name"] if r_row else ""
            category = r_row["category"] if r_row else ""

            self.conn.execute("""
                INSERT INTO events_fts(rowid, ocr_text, audio_text, file_name, category)
                VALUES (?, ?, ?, ?, ?)
            """, (
                event_id,
                event_data.get("ocr_text", ""),
                event_data.get("audio_text", ""),
                file_name,
                category
            ))

            return event_id

    def search(self, query: str, file_type: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Full-text search query across all indexed OCR text and audio transcripts.
        Returns ranked results with snippets, exact timestamps, and record metadata.
        """
        query = query.strip()
        if not query:
            return self.get_recent_records(file_type=file_type, category=category)

        clean_words = []
        for word in query.split():
            clean_word = ''.join(c for c in word if c.isalnum() or c in '_-')
            if clean_word:
                clean_words.append(f'"{clean_word}"*')
        
        if not clean_words:
            return []
        fts_query = ' AND '.join(clean_words)

        sql = """
            SELECT 
                e.id AS event_id,
                e.record_id,
                e.timestamp_sec,
                e.frame_idx,
                e.ocr_text,
                e.audio_text,
                e.bounding_boxes,
                e.frame_thumb_path,
                r.file_path,
                r.file_name,
                r.file_type,
                r.duration_sec,
                r.app_name,
                r.category,
                r.thumbnail_path,
                snippet(events_fts, 0, '<mark>', '</mark>', '...', 15) AS ocr_snippet,
                snippet(events_fts, 1, '<mark>', '</mark>', '...', 15) AS audio_snippet,
                bm25(events_fts) AS rank
            FROM events_fts
            JOIN events e ON events_fts.rowid = e.id
            JOIN records r ON e.record_id = r.id
            WHERE events_fts MATCH ?
        """
        params = [fts_query]

        if file_type and file_type != 'all':
            sql += " AND r.file_type = ?"
            params.append(file_type)

        if category and category != 'all':
            sql += " AND r.category = ?"
            params.append(category)

        sql += " ORDER BY rank ASC LIMIT 50"

        cur = self.conn.execute(sql, params)
        results = []
        for row in cur.fetchall():
            res = dict(row)
            try:
                res["bounding_boxes"] = json.loads(res.get("bounding_boxes") or "[]")
            except Exception:
                res["bounding_boxes"] = []
            results.append(res)
        return results

    def get_recent_records(self, limit: int = 40, file_type: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent recordings or screenshots."""
        sql = """
            SELECT id AS record_id, id, file_path, file_name, file_type, duration_sec,
                   width, height, file_size_bytes, created_at, indexed_at,
                   app_name, category, thumbnail_path
            FROM records
            WHERE 1=1
        """
        params = []
        if file_type and file_type != 'all':
            sql += " AND file_type = ?"
            params.append(file_type)
        if category and category != 'all':
            sql += " AND category = ?"
            params.append(category)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def get_record(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Get record details by ID."""
        cur = self.conn.execute("SELECT * FROM records WHERE id = ?", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_record_events(self, record_id: int) -> List[Dict[str, Any]]:
        """Get all timestamped events/chapters for a specific recording."""
        cur = self.conn.execute("""
            SELECT id, record_id, timestamp_sec, frame_idx, ocr_text,
                   audio_text, bounding_boxes, is_keyframe, frame_thumb_path
            FROM events
            WHERE record_id = ?
            ORDER BY timestamp_sec ASC
        """, (record_id,))
        events = []
        for row in cur.fetchall():
            ev = dict(row)
            try:
                ev["bounding_boxes"] = json.loads(ev.get("bounding_boxes") or "[]")
            except Exception:
                ev["bounding_boxes"] = []
            events.append(ev)
        return events

    def delete_record(self, record_id: int):
        """Delete a record and all associated events."""
        with self.conn:
            self.conn.execute("""
                DELETE FROM events_fts WHERE rowid IN (
                    SELECT id FROM events WHERE record_id = ?
                )
            """, (record_id,))
            self.conn.execute("DELETE FROM records WHERE id = ?", (record_id,))

    def update_record_file_path(self, record_id: int, new_path: str, new_name: str):
        """Update file path and name on disk and sync with FTS5."""
        with self.conn:
            self.conn.execute("""
                UPDATE records SET file_path = ?, file_name = ? WHERE id = ?
            """, (new_path, new_name, record_id))

            # Sync new file_name in events_fts
            self.conn.execute("""
                UPDATE events_fts SET file_name = ?
                WHERE rowid IN (SELECT id FROM events WHERE record_id = ?)
            """, (new_name, record_id))

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate summary statistics for the portfolio dashboard."""
        cur = self.conn.execute("""
            SELECT 
                COUNT(CASE WHEN file_type = 'video' THEN 1 END) AS total_videos,
                COUNT(CASE WHEN file_type = 'screenshot' THEN 1 END) AS total_screenshots,
                COALESCE(SUM(duration_sec), 0) AS total_duration_sec,
                COALESCE(SUM(file_size_bytes), 0) AS total_size_bytes,
                (SELECT COUNT(*) FROM events) AS total_indexed_events
            FROM records
        """)
        row = cur.fetchone()
        return dict(row) if row else {
            "total_videos": 0,
            "total_screenshots": 0,
            "total_duration_sec": 0,
            "total_size_bytes": 0,
            "total_indexed_events": 0
        }
