"""Optional compiled per-pixel shading; renderer keeps a NumPy fallback."""

from __future__ import annotations

import math
import os
import numpy as np

try:
    if os.environ.get("RAY_DISABLE_NUMBA") == "1":
        raise ImportError("Numba disabled for fallback verification")
    from numba import njit
except ImportError:
    FAST_SHADING = False
    shade_frame = None
else:
    FAST_SHADING = True

    @njit(cache=True)
    def shade_frame(planes, walls, wall_mask, plane_x, plane_y, plane_face,
                    wall_x, wall_y, wall_face, plane_distance, wall_depth,
                    lightmap, ambient, fog, density, map_scale, lighting_on, fog_on):
        """Sample the lightmap and finish RGB in native code, one pixel at a time."""
        height, width = wall_mask.shape
        result = np.empty((height, width, 3), dtype=np.uint8)
        map_h, map_w = lightmap.shape[1], lightmap.shape[2]
        for y in range(height):
            for x in range(width):
                wall = wall_mask[y, x]
                if wall:
                    wx, wy, face = wall_x[x], wall_y[x], wall_face[x]
                    distance = wall_depth[x]
                else:
                    wx, wy, face = plane_x[y, x], plane_y[y, x], plane_face[y, x]
                    distance = plane_distance[y, x]
                if lighting_on:
                    sx = min(max(wx * map_scale - 0.5, 0.0), map_w - 1.001)
                    sy = min(max(wy * map_scale - 0.5, 0.0), map_h - 1.001)
                    x0, y0 = int(sx), int(sy)
                    fx, fy = sx - x0, sy - y0
                if fog_on:
                    amount = 1.0 - math.exp(-min(distance, 200.0) * density)
                for channel in range(3):
                    texture = (walls[y, x, channel] if wall else planes[y, x, channel]) / 255.0
                    if lighting_on:
                        a = lightmap[face, y0, x0, channel] * (1 - fx) + lightmap[face, y0, x0 + 1, channel] * fx
                        b = lightmap[face, y0 + 1, x0, channel] * (1 - fx) + lightmap[face, y0 + 1, x0 + 1, channel] * fx
                        linear = texture * (ambient[channel] + a * (1 - fy) + b * fy)
                        value = 1.0 - math.exp(-linear * 1.35)
                    else:
                        value = texture
                    if fog_on:
                        value = value * (1 - amount) + fog[channel] * amount
                    result[y, x, channel] = min(255, max(0, int(value * 255)))
        return result
