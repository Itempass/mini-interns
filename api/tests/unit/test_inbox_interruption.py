import asyncio
import sys
import os
from unittest.mock import MagicMock, patch
import pytest

# 1. Set up the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# 2. Mock the modules that make network calls on import, BEFORE they are imported by other code.
sys.modules['shared.redis.redis_client'] = MagicMock()
sys.modules['shared.qdrant.qdrant_client'] = MagicMock()
sys.modules['shared.services.embedding_service'] = MagicMock()

# 3. Now that the mocks are in place, we can safely import our module under test.
from api.background_tasks.inbox_initializer import initialize_inbox, BATCH_SIZE
from shared.redis.keys import RedisKeys

@pytest.mark.asyncio
@patch('api.background_tasks.inbox_initializer.get_recent_threads_bulk')
@patch('api.background_tasks.inbox_initializer.upsert_points')
@patch('api.background_tasks.inbox_initializer.get_redis_client')
@patch('api.background_tasks.inbox_initializer.get_embedding', return_value=[0.1]*1024)
@patch('api.background_tasks.inbox_initializer.generate_qdrant_point_id')
async def test_interruption_during_fetch_prevents_upsert(
    mock_generate_point_id,
    mock_get_embedding,
    mock_get_redis_client,
    mock_upsert_points,
    mock_get_threads
):
    """
    Test that interruption during fetch prevents any data from being upserted.
    
    Scenario: User clicks "Re-vectorize" while a long fetch operation is running.
    Expected outcome: No data should be written to the vector database.
    """
    # Arrange
    mock_generate_point_id.side_effect = lambda thread_id: f"point_{thread_id}"
    
    # Create mock threads that would normally be processed
    threads = []
    for i in range(15):  # More than one batch worth
        thread_mock = MagicMock()
        thread_mock.markdown = f"email content {i}"
        thread_mock.thread_id = f"thread_{i}"
        thread_mock.message_count = 1
        thread_mock.subject = "test"
        thread_mock.participants = ["test@test.com"]
        thread_mock.last_message_date = "2024-01-01"
        thread_mock.folders = ["INBOX"]
        threads.append(thread_mock)
    mock_get_threads.return_value = (threads, {})
    
    # Simulate the race condition: flag is set DURING the fetch
    # The exists() method will return False initially (at i=0), 
    # but True later, simulating the flag being set mid-process
    mock_redis = MagicMock()
    mock_redis.delete.return_value = None
    # This simulates: first check passes, but flag gets set before second batch
    mock_redis.exists.side_effect = [False, True, True]  # i=0: False, i=10: True, final: True
    mock_get_redis_client.return_value = mock_redis

    # Act
    await initialize_inbox()

    # Assert: The key outcome - no data should be written if properly handled
    # This test will FAIL with current code because it processes the first batch
    # before checking for interruption at i=10
    mock_upsert_points.assert_not_called()

@pytest.mark.asyncio
@patch('api.background_tasks.inbox_initializer.get_recent_threads_bulk')
@patch('api.background_tasks.inbox_initializer.upsert_points')
@patch('api.background_tasks.inbox_initializer.get_redis_client')
@patch('api.background_tasks.inbox_initializer.get_embedding', return_value=[0.1]*1024)
@patch('api.background_tasks.inbox_initializer.generate_qdrant_point_id')
async def test_interruption_during_processing_loop(
    mock_generate_point_id,
    mock_get_embedding,
    mock_get_redis_client,
    mock_upsert_points,
    mock_get_threads
):
    """
    Tests that if an interruption signal is received during the processing loop,
    the process stops and does not complete all batches.
    """
    # Arrange
    mock_generate_point_id.side_effect = lambda thread_id: f"point_{thread_id}"
    
    num_threads = BATCH_SIZE * 2
    threads = []
    for i in range(num_threads):
        thread_mock = MagicMock()
        thread_mock.markdown = f"email content {i}"
        thread_mock.thread_id = f"thread_{i}"
        thread_mock.message_count = 1
        thread_mock.subject = "test"
        thread_mock.participants = ["test@test.com"]
        thread_mock.last_message_date = "2024-01-01"
        thread_mock.folders = ["INBOX"]
        threads.append(thread_mock)
    mock_get_threads.return_value = (threads, {})

    mock_redis = MagicMock()
    # No interruption after fetch, first check (i=0) passes, second check (i=10) finds the interruption flag.
    mock_redis.exists.side_effect = [False, False, False, True, False] # After fetch, Loop check 1, before upsert 1, Loop check 2, final check
    mock_get_redis_client.return_value = mock_redis

    # Act
    await initialize_inbox()

    # Assert
    # The first batch should have been upserted, but not the second.
    mock_upsert_points.assert_called_once()
    # Verify it was the first batch by checking the content.
    assert len(mock_upsert_points.call_args[1]['points']) == BATCH_SIZE
    assert mock_upsert_points.call_args[1]['points'][0].payload['thread_id'] == 'thread_0'

@pytest.mark.asyncio
@patch('api.background_tasks.inbox_initializer.get_recent_threads_bulk')
@patch('api.background_tasks.inbox_initializer.upsert_points')
@patch('api.background_tasks.inbox_initializer.get_redis_client')
@patch('api.background_tasks.inbox_initializer.get_embedding', return_value=[0.1]*1024)
@patch('api.background_tasks.inbox_initializer.generate_qdrant_point_id')
async def test_no_interruption_happy_path(
    mock_generate_point_id,
    mock_get_embedding,
    mock_get_redis_client,
    mock_upsert_points,
    mock_get_threads
):
    """
    Tests the normal, uninterrupted execution path to ensure it still works.
    """
    # Arrange
    mock_generate_point_id.side_effect = lambda thread_id: f"point_{thread_id}"
    
    num_threads = BATCH_SIZE + 5  # One full batch and one partial
    threads = []
    for i in range(num_threads):
        thread_mock = MagicMock()
        thread_mock.markdown = f"email content {i}"
        thread_mock.thread_id = f"thread_{i}"
        thread_mock.message_count = 1
        thread_mock.subject = "test"
        thread_mock.participants = ["test@test.com"]
        thread_mock.last_message_date = "2024-01-01"
        thread_mock.folders = ["INBOX"]
        threads.append(thread_mock)
    mock_get_threads.return_value = (threads, {})

    mock_redis = MagicMock()
    # No interruption signal exists.
    mock_redis.exists.return_value = False
    mock_get_redis_client.return_value = mock_redis

    # Act
    await initialize_inbox()

    # Assert
    # Two upserts should happen: one for the full batch, one for the remainder.
    assert mock_upsert_points.call_count == 2
    # Check the first batch
    assert len(mock_upsert_points.call_args_list[0][1]['points']) == BATCH_SIZE
    # Check the second (partial) batch
    assert len(mock_upsert_points.call_args_list[1][1]['points']) == 5 

@pytest.mark.asyncio
@patch('api.background_tasks.inbox_initializer.get_recent_threads_bulk')
@patch('api.background_tasks.inbox_initializer.upsert_points')
@patch('api.background_tasks.inbox_initializer.get_redis_client')
@patch('api.background_tasks.inbox_initializer.get_embedding', return_value=[0.1]*1024)
@patch('api.background_tasks.inbox_initializer.generate_qdrant_point_id')
async def test_interruption_during_vector_upload(
    mock_generate_point_id,
    mock_get_embedding,
    mock_get_redis_client,
    mock_upsert_points,
    mock_get_threads
):
    """
    Test that interruption during vector upload (upsert_points) is not handled.
    
    Scenario: User clicks "Re-vectorize" while upsert_points is executing.
    Current behavior: Process continues and uploads more batches.
    Expected behavior: Process should stop after current upload completes.
    """
    # Arrange
    mock_generate_point_id.side_effect = lambda thread_id: f"point_{thread_id}"
    
    # Create enough threads for multiple batches
    threads = []
    for i in range(25):  # 3 batches (10, 10, 5)
        thread_mock = MagicMock()
        thread_mock.markdown = f"email content {i}"
        thread_mock.thread_id = f"thread_{i}"
        thread_mock.message_count = 1
        thread_mock.subject = "test"
        thread_mock.participants = ["test@test.com"]
        thread_mock.last_message_date = "2024-01-01"
        thread_mock.folders = ["INBOX"]
        threads.append(thread_mock)
    mock_get_threads.return_value = (threads, {})

    mock_redis = MagicMock()
    # Simulate interruption flag being set during the first upsert operation
    def mock_upsert_side_effect(*args, **kwargs):
        # Set the flag after first upsert call to simulate user clicking during upload
        mock_redis.exists.return_value = True
        
    mock_upsert_points.side_effect = mock_upsert_side_effect
    
    # Initially no interruption, then flag gets set during upsert
    mock_redis.exists.side_effect = [False, False, False, True, True]  # After fetch, i=0 check, during upsert, i=10 check, final check
    mock_get_redis_client.return_value = mock_redis

    # Act
    await initialize_inbox()

    # Assert
    # With current code, this will fail because process continues after interruption during upload
    # Process should stop after first batch, but currently it continues to second batch
    assert mock_upsert_points.call_count == 1, f"Expected 1 upsert call (should stop after interruption), but got {mock_upsert_points.call_count}" 

@pytest.mark.asyncio
@patch('api.background_tasks.inbox_initializer.get_recent_threads_bulk')
@patch('api.background_tasks.inbox_initializer.upsert_points')
@patch('api.background_tasks.inbox_initializer.get_redis_client')
@patch('api.background_tasks.inbox_initializer.get_embedding', return_value=[0.1]*1024)
@patch('api.background_tasks.inbox_initializer.generate_qdrant_point_id')
async def test_interruption_before_vector_upload(
    mock_generate_point_id,
    mock_get_embedding,
    mock_get_redis_client,
    mock_upsert_points,
    mock_get_threads
):
    """
    Test that interruption is checked BEFORE starting vector upload.
    
    Scenario: User clicks "Re-vectorize" just before upsert_points is called.
    Expected behavior: Process should stop without calling upsert_points.
    """
    # Arrange
    mock_generate_point_id.side_effect = lambda thread_id: f"point_{thread_id}"
    
    # Create exactly one batch worth of threads
    threads = []
    for i in range(10):
        thread_mock = MagicMock()
        thread_mock.markdown = f"email content {i}"
        thread_mock.thread_id = f"thread_{i}"
        thread_mock.message_count = 1
        thread_mock.subject = "test"
        thread_mock.participants = ["test@test.com"]
        thread_mock.last_message_date = "2024-01-01"
        thread_mock.folders = ["INBOX"]
        threads.append(thread_mock)
    mock_get_threads.return_value = (threads, {})

    mock_redis = MagicMock()
    # No interruption after fetch, first check (i=0) passes, but interruption is detected before first upsert
    mock_redis.exists.side_effect = [False, False, True]  # After fetch, i=0 check passes, before upsert check finds interruption
    mock_get_redis_client.return_value = mock_redis

    # Act
    await initialize_inbox()

    # Assert
    # No upserts should happen since interruption is detected before the first upload
    mock_upsert_points.assert_not_called() 