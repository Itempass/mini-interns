import pytest
import os
from src.services.summarization_service import SummarizationService

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set, skipping live API test.")
def test_summarize_email_body_live():
    """
    Tests the SummarizationService's summarize_email_body method with a live API call.
    """
    # 1. Initialize the service
    service = SummarizationService()
    
    # 2. Define test input
    test_body = """
    Hello Team,

    This is a reminder about our quarterly all-hands meeting next Tuesday at 10 AM PST. 
    We will be discussing the product roadmap for the next quarter, and we'll also have a Q&A session with leadership.
    Please submit your questions in advance via the form linked in the calendar invite.

    Looking forward to seeing you all there.

    Best,
    Management
    """
    
    # 3. Generate summary
    summary = service.summarize_email_body(test_body)
    
    # 4. Assertions
    assert isinstance(summary, str), "Summary should be a string."
    assert len(summary) > 0, "Summary should not be empty."
    assert len(summary.split('.')) <= 4, "Summary should be around 3 sentences long." # Approximate check
    
    # Test invalid input
    with pytest.raises(ValueError):
        service.summarize_email_body("") # Empty string
    
    with pytest.raises(ValueError):
        service.summarize_email_body(None) # None input 