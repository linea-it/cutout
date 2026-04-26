import pytest
from pathlib import Path


def _has_tiles() -> bool:
    return Path("/data/tiles").exists()


def test_astrocut_end_to_end_png():
    if not _has_tiles():
        pytest.skip("No tiles available in /data/tiles for E2E test")

    from cutout.lib.des_cutout import DesCutout
    from cutout.service.tasks import image_cutout
    from PIL import Image

    ra = 36.30911
    dec = -10.18749
    size = 2.0
    dc = DesCutout()
    verts = dc.get_cutout_verts(ra, dec, size)

    bands = ["g", "r", "i"]
    files_map = {}
    for b in bands:
        comp_files = dc.get_fits_files(verts, b)
        if not comp_files:
            pytest.skip(f"No files found for band {b}")
        files_map[b] = [str(p.file_path) if hasattr(p, 'file_path') else str(p) for p in comp_files]

    out = "/data/results/test_e2e_astrocut_gri.png"

    res = image_cutout.run(
        job_id="e2e-test",
        source_id="des_dr2",
        stencil={"type": "circle", "center": {"ra": ra, "dec": dec}, "radius": size},
        engine="astrocut",
        band="gri",
        format="png",
        path=out,
        files=files_map,
        color=True,
        rgb_bands="gri",
        persist=False,
    )

    assert Path(res).exists(), f"Result file missing: {res}"
    im = Image.open(res)
    assert im.mode in ("RGB", "RGBA")
    assert im.size[0] > 0 and im.size[1] > 0
