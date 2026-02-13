import argparse
import json
import sys

from _tinyfish_client import run_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TinyFish automation in synchronous mode.")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--goal", required=True, help="Automation goal in natural language")
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Enable stealth browser profile and default US proxy",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print compact JSON only",
    )
    args = parser.parse_args()

    extra_payload = {}
    if args.stealth:
        extra_payload["browser_profile"] = "stealth"
        extra_payload["proxy_config"] = {"enabled": True, "country_code": "US"}

    result = run_sync(args.url, args.goal, **extra_payload)

    if args.json_only:
        print(json.dumps(result, ensure_ascii=True))
        return 0

    print("TinyFish sync run finished.")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
