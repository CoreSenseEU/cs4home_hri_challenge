# Energy Measurement Status

- Enabled: `true`
- Source: `laptop_battery_total:BAT1`
- Reason/status: enabled

Energy is reported only for `total_measured_processes` because processor RAPL/powercap and battery readings are global measurements, not per-process energy attribution. Per-process CPU/RSS/PSS are still reported separately.
The script prioritizes processor hardware counters from Linux RAPL/powercap `energy_uj` when readable, including AMD processor powercap interfaces if exposed by the kernel. It then checks CPU/processor `hwmon` energy or power sensors and integrates power over time when only instantaneous power is available.
If processor energy is unavailable and the laptop battery is discharging, energy is estimated by integrating `/sys/class/power_supply/BAT*/power_now` or `voltage_now * current_now` over time. This fallback is labelled `laptop_battery_total:*` and represents total laptop battery draw, not CPU/package energy.
