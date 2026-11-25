import holoviews as hv
import numpy as np
import panel as pn
import pytest
import xarray as xr

import brimview_widgets.bls_data_visualizer as visualizer_module
from brimview_widgets.bls_data_visualizer import BlsDataVisualizer
from brimview_widgets.bls_file_input import BlsFileInput


def image_dataset(nx, ny, nz=2, x_step=1, y_step=1):
    data = np.arange(nz * ny * nx).reshape(nz, ny, nx)
    return hv.Dataset(
        xr.DataArray(
            data,
            dims=["z", "y", "x"],
            coords={
                "x": np.arange(nx) * x_step,
                "y": np.arange(ny) * y_step,
                "z": np.arange(nz),
            },
            name="value",
        )
    )


@pytest.fixture
def visualizer():
    hv.extension("bokeh")
    pn.extension(notifications=True)
    widget = BlsDataVisualizer(BlsFileInput())
    widget.__panel__()
    return widget


def test_initial_image_and_label():
    widget = BlsDataVisualizer(BlsFileInput())
    assert widget.label == "Data Analysis visualization"
    np.testing.assert_array_equal(widget.img_data, np.zeros((512, 512)))


def test_initial_image_can_be_supplied():
    image = np.ones((2, 3))
    widget = BlsDataVisualizer(BlsFileInput(), img_data=image)
    np.testing.assert_array_equal(widget.img_data, image)


def test_image_geometry_updates_each_render_and_preserves_zoom(visualizer):
    plots = [hv.renderer("bokeh").get_plot(visualizer._masked_dmap) for _ in range(2)]
    figures = [plot.state for plot in plots]

    visualizer.img_dataset = image_dataset(20, 10)
    for fig in figures:
        assert fig.aspect_ratio == pytest.approx(2)
        assert (fig.x_range.start, fig.x_range.end) == pytest.approx((-0.5, 19.5))
        assert (fig.y_range.start, fig.y_range.end) == pytest.approx((9.5, -0.5))
        assert (fig.x_range.reset_start, fig.x_range.reset_end) == pytest.approx(
            (-0.5, 19.5)
        )
        assert (fig.y_range.reset_start, fig.y_range.reset_end) == pytest.approx(
            (9.5, -0.5)
        )
        fig.x_range.update(start=2, end=8)
        fig.y_range.update(start=4, end=1)

    visualizer.img_axis_3_slice = 1
    for plot, fig in zip(plots, figures):
        assert (fig.x_range.start, fig.x_range.end) == (2, 8)
        assert (fig.y_range.start, fig.y_range.end) == (4, 1)
        image = plot.subplots[("Image", "I")].handles["source"].data["image"][0]
        assert image[0, 0] == 200

    visualizer.autoscale = False
    visualizer.colorrange = (210, 230)
    visualizer.param.trigger("_colorrange_committed")
    for plot, fig in zip(plots, figures):
        mapper = plot.subplots[("Image", "I")].handles["color_mapper"]
        assert (mapper.low, mapper.high) == (210, 230)
        assert (fig.x_range.start, fig.x_range.end) == (2, 8)

    visualizer.img_axis_1 = "z"
    for fig in figures:
        assert fig.aspect_ratio == pytest.approx(0.2)
        assert (fig.x_range.start, fig.x_range.end) == pytest.approx((-0.5, 1.5))
        assert (fig.y_range.start, fig.y_range.end) == pytest.approx((9.5, -0.5))
        assert (fig.x_range.reset_start, fig.x_range.reset_end) == pytest.approx(
            (-0.5, 1.5)
        )
        assert (fig.y_range.reset_start, fig.y_range.reset_end) == pytest.approx(
            (9.5, -0.5)
        )
        assert fig.xaxis[0].axis_label == "z"


def test_physical_pixel_spacing_changes_aspect(visualizer):
    plot = hv.renderer("bokeh").get_plot(visualizer._masked_dmap)
    visualizer.img_dataset = image_dataset(20, 10, x_step=0.5, y_step=2)
    assert plot.state.aspect_ratio == pytest.approx(0.5)
    plot.state.x_range.update(start=1, end=3)
    visualizer.img_dataset = image_dataset(20, 10, x_step=0.5, y_step=2).redim(
        x=hv.Dimension("x", unit="um"),
        y=hv.Dimension("y", unit="um"),
    )
    assert (plot.state.x_range.start, plot.state.x_range.end) == pytest.approx(
        (-0.25, 9.75)
    )


def test_colorbar_label_updates_with_quantity(visualizer):
    plot = hv.renderer("bokeh").get_plot(visualizer._masked_dmap)
    visualizer.img_vunit = hv.Dimension("frequency", unit="GHz")
    visualizer.img_dataset = image_dataset(20, 10)
    colorbar = plot.subplots[("Image", "I")].handles["colorbar"]
    assert colorbar.title == "frequency (GHz)"


def test_interaction_streams_survive_image_updates(visualizer, monkeypatch):
    monkeypatch.setattr(visualizer_module, "_defer_param_update", lambda fn: fn())
    visualizer.img_dataset = image_dataset(8, 4)
    hv.renderer("bokeh").get_plot(visualizer._masked_dmap)
    visualizer.img_axis_3_slice = 1

    tap = visualizer._image_streams[0]
    tap.event(x=2, y=3)
    assert visualizer.dataset_zyx_click == (1, 3, 2)

    if not visualizer_module._GUI_ROI_SELECTION:
        pytest.skip("Lasso selection requires scipy")
    lasso, reset = visualizer._image_streams[1:]
    lasso.event(geometry=np.array([(0, -1), (4, -1), (4, 3), (0, 3)]))
    assert visualizer.mask.shape == (4, 8)
    assert visualizer.mask.values.any()
    reset.event(resetting=True)
    assert visualizer.mask is None


@pytest.mark.parametrize("selected", [False, True])
def test_mask_overlay_has_fixed_color_range_and_transparent_selection(
    visualizer, selected
):
    """
    The overlay is patched in place in the browser, so its colour range must not depend on
    what was drawn first: 0 (not selected) → grey, 1 (selected) → fully transparent.
    """
    visualizer.img_dataset = image_dataset(20, 10)
    if selected:
        mask = np.zeros((10, 20), dtype=bool)
        mask[2:7, 3:10] = True
        visualizer.mask = xr.DataArray(
            mask, dims=["y", "x"], coords={"x": np.arange(20), "y": np.arange(10)}
        )
    else:
        visualizer.mask = None  # the placeholder must be invisible too

    plot = hv.renderer("bokeh").get_plot(visualizer._plot_mask())
    mapper = plot.handles["color_mapper"]
    assert (mapper.low, mapper.high) == (0, 1)
    assert list(mapper.palette) == visualizer_module.MASK_CMAP
    assert mapper.palette[1].endswith("00") and len(mapper.palette[1]) == 9
    assert plot.handles["glyph"].global_alpha == visualizer_module.MASK_ALPHA
