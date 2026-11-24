"""
Starting values for fitting a spectrum when the file has no analysis results.

When analysis results exist, the "Auto re-fit" starts from the saved fit of the pixel.
Without them, the starting values are estimated from the spectrum itself and from the
Brillouin shift and linewidth of water (the same reference as the elastic and viscous
contrast of brimfile).
"""

from __future__ import annotations

import numpy as np
from brimfile.file_abstraction import sync
from brimfile.physics import Brillouin_shift_water, Brillouin_width_water

# The peak of each side (Stokes / anti-Stokes) is searched around the shift of water:
# in the window [WINDOW_LOW, WINDOW_HIGH] x shift of water
WINDOW_LOW = 0.5
WINDOW_HIGH = 2.0

# A side only has a peak if its maximum is at least this fraction of the highest point of
# the spectrum (above the baseline): otherwise it is just noise or the tail of another peak
MIN_RELATIVE_AMPLITUDE = 0.1

# Values used by brimfile when computing the contrast and the metadata are missing
DEFAULT_TEMPERATURE_C = 22
DEFAULT_SCATTERING_ANGLE_DEG = 180


def water_shift_and_width(data) -> tuple[float, float]:
    """
    Brillouin shift and linewidth of water (both in GHz, positive) for the acquisition
    parameters stored in the metadata of `data` (a `brimfile.Data`).

    The wavelength is required; if the temperature or the scattering angle are missing
    the same default values as brimfile (22 °C, 180°) are used.

    Raises
    ------
    ValueError
        if the wavelength cannot be retrieved from the metadata.
    """
    # TODO: brimfile only exposes these through private methods of `Metadata` (used for
    # the elastic/viscous contrast); ask for a public accessor and use it here.
    metadata = data.get_metadata()
    try:
        wavelength_nm = sync(metadata._get_wavelength_nm_async())
    except Exception as e:
        raise ValueError(
            f"the wavelength is not available in the metadata ({e})"
        ) from e
    try:
        temperature_c = sync(metadata._get_temperature_c_async())
    except Exception:
        temperature_c = DEFAULT_TEMPERATURE_C
    try:
        scattering_angle_deg = sync(metadata._get_scattering_angle_deg_async())
    except Exception:
        scattering_angle_deg = DEFAULT_SCATTERING_ANGLE_DEG
    return (
        abs(Brillouin_shift_water(wavelength_nm, temperature_c, scattering_angle_deg)),
        abs(Brillouin_width_water(wavelength_nm, temperature_c, scattering_angle_deg)),
    )


def _fwhm_around(frequency: np.ndarray, PSD: np.ndarray, i_max: int, half_level: float) -> float:
    """Full width at `half_level` of the peak at index `i_max` (frequency sorted ascending)."""
    left = i_max
    while left > 0 and PSD[left - 1] >= half_level:
        left -= 1
    right = i_max
    while right < len(PSD) - 1 and PSD[right + 1] >= half_level:
        right += 1
    width = frequency[right] - frequency[left]
    if width <= 0:  # a single point above the half level: use the sampling step
        width = np.median(np.diff(frequency))
    return float(width)


def initial_peak_guess(
    PSD,
    frequency,
    water_shift: float | None = None,
    water_width: float | None = None,
) -> tuple[int, dict[str, float]]:
    """
    Starting values to fit one spectrum with one peak per side (anti-Stokes: positive
    frequencies, Stokes: negative frequencies) of the spectrum where a peak is found.

    For each side, the peak is searched in a window around the shift of water (a side
    without a clear maximum there has no peak). Its position
    and amplitude are those of the maximum of the spectrum in this window, and its linewidth
    that of water. The offset is the baseline level (10th percentile) of the spectrum, shared between
    the peaks (the model has one offset per peak, which add up).
    Without the shift of water the whole side of the spectrum is searched, and without its
    linewidth the width at half height of the maximum is used.

    Parameters
    ----------
    PSD, frequency : array-like
        The spectrum (1D) and its frequency axis (GHz).
    water_shift, water_width : float, optional
        Shift and linewidth of water (GHz, positive), see `water_shift_and_width`.

    Returns
    -------
    (n_peaks, guess)
        `guess` is named as expected by `MultiPeakModel`: `b0, a0, nu00, gamma0, b1, ...`
        (offset, amplitude, position, linewidth of each peak).

    Raises
    ------
    ValueError
        if no peak can be found.
    """
    PSD = np.asarray(PSD, dtype=float).ravel()
    frequency = np.asarray(frequency, dtype=float).ravel()
    valid = np.isfinite(PSD) & np.isfinite(frequency)
    PSD, frequency = PSD[valid], frequency[valid]
    if PSD.size < 5:
        raise ValueError("not enough points in the spectrum to estimate a peak")
    order = np.argsort(frequency)
    PSD, frequency = PSD[order], frequency[order]

    offset = float(np.percentile(PSD, 10))
    min_amplitude = MIN_RELATIVE_AMPLITUDE * (float(PSD.max()) - offset)

    peaks = []
    for sign in (1, -1):  # anti-Stokes first, as for the saved analysis results
        side = sign * frequency > 0
        window = side
        if water_shift:
            window = side & (sign * frequency >= WINDOW_LOW * water_shift) & (
                sign * frequency <= WINDOW_HIGH * water_shift
            )
        if window.sum() < 3:
            continue
        indices = np.flatnonzero(window)
        i_max = int(indices[np.argmax(PSD[indices])])
        amplitude = float(PSD[i_max] - offset)
        if amplitude <= 0 or amplitude < min_amplitude:
            continue
        width = water_width or _fwhm_around(
            frequency, PSD, i_max, offset + amplitude / 2
        )
        peaks.append((offset, amplitude, float(frequency[i_max]), float(width)))

    if not peaks:
        raise ValueError("no peak found in the spectrum")

    guess = {}
    for i, (b, a, nu0, gamma) in enumerate(peaks):
        # Each peak has its own offset in the multi-peak model: they add up to the baseline
        guess[f"b{i}"] = b / len(peaks)
        guess[f"a{i}"] = a
        guess[f"nu0{i}"] = nu0
        guess[f"gamma{i}"] = gamma
    return len(peaks), guess
