"""Cover platform for LOGO shutters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any
from time import monotonic

import yaml

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from homeassistant.components.switch import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CLOSE_SWITCH,
    CONF_INITIAL_POSITION,
    CONF_MOVING_DOWN_SENSOR,
    CONF_MOVING_UP_SENSOR,
    CONF_OPEN_SWITCH,
    CONF_OPEN_TIME,
    CONF_CLOSE_TIME,
    CONF_STOP_SEQUENCE,
    CONF_STOP_SEQUENCE_UP,
    CONF_STOP_SEQUENCE_DOWN,
    CONF_SHADE_POSITION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _clamp_position(value: float) -> int:
    """Clamp a float to a 0-100 int."""
    return max(0, min(100, int(round(value))))


@dataclass
class StopStep:
    """Single step in a stop sequence."""

    domain: str
    service: str
    entity_id: str | None
    service_data: dict[str, Any]
    delay: float


def _parse_stop_sequence(raw: str) -> list[StopStep]:
    """Parse a YAML/JSON stop sequence string."""
    if not raw or not raw.strip():
        return []
    try:
        loaded = yaml.safe_load(raw)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Could not parse stop_sequence; falling back to default")
        return []

    if not isinstance(loaded, list):
        _LOGGER.warning("Stop sequence must be a list of steps")
        return []

    steps: list[StopStep] = []
    for idx, step in enumerate(loaded):
        if not isinstance(step, dict):
            _LOGGER.warning("Stop step %s ignored: not a mapping", idx)
            continue
        service = step.get("service")
        if not service or "." not in service:
            _LOGGER.warning("Stop step %s ignored: invalid service", idx)
            continue
        domain, service_name = service.split(".", 1)
        entity_id = step.get("entity_id")
        delay_val = step.get("delay", 0)
        try:
            delay = float(delay_val)
        except (TypeError, ValueError):
            delay = 0
        service_data = step.get("service_data") or {}
        if not isinstance(service_data, dict):
            _LOGGER.warning("Stop step %s ignored: service_data must be an object", idx)
            service_data = {}
        steps.append(
            StopStep(
                domain=domain,
                service=service_name,
                entity_id=entity_id,
                service_data=service_data,
                delay=delay,
            )
        )
    return steps


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities from config entry."""
    entity = LogoCover(hass, entry)
    async_add_entities([entity], update_before_add=True)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("set_shade", {}, "async_set_shade")


class LogoCover(CoverEntity, RestoreEntity):
    """Representation of a LOGO-driven shutter."""

    _attr_should_poll = False
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_is_closed: bool | None = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the cover entity."""
        self.hass = hass
        self.entry = entry
        data = {**entry.data, **entry.options}

        self._name: str = data[CONF_NAME]
        self._open_switch = data[CONF_OPEN_SWITCH]
        self._close_switch = data[CONF_CLOSE_SWITCH]
        self._moving_up_sensor = data.get(CONF_MOVING_UP_SENSOR) or None
        self._moving_down_sensor = data.get(CONF_MOVING_DOWN_SENSOR) or None
        self._open_time: float = float(data[CONF_OPEN_TIME])
        self._close_time: float = float(data[CONF_CLOSE_TIME])
        self._initial_position: int = _clamp_position(
            float(data.get(CONF_INITIAL_POSITION, 0))
        )
        self._shade_position: int = _clamp_position(
            float(data.get(CONF_SHADE_POSITION, 40))
        )
        common_stop_seq = _parse_stop_sequence(data.get(CONF_STOP_SEQUENCE, ""))
        self._stop_sequence_up: list[StopStep] = _parse_stop_sequence(
            data.get(CONF_STOP_SEQUENCE_UP, "")
        ) or common_stop_seq
        self._stop_sequence_down: list[StopStep] = _parse_stop_sequence(
            data.get(CONF_STOP_SEQUENCE_DOWN, "")
        ) or common_stop_seq

        self._position: int = self._initial_position
        self._is_opening: bool = False
        self._is_closing: bool = False
        self._sensor_up_active: bool = False
        self._sensor_down_active: bool = False
        self._movement_task: asyncio.Task | None = None
        self._movement_start: float | None = None
        self._movement_start_position: float = float(self._position)
        self._movement_target: float | None = None
        self._movement_expected_duration: float | None = None
        self._last_direction_opening: bool | None = None

        self._attr_name = self._name
        self._attr_unique_id = entry.entry_id
        self._attr_assumed_state = self._moving_up_sensor is None and self._moving_down_sensor is None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the cover."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self._name,
            manufacturer="Siemens",
            model="LOGO!",
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self._position

    @property
    def is_opening(self) -> bool | None:
        """Return if the cover is opening."""
        return self._is_opening

    @property
    def is_closing(self) -> bool | None:
        """Return if the cover is closing."""
        return self._is_closing

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is fully closed."""
        return self._position == 0

    async def async_added_to_hass(self) -> None:
        """Restore state and attach listeners."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and (pos := last_state.attributes.get("current_position")) is not None:
            self._position = _clamp_position(pos)

        if self._moving_up_sensor:
            async_track_state_change_event(
                self.hass,
                self._moving_up_sensor,
                self._handle_motion_sensor,
            )
        if self._moving_down_sensor:
            async_track_state_change_event(
                self.hass,
                self._moving_down_sensor,
                self._handle_motion_sensor,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any running tasks."""
        await self._cancel_movement(update_position=False)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover fully."""
        await self.async_set_cover_position(**{ATTR_POSITION: 100})

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover fully."""
        await self.async_set_cover_position(**{ATTR_POSITION: 0})

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        target = kwargs.get(ATTR_POSITION)
        if target is None:
            return
        target = _clamp_position(target)

        if target == self._position:
            await self.async_stop_cover()
            return

        await self._cancel_movement(update_position=True)

        direction_open = target > self._position
        duration = self._open_time if direction_open else self._close_time

        await self._fire_direction_switch(direction_open)
        await self._start_movement(target, duration, direction_open)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        direction = self._active_or_last_direction()
        await self._cancel_movement(update_position=True)
        await self._execute_stop_sequence(direction)
        self._set_motion(False, False)
        self.async_write_ha_state()

    async def async_set_shade(self, **kwargs: Any) -> None:
        """Move cover to the configured shade position."""
        await self.async_set_cover_position(**{ATTR_POSITION: self._shade_position})

    async def _fire_direction_switch(self, opening: bool) -> None:
        """Trigger the configured switch to start movement."""
        entity_id = self._open_switch if opening else self._close_switch
        await self.hass.services.async_call(
            "switch",
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
            context=self._context,
        )

    async def _start_movement(self, target: int, duration: float, opening: bool) -> None:
        """Track movement towards a target position."""
        self._movement_start = monotonic()
        self._movement_start_position = float(self._position)
        self._movement_target = float(target)
        self._movement_expected_duration = duration
        self._last_direction_opening = opening
        self._set_motion(opening, not opening)

        if self._movement_task:
            self._movement_task.cancel()

        self._movement_task = asyncio.create_task(self._run_movement_task())
        self.async_write_ha_state()

    async def _run_movement_task(self) -> None:
        """Update position while moving until target is reached."""
        assert self._movement_target is not None
        assert self._movement_expected_duration is not None

        try:
            while True:
                await asyncio.sleep(0.5)
                new_position = self._interpolated_position()
                self._position = _clamp_position(new_position)
                self.async_write_ha_state()

                if self._movement_start is None:
                    break

                elapsed = monotonic() - self._movement_start
                if elapsed >= self._movement_expected_duration:
                    break
        except asyncio.CancelledError:
            return

        self._position = _clamp_position(self._movement_target)
        if self._sensor_up_active or self._sensor_down_active:
            self._set_motion(self._sensor_up_active, self._sensor_down_active)
        else:
            self._set_motion(False, False)
        self._movement_task = None
        self.async_write_ha_state()

    async def _cancel_movement(self, update_position: bool) -> None:
        """Cancel any in-flight movement."""
        if self._movement_task:
            self._movement_task.cancel()
            self._movement_task = None

        if update_position and self._movement_start is not None:
            self._position = _clamp_position(self._interpolated_position())

        self._movement_start = None
        self._movement_target = None
        self._movement_expected_duration = None
        self._set_motion(False, False)

    async def _execute_stop_sequence(self, opening: bool | None) -> None:
        """Run the configured stop sequence, or a safe default."""
        sequence: list[StopStep] = []
        if opening is True:
            sequence = self._stop_sequence_up
        elif opening is False:
            sequence = self._stop_sequence_down

        if not sequence:
            await self.hass.services.async_call(
                "switch",
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: [self._open_switch, self._close_switch]},
                blocking=True,
                context=self._context,
            )
            return

        for step in sequence:
            data = dict(step.service_data)
            if step.entity_id and ATTR_ENTITY_ID not in data:
                data[ATTR_ENTITY_ID] = step.entity_id
            await self.hass.services.async_call(
                step.domain,
                step.service,
                data,
                blocking=True,
                context=self._context,
            )
            if step.delay > 0:
                await asyncio.sleep(step.delay)

    def _interpolated_position(self) -> float:
        """Calculate position based on elapsed movement time."""
        if (
            self._movement_start is None
            or self._movement_target is None
            or self._movement_expected_duration is None
        ):
            return float(self._position)

        elapsed = monotonic() - self._movement_start
        progress = min(1.0, elapsed / self._movement_expected_duration)
        delta = self._movement_target - self._movement_start_position
        return self._movement_start_position + delta * progress

    @callback
    def _set_motion(self, opening: bool, closing: bool) -> None:
        """Update motion flags."""
        self._is_opening = opening
        self._is_closing = closing

    def _active_or_last_direction(self) -> bool | None:
        """Return the current or last movement direction (True=open, False=close)."""
        if self._sensor_up_active or self._is_opening:
            return True
        if self._sensor_down_active or self._is_closing:
            return False
        return self._last_direction_opening

    async def _handle_motion_sensor(self, event) -> None:
        """Handle updates from movement status sensors."""
        if event.data.get("entity_id") not in {self._moving_up_sensor, self._moving_down_sensor}:
            return

        new_state = event.data.get("new_state")
        is_on = new_state.state == "on" if new_state else False

        entity_id = event.data.get("entity_id")
        opening = entity_id == self._moving_up_sensor

        if opening:
            self._sensor_up_active = is_on
        else:
            self._sensor_down_active = is_on

        # When a motion sensor turns on, start tracking a physical move toward 100%/0%.
        if is_on:
            await self._cancel_movement(update_position=True)
            target = 100 if opening else 0
            duration = self._open_time if opening else self._close_time
            await self._start_movement(target, duration, opening)
        else:
            # Only stop tracking if no motion sensor reports movement.
            if not self._sensor_up_active and not self._sensor_down_active:
                await self._cancel_movement(update_position=True)

        self.async_write_ha_state()
