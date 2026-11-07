"""Incremental offsets into observation logs; raw trading files stay untouched."""

import csv
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


def instant(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


class ReplayIndex:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('CREATE TABLE IF NOT EXISTS sources (path TEXT PRIMARY KEY, kind TEXT, device INTEGER, inode INTEGER, size INTEGER, mtime INTEGER, cursor INTEGER, header TEXT)')
        connection.execute('CREATE TABLE IF NOT EXISTS observations (source TEXT, position INTEGER, length INTEGER, at REAL, PRIMARY KEY(source, position))')
        connection.execute('CREATE INDEX IF NOT EXISTS replay_time ON observations(at)')
        return connection

    def update(self, sources, progress=lambda **values: None):
        rows = 0
        with closing(self.connect()) as connection:
            for file_index, (path, kind) in enumerate(sources):
                path = Path(path)
                if not path.exists():
                    continue
                with path.open('rb') as file:
                    stat = os.fstat(file.fileno())
                    previous = connection.execute('SELECT device,inode,size,mtime,cursor,header FROM sources WHERE path=?', (str(path),)).fetchone()
                    reset = not previous or previous[:2] != (stat.st_dev, stat.st_ino) or stat.st_size < previous[4] or (stat.st_size == previous[2] and stat.st_mtime_ns != previous[3])
                    if reset:
                        connection.execute('DELETE FROM observations WHERE source=?', (str(path),))
                        cursor = 0
                        header = []
                        if kind != 'recorded':
                            line = file.readline()
                            if not line.endswith(b'\n'):
                                continue
                            header = next(csv.reader([line.decode('utf-8-sig')]))
                            cursor = file.tell()
                    else:
                        cursor, header = previous[4], json.loads(previous[5])
                    file.seek(cursor)
                    batch = []
                    while file.tell() < stat.st_size:
                        position = file.tell()
                        line = file.readline(stat.st_size - position)
                        if not line.endswith(b'\n'):
                            break  # Do not index an append which has not finished.
                        cursor = file.tell()
                        try:
                            if kind == 'recorded':
                                at = instant(json.loads(line).get('timestamp'))
                            else:
                                # All supported CSV sources have timestamp first.
                                at = instant(line.split(b',', 1)[0].decode().strip('"'))
                            if at is not None:
                                batch.append((str(path), position, len(line), at))
                        except (ValueError, UnicodeError, AttributeError):
                            continue
                        if len(batch) >= 5000:
                            connection.executemany('INSERT OR REPLACE INTO observations VALUES (?,?,?,?)', batch)
                            rows += len(batch)
                            batch.clear()
                            connection.commit()
                            progress(rows=rows, files=file_index, totalFiles=len(sources))
                    if batch:
                        connection.executemany('INSERT OR REPLACE INTO observations VALUES (?,?,?,?)', batch)
                        rows += len(batch)
                    connection.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?)',
                        (str(path), kind, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, cursor, json.dumps(header)))
                    connection.commit()
                    progress(rows=rows, files=file_index + 1, totalFiles=len(sources))

    def window(self, start, end, sources):
        allowed = {str(Path(path)) for path, _ in sources}
        if not allowed:
            return [], False
        result = []
        files = {}
        try:
            with closing(self.connect()) as connection:
                placeholders = ','.join('?' for _ in allowed)
                query = connection.execute('SELECT o.source,o.position,o.length,o.at,s.kind,s.device,s.inode,s.header '
                    f'FROM observations o JOIN sources s ON s.path=o.source WHERE o.at>=? AND o.at<=? AND o.source IN ({placeholders}) ORDER BY o.at LIMIT 25001', (start, end, *sorted(allowed)))
                for source, position, length, at, kind, device, inode, header in query:
                    if source not in allowed:
                        continue
                    if source not in files:
                        file = open(source, 'rb')
                        stat = os.fstat(file.fileno())
                        if (stat.st_dev, stat.st_ino) != (device, inode):
                            file.close()
                            raise ValueError('An observation log changed. Refresh replay data.')
                        files[source] = file
                    file = files[source]
                    file.seek(position)
                    line = file.read(length)
                    try:
                        if not line.endswith(b'\n'):
                            continue
                        if kind == 'recorded':
                            row = json.loads(line)
                        else:
                            values = next(csv.reader([line.decode('utf-8')]))
                            fields = json.loads(header)
                            if len(values) != len(fields):
                                continue
                            row = dict(zip(fields, values))
                        if isinstance(row, dict) and instant(row.get('timestamp')) == at:
                            result.append((source, kind, at, row))
                    except (ValueError, UnicodeError, StopIteration):
                        continue
        finally:
            for file in files.values():
                file.close()
        return result[:25000], len(result) > 25000
