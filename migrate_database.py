#!/usr/bin/env python3
"""
Database migration utility for Pump/Dump Screener Bot.
Handles migration from old schema (without user_id) to new schema (with user_id).

SAFE TO RUN MULTIPLE TIMES - Will detect existing columns and skip if already migrated.
"""

import sqlite3
import shutil
from datetime import datetime
import sys
import os


def backup_database():
    """Create a timestamped backup of the current database."""
    if not os.path.exists("keys.db"):
        print("⚠️  No existing database found (keys.db does not exist)")
        return None
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"keys.db.backup_{timestamp}"
    try:
        shutil.copy2("keys.db", backup_name)
        print(f"✅ Database backed up to: {backup_name}")
        return backup_name
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None


def check_column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = sqlite3.connect("keys.db")
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in c.fetchall()]
    conn.close()
    return column_name in columns


def migrate_add_user_id_column():
    """
    Add user_id column to access_keys table if missing.
    SAFE TO RUN - Will skip if column already exists.
    """
    try:
        if not os.path.exists("keys.db"):
            print("❌ keys.db does not exist. Use option 2 (fresh start) instead.")
            return False
            
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        
        # Check if access_keys table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_keys'")
        if not c.fetchone():
            conn.close()
            print("❌ access_keys table does not exist. Use option 2 (fresh start) instead.")
            return False
        
        # Add user_id column to access_keys if missing
        if check_column_exists("access_keys", "user_id"):
            print("✅ access_keys.user_id column already exists")
        else:
            print("Adding user_id column to access_keys table...")
            c.execute("ALTER TABLE access_keys ADD COLUMN user_id INTEGER")
            conn.commit()
            print("✅ user_id column added to access_keys")
        
        # Verify user_settings table exists and has user_id
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_settings'")
        if not c.fetchone():
            print("⚠️  user_settings table missing, creating...")
            conn.close()
            from database import init_db
            init_db()
            print("✅ user_settings table created")
            # Reopen connection after creating tables
            conn = sqlite3.connect("keys.db")
            c = conn.cursor()
        else:
            if not check_column_exists("user_settings", "user_id"):
                print("⚠️  user_settings missing user_id column, adding...")
                c.execute("ALTER TABLE user_settings ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
                conn.commit()
                print("✅ user_id column added to user_settings")
            else:
                print("✅ user_settings.user_id column exists")
        
        # Try to backfill user_id from user_settings to access_keys where possible
        print("\nAttempting to backfill user_id values...")
        c.execute("""
            UPDATE access_keys 
            SET user_id = (
                SELECT user_id FROM user_settings 
                WHERE user_settings.username = access_keys.username
            )
            WHERE access_keys.username IS NOT NULL 
            AND access_keys.user_id IS NULL
            AND EXISTS (
                SELECT 1 FROM user_settings 
                WHERE user_settings.username = access_keys.username 
                AND user_settings.user_id IS NOT NULL 
                AND user_settings.user_id != 0
            )
        """)
        backfilled = c.rowcount
        conn.commit()
        
        if backfilled > 0:
            print(f"✅ Backfilled {backfilled} user_id value(s) in access_keys")
        else:
            print("⚠️  No user_id values could be backfilled automatically")
        
        # Check for remaining NULL values
        c.execute("SELECT COUNT(*) FROM access_keys WHERE user_id IS NULL AND is_active=1")
        null_count = c.fetchone()[0]
        
        conn.close()
        print("\n✅ Migration completed successfully!")
        print("\n📋 POST-MIGRATION STATUS:")
        if null_count > 0:
            print(f"   ⚠️  {null_count} active key(s) still have user_id=NULL")
            print("   → These users should send /start to their bot")
            print("   → They'll be asked to re-enter their key (this updates user_id)")
        else:
            print("   ✅ All active keys have valid user_id values!")
        print("\n   • NEW activations will work immediately")
        print("   • Existing users can /start and re-enter key to update user_id")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_fresh_database():
    """Create a brand new database with correct schema."""
    from database import init_db
    
    print("Creating fresh database with user_id support...")
    init_db()
    print("✅ Fresh database created successfully")


def verify_schema():
    """Verify the database schema is correct."""
    if not os.path.exists("keys.db"):
        print("❌ No database found to verify")
        return False
        
    try:
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        
        print("\n[DATABASE SCHEMA VERIFICATION]")
        
        # Check access_keys
        c.execute("PRAGMA table_info(access_keys)")
        access_keys_columns = [row[1] for row in c.fetchall()]
        has_access_user_id = "user_id" in access_keys_columns
        print(f"✓ access_keys has user_id column: {'✅ YES' if has_access_user_id else '❌ NO'}")
        
        # Check user_settings
        c.execute("PRAGMA table_info(user_settings)")
        user_settings_columns = [row[1] for row in c.fetchall()]
        has_settings_user_id = "user_id" in user_settings_columns
        print(f"✓ user_settings has user_id column: {'✅ YES' if has_settings_user_id else '❌ NO'}")
        
        # Count users
        c.execute("SELECT COUNT(*) FROM user_settings")
        user_count = c.fetchone()[0]
        print(f"✓ Total users in database: {user_count}")
        
        # Count activated keys
        c.execute("SELECT COUNT(*) FROM access_keys WHERE is_active=1")
        active_keys = c.fetchone()[0]
        print(f"✓ Active license keys: {active_keys}")
        
        conn.close()
        
        if has_access_user_id and has_settings_user_id:
            print("\n✅ Database schema is CORRECT and ready for use!")
            return True
        else:
            print("\n❌ Database schema is INCOMPLETE - run migration")
            return False
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def main():
    print("="*70)
    print("PUMP/DUMP SCREENER BOT - DATABASE MIGRATION UTILITY")
    print("="*70)
    print("\nThis tool migrates your database to support user_id columns")
    print("for reliable user identification.\n")
    print("SAFE TO RUN MULTIPLE TIMES - Skips if already migrated.\n")
    print("Options:")
    print("  1. Migrate existing database (add user_id column, keep data)")
    print("  2. Fresh start (backup old DB, create new one)")
    print("  3. Verify database schema")
    print("  4. Backup database only")
    print("  5. Exit")
    
    choice = input("\nSelect option (1-5): ").strip()
    
    if choice == "1":
        print("\n[OPTION 1: MIGRATE EXISTING DATABASE]")
        print("This will ADD the user_id column if missing.")
        print("Your existing data will be PRESERVED.\n")
        
        backup = backup_database()
        if backup:
            print(f"Backup created: {backup}")
        
        if migrate_add_user_id_column():
            print("\n✅ SUCCESS - Migration complete!")
            verify_schema()
            print("\n✅ You can now restart your bot:")
            print("   systemctl restart pumpscreener.service")
            print("\n📝 Note: Existing users should reactivate keys to populate user_id")
        else:
            print("\n❌ MIGRATION FAILED")
            if backup:
                print(f"Your original database is safe: {backup}")
            sys.exit(1)
            
    elif choice == "2":
        print("\n[OPTION 2: FRESH START]")
        print("⚠️  WARNING: This creates a BRAND NEW database.")
        print("⚠️  ALL existing activations and user data will be LOST.")
        confirm = input("\nType 'yes' to confirm: ").strip().lower()
        
        if confirm == "yes":
            backup = backup_database()
            if backup:
                print(f"Old database backed up: {backup}")
            
            # Remove old database
            if os.path.exists("keys.db"):
                os.remove("keys.db")
                print("Old database removed")
                
            create_fresh_database()
            verify_schema()
            print("\n✅ SUCCESS - Fresh database created!")
            print("Users must activate their keys again.")
        else:
            print("Cancelled - no changes made.")
            
    elif choice == "3":
        print("\n[OPTION 3: VERIFY SCHEMA]")
        verify_schema()
        
    elif choice == "4":
        print("\n[OPTION 4: BACKUP ONLY]")
        backup = backup_database()
        if backup:
            print(f"\n✅ Backup complete: {backup}")
        
    elif choice == "5":
        print("Exiting...")
        sys.exit(0)
        
    else:
        print("❌ Invalid option")
        sys.exit(1)


if __name__ == "__main__":
    main()
