import sqlite3
from typing import Optional, List, Dict, Any, Union
from contextlib import contextmanager
import logging
from pathlib import Path

from ..models.event import Event, EventSource

class DatabaseService:
    """
    Service for database operations.
    
    Handles SQLite database initialization, connection management,
    and provides a foundation for repository pattern implementation.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize the database service.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._logger = logging.getLogger(__name__)
        
        # Ensure database directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """
        Get a database connection with automatic cleanup.
        
        Yields:
            sqlite3.Connection: Database connection
            
        Raises:
            Exception: If connection fails
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
            yield conn
            
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise Exception(f"Database operation failed: {str(e)}")
            
        finally:
            if conn:
                conn.close()
    
    def initialize_database(self) -> None:
        """
        Initialize the database schema.
        
        Raises:
            Exception: If database initialization fails
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create events table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        start TEXT NOT NULL,
                        end TEXT NOT NULL,
                        source TEXT NOT NULL,
                        calendar_event_id TEXT,
                        tournament TEXT,
                        player1_id INTEGER,
                        player2_id INTEGER,
                        player1_name TEXT,
                        player2_name TEXT,
                        event_id INTEGER,
                        round_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_events_source 
                    ON events (source)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_events_start 
                    ON events (start)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_events_calendar_id 
                    ON events (calendar_event_id)
                ''')
                
                # Create trigger to update updated_at timestamp
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS events_updated_at
                    AFTER UPDATE ON events
                    FOR EACH ROW
                    BEGIN
                        UPDATE events SET updated_at = CURRENT_TIMESTAMP
                        WHERE id = NEW.id;
                    END
                ''')
                
                conn.commit()
                self._logger.info("Database initialized successfully")
                
        except Exception as e:
            raise Exception(f"Failed to initialize database: {str(e)}")
    
    def execute_query(
        self, 
        query: str, 
        params: Union[tuple, dict, None] = None,
        fetch: bool = False
    ) -> Optional[List[sqlite3.Row]]:
        """
        Execute a SQL query.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: Whether to fetch results
            
        Returns:
            Query results if fetch=True, None otherwise
            
        Raises:
            Exception: If query execution fails
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch:
                    return cursor.fetchall()
                
                conn.commit()
                return None
                
        except sqlite3.Error as e:
            raise Exception(f"Query execution failed: {str(e)} (query: {query})")
    
    def get_row_count(self, table_name: str, where_clause: str = "", params: tuple = ()) -> int:
        """
        Get the number of rows in a table.
        
        Args:
            table_name: Name of the table
            where_clause: Optional WHERE clause (without WHERE keyword)
            params: Parameters for the WHERE clause
            
        Returns:
            Number of rows
        """
        query = f"SELECT COUNT(*) FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        
        result = self.execute_query(query, params, fetch=True)
        return result[0][0] if result else 0
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get general database information.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get page count and page size
                cursor.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]
                
                cursor.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                
                # Get table list
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                # Get events count
                events_count = self.get_row_count("events")
                
                return {
                    "database_path": self.db_path,
                    "size_bytes": page_count * page_size,
                    "page_count": page_count,
                    "page_size": page_size,
                    "tables": tables,
                    "events_count": events_count,
                }
                
        except Exception as e:
            self._logger.error(f"Failed to get database info: {str(e)}")
            return {
                "database_path": self.db_path,
                "error": str(e),
            }