#!/usr/bin/env python3
"""Add owner_id column to pages table"""

from database import engine
from sqlalchemy import text

def add_owner_column():
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("PRAGMA table_info(pages)"))
        columns = [row[1] for row in result]
        
        if 'owner_id' not in columns:
            conn.execute(text('ALTER TABLE pages ADD COLUMN owner_id INTEGER'))
            conn.commit()
            print('✓ Added owner_id column to pages table')
        else:
            print('✓ owner_id column already exists')

if __name__ == "__main__":
    add_owner_column()