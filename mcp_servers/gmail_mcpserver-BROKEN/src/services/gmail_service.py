"""
Service for interacting with the Gmail API using HTTPx.

This service abstracts away the direct REST calls to the Gmail API,
handling authentication, request construction, and response parsing.
It uses an async httpx.AsyncClient for all communications.
"""

import httpx
import base64
import json
import email
from typing import List, Dict, Any, Optional
from uuid import uuid4

class GmailService:
    """A service for making direct API calls to Gmail."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self.http_client = http_client if http_client else httpx.AsyncClient()
        self.base_url = "https://www.googleapis.com/gmail/v1/users/me"
        self.batch_url = "https://www.googleapis.com/batch/gmail/v1"

    async def _get_auth_headers(self, access_token: str) -> Dict[str, str]:
        """Constructs the authorization headers."""
        return {"Authorization": f"Bearer {access_token}"}

    async def list_messages(self, access_token: str, max_results: int = 10, query: str = 'in:inbox -in:draft') -> List[Dict[str, Any]]:
        """Lists messages in the user's inbox."""
        headers = await self._get_auth_headers(access_token)
        params = {"maxResults": max_results, "q": query}
        response = await self.http_client.get(f"{self.base_url}/messages", headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('messages', [])

    async def get_message(self, access_token: str, message_id: str, format: str = 'full') -> Dict[str, Any]:
        """Gets a single message by its ID."""
        headers = await self._get_auth_headers(access_token)
        response = await self.http_client.get(f"{self.base_url}/messages/{message_id}", headers=headers, params={"format": format})
        response.raise_for_status()
        return response.json()

    async def get_thread(self, access_token: str, thread_id: str) -> Dict[str, Any]:
        """Gets a full thread by its ID."""
        headers = await self._get_auth_headers(access_token)
        response = await self.http_client.get(f"{self.base_url}/threads/{thread_id}", headers=headers, params={"format": "full"})
        response.raise_for_status()
        return response.json()

    async def create_draft(self, access_token: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new draft email."""
        headers = await self._get_auth_headers(access_token)
        headers["Content-Type"] = "application/json"
        response = await self.http_client.post(f"{self.base_url}/drafts", headers=headers, json={"message": message_data})
        response.raise_for_status()
        return response.json()

    async def batch_get_threads(self, access_token: str, thread_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetches multiple threads in a single batch request."""
        if not thread_ids:
            return []

        boundary = f"batch_{uuid4()}"
        multipart_body = []
        for thread_id in thread_ids:
            multipart_body.append(f"--{boundary}")
            multipart_body.append("Content-Type: application/http")
            multipart_body.append("")
            multipart_body.append(f"GET /gmail/v1/users/me/threads/{thread_id}?format=full")
            multipart_body.append("")
        
        multipart_body.append(f"--{boundary}--")
        request_body = "\r\n".join(multipart_body)

        headers = await self._get_auth_headers(access_token)
        headers["Content-Type"] = f"multipart/mixed; boundary={boundary}"

        response = await self.http_client.post(
            self.batch_url,
            headers=headers,
            content=request_body,
            timeout=60.0
        )
        response.raise_for_status()

        # Parse the multipart response
        response_content_type = response.headers['content-type']
        full_response_bytes = f"Content-Type: {response_content_type}\\r\\n\\r\\n".encode('ascii') + response.content
        msg = email.message_from_bytes(full_response_bytes)
        
        threads_data = []
        if msg.is_multipart():
            for part in msg.get_payload():
                http_response_bytes = part.get_payload(decode=True)
                try:
                    header_bytes, _, body_bytes = http_response_bytes.partition(b'\\r\\n\\r\\n')
                    header_part = header_bytes.decode('ascii', errors='ignore')
                    
                    if "200 OK" in header_part:
                        body_part = body_bytes.decode('utf-8')
                        thread_details = json.loads(body_part)
                        if "error" not in thread_details:
                            threads_data.append(thread_details)
                except Exception:
                    # Log or handle parsing errors if necessary
                    continue
        
        return threads_data 