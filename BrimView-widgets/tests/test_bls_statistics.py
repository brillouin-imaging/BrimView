from types import SimpleNamespace

import numpy as np
import panel as pn
import pytest

from brimview_widgets.bls_statistics import BlsStatistics, Data


def test_selected_points_debug_table():
    widget = SimpleNamespace(selected_points=[(1, 2, 3)])
    table = BlsStatistics.selected_points_widget(widget)
    assert isinstance(table, pn.widgets.Tabulator)
    assert table.value.to_dict("records") == [{"z": 1, "y": 2, "x": 3}]


@pytest.mark.parametrize("fails", [False, True])
def test_interpolation_shows_progress_and_clears_it(monkeypatch, fails):
    tqdm = pn.ui.Tqdm()
    widget = SimpleNamespace(tqdm=tqdm)
    spectra = [
        (np.array([1.0, 3.0]), np.array([0.0, 1.0]), "PSD", "Hz"),
        (np.array([3.0, 5.0]), np.array([0.0, 1.0]), "PSD", "Hz"),
    ]

    def interpolate(psds, frequencies):
        assert "Interpolating spectra" in tqdm.text
        assert tqdm.value == 0
        if fails:
            raise RuntimeError("interpolation failed")
        return psds, frequencies[0]

    monkeypatch.setattr(Data, "interpolate_spectra", interpolate)

    if fails:
        with pytest.raises(RuntimeError, match="interpolation failed"):
            BlsStatistics.compute_average_spectrum(widget, spectra)
    else:
        frequency, mean, std, psd_units, frequency_units = (
            BlsStatistics.compute_average_spectrum(widget, spectra)
        )
        np.testing.assert_array_equal(frequency, [0.0, 1.0])
        np.testing.assert_array_equal(mean, [2.0, 4.0])
        np.testing.assert_array_equal(std, [1.0, 1.0])
        assert (psd_units, frequency_units) == ("PSD", "Hz")

    assert tqdm.text == ""
    assert tqdm.value == 0
