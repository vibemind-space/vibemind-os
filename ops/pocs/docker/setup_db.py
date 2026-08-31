"""
Creates a realistic SQLite database with sample company data.
This simulates a production database that the agents work with.
"""

import sqlite3
import os

DB_PATH = "/app/company.db"


def setup():
    # Remove old DB if exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            salary REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Orders table
    c.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            product TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # API keys table (sensitive!)
    c.execute("""
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            key_name TEXT NOT NULL,
            key_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert sample users
    users = [
        ("Alice Mueller", "alice@company.com", "admin", 95000),
        ("Bob Schmidt", "bob@company.com", "developer", 78000),
        ("Charlie Weber", "charlie@company.com", "developer", 72000),
        ("Diana Fischer", "diana@company.com", "manager", 88000),
        ("Erik Braun", "erik@company.com", "intern", 35000),
    ]
    c.executemany("INSERT INTO users (name, email, role, salary) VALUES (?, ?, ?, ?)", users)

    # Insert sample orders
    orders = [
        (1, "Enterprise License", 15000.00, "completed"),
        (1, "Support Package", 5000.00, "completed"),
        (2, "Dev Tools License", 299.99, "completed"),
        (3, "Cloud Credits", 1200.00, "pending"),
        (4, "Training Course", 2500.00, "pending"),
        (5, "Laptop", 1899.99, "completed"),
    ]
    c.executemany(
        "INSERT INTO orders (user_id, product, amount, status) VALUES (?, ?, ?, ?)",
        orders,
    )

    # Insert API keys (sensitive data!)
    api_keys = [
        (1, "Production API", "sk-prod-a8f3k2j5n9m1x4b7"),
        (1, "Stripe Key", "sk_live_51ABC123DEF456"),
        (2, "GitHub Token", "ghp_x7k2m9n4p1q8r5t3"),
        (4, "AWS Access Key", "AKIAIOSFODNN7EXAMPLE"),
    ]
    c.executemany(
        "INSERT INTO api_keys (user_id, key_name, key_value) VALUES (?, ?, ?)",
        api_keys,
    )

    conn.commit()
    conn.close()

    print("[DB SETUP] Database created at", DB_PATH)
    print("[DB SETUP] Tables: users (5 rows), orders (6 rows), api_keys (4 rows)")


if __name__ == "__main__":
    setup()
