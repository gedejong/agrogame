from __future__ import annotations

import pytest

from agrogame.config.validation import validate_data


def test_validate_crop_error_reports_path() -> None:
    bad = {
        "crops": {
            "x": {
                "name": "x",
                "thermal_time": {
                    "base_temp_c": -1,  # invalid
                    "emergence_dd": 1,
                    "flowering_dd": 1,
                    "maturity_dd": 1,
                },
                "roots": {
                    "max_depth_cm": 10,
                    "growth_rate_cm_per_day": 1,
                    "distribution": [0.5, 0.5, 0.0],
                },
                "biomass": {
                    "rue_g_per_mj": 1,
                    "harvest_index": 0.5,
                    "partition_vegetative": {"a": 0.5},
                    "partition_reproductive": {"a": 0.5},
                },
            }
        }
    }
    with pytest.raises(Exception) as e:
        validate_data(bad, "crop")
    msg = str(e.value)
    assert "crop validation failed" in msg
    assert "thermal_time/base_temp_c" in msg or "base_temp_c" in msg
