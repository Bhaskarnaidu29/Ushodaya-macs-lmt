"""
Database Connection Module
Handles all database connections for UDLMS
Production Ready Version
"""

import pyodbc
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# -------------------------------------------------
# Build Connection String
# -------------------------------------------------
def build_connection_string():
    driver = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("SQL_SERVER", "localhost")
    database = os.getenv("SQL_DATABASE", "udlms")
    username = os.getenv("SQL_USERNAME")
    password = os.getenv("SQL_PASSWORD")

    if username and password:
        # SQL Server Authentication
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
        )
    else:
        # Windows Authentication
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )


# -------------------------------------------------
# Get Database Connection
# -------------------------------------------------
def get_db_connection():
    """
    Creates and returns a new database connection.
    """
    try:
        conn_str = build_connection_string()

        # Optional: Enable connection pooling (default True)
        pyodbc.pooling = True

        conn = pyodbc.connect(conn_str, timeout=10)
        return conn

    except pyodbc.Error as e:
        logger.error(f"Database connection error: {e}")
        raise Exception("Failed to connect to database.")
    except Exception as e:
        logger.error(f"Unexpected DB connection error: {e}")
        raise


# -------------------------------------------------
# Test Connection
# -------------------------------------------------
def test_connection():
    """
    Test database connection.
    Returns True if successful.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


# -------------------------------------------------
# Execute Query (Safe Utility Function)
# -------------------------------------------------
def execute_query(query, params=None, fetch=True):
    """
    Execute a SQL query safely.

    Args:
        query (str): SQL query
        params (tuple): Parameters for query
        fetch (bool): If True, fetch results

    Returns:
        list or None
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch:
            return cursor.fetchall()
        else:
            conn.commit()
            return None

    except Exception as e:
        logger.error(f"Query execution error: {e}")

        if conn:
            try:
                conn.rollback()
            except:
                pass

        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()