from cutout.service.stencils import CircleStencil, PolygonStencil, RangeStencil


def test_circle_axis_aligned_bounds_is_center_plus_minus_radius() -> None:
    stencil = CircleStencil.from_string("10.5 0 1")
    assert stencil.axis_aligned_bounds() == (9.5, 11.5, -1.0, 1.0)


def test_range_axis_aligned_bounds_copies_edges() -> None:
    stencil = RangeStencil.from_string("19.4 19.8 19.4 19.8")
    assert stencil.axis_aligned_bounds() == (19.4, 19.8, 19.4, 19.8)


def test_polygon_axis_aligned_bounds_is_vertex_minmax() -> None:
    stencil = PolygonStencil.from_string("10 -0.5 12 -0.5 12 0.5 10 0.5")
    ra_min, ra_max, dec_min, dec_max = stencil.axis_aligned_bounds()
    assert (ra_min, ra_max, dec_min, dec_max) == (10.0, 12.0, -0.5, 0.5)
