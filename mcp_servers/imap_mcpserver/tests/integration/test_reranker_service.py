import pytest
import os
import sys
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

# This assumes tests are run from the project root.
# The .env files should be located there.
load_dotenv(override=True)

from shared.services.embedding_service import rerank_documents

@pytest.fixture(scope="module")
def check_api_key():
    """Fixture to check if API key is available."""
    if not os.getenv("EMBEDDING_VOYAGE_API_KEY") or os.getenv("EMBEDDING_VOYAGE_API_KEY") == "EDIT-ME":
        pytest.skip("EMBEDDING_VOYAGE_API_KEY is not set, skipping integration test.")

@pytest.mark.integration
def test_rerank_documents_basic(check_api_key):
    """
    Tests that the rerank_documents function works with a simple query and documents.
    """
    # Arrange
    query = "What is the audience for the pitch session?"
    documents = [
        "The audience consists of pre-seed to Series A VCs, many industry agnostic.",
        "This is about a completely different topic like cooking recipes.",
        "The pitch session audience includes investors with Yale connections.",
        "Random text that is not relevant to the query at all."
    ]
    
    # Act
    try:
        results = rerank_documents(query=query, documents=documents, top_k=3)
        
        # Debug: Print the actual results to understand the structure
        print(f"Rerank results: {results}")
        print(f"Result type: {type(results)}")
        if results:
            print(f"First result: {results[0]}")
            print(f"First result type: {type(results[0])}")
        
        # Assert
        assert isinstance(results, list)
        assert len(results) <= 3  # Should respect top_k
        assert len(results) > 0   # Should have some results
        
        # Check that each result has expected structure
        for result in results:
            assert isinstance(result, dict)
            assert "index" in result
            assert "relevance_score" in result  
            assert "document" in result
            assert isinstance(result["index"], int)
            assert isinstance(result["relevance_score"], (int, float))
            assert isinstance(result["document"], str)
            
    except Exception as e:
        # Print detailed error info for debugging
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        print(f"Error args: {e.args}")
        import traceback
        traceback.print_exc()
        raise 