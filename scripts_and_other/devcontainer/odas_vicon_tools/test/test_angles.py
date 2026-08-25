"""Self-check for the SST direction math in capture_sss."""
from odas_vicon_tools.capture_sss import vec_to_azimuth, vec_to_elevation, _wrap180


def test_azimuth():
    assert abs(vec_to_azimuth(1, 0) - 0.0) < 1e-6      # forward
    assert abs(vec_to_azimuth(0, 1) - 90.0) < 1e-6     # left
    assert abs(vec_to_azimuth(0, -1) + 90.0) < 1e-6    # right
    assert abs(abs(vec_to_azimuth(-1, 0)) - 180.0) < 1e-6  # behind


def test_elevation():
    assert abs(vec_to_elevation(1, 0, 0) - 0.0) < 1e-6   # in-plane
    assert abs(vec_to_elevation(0, 0, 1) - 90.0) < 1e-6  # straight up


def test_wrap180():
    assert abs(_wrap180(10 - 350) - 20.0) < 1e-6   # wraps the seam
    assert abs(_wrap180(90) - 90.0) < 1e-6
    assert abs(_wrap180(270) - 90.0) < 1e-6


if __name__ == '__main__':
    test_azimuth()
    test_elevation()
    test_wrap180()
    print("ok")
