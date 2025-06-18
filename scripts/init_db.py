import sqlite3
import os

# Define the path for the SQLite database within the container
DATABASE_PATH = '/data/db/database.sqlite3'

def main():
    """
    Initializes the database. Creates the directory, database file,
    and tables if they don't already exist.
    """
    print("--- Running database initialization ---")

    # Ensure the directory for the database exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if not os.path.exists(db_dir):
        print(f"Database directory not found. Creating {db_dir}...")
        os.makedirs(db_dir)
        print("Directory created.")
    else:
        print("Database directory already exists.")

    try:
        # Connect to the database. This will create the file if it doesn't exist.
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            print("Successfully connected to the database.")

            # Create the 'messages' table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("Table 'messages' is present or was created successfully.")
        
        print("--- Database initialization complete ---")

    except sqlite3.Error as e:
        print(f"An error occurred during database initialization: {e}")
        # Exit with a non-zero status code to indicate failure
        exit(1)

if __name__ == "__main__":
    main() 