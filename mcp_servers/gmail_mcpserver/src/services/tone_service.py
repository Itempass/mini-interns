import os
from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

# Define the base for SQLAlchemy models
Base = declarative_base()

class ToneOfVoice(Base):
    """SQLAlchemy model for the tone_of_voice table."""
    __tablename__ = "tone_of_voice"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False)
    tone_description = Column(Text)

    __table_args__ = (UniqueConstraint('email', 'language', name='_email_language_uc'),)

class ToneService:
    """Service class for interacting with the tone-of-voice database."""
    def __init__(self):
        """Initializes the database engine and session."""
        db_url = os.getenv("TONE_OF_VOICE_DB")
        if not db_url:
            raise ValueError("TONE_OF_VOICE_DB environment variable not set.")
        
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _get_db(self) -> Session:
        """Provides a database session."""
        return self.SessionLocal()

    def get_available_languages(self, email: str) -> List[str]:
        """
        Retrieves a list of available languages for a specific email.
        
        Args:
            email: The user's email address.
        
        Returns:
            A list of unique language strings.
        """
        db = self._get_db()
        try:
            # Query for distinct languages for the given email
            languages = db.query(ToneOfVoice.language).filter(ToneOfVoice.email == email).distinct().all()
            return [lang[0] for lang in languages]
        finally:
            db.close()

    def get_tone(self, email: str, language: str) -> Optional[str]:
        """
        Retrieves the tone description for a specific email and language.
        
        Args:
            email: The user's email address.
            language: The language of the tone profile.
            
        Returns:
            The tone description string, or None if not found.
        """
        db = self._get_db()
        try:
            # Query for the specific tone of voice entry
            tone_entry = db.query(ToneOfVoice.tone_description).filter(
                ToneOfVoice.email == email, 
                ToneOfVoice.language == language
            ).first()
            return tone_entry[0] if tone_entry else None
        finally:
            db.close() 