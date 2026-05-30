"""box_client.py — Task 7.1: Box archival for negotiation artifacts.

Fire-and-forget: every public method swallows exceptions so a Box outage never
blocks or delays a live negotiation. Archival only — never on the hot path.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

from negagent.models import NegotiationState


class BoxArchiveClient:
    """Uploads per-negotiation artifacts to a Box folder hierarchy."""

    def __init__(
        self,
        root_folder_id: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        jwt_config_path: Optional[Path] = None,
        developer_token: Optional[str] = None,
        sdk: Any = None,
    ) -> None:
        self._root_folder_id = root_folder_id
        if sdk is not None:
            self._sdk = sdk
        elif developer_token is not None:  # pragma: no cover — exercised only against real Box
            from boxsdk import OAuth2, Client as BoxClient
            auth = OAuth2(
                client_id=client_id,
                client_secret=client_secret,
                access_token=developer_token,
            )
            self._sdk = BoxClient(auth)
        elif jwt_config_path is not None:  # pragma: no cover
            from boxsdk import JWTAuth, Client as BoxClient
            auth = JWTAuth.from_settings_file(str(jwt_config_path))
            self._sdk = BoxClient(auth)
        else:  # pragma: no cover
            from boxsdk import OAuth2, Client as BoxClient
            auth = OAuth2(client_id=client_id, client_secret=client_secret)
            self._sdk = BoxClient(auth)

    def archive_negotiation(self, state: NegotiationState) -> bool:
        """Upload the full negotiation transcript JSON to a per-listing subfolder.

        Returns True on success, False on failure (never raises).
        """
        try:
            root = self._sdk.folder(self._root_folder_id)
            folder_name = f"negotiation-{state.listing_id}"
            try:
                folder = root.create_subfolder(folder_name)
            except Exception:
                # folder already exists — find it
                items = root.get_items()
                folder = next(
                    (i for i in items if i.type == "folder" and i.name == folder_name),
                    None,
                )
                if folder is None:
                    raise
            transcript = state.model_dump_json(indent=2).encode()
            folder.upload_stream(
                io.BytesIO(transcript),
                file_name=f"transcript-{state.listing_id}.json",
            )
            return True
        except Exception as exc:
            print(f"  [Box] archive failed: {exc}", flush=True)
            return False

    def archive_file(self, negotiation_id: str, data: bytes, filename: str) -> None:
        """Upload an arbitrary artifact (photo, comp dump, snapshot) fire-and-forget."""
        try:
            folder = self._sdk.folder(self._root_folder_id).create_subfolder(
                f"negotiation-{negotiation_id}"
            )
            folder.upload_stream(io.BytesIO(data), file_name=filename)
        except Exception:
            pass
