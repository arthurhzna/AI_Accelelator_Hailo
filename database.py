import sqlite3
import os
from datetime import datetime
import threading

class InitDatabase:
    def __init__(self, db_path='counter.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.db_lock = threading.Lock()
        
    def connect(self):
        """Koneksi ke database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.execute('PRAGMA journal_mode = WAL;')
        self.cursor = self.conn.cursor()
        return self.conn
    
    def close(self):
        """Tutup koneksi database"""
        if self.conn:
            self.conn.close()
    
    def init_database(self):
        db_exists = os.path.exists(self.db_path)
        self.connect()
        
        if not db_exists:
            self._run_migrations()
        else:
            self._check_and_create_missing_tables()
        
        return self.conn
    
    def _run_migrations(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_info (
                id_device TEXT PRIMARY KEY,
                is_registered INTEGER
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS line (
                line_number INTEGER PRIMARY KEY,
                x1 INTEGER,
                x2 INTEGER,
                y1 INTEGER,
                y2 INTEGER
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS impression (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_number INTEGER,
                type TEXT,
                rb INTEGER,
                br INTEGER,
                time_stamp TEXT,
                is_send INTEGER DEFAULT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS class_detection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id TEXT NOT NULL,
                class_name TEXT NOT NULL UNIQUE
            )
        ''')
        
        self.conn.commit()
    
    def _check_and_create_missing_tables(self):
        self.cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        existing_tables = [row[0] for row in self.cursor.fetchall()]
        required_tables = ['device_info', 'line', 'impression', 'class_detection']
        missing_tables = [t for t in required_tables if t not in existing_tables]
        
        if missing_tables:
            self._run_migrations()
    
    def insert_device_info(self, id_device, is_registered=0):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO device_info (id_device, is_registered) 
                    VALUES (?, ?)
                """, (id_device, is_registered))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    def get_device_info(self, id_device):
        self.cursor.execute("""
            SELECT * FROM device_info WHERE id_device = ?
        """, (id_device,))
        return self.cursor.fetchone()
    
    def get_device_info_formatted(self, id_device):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    SELECT * FROM device_info WHERE id_device = ?
                """, (id_device,))
                result = cur.fetchone()
                if result is None:
                    return None
                return True if result[1] == 1 else False
            finally:
                cur.close()
    
    def update_device_registration(self, id_device, is_registered):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    UPDATE device_info SET is_registered = ? WHERE id_device = ?
                """, (is_registered, id_device))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()
    
    def insert_line(self, line_number, x1, x2, y1, y2):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO line (line_number, x1, x2, y1, y2) 
                    VALUES (?, ?, ?, ?, ?)
                """, (line_number, x1, x2, y1, y2))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()
    
    def get_all_lines(self, line_number):
        self.cursor.execute("""
            SELECT * FROM line WHERE line_number = ?
        """, (line_number,))
        return self.cursor.fetchone()
    
    def get_all_lines_formatted(self):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    SELECT line_number, x1, y1, x2, y2 
                    FROM line 
                    ORDER BY line_number
                """)
                results = cur.fetchall()
                if not results:
                    return None
                line_values = []
                for row in results:
                    line_number, x1, y1, x2, y2 = row
                    line_values.append([(x1, y1), (x2, y2)])
                return line_values
            finally:
                cur.close()
        
    def get_all_lines(self):
        self.cursor.execute("SELECT * FROM line ORDER BY line_number")
        return self.cursor.fetchall()
    
    def insert_impression(self, line_number, type_val, rb, br, time_stamp=None, is_send=0):
        if time_stamp is None:
            time_stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO impression (line_number, type, rb, br, time_stamp, is_send) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (line_number, type_val, rb, br, time_stamp, is_send))
                self.conn.commit()
                last_id = cur.lastrowid
                return last_id
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()
    
    def get_pending_impressions(self):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    SELECT * FROM impression 
                    WHERE is_send IS NULL OR is_send = 0
                    ORDER BY id
                """)
                return cur.fetchall()
            finally:
                cur.close()
    
    def mark_impression_as_sent(self, impression_id):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    UPDATE impression SET is_send = 1 WHERE id = ?
                """, (impression_id,))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    def mark_impression_as_sent_by_line_number_and_type(self, line_number, type_val):
        self.cursor.execute("""
            UPDATE impression SET is_send = 1 WHERE line_number = ? AND type = ?
        """, (line_number, type_val))
        self.conn.commit()
    
    def get_impressions_by_line(self, line_number, limit=100):
        self.cursor.execute("""
            SELECT * FROM impression 
            WHERE line_number = ?
            ORDER BY id DESC
            LIMIT ?
        """, (line_number, limit))
        return self.cursor.fetchall()
    
    def show_all_tables(self):
        print("\n" + "="*50)
        print("DEVICE INFO:")
        self.cursor.execute("SELECT * FROM device_info")
        for row in self.cursor.fetchall():
            print(row)
        
        print("\n" + "="*50)
        print("LINE:")
        self.cursor.execute("SELECT * FROM line")
        for row in self.cursor.fetchall():
            print(row)
        
        print("\n" + "="*50)
        print("IMPRESSION:")
        self.cursor.execute("SELECT * FROM impression")
        for row in self.cursor.fetchall():
            print(row)
        print("="*50 + "\n")

        print("\n" + "="*50)
        print("CLASS DETECTION:")
        self.cursor.execute("SELECT * FROM class_detection")
        for row in self.cursor.fetchall():
            print(row)
        print("="*50 + "\n")

    def insert_class_detection(self, class_id, class_name):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO class_detection (class_id, class_name) 
                    VALUES (?, ?)
                """, (class_id, class_name))
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    def insert_multiple_classes(self,id_type_to_class_name_coco, class_id_list):
        for class_id in class_id_list:
            class_name = id_type_to_class_name_coco.get(class_id)
            if class_name:
                self.insert_class_detection(class_id, class_name)
            else:
                # print(f"Unknown class_id: {class_id}")
                pass

    def get_all_classes(self):
        self.cursor.execute("""
            SELECT * FROM class_detection ORDER BY id
        """)
        return self.cursor.fetchall()

    def get_all_class_names(self):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    SELECT class_name FROM class_detection ORDER BY id
                """)
                results = cur.fetchall()
                return [row[0] for row in results]
            finally:
                cur.close()

    def delete_class_detection(self, class_name):
        self.cursor.execute("""
            DELETE FROM class_detection WHERE class_name = ?
        """, (class_name,))
        self.conn.commit()

    def clear_all_classes(self):
        with self.db_lock:
            cur = self.conn.cursor()
            try:
                cur.execute("DELETE FROM class_detection")
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()
