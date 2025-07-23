import logging
from typing import Optional
from uuid import UUID
import mysql.connector

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

def get_default_user() -> Optional[User]:
    """Retrieves the default system user from the database."""
    default_user_uuid_str = "12345678-1234-5678-9012-123456789012"
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the user by UUID, converting the string to binary for the query
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at FROM users WHERE uuid = UUID_TO_BIN(%s)"
        cursor.execute(query, (default_user_uuid_str,))
        user_data = cursor.fetchone()
        if user_data:
            # The UUID from the database needs to be converted back from bytes to a UUID object
            user_data['uuid'] = UUID(bytes=user_data['uuid'])
            return User(**user_data)
        return None
    finally:
        cursor.close()
        conn.close()

def get_user_by_uuid(user_uuid: UUID) -> Optional[User]:
    """Retrieves a user from the database by their UUID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at FROM users WHERE uuid = UUID_TO_BIN(%s)"
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
            INSERT INTO users (uuid, auth0_sub, email, is_anonymous, created_at)
            VALUES (UUID_TO_BIN(%s), %s, %s, %s, %s)
        """
        cursor.execute(query, (
            str(user.uuid),
            user.auth0_sub,
            user.email,
            user.is_anonymous,
            user.created_at
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
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # First, try to find the user by auth0_sub
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at FROM users WHERE auth0_sub = %s"
        cursor.execute(query, (auth0_sub,))
        user_data = cursor.fetchone()

        if user_data:
            user_data['uuid'] = UUID(bytes=user_data['uuid'])
            return User(**user_data)
        else:
            # User not found, create a new one
            from uuid import uuid4
            from datetime import datetime

            new_user = User(
                uuid=uuid4(),
                auth0_sub=auth0_sub,
                email=email,
                is_anonymous=is_anonymous,
                created_at=datetime.utcnow()
            )
            
            insert_query = """
                INSERT INTO users (uuid, auth0_sub, email, is_anonymous, created_at)
                VALUES (UUID_TO_BIN(%s), %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                str(new_user.uuid),
                new_user.auth0_sub,
                new_user.email,
                new_user.is_anonymous,
                new_user.created_at
            ))
            conn.commit()
            return new_user
    finally:
        cursor.close()
        conn.close()

def _get_all_users_from_db() -> list[User]:
    """Retrieves all users from the database."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    users = []
    try:
        query = "SELECT uuid, auth0_sub, email, is_anonymous, created_at FROM users"
        cursor.execute(query)
        for row in cursor.fetchall():
            row['uuid'] = UUID(bytes=row['uuid'])
            users.append(User(**row))
        return users
    finally:
        cursor.close()
        conn.close() 