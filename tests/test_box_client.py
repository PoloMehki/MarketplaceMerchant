"""Task 7.1: test_box_upload_called_with_expected_payload,
test_box_failure_does_not_raise_into_pipeline."""
import json
from unittest.mock import MagicMock, patch

from negagent.clients.box_client import BoxArchiveClient
from negagent.models import NegotiationState, OfferTurn
from datetime import datetime, timezone


def _sample_state() -> NegotiationState:
    return NegotiationState(
        listing_id="fb123",
        status="accepted",
        current_offer=320.0,
        best_price_found=320.0,
        turns=[
            OfferTurn(
                role="buyer", amount=300.0, message="Would you take $300?",
                ts=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            ),
            OfferTurn(
                role="seller", amount=320.0, message="Best I can do is $320.",
                ts=datetime(2026, 5, 30, 10, 5, tzinfo=timezone.utc),
            ),
        ],
    )


def _client_with_mock_sdk():
    sdk = MagicMock()
    folder = MagicMock()
    sdk.folder.return_value.create_subfolder.return_value = folder
    folder.id = "subfolder-id"
    sdk.folder.return_value.upload_stream.return_value = MagicMock()
    folder.upload_stream.return_value = MagicMock()
    return BoxArchiveClient(root_folder_id="root-123", sdk=sdk), sdk, folder


def test_box_upload_called_with_expected_payload():
    """archive_negotiation() creates a subfolder and uploads the transcript JSON."""
    client, sdk, folder = _client_with_mock_sdk()
    state = _sample_state()

    client.archive_negotiation(state)

    # a subfolder named after the listing_id was created
    sdk.folder.return_value.create_subfolder.assert_called_once()
    call_args = sdk.folder.return_value.create_subfolder.call_args
    assert "fb123" in str(call_args)

    # transcript was uploaded
    folder.upload_stream.assert_called()
    upload_call = folder.upload_stream.call_args_list[0]
    filename = upload_call[1].get("file_name") or upload_call[0][1]
    assert "transcript" in filename.lower()


def test_box_failure_does_not_raise_into_pipeline():
    """A Box SDK exception is swallowed; the pipeline is unaffected."""
    sdk = MagicMock()
    sdk.folder.side_effect = Exception("Box is down")
    client = BoxArchiveClient(root_folder_id="root-123", sdk=sdk)

    # must not raise
    client.archive_negotiation(_sample_state())
