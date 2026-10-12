import sys
import pytest
from tabletspeed.single_instance import SingleInstance

@pytest.mark.skipif(sys.platform!="win32",reason="Windows named mutex/event")
def test_second_instance_requests_activation_and_releases():
    name=f"Local\\TabletSpeed.Test.{__import__('time').time_ns()}"
    first=SingleInstance(name); second=SingleInstance(name)
    try:
        assert first.acquire() is True
        assert first.consume_activation() is False
        assert second.acquire() is False
        assert first.consume_activation() is True
        assert first.consume_activation() is False
    finally:
        first.close(); second.close()
    third=SingleInstance(name)
    try: assert third.acquire() is True
    finally: third.close()
