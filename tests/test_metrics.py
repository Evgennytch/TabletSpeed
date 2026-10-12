import math
import pytest
from tabletspeed.metrics import Metrics, physical_size, convert_distance, screen_to_physical

def test_physical_size_diagonal_and_aspect_ratio():
    w,h=physical_size(10,16/9)
    assert w == pytest.approx(8.715755371245493)
    assert math.hypot(w,h) == pytest.approx(10)

@pytest.mark.parametrize("d,r",[(0,1),(-1,1),(10,0),(float("nan"),2)])
def test_invalid_area(d,r):
    with pytest.raises(ValueError): physical_size(d,r)

def test_speed_and_path():
    m=Metrics(smoothing=1)
    m.add(0,0,1); x=m.add(3,4,2)
    assert x.current_speed == pytest.approx(5)
    assert x.map_distance == pytest.approx(5)
    assert x.max_session_speed == pytest.approx(5)
    m.add(6,8,3)
    assert m.measurement.session_distance == pytest.approx(10)

def test_distance_units(): assert convert_distance(1,"cm","mm") == 10

def test_resets_and_jumps():
    m=Metrics(max_jump=50); m.add(0,0,1); m.add(1000,0,2)
    assert m.measurement.map_distance == 0
    m.add(1001,0,3); assert m.measurement.map_distance == 1
    m.reset_map(); assert m.measurement.map_distance == 0
    assert m.measurement.session_distance == 1
    m.reset_session(); assert m.measurement.session_distance == 0
    assert m.measurement.max_session_speed == 0

def test_zero_time_and_noise_filter():
    m=Metrics(noise_threshold=2,smoothing=1); m.add(0,0,1); m.add(1,0,1); assert m.measurement.map_distance == 0
    m.add(4,0,2); assert m.measurement.map_distance == 3


def test_screen_to_physical_calibration():
    assert screen_to_physical(960,540,1920,1080,20,11.25)==pytest.approx((10,5.625))
    with pytest.raises(ValueError): screen_to_physical(0,0,0,1080,20,10)


def test_speed_smoothing_and_negative_interval():
    m=Metrics(smoothing=.5); m.add(0,0,2); first=m.add(10,0,3); assert first.current_speed==pytest.approx(5)
    second=m.add(10,0,4); assert second.current_speed==pytest.approx(2.5)
    before=m.measurement.map_distance; m.add(30,0,3.5); assert m.measurement.map_distance==before


def test_reset_all_clears_every_statistic():
    m=Metrics(smoothing=1); m.add(0,0,1); m.add(5,0,2); m.reset_all()
    assert m.measurement.map_distance==0 and m.measurement.session_distance==0
    assert m.measurement.max_speed==0 and m.measurement.max_session_speed==0
    assert m.measurement.current_speed==0 and m.measurement.average_speed==0
