#!/usr/bin/env python3
from cutout.lib.des_cutout import DesCutout
from cutout.service.cutout_engine import create_cutout_engine
from pathlib import Path
from astropy import units as u
from astropy.coordinates import SkyCoord

OUTDIR = Path('/data/results/debug')
OUTDIR.mkdir(parents=True, exist_ok=True)

def main():
    ra = 36.30911
    dec = -10.18749
    size = 2.0
    dc = DesCutout()
    verts = dc.get_cutout_verts(ra, dec, size)
    bands = ['g','r','i']
    files_map = {}
    for b in bands:
        comp_files = dc.get_fits_files(verts, b)
        files_map[b] = []
        for comp in comp_files:
            fits_filename = comp.name.split('.fz')[0]
            uncompressed = dc.tmp_path.joinpath(fits_filename)
            if not uncompressed.exists():
                print('uncompressing', comp, '->', uncompressed)
                dc.funpack(comp, uncompressed)
            files_map[b].append(str(uncompressed))

    print('files_map:', files_map)
    stencil = {"type": "circle", "center": {"ra": ra, "dec": dec}, "radius": size}
    engine = create_cutout_engine('astrocut')
    out = OUTDIR.joinpath('engine_astrocut_test_gri.png')
    try:
        res = engine.run_cutout(source_id='des_dr2', stencil=stencil, input_files=files_map, band='gri', output_format='png', output_path=out, color=True, rgb_bands='gri')
        print('engine produced', res)
    except Exception as e:
        import traceback
        print('engine.run_cutout failed:', e)
        traceback.print_exc()

if __name__ == '__main__':
    main()
