"""Mappings and constants for the water module.

Includes a texture-to-curve-number lookup used to derive SCS CN values
from the top-layer texture.
"""

TEXTURE_TO_CN = {
    "sand": 77,
    "sandy_loam": 79,
    "loam": 86,
    "clay_loam": 89,
    "clay": 91,
    "peat": 85,
}
