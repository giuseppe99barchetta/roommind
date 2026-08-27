# Native hybrid heating

RoomMind can be the single room-level climate controller for installations that combine radiator TRVs, one heat pump/AC per room, and a central boiler.

Enable **Smart source selection** in a room, then enable **Heat pump / Hybrid / Boiler**. RoomMind keeps MPC, schedules, presence, window pause and compressor protection responsible for how much heat a room needs; the native source selector only determines which configured devices may satisfy it.

Configure the global **Heating system** section before enabling a central boiler. Select its climate or switch entity, at least one bypass TRV, and the pre-open/post-stop delays. Boiler operation is fail-closed: the boiler starts only after RoomMind has opened an available bypass; losing every usable bypass while active immediately turns the boiler off. Never configure a bypass that cannot provide a real open hydraulic path.

The same section optionally enables the house electrical budget. Select either an available-power or a consumption sensor, a contract limit and a reserve. Enter each room heat pump's estimated watts. Reservations are made by the single coordinator task, so simultaneous room decisions cannot oversubscribe a single sensor reading. Existing running heat pumps are already reserved and are never charged twice.

Each room now exposes the canonical `climate.roommind_<area>` entity. It owns the logical HVAC mode and separate heating/cooling targets; it never reads a physical TRV frost target as a room cooling target. Expose this entity, and only this entity, to HomeKit. Physical TRVs, ACs and the boiler remain implementation details.

`climate.roommind_<area>_override` remains as a disabled-by-default compatibility entity for existing automations. Do not expose it to HomeKit and migrate automations to the canonical entity. The canonical entity exposes only modes its configured hardware can provide: TRV-only rooms expose heat; AC-only modes (cool, dry, fan-only, fan/swing controls) are routed only to the AC. Heat/cool continues to use MPC and the source planner on heating demand.

Diagnostics include `sensor.roommind_<area>_heat_source`, its reason sensor, `sensor.roommind_boiler_demand`, available/reserved power, and boiler/hydraulic binary sensors.

## Migration

1. Upgrade RoomMind and configure one room completely; do not remove existing Home Assistant automations or helpers yet.
2. Add the external room sensor, AC and every TRV (multiple TRVs are supported) to that RoomMind room. Set its estimated heat-pump watts.
3. Configure and test the global bypass while the boiler is off. Confirm the bypass physically opens and the hydraulic-path diagnostic becomes on.
4. Configure the boiler and power budget; test heat-pump, hybrid and boiler operation while observing diagnostics and service history.
5. Replace each Climate Group Helper in dashboards, HomeKit and automations with `climate.roommind_<area>`. Verify off → cool, cool → off, heat → cool, dry and fan-only transitions. In particular, verify that a TRV frost target does not alter the remembered cooling target.
6. Verify windows, schedules, presence and compressor protection through the canonical climate, then disable the old RoomMind `_override` entity if no legacy automation needs it.
7. Only after several verified heating cycles, disable the old HA automations, Climate Group Helper and their input helpers. Keep a backup of their YAML.
