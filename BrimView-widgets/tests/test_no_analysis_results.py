"""
Behaviour of BrimView with data groups that have no analysis results: an image is computed
from the PSD, and the spectrum, the statistics, the auto re-fit and the (re-)analysis of the
spectra all have to keep working.
"""

import asyncio

import brimfile as bls
import holoviews as hv
import numpy as np
import panel as pn
import pytest

import brimview_widgets as bw
import brimview_widgets.bls_data_visualizer as visualizer_module
from brimview_widgets.bls_data_visualizer import NO_ANALYSIS_MESSAGE, BlsDataVisualizer
from brimview_widgets.bls_file_input import BlsFileInput
from brimview_widgets.bls_spectrum import BlsSpectrumVisualizer
from brimview_widgets.bls_statistics import BlsStatistics
from brimview_widgets.fit_initial_guess import initial_peak_guess, water_shift_and_width

FREQ = np.linspace(-10, 10, 128)
PIXEL_SIZE_UM = (1.0, 2.0, 3.0)  # z, y, x


def lorentzian(nu, amplitude, center, width):
    return amplitude * (width / 2) ** 2 / ((nu - center) ** 2 + (width / 2) ** 2)


def make_psd(shape, seed=0, base_shift=5.0, width=0.6):
    """Stokes + anti-Stokes peaks (more intense with y and x) on top of an offset and noise"""
    rng = np.random.default_rng(seed)
    z, y, x = np.meshgrid(*(range(n) for n in shape), indexing="ij")
    shift = base_shift + 0.05 * y + 0.03 * x
    amplitude = 400 + 20 * y + 10 * x + 0 * z
    psd = (
        lorentzian(FREQ, amplitude[..., None], shift[..., None], width)
        + lorentzian(FREQ, amplitude[..., None], -shift[..., None], width)
        + 30
    )
    return psd + rng.normal(0, 1.0, psd.shape), shift, amplitude


def create_brim(path, shape=(1, 5, 6), with_analysis=False, seed=0, wavelength_nm=780):
    psd, shift, amplitude = make_psd(shape, seed=seed)
    file = bls.File.create(str(path))
    data = file.create_data_group(psd, FREQ, PIXEL_SIZE_UM, name="Data1")
    if wavelength_nm is not None:
        data.get_metadata().add(
            bls.Metadata.Type.Optics,
            {"Wavelength": bls.Metadata.Item(wavelength_nm, "nm")},
        )
    if with_analysis:

        def peak(sign):
            return dict(
                shift=sign * shift,
                shift_units="GHz",
                width=np.full(shape, 0.6),
                width_units="GHz",
                amplitude=amplitude.astype(float),
                amplitude_units="a.u.",
                offset=np.full(shape, 30.0),
                offset_units="a.u.",
            )

        data.create_analysis_results_group(peak(1), peak(-1), name="Fit1")
    file.close()
    return psd, shift


def create_sparse_brim(path):
    """3 x 4 pixels, of which 2 have no spectrum"""
    pixel_to_spectrum = np.arange(12).reshape(1, 3, 4)
    pixel_to_spectrum[0, 0, 0] = -1
    pixel_to_spectrum[0, 1, 2] = -1
    valid = pixel_to_spectrum >= 0
    pixel_to_spectrum[valid] = np.arange(valid.sum())
    psd, _, _ = make_psd((valid.sum(), 1, 1))
    file = bls.File.create(str(path))
    file.create_data_group_sparse(
        psd[:, 0, 0, :],
        FREQ,
        dict(
            Cartesian_visualisation=pixel_to_spectrum,
            Cartesian_visualisation_pixel=PIXEL_SIZE_UM,
        ),
        name="Sparse",
    )
    file.close()
    return psd[:, 0, 0, :]


@pytest.fixture
def notifications(monkeypatch):
    """The (kind, message) of the toast notifications shown to the user"""
    shown = []

    class Capture:
        def __getattr__(self, kind):
            return lambda message, *args, **kwargs: shown.append((kind, message))

    monkeypatch.setattr(
        type(pn.state), "notifications", property(lambda self: Capture())
    )
    return shown


@pytest.fixture
def app(notifications, monkeypatch):
    """The widgets of the visualizer tab of BrimView, connected as in `src/index.py`"""
    hv.extension("bokeh")
    pn.extension(notifications=True)
    monkeypatch.setattr(visualizer_module, "_defer_param_update", lambda fn: fn())

    class App:
        file_input = BlsFileInput()
        file_input.__panel__()
        visualizer = BlsDataVisualizer(file_input)
        visualizer.__panel__()
        spectrum = BlsSpectrumVisualizer(visualizer, dark_theme=False)
        spectrum.__panel__()
        statistics = BlsStatistics(visualizer)
        statistics.__panel__()
        treatment = bw.BlsDoTreatment(file_input)
        treatment.__panel__()

        @classmethod
        def load(cls, path, mode="r"):
            # same entry point as the app: it resets the previous file first
            cls.file_input.external_file_update(bls.File(str(path), mode=mode))

        @classmethod
        def click(cls, z=0, y=0, x=0):
            """Click on a pixel of the image (the image is in physical units)"""
            cls.visualizer.img_axis_3_slice = z
            cls.visualizer._update_click_param(
                x=x * PIXEL_SIZE_UM[2], y=y * PIXEL_SIZE_UM[1]
            )

        @classmethod
        def image(cls):
            dataset = cls.visualizer.img_dataset
            return dataset.data[dataset.vdims[0].name].values  # (z, y, x)

        @classmethod
        def problems(cls):
            return [n for n in notifications if n[0] in ("warning", "error")]

    return App


def selection_state(visualizer):
    return dict(
        index=visualizer.result_index_dropdown.disabled,
        quantity=visualizer.result_quantity_dropdown.disabled,
        peak=visualizer.result_peak_dropdown.disabled,
        export=visualizer.result_download.disabled,
        message=visualizer._no_analysis_alert.visible,
    )


NO_ANALYSIS_STATE = dict(index=True, quantity=True, peak=True, export=True, message=True)


# ---------------------------------------------------------------------------------------
# Starting values of the fit
# ---------------------------------------------------------------------------------------


def test_initial_guess_one_peak_per_side():
    psd, shift, amplitude = make_psd((1, 1, 1))
    n_peaks, guess = initial_peak_guess(psd[0, 0, 0], FREQ, 5.09, 0.15)
    assert n_peaks == 2
    assert guess["nu00"] == pytest.approx(shift[0, 0, 0], abs=0.2)  # anti-Stokes
    assert guess["nu01"] == pytest.approx(-shift[0, 0, 0], abs=0.2)  # Stokes
    assert guess["a0"] == pytest.approx(amplitude[0, 0, 0], rel=0.15)
    assert guess["gamma0"] == guess["gamma1"] == 0.15  # the linewidth of water
    # the offset of the baseline is shared by the two peaks
    assert guess["b0"] + guess["b1"] == pytest.approx(30, abs=5)


def test_initial_guess_without_water_or_with_one_side():
    psd, shift, _ = make_psd((1, 1, 1))
    n_peaks, guess = initial_peak_guess(psd[0, 0, 0], FREQ)  # no water: whole sides
    assert n_peaks == 2
    assert guess["gamma0"] == pytest.approx(0.6, abs=0.3)  # width at half height

    positive = FREQ > 0
    n_peaks, guess = initial_peak_guess(psd[0, 0, 0][positive], FREQ[positive], 5.09, 0.15)
    assert n_peaks == 1 and guess["nu00"] > 0


def test_initial_guess_peak_outside_the_water_window_is_ignored():
    psd = np.full(FREQ.shape, 10.0) + lorentzian(FREQ, 100, 1.0, 0.5)  # far from 5 GHz
    with pytest.raises(ValueError, match="no peak"):
        initial_peak_guess(psd, FREQ, 5.09, 0.15)
    with pytest.raises(ValueError, match="not enough"):
        initial_peak_guess([1.0, 2.0], [0.0, 1.0])


def test_water_reference_needs_the_wavelength(tmp_path):
    create_brim(tmp_path / "with.brim.zip")
    create_brim(tmp_path / "without.brim.zip", wavelength_nm=None)
    shift, width = water_shift_and_width(bls.File(str(tmp_path / "with.brim.zip")).get_data(0))
    assert shift == pytest.approx(5.09, abs=0.05)  # GHz, at 780 nm
    assert 0.05 < width < 0.5
    with pytest.raises(ValueError, match="wavelength"):
        water_shift_and_width(bls.File(str(tmp_path / "without.brim.zip")).get_data(0))


# ---------------------------------------------------------------------------------------
# Visualizer
# ---------------------------------------------------------------------------------------


def test_image_is_the_maximum_of_the_spectra(app, tmp_path, notifications):
    psd, _ = create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    viz = app.visualizer

    assert notifications == []
    assert viz.bls_analysis is None
    np.testing.assert_allclose(app.image(), psd.max(axis=-1))
    assert (viz.z_px.value, viz.y_px.value, viz.x_px.value) == PIXEL_SIZE_UM
    assert viz._colorbar_label().startswith("Max PSD")

    plot = hv.renderer("bokeh").get_plot(viz._masked_dmap)
    assert "PSD maximum" in plot.state.title.text
    assert plot.subplots[("Image", "I")].handles["colorbar"].title.startswith("Max PSD")

    viz.use_physical_units = False  # the image doesn't change, only the units
    assert (viz.x_px.value, viz.y_px.value) == (1, 1)
    np.testing.assert_allclose(app.image(), psd.max(axis=-1))


def test_result_selection_is_disabled_and_explained(app, tmp_path):
    create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    viz = app.visualizer

    assert selection_state(viz) == NO_ANALYSIS_STATE
    assert "No analysis results present in the file" in NO_ANALYSIS_MESSAGE
    assert viz._no_analysis_alert.object == NO_ANALYSIS_MESSAGE
    assert (viz.result_index, viz.result_quantity, viz.result_peak) == (None, None, None)


def test_switching_between_files_with_and_without_analysis(app, tmp_path, notifications):
    psd, shift = create_brim(tmp_path / "no.brim.zip")
    create_brim(tmp_path / "with.brim.zip", with_analysis=True)
    psd_other = create_brim(tmp_path / "other.brim.zip", shape=(2, 3, 4), seed=3)[0]
    viz = app.visualizer

    app.load(tmp_path / "no.brim.zip")
    assert selection_state(viz) == NO_ANALYSIS_STATE

    app.load(tmp_path / "with.brim.zip")
    assert viz.bls_analysis is not None
    assert viz.img_vunit.label == "Shift"
    assert not viz._no_analysis_alert.visible and not viz.result_download.disabled
    assert not viz.result_quantity_dropdown.disabled
    assert viz.result_index == 0 and viz.result_quantity is not None

    app.load(tmp_path / "no.brim.zip")  # nothing of the previous analysis may stay
    assert viz.bls_analysis is None
    assert selection_state(viz) == NO_ANALYSIS_STATE
    np.testing.assert_allclose(app.image(), psd.max(axis=-1))

    app.load(tmp_path / "other.brim.zip")  # the image is computed again for another file
    np.testing.assert_allclose(app.image(), psd_other.max(axis=-1))
    assert viz.img_axis_3_slice_widget.fixed_end == 1

    app.file_input.bls_file = None  # closing the file hides the message
    assert not viz._no_analysis_alert.visible
    assert notifications == []


def test_sparse_pixels_without_spectrum_are_nan(app, tmp_path, notifications):
    psd = create_sparse_brim(tmp_path / "sparse.brim.zip")
    app.load(tmp_path / "sparse.brim.zip")

    image = app.image()
    assert image.shape == (1, 3, 4)
    assert np.isnan(image[0, 0, 0]) and np.isnan(image[0, 1, 2])
    assert np.isnan(image).sum() == 2
    assert image[0, 0, 1] == pytest.approx(psd[0].max())

    app.click(y=0, x=1)  # a pixel with a spectrum
    assert app.spectrum.bls_spectrum_in_image[0] is not None
    app.click(y=1, x=2)  # a pixel without any
    assert app.spectrum.bls_spectrum_in_image[0] is None
    assert len(app.spectrum.plot_spectrum()) == 1  # no spectrum to draw, but no error
    assert app.problems() == []


# ---------------------------------------------------------------------------------------
# Spectrum
# ---------------------------------------------------------------------------------------


def test_clicking_a_pixel_shows_its_spectrum(app, tmp_path, notifications):
    psd, _ = create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    spectrum = app.spectrum

    app.click(y=1, x=2)
    assert app.visualizer.dataset_zyx_click == (0, 1, 2)
    np.testing.assert_allclose(spectrum.bls_spectrum_in_image[0], psd[0, 1, 2])
    overlay = spectrum.plot_spectrum()
    assert len(overlay) == 1  # the acquired points only: there is no saved fit
    hv.renderer("bokeh").get_plot(overlay)

    # `results_at_point` is {} for every pixel: the plot must still follow the clicks
    changes = []
    spectrum.param.watch(lambda event: changes.append(event), "results_at_point")
    app.click(y=4, x=5)
    assert len(changes) == 1
    np.testing.assert_allclose(spectrum.bls_spectrum_in_image[0], psd[0, 4, 5])

    spectrum.saved_fit._process_switch.value = True  # there is no saved fit to show
    assert len(spectrum.plot_spectrum()) == 1
    assert app.problems() == []


def test_spectrum_controls_follow_the_analysis_availability(app, tmp_path):
    create_brim(tmp_path / "no.brim.zip")
    create_brim(tmp_path / "with.brim.zip", with_analysis=True)
    spectrum = app.spectrum

    app.load(tmp_path / "no.brim.zip")
    assert spectrum._no_analysis_alert.visible
    assert spectrum.saved_fit._process_switch._switch.disabled
    assert spectrum.saved_fit._model_dropdown.disabled
    # the auto re-fit doesn't need analysis results
    assert not spectrum.auto_refit._process_switch._switch.disabled
    assert not spectrum.auto_refit._model_dropdown.disabled
    assert spectrum.auto_refit._process_switch.value is False  # and is off by default

    app.load(tmp_path / "with.brim.zip")
    assert not spectrum._no_analysis_alert.visible
    assert not spectrum.saved_fit._process_switch._switch.disabled


def test_auto_refit_without_analysis(app, tmp_path, notifications):
    _, shift = create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    refit = app.spectrum.auto_refit
    refit._process_switch.value = True

    app.click(y=2, x=3)
    overlay = app.spectrum.plot_spectrum()
    assert len(overlay) == 2  # acquired points + fit
    assert app.problems() == []

    fit = refit.fitted_parameters.set_index(["Peak", "Parameter"])
    assert fit.loc[("0", "nu0"), "Value"] == pytest.approx(shift[0, 2, 3], abs=0.05)
    assert fit.loc[("1", "nu0"), "Value"] == pytest.approx(-shift[0, 2, 3], abs=0.05)
    assert abs(fit.loc[("0", "gamma"), "Value"]) == pytest.approx(0.6, abs=0.1)
    first_start = fit["Starting value"].copy()

    # every pixel gets its own starting values...
    app.click(y=4, x=5)
    app.spectrum.plot_spectrum()
    start = refit.fitted_parameters.set_index(["Peak", "Parameter"])["Starting value"]
    assert not np.allclose(start.values, first_start.values)

    # ...unless the user chose some
    refit._on_constraint_edit(None)
    chosen = start.copy()
    app.click(y=1, x=1)
    app.spectrum.plot_spectrum()
    start = refit.fitted_parameters.set_index(["Peak", "Parameter"])["Starting value"]
    np.testing.assert_allclose(start.values, chosen.values)
    refit._reset_fitted_parameters(None)
    assert not refit.user_edited


def test_auto_refit_without_water_reference_warns_once(app, tmp_path, notifications):
    create_brim(tmp_path / "a.brim.zip", wavelength_nm=None)
    app.load(tmp_path / "a.brim.zip")
    app.spectrum.auto_refit._process_switch.value = True

    for y, x in [(1, 1), (2, 3)]:
        app.click(y=y, x=x)
        assert len(app.spectrum.plot_spectrum()) == 2  # estimated from the spectrum alone
    water_warnings = [n for n in notifications if "water" in n[1]]
    assert len(water_warnings) == 1


def test_csv_export_without_analysis(app, tmp_path, notifications):
    psd, _ = create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    app.click(y=1, x=2)

    with open(app.spectrum.csv_export()) as f:
        rows = [line for line in f.read().splitlines() if not line.startswith("#")]
    assert rows[0] == "Frequency,PSD"
    assert len(rows) - 1 == psd.shape[-1]
    assert app.problems() == []


# ---------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------


def test_statistics_of_a_selection_without_analysis(app, tmp_path, notifications):
    create_brim(tmp_path / "a.brim.zip")
    app.load(tmp_path / "a.brim.zip")
    stats = app.statistics

    lasso = app.visualizer._image_streams[1]
    lasso.event(geometry=np.array([(-1, -1), (10, -1), (10, 6), (-1, 6)]))
    assert len(stats.selected_points) > 0
    assert stats.spectrum_plot_widget.object is not None  # the average spectrum
    assert stats.statistic_tabulator_widget.visible is False  # no quantities to average
    assert notifications == []


# ---------------------------------------------------------------------------------------
# (Re-)analysis of the spectra
# ---------------------------------------------------------------------------------------


def test_analyzing_the_spectra_updates_the_visualizer(app, tmp_path, notifications):
    _, shift = create_brim(tmp_path / "a.brim.zip", shape=(1, 4, 5))
    app.load(tmp_path / "a.brim.zip", mode="a")
    treatment, viz = app.treatment, app.visualizer
    assert not treatment.btn_process_data.disabled
    assert not treatment.mean_spectra_button.disabled

    # (the default number of spectra to use is larger than the number of spectra: 20)
    treatment.compute_mean_spectra(None)
    assert treatment.mean_spectra[0] is not None

    app.click(y=2, x=3)  # a spectrum is displayed while the analysis is done
    assert app.spectrum._no_analysis_alert.visible

    asyncio.run(treatment.process_and_save_treatment())
    assert app.problems() == []
    assert len(app.file_input.data.list_AnalysisResults()) == 1

    assert viz.bls_analysis is not None
    assert selection_state(viz) == dict(
        index=True, quantity=False, peak=viz.result_peak_dropdown.disabled, export=False, message=False
    )
    assert viz.img_vunit.label == "Shift"
    assert np.nanmin(app.image()) > 4.9 and np.nanmax(app.image()) < 5.5
    # the displayed spectrum doesn't keep the state it had without analysis
    assert not app.spectrum._no_analysis_alert.visible
    assert not app.spectrum.saved_fit._process_switch._switch.disabled
    assert len(app.spectrum.plot_spectrum()) >= 2  # now with the saved fit
