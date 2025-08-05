import logging
from typing import Optional
from uuid import UUID, uuid4
import mysql.connector
from datetime import datetime

from shared.config import settings
from user.models import User

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    return mysql.connector.connect(
        host='db',
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        port=3306
    )

def get_or_create_default_user() -> User:
    """
    Retrieves the default system user from the database.
    If the user does not exist, it creates one.
    """
    default_user_uuid_str = "12345678-1234-5678-9012-123456789012"
    default_user_uuid = UUID(default_user_uuid_str)

    # First, try to get the user
    user = get_user_by_uuid(default_user_uuid)
    if user:
        return user

    # If user not found, create it
    logger.info("Default user not found. Creating a new one.")
    new_user = User(
        uuid=default_user_uuid,
        auth0_sub=None,  # No Auth0 sub for the default user
        email="default-user@example.com",
        is_anonymous=True,
        created_at=datetime.utcnow()
    )
    
    # Use a new connection to avoid issues with closed cursors from get_user_by_uuid
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check again if the user was created by another process
        # This is a simple way to handle potential race conditions
        cursor.execute("SELECT uuid FROM users WHERE uuid = UUID_TO_BIN(%s)", (str(default_user_uuid),))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return get_user_by_uuid(default_user_uuid)

        query = """
            INSERT INTO users (uuid, auth0_sub, email, is_anonymous, created_at, balance)
            VALUES (UUID_TO_BIN(%s), %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            str(new_user.uuid),
            new_user.auth0_sub,
            new_user.email,
            new_user.is_anonymous,
            new_user.created_at,
            new_user.balance
        ))
        conn.commit()
        return new_user
    except mysql.connector.Error as err:
        logger.error(f"Failed to create default user: {err}")
        # If it's a duplicate entry error, it means another process created it.
        # We can try to fetch it again.
        if err.errno == 1062: # ER_DUP_ENTRY
             return get_user_by_uuid(default_user_uuid)
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_by_uuid(user_uuid: UUID) -> Optional[User]:
    """Retrieves a user from the database by their UUID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at, balance FROM users WHERE uuid = UUID_TO_BIN(%s)"
        cursor.execute(query, (str(user_uuid),))
        user_data = cursor.fetchone()
        if user_data:
            user_data['uuid'] = UUID(bytes=user_data['uuid'])
            return User(**user_data)
        return None
    finally:
        cursor.close()
        conn.close()

def create_user(user: User) -> User:
    """Creates a new user in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO users (uuid, auth0_sub, email, is_anonymous, created_at, balance)
            VALUES (UUID_TO_BIN(%s), %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            str(user.uuid),
            user.auth0_sub,
            user.email,
            user.is_anonymous,
            user.created_at,
            user.balance
        ))
        conn.commit()
        return user
    except mysql.connector.Error as err:
        logger.error(f"Failed to create user: {err}")
        # In a real app, you might want to handle specific errors, e.g., duplicate entry
        raise
    finally:
        cursor.close()
        conn.close()

def find_or_create_user_by_auth0_sub(auth0_sub: str, email: Optional[str] = None, is_anonymous: bool = False) -> User:
    """
    Finds a user by their Auth0 subject (sub). If the user doesn't exist,
    it creates a new one.
    """
    logger.info(f"Attempting to find or create user with auth0_sub: {auth0_sub}, email: {email}")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # First, try to find the user by auth0_sub
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at, balance FROM users WHERE auth0_sub = %s"
        cursor.execute(query, (auth0_sub,))
        user_data = cursor.fetchone()

        if user_data:
            user_data['uuid'] = UUID(bytes=user_data['uuid'])
            return User(**user_data)
        else:
            # User not found, create a new one
            logger.info(f"User with auth0_sub: {auth0_sub} not found. Creating new user with email: {email}")
            new_user = User(
                uuid=uuid4(),
                auth0_sub=auth0_sub,
                email=email,
                is_anonymous=is_anonymous,
                created_at=datetime.utcnow()
            )
            
            insert_query = """
                INSERT INTO users (uuid, auth0_sub, email, is_anonymous, created_at, balance)
                VALUES (UUID_TO_BIN(%s), %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                str(new_user.uuid),
                new_user.auth0_sub,
                new_user.email,
                new_user.is_anonymous,
                new_user.created_at,
                new_user.balance
            ))
            conn.commit()
            return new_user
    finally:
        cursor.close()
        conn.close()

def set_user_balance(user_uuid: UUID, new_balance: float) -> Optional[User]:
    """Updates the balance for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = "UPDATE users SET balance = %s WHERE uuid = UUID_TO_BIN(%s)"
        cursor.execute(query, (new_balance, str(user_uuid)))
        conn.commit()
        if cursor.rowcount > 0:
            return get_user_by_uuid(user_uuid)
        return None
    finally:
        cursor.close()
        conn.close()

def deduct_from_balance(user_uuid: UUID, cost: float) -> Optional[User]:
    """Deducts a cost from a user's balance atomically."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = "UPDATE users SET balance = balance - %s WHERE uuid = UUID_TO_BIN(%s)"
        cursor.execute(query, (cost, str(user_uuid)))
        conn.commit()
        if cursor.rowcount > 0:
            return get_user_by_uuid(user_uuid)
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_users() -> list[User]:
    """Retrieves all users from the database."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    users = []
    try:
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at, balance FROM users"
        cursor.execute(query)
        for row in cursor.fetchall():
            row['uuid'] = UUID(bytes=row['uuid'])
            users.append(User(**row))
        return users
    finally:
        cursor.close()
        conn.close() 