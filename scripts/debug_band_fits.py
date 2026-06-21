#!/usr/bin/env python3
from cutout.lib.des_cutout import DesCutout
from astrocut import fits_cut
from astropy import units as u
from astropy.coordinates import SkyCoord
from pathlib import Path

OUTDIR = Path('/data/results/debug')
OUTDIR.mkdir(parents=True, exist_ok=True)

def main():
    ra = 36.30911
    dec = -10.18749
    size = 2.0
    print('Testing per-band fits_cut for coord', ra, dec)
    dc = DesCutout()
    verts = dc.get_cutout_verts(ra, dec, size)
    for b in ['g','r','i']:
        print('\n--- band', b, '---')
        comp_files = dc.get_fits_files(verts, b)
        print('compressed:', comp_files)
        files = []
        for c in comp_files:
            fits_filename = c.name.split('.fz')[0]
            uncompressed = dc.tmp_path.joinpath(fits_filename)
            if not uncompressed.exists():
                print(' uncompressing', c, '->', uncompressed)
                try:
                    dc.funpack(c, uncompressed)
                except Exception as e:
                    print('  funpack failed', e)
            files.append(str(uncompressed))
        print('uncompressed files:', files)
        try:
            coord = SkyCoord(ra * u.deg, dec * u.deg, frame='icrs')
            res = fits_cut(input_files=files, coordinates=coord, cutout_size=size * u.arcmin, single_outfile=True, cutout_prefix=f'dbg_{b}', output_dir=str(OUTDIR))
            print('fits_cut produced', res)
        except Exception as e:
            import traceback
            print('fits_cut failed for band', b, ':', e)
            traceback.print_exc()

if __name__ == '__main__':
    main()
