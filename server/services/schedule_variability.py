"""globi's schedule variability: globi's own module once its main has it, else sbem-ui's copy."""

try:
    from globi.models.schedule_variability import (
        ScheduleVariabilityConfig,
        _ar1,
        _clipped_normal,
        perturb_space_use,
        seeded_rng,
        shift_values,
    )
except ModuleNotFoundError:
    from services.vendored_schedule_variability import (
        ScheduleVariabilityConfig,
        _ar1,
        _clipped_normal,
        perturb_space_use,
        seeded_rng,
        shift_values,
    )

__all__ = ["ScheduleVariabilityConfig", "_ar1", "_clipped_normal", "perturb_space_use", "seeded_rng", "shift_values"]
