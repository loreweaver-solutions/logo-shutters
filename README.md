# LOGO Shutters (Home Assistant)

Custom cover platform for Siemens LOGO! based shutter/covers driven by self-holding relays. Each config entry represents one cover and uses existing Home Assistant entities (e.g., Modbus switches/binary_sensors) for control and feedback.

## Features
- Per-cover config (add one integration entry per cover)
- Use existing switch entities for **up** and **down**
- Optional binary sensors for **moving up/down** feedback; when provided, manual/physical moves are tracked as motion starts/stops
- Time-based position tracking with configurable open/close durations
- Optional initial position restore value
- Configurable stop sequence (YAML list of HA service calls)
- Fully HACS compatible

## Install (HACS)
1) Add this repository as a custom repository in HACS (category: integration).
2) Install **LOGO Shutters**.
3) Restart Home Assistant.
4) Add the integration via **Settings → Devices & Services → Add Integration → LOGO Shutters**.

## Stop sequence format
Provide a YAML/JSON list where each step defines a `service`, optional `entity_id`, optional `service_data`, and optional `delay` between steps. Example:

```yaml
- service: switch.turn_off
  entity_id: switch.logo_up
- service: switch.turn_off
  entity_id: switch.logo_down
- service: switch.turn_on
  entity_id: switch.logo_stop
  delay: 0.2
```

If no stop sequence is provided, both direction switches are turned off.

## Notes
- Position is estimated from timing; add limit sensors if you need exact positioning.
- On restart, the cover restores the last known position if available; otherwise it uses the configured initial position.
