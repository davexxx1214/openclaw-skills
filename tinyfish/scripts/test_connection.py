import json
import sys

from _tinyfish_client import run_sync


def main() -> int:
    """
    Lightweight connectivity test:
    - Verifies API key loading from skills/tinyfish/.env
    - Verifies TinyFish /run endpoint is reachable and returns a valid response
    """
    test_url = "https://example.com"
    test_goal = "Extract the page title and return it as JSON."

    print("Running TinyFish connectivity test...")
    result = run_sync(test_url, test_goal)

    status = str(result.get("status", "")).upper()
    if status == "COMPLETED":
        print("Connectivity test passed. TinyFish API returned COMPLETED.")
    else:
        print(f"Connectivity test returned status={status or 'UNKNOWN'}.")

    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if status == "COMPLETED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI fallback
        print(f"Connectivity test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
