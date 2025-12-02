"""Constants for LOGO Shutters."""

DOMAIN = "logo_shutters"
PLATFORMS: list[str] = ["cover"]

# Config keys
CONF_OPEN_SWITCH = "open_switch"
CONF_CLOSE_SWITCH = "close_switch"
CONF_MOVING_UP_SENSOR = "moving_up_sensor"
CONF_MOVING_DOWN_SENSOR = "moving_down_sensor"
CONF_OPEN_TIME = "open_time"
CONF_CLOSE_TIME = "close_time"
CONF_STOP_SEQUENCE = "stop_sequence"
CONF_STOP_SEQUENCE_UP = "stop_sequence_up"
CONF_STOP_SEQUENCE_DOWN = "stop_sequence_down"
CONF_INITIAL_POSITION = "initial_position"
CONF_SHADE_POSITION = "shade_position"
CONF_END_OVERRUN = "end_overrun"
