import argparse
import json
import sys

from _tinyfish_client import run_sse_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TinyFish automation in streaming SSE mode.")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--goal", required=True, help="Automation goal in natural language")
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Enable stealth browser profile and default US proxy",
    )
    args = parser.parse_args()

    extra_payload = {}
    if args.stealth:
        extra_payload["browser_profile"] = "stealth"
        extra_payload["proxy_config"] = {"enabled": True, "country_code": "US"}

    print("Streaming TinyFish events...")
    for event in run_sse_events(args.url, args.goal, **extra_payload):
        event_type = event.get("type")
        if event_type == "PROGRESS":
            purpose = event.get("purpose", "")
            print(f"[PROGRESS] {purpose}")
        elif event_type == "COMPLETE":
            status = event.get("status", "UNKNOWN")
            print(f"[COMPLETE] status={status}")
            print(json.dumps(event, indent=2, ensure_ascii=True))
            return 0 if status == "COMPLETED" else 2
        else:
            print(json.dumps(event, ensure_ascii=True))

    print("No COMPLETE event was received before stream ended.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
