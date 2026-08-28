from pathlib import Path

p = Path("custom_components/roommind/coordinator.py")
text = p.read_text()
old = '''        # Apply mold prevention only while RoomMind owns thermal control.
        # An explicit manual OFF/FAN_ONLY/DRY command is authoritative and must
        # never be silently replaced by autonomous heating. The mold risk level
        # remains visible, but prevention is reported active only when applied.
        manual_aux_or_off = requested_hvac_mode in ("off", "dry", "fan_only")
        force_off = targets.heat is None and targets.cool is None or manual_aux_or_off
        mold_prevention_effective = bool(
            mold_prevention_active_room and mold_prevention_temp_delta > 0 and not manual_aux_or_off
        )
        if mold_prevention_effective and targets.heat is not None:
            targets = TargetTemps(
                heat=targets.heat + mold_prevention_temp_delta,
                cool=targets.cool,
            )
        mold_prevention_active_room = mold_prevention_effective
'''
new = '''        # Mold prevention may override autonomous schedule/presence OFF, but
        # never an explicit manual OFF/FAN_ONLY/DRY selection on the canonical
        # climate entity. Manual intent is authoritative; mold risk remains
        # visible while prevention is reported active only when actually applied.
        manual_aux_or_off = requested_hvac_mode in ("off", "dry", "fan_only")
        force_off = targets.heat is None and targets.cool is None or manual_aux_or_off
        mold_prevention_effective = bool(
            mold_prevention_active_room and mold_prevention_temp_delta > 0 and not manual_aux_or_off
        )
        if mold_prevention_effective:
            if targets.heat is None:
                eco_heat = room.get("eco_heat", room.get("eco_temp", DEFAULT_ECO_HEAT))
                eco_cool = room.get("eco_cool", DEFAULT_ECO_COOL)
                targets = TargetTemps(
                    heat=eco_heat + mold_prevention_temp_delta,
                    cool=eco_cool,
                )
                force_off = False
            else:
                targets = TargetTemps(
                    heat=targets.heat + mold_prevention_temp_delta,
                    cool=targets.cool,
                )
        mold_prevention_active_room = mold_prevention_effective
'''
if old not in text:
    raise RuntimeError("staged mold prevention block not found")
p.write_text(text.replace(old, new, 1))
