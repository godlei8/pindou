import numpy as np

from app.core.detect import GridInfo
from app.core.downsample import CellImage, downsample_area, downsample_mode, grid_shape


def test_grid_shape_keeps_aspect():
    assert grid_shape(1000, 2000, 58) == (29, 58)
    assert grid_shape(2000, 1000, 58) == (58, 29)
    assert grid_shape(100, 100, 30) == (30, 30)
    assert grid_shape(10, 1000, 58)[0] >= 1


def test_area_average_in_linear_space_not_srgb():
    # 一半纯黑一半纯白的 2×1 格：sRGB 直接平均给 0.5，线性平均后转回 sRGB 应约 0.735
    rgba = np.zeros((10, 20, 4), dtype=np.float32)
    rgba[:, 10:, :3] = 1.0
    rgba[..., 3] = 1.0
    cell = downsample_area(rgba, rows=1, cols=1, denoise=False)
    assert cell.rgb.shape == (1, 1, 3)
    assert abs(cell.rgb[0, 0, 0] - 0.735) < 0.02


def test_area_average_ignores_transparent_pixels_and_reports_coverage():
    rgba = np.zeros((10, 10, 4), dtype=np.float32)
    rgba[..., :3] = [1.0, 0.0, 0.0]
    rgba[:, :5, 3] = 1.0          # 左半不透明，右半透明
    cell = downsample_area(rgba, rows=1, cols=1, denoise=False)
    assert abs(cell.coverage[0, 0] - 0.5) < 1e-6
    assert np.allclose(cell.rgb[0, 0], [1.0, 0.0, 0.0], atol=1e-6)   # 不被透明像素的黑拉暗
    assert cell.mask[0, 0]        # 恰好 0.5 视为有豆


def test_fully_transparent_cell_is_masked_out():
    rgba = np.zeros((8, 16, 4), dtype=np.float32)
    rgba[:, :8, 3] = 1.0
    cell = downsample_area(rgba, rows=1, cols=2, denoise=False)
    assert cell.mask.tolist() == [[True, False]]


def test_denoise_keeps_flat_colors():
    rgba = np.zeros((40, 40, 4), dtype=np.float32)
    rgba[..., :3] = [0.2, 0.6, 0.9]
    rgba[..., 3] = 1.0
    cell = downsample_area(rgba, rows=4, cols=4, denoise=True)
    assert np.allclose(cell.rgb, [0.2, 0.6, 0.9], atol=0.02)


def test_mode_sampling_picks_dominant_color_per_cell():
    rgba = np.zeros((16, 16, 4), dtype=np.float32)
    rgba[..., 3] = 1.0
    rgba[:8, :8, :3] = [1, 0, 0]
    rgba[:8, 8:, :3] = [0, 1, 0]
    rgba[8:, :8, :3] = [0, 0, 1]
    rgba[8:, 8:, :3] = [1, 1, 0]
    rgba[0, 0, :3] = [0.5, 0.5, 0.5]          # 一颗噪点，不应影响众数
    info = GridInfo(cell=8, offset_x=0, offset_y=0, cols=2, rows=2, confidence=1.0)
    cell = downsample_mode(rgba, info)
    assert np.allclose(cell.rgb[0, 0], [1, 0, 0]) and np.allclose(cell.rgb[1, 1], [1, 1, 0])
    assert cell.mask.all()
