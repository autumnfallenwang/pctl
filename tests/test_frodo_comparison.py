#!/usr/bin/env python3
"""
Comparative test: Run our PAICLogService and Frodo log tail simultaneously
Compare outputs to ensure identical behavior
"""

import asyncio
import sys
import json
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Add pctl to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pctl.services.conn.log_service import PAICLogService
from pctl.services.conn.conn_service import ConnectionService


@dataclass
class LogEntry:
    """Parsed log entry for comparison"""
    timestamp: str
    source: str
    type: str
    level: Optional[str]
    logger: Optional[str]
    message: str
    raw_json: str


class LogComparator:
    """Compare logs from our streamer vs Frodo"""

    def __init__(self):
        self.our_logs: List[LogEntry] = []
        self.frodo_logs: List[LogEntry] = []

    def parse_log_entry(self, log_json: str) -> Optional[LogEntry]:
        """Parse a log JSON line into structured entry"""
        try:
            log_data = json.loads(log_json.strip())

            timestamp = log_data.get('timestamp', '')
            source = log_data.get('source', '')
            log_type = log_data.get('type', '')

            # Extract level, logger, message from payload
            payload = log_data.get('payload', {})
            if isinstance(payload, dict):
                level = payload.get('level', '')
                logger = payload.get('logger', '')
                message = payload.get('message', '')
            else:
                level = ''
                logger = ''
                message = str(payload)[:200]  # Truncate long messages

            return LogEntry(
                timestamp=timestamp,
                source=source,
                type=log_type,
                level=level,
                logger=logger,
                message=message,
                raw_json=log_json.strip()
            )
        except Exception as e:
            print(f"⚠️  Failed to parse log: {e}")
            return None

    def add_our_log(self, log_json: str):
        """Add log from our streamer"""
        entry = self.parse_log_entry(log_json)
        if entry:
            self.our_logs.append(entry)

    def add_frodo_log(self, log_json: str):
        """Add log from Frodo"""
        entry = self.parse_log_entry(log_json)
        if entry:
            self.frodo_logs.append(entry)

    def analyze_differences(self) -> Dict[str, Any]:
        """Analyze differences between the two streams"""
        analysis = {
            "our_count": len(self.our_logs),
            "frodo_count": len(self.frodo_logs),
            "timestamp_overlap": 0,
            "identical_entries": 0,
            "format_differences": [],
            "unique_to_ours": [],
            "unique_to_frodo": [],
            "timing_analysis": {}
        }

        # Find timestamp overlaps (logs that appear in both streams)
        our_timestamps = {log.timestamp for log in self.our_logs}
        frodo_timestamps = {log.timestamp for log in self.frodo_logs}

        common_timestamps = our_timestamps.intersection(frodo_timestamps)
        analysis["timestamp_overlap"] = len(common_timestamps)

        # Compare entries with same timestamps
        for timestamp in common_timestamps:
            our_entries = [log for log in self.our_logs if log.timestamp == timestamp]
            frodo_entries = [log for log in self.frodo_logs if log.timestamp == timestamp]

            for our_log in our_entries:
                for frodo_log in frodo_entries:
                    if (our_log.message == frodo_log.message and
                        our_log.level == frodo_log.level):
                        analysis["identical_entries"] += 1
                    elif our_log.message == frodo_log.message:
                        # Same message, different formatting
                        analysis["format_differences"].append({
                            "timestamp": timestamp,
                            "message": our_log.message[:100],
                            "our_format": {
                                "type": our_log.type,
                                "level": our_log.level,
                                "logger": our_log.logger
                            },
                            "frodo_format": {
                                "type": frodo_log.type,
                                "level": frodo_log.level,
                                "logger": frodo_log.logger
                            }
                        })

        # Find unique entries
        our_messages = {(log.timestamp, log.message) for log in self.our_logs}
        frodo_messages = {(log.timestamp, log.message) for log in self.frodo_logs}

        unique_ours = our_messages - frodo_messages
        unique_frodo = frodo_messages - our_messages

        analysis["unique_to_ours"] = [
            {"timestamp": ts, "message": msg[:100]}
            for ts, msg in list(unique_ours)[:5]  # Show first 5
        ]

        analysis["unique_to_frodo"] = [
            {"timestamp": ts, "message": msg[:100]}
            for ts, msg in list(unique_frodo)[:5]  # Show first 5
        ]

        # Timing analysis
        if self.our_logs and self.frodo_logs:
            our_start = min(log.timestamp for log in self.our_logs)
            our_end = max(log.timestamp for log in self.our_logs)
            frodo_start = min(log.timestamp for log in self.frodo_logs)
            frodo_end = max(log.timestamp for log in self.frodo_logs)

            analysis["timing_analysis"] = {
                "our_timespan": {"start": our_start, "end": our_end},
                "frodo_timespan": {"start": frodo_start, "end": frodo_end},
                "overlap_start": max(our_start, frodo_start),
                "overlap_end": min(our_end, frodo_end)
            }

        return analysis


async def run_our_streamer(profile_name: str, source: str, duration: int, comparator: LogComparator):
    """Run our PAICLogService streamer"""
    print(f"🚀 Starting our streamer (profile: {profile_name}, source: {source})")

    log_service = PAICLogService()
    start_time = time.time()
    count = 0

    try:
        async for log_json in log_service.stream_logs(
            profile_name=profile_name,
            source=source,
            level=2,  # INFO level
            use_default_noise_filter=True
        ):
            comparator.add_our_log(log_json)
            count += 1

            # Stop after duration
            if time.time() - start_time > duration:
                break

    except Exception as e:
        print(f"❌ Our streamer error: {e}")

    print(f"✅ Our streamer completed: {count} logs")


def run_frodo_streamer(profile_name: str, source: str, duration: int, comparator: LogComparator):
    """Run Frodo log tail subprocess"""
    print(f"🔧 Starting Frodo streamer (profile: {profile_name}, source: {source})")

    # Build frodo command
    frodo_cmd = [
        "frodo", "log", "tail",
        "-c", source,
        "-l", "2",  # INFO level
        profile_name
    ]

    print(f"   Command: {' '.join(frodo_cmd)}")

    count = 0
    start_time = time.time()

    try:
        # Start frodo process
        process = subprocess.Popen(
            frodo_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )

        # Read output with timeout
        while time.time() - start_time < duration:
            try:
                # Non-blocking read with timeout
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line and line.startswith('{'):  # Only JSON lines
                        comparator.add_frodo_log(line)
                        count += 1
                elif process.poll() is not None:
                    # Process terminated
                    break
                else:
                    # No output, brief sleep
                    time.sleep(0.1)

            except Exception as e:
                print(f"⚠️  Frodo read error: {e}")
                break

        # Terminate process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    except Exception as e:
        print(f"❌ Frodo streamer error: {e}")

    print(f"✅ Frodo streamer completed: {count} logs")


async def main():
    """Main comparison test"""
    print("🔬 Frodo vs PAICLogService Comparison Test")
    print("=" * 60)

    # Get available profiles
    conn_service = ConnectionService()
    profiles_result = conn_service.list_profiles()

    if not profiles_result["success"] or not profiles_result["profiles"]:
        print("❌ No connection profiles found!")
        return False

    # Find validated profile with log credentials
    test_profile = None
    for profile in profiles_result["profiles"]:
        if (profile.get("validated") and
            profile.get("log_api_key") and
            profile.get("log_api_secret")):
            test_profile = profile["name"]
            break

    if not test_profile:
        print("❌ No validated profiles with log credentials found!")
        return False

    print(f"🎯 Using profile: {test_profile}")

    # Test parameters
    source = "idm-core"
    duration = 45  # seconds

    print(f"📊 Test parameters:")
    print(f"   Source: {source}")
    print(f"   Duration: {duration} seconds")
    print(f"   Level: INFO (2)")
    print(f"   Noise filter: enabled")
    print()

    # Create comparator
    comparator = LogComparator()

    # Start both streamers simultaneously
    print("🚀 Starting both streamers simultaneously...")

    # Run Frodo in separate thread (since it's blocking)
    import threading
    frodo_thread = threading.Thread(
        target=run_frodo_streamer,
        args=(test_profile, source, duration, comparator)
    )

    # Start both at the same time
    frodo_thread.start()
    await run_our_streamer(test_profile, source, duration, comparator)

    # Wait for Frodo to complete
    frodo_thread.join(timeout=duration + 10)

    print("\n📊 Analyzing results...")
    analysis = comparator.analyze_differences()

    # Print analysis
    print("\n" + "=" * 60)
    print("📈 COMPARISON ANALYSIS")
    print("=" * 60)

    print(f"📊 Log Counts:")
    print(f"   Our streamer:   {analysis['our_count']:4d} logs")
    print(f"   Frodo streamer: {analysis['frodo_count']:4d} logs")
    print(f"   Difference:     {abs(analysis['our_count'] - analysis['frodo_count']):4d} logs")

    print(f"\n🔗 Overlap Analysis:")
    print(f"   Common timestamps: {analysis['timestamp_overlap']}")
    print(f"   Identical entries: {analysis['identical_entries']}")

    if analysis['format_differences']:
        print(f"\n⚠️  Format Differences ({len(analysis['format_differences'])}):")
        for diff in analysis['format_differences'][:3]:  # Show first 3
            print(f"   Timestamp: {diff['timestamp']}")
            print(f"   Message: {diff['message']}")
            print(f"   Our:   {diff['our_format']}")
            print(f"   Frodo: {diff['frodo_format']}")
            print()

    if analysis['unique_to_ours']:
        print(f"\n🔵 Unique to Our Streamer ({len(analysis['unique_to_ours'])} shown):")
        for unique in analysis['unique_to_ours']:
            print(f"   [{unique['timestamp']}] {unique['message']}")

    if analysis['unique_to_frodo']:
        print(f"\n🟠 Unique to Frodo ({len(analysis['unique_to_frodo'])} shown):")
        for unique in analysis['unique_to_frodo']:
            print(f"   [{unique['timestamp']}] {unique['message']}")

    # Success criteria
    total_logs = max(analysis['our_count'], analysis['frodo_count'])
    if total_logs == 0:
        print("\n❌ No logs received from either streamer!")
        return False

    overlap_percentage = (analysis['timestamp_overlap'] / total_logs) * 100
    identical_percentage = (analysis['identical_entries'] / total_logs) * 100

    print(f"\n🎯 Compatibility Score:")
    print(f"   Timestamp overlap: {overlap_percentage:.1f}%")
    print(f"   Identical entries: {identical_percentage:.1f}%")

    # Verdict
    if identical_percentage >= 80:
        print(f"\n✅ EXCELLENT: {identical_percentage:.1f}% identical - Ready for production!")
        return True
    elif identical_percentage >= 60:
        print(f"\n⚠️  GOOD: {identical_percentage:.1f}% identical - Minor differences acceptable")
        return True
    else:
        print(f"\n❌ POOR: {identical_percentage:.1f}% identical - Needs investigation")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)