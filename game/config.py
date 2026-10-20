"""User-facing rendering, movement and lighting settings."""

WINDOW_SIZE = (1280, 800)
RENDER_SIZE = (320, 200)
FOV_DEG = 70.0
TARGET_FPS = 60

WALK_SPEED = 2.9
RUN_MULTIPLIER = 1.65
TURN_SPEED = 2.1
PLAYER_RADIUS = 0.23
MOUSE_SENSITIVITY_X = 0.0025
MOUSE_SENSITIVITY_Y = 0.55  # internal pixels per mouse pixel
INVERT_MOUSE_Y = False
ENABLE_VERTICAL_LOOK = False
MAX_PITCH = 0.25  # fraction of internal height

LIGHTING_QUALITY = "medium"  # low / medium / high; F4 cycles at runtime
QUALITY_LEVELS = {"low": (2, 3), "medium": (4, 2), "high": (6, 1)}
FALLOFF_CURVE = "smooth"  # smooth / inverse
FLASHLIGHT_LAG = 0.14  # seconds; 0 follows immediately
