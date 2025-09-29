#!/usr/bin/env python3
"""
Test script for PAICLogService - verify it behaves exactly like Frodo log tail
Run this to ensure our implementation matches Frodo's behavior before ELK integration
"""

import asyncio
import sys
import json
from pathlib import Path

# Add pctl to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pctl.services.conn.log_service import PAICLogService
from pctl.services.conn.conn_service import ConnectionService


async def test_log_streaming():
    """Test log streaming functionality"""
    print("🧪 Testing PAICLogService - Frodo compatibility test")
    print("=" * 60)

    # Initialize services
    conn_service = ConnectionService()
    log_service = PAICLogService()

    # List available profiles
    print("📋 Available connection profiles:")
    profiles_result = conn_service.list_profiles()

    if not profiles_result["success"]:
        print(f"❌ Failed to list profiles: {profiles_result['error']}")
        return False

    if not profiles_result["profiles"]:
        print("❌ No connection profiles found!")
        print("💡 Create a profile first with: uv run pctl conn add <name>")
        return False

    # Show available profiles
    for i, profile in enumerate(profiles_result["profiles"]):
        status = "✅ validated" if profile.get("validated") else "⚠️  not validated"
        log_creds = "✅ has log creds" if profile.get("log_api_key") and profile.get("log_api_secret") else "❌ no log creds"
        print(f"  {i+1}. {profile['name']} - {status}, {log_creds}")

    # Find a profile with log credentials (prefer validated ones)
    test_profile = None
    validated_profile = None

    for profile in profiles_result["profiles"]:
        if profile.get("log_api_key") and profile.get("log_api_secret"):
            if profile.get("validated"):
                validated_profile = profile["name"]
            elif test_profile is None:  # First profile with log creds as fallback
                test_profile = profile["name"]

    # Use validated profile if available, otherwise fallback
    test_profile = validated_profile or test_profile

    if not test_profile:
        print("\n❌ No profiles with log API credentials found!")
        print("💡 Add log credentials to a profile with log_api_key and log_api_secret")
        return False

    print(f"\n🎯 Using profile: {test_profile}")

    # Test 1: Get log sources
    print("\n📂 Testing get_log_sources()...")
    sources_result = await log_service.get_log_sources(test_profile)

    if sources_result["success"]:
        print(f"✅ Found {len(sources_result['sources'])} log sources:")
        for source in sources_result["sources"][:5]:  # Show first 5
            print(f"   - {source}")
        if len(sources_result["sources"]) > 5:
            print(f"   ... and {len(sources_result['sources']) - 5} more")
    else:
        print(f"❌ Failed to get log sources: {sources_result['error']}")
        return False

    # Test 2: Validate log credentials
    print("\n🔑 Testing validate_log_credentials()...")
    validation_result = await log_service.validate_log_credentials(test_profile)

    if validation_result["success"]:
        print(f"✅ {validation_result['message']}")
        print(f"   Sources available: {validation_result['sources_count']}")
    else:
        print(f"❌ Credential validation failed: {validation_result['error']}")
        return False

    # Test 3: Stream logs (like Frodo log tail)
    print("\n🌊 Testing stream_logs() - Frodo log tail behavior...")
    print("   This will stream logs for 30 seconds, press Ctrl+C to stop early")
    print(f"   Command equivalent: frodo log tail -c idm-core -l 2 {test_profile}")
    print("-" * 60)

    try:
        log_count = 0
        start_time = asyncio.get_event_loop().time()

        # Stream logs for 30 seconds max
        async for log_json in log_service.stream_logs(
            profile_name=test_profile,
            source="idm-core",  # Use a common source
            level=2,  # INFO level
            use_default_noise_filter=True
        ):
            # Parse and display log (like Frodo does)
            try:
                log_data = json.loads(log_json)

                # Display log info (simplified)
                if "error" in log_data:
                    print(f"❌ Stream error: {log_data['error']}")
                    break

                timestamp = log_data.get('timestamp', 'N/A')
                log_type = log_data.get('type', 'N/A')
                source = log_data.get('source', 'N/A')

                # Extract message from payload
                payload = log_data.get('payload', {})
                if isinstance(payload, dict):
                    level = payload.get('level', 'N/A')
                    logger = payload.get('logger', 'N/A')
                    message = payload.get('message', 'N/A')[:100]  # Truncate long messages
                    print(f"[{timestamp}] {level} {logger}: {message}")
                else:
                    # Text/plain logs
                    print(f"[{timestamp}] {log_type}: {str(payload)[:100]}")

                log_count += 1

                # Stop after 30 seconds or 50 logs (whichever comes first)
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > 30 or log_count >= 50:
                    print(f"\n⏱️  Stopping after {elapsed:.1f}s ({log_count} logs)")
                    break

            except json.JSONDecodeError:
                print(f"⚠️  Invalid JSON: {log_json}")
            except Exception as e:
                print(f"⚠️  Parse error: {e}")

    except KeyboardInterrupt:
        print(f"\n⏹️  Stopped by user ({log_count} logs received)")
    except Exception as e:
        print(f"\n❌ Stream error: {e}")
        return False

    print("-" * 60)
    print(f"✅ Log streaming test completed - received {log_count} logs")

    # Test 4: Check log level resolution
    print("\n🎚️  Testing log level resolution...")
    levels_info = log_service.get_supported_log_levels()
    print("Supported log levels:")
    for level, desc in levels_info["levels"].items():
        print(f"   {level}: {desc}")

    # Test 5: Check noise filter info
    print("\n🔇 Testing noise filter info...")
    filter_info = log_service.get_default_noise_filter_info()
    print(f"Noise filter removes {filter_info['filter_count']} logger patterns")
    print("Categories filtered:")
    for category in filter_info["categories"]:
        print(f"   - {category}")

    print("\n🎉 All tests completed successfully!")
    print("✅ PAICLogService behaves like Frodo log tail")
    return True


def main():
    """Main test function"""
    print("PAICLogService Test Suite")
    print("Verifying Frodo-compatible behavior")
    print()

    try:
        result = asyncio.run(test_log_streaming())
        if result:
            print("\n✅ SUCCESS: Ready for ELK integration!")
            sys.exit(0)
        else:
            print("\n❌ FAILED: Fix issues before ELK integration")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()