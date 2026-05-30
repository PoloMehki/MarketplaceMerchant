"""verify_stage0_bedrock.py — manual: send 'reply with OK' to Bedrock, print reply.

Hits the REAL Bedrock service. Run by a human, never in CI. Requires AWS creds
in the environment and these env vars (see .env.example):
    AWS_REGION, BEDROCK_MODEL_ID

Usage:
    python scripts/verify_stage0_bedrock.py
"""
import os
import sys

from dotenv import load_dotenv

from negagent.clients.bedrock_client import BedrockClient


def main() -> int:
    load_dotenv()
    region = os.environ.get("AWS_REGION")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not region or not model_id:
        print("ERROR: set AWS_REGION and BEDROCK_MODEL_ID (see .env.example)")
        return 1

    bc = BedrockClient(model_id=model_id, region=region)
    messages = [{"role": "user", "content": [{"text": "Reply with exactly: OK"}]}]
    reply = bc.complete(messages)
    print(f"model={model_id} region={region}")
    print(f"reply: {reply!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
