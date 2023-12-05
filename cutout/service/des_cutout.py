import subprocess
import warnings
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata.utils import Cutout2D
from astropy.wcs import WCS
from astropy.wcs.wcs import FITSFixedWarning

from cutout.service.base_cutout import BaseCutout

warnings.simplefilter("ignore", category=FITSFixedWarning)


class DesCutout(BaseCutout):
    # TODO: Melhorar a forma de armazenar e ler a lista de tiles.
    tile_list_path: Path = Path("/app/cutout/service/dr2_tiles.csv")
    path_to_fits: Path = Path("/data/tiles")
    tmp_path: Path = Path("/data/tmp")

    def get_fits_data(self, ra: float, dec: float, size_arcmin: float, band: str) -> tuple:
        # Calcular os vertices do cutout
        verts = self.get_cutout_verts(ra, dec, size_arcmin)

        # A partir dos vertices identificar os arquivos fits e ler os dados
        compressed_fits_files = self.get_fits_files(verts, band)

        fits_files = []
        # Descompactar os arquivos fits
        for compressed in compressed_fits_files:
            fits_filename = compressed.name.split(".fz")[0]
            uncompressed = self.tmp_path.joinpath(fits_filename)
            if not uncompressed.exists():
                self.funpack(compressed, uncompressed)
            fits_files.append(uncompressed)

        if len(fits_files) == 1:
            data_, wcs_ = self.read_fits_partial_data(fits_files[0], ra, dec, size_arcmin, mode="trim")
            return (data_, wcs_)

        elif len(fits_files) == 2:
            data_1, wcs_1 = self.read_fits_partial_data(fits_files[0], ra, dec, size_arcmin, mode="trim")
            data_2, wcs_2 = self.read_fits_partial_data(fits_files[1], ra, dec, size_arcmin, mode="trim")

            if np.shape(data_1)[1] < np.shape(data_1)[0]:
                # side-by-side
                data_1 = data_1[:, :-118]
                data_2 = data_2[:, 118:]
                data_ = np.concatenate((data_1, data_2), axis=1)
                return (data_, wcs_1)

            else:
                # top-bottom
                data_1 = data_1[114:, :]
                data_2 = data_2[:-114, :]
                data_ = np.concatenate((data_2, data_1), axis=0)
                return (data_, wcs_2)

        elif len(fits_files) == 3:
            data_1, wcs_1 = self.read_fits_partial_data(fits_files[0], ra, dec, size_arcmin, mode="trim")
            data_2, wcs_2 = self.read_fits_partial_data(fits_files[1], ra, dec, size_arcmin, mode="trim")
            data_3, wcs_3 = self.read_fits_partial_data(fits_files[2], ra, dec, size_arcmin, mode="trim")

            # Biggest at bottom:
            if np.shape(data_1)[1] < np.shape(data_3)[1]:
                data_12 = np.concatenate((data_1[118:, :-118], data_2[118:, 118:]), axis=1)
                data_ = np.concatenate((data_3[:-118, :], data_12[:, 0 : np.shape(data_3)[1]]), axis=0)
            # Biggest at top:
            else:
                data_23 = np.concatenate((data_2[:-118, 118:], data_3[:-118, :-118]), axis=1)
                data_ = np.concatenate((data_23, data_1[118:, 0 : np.shape(data_23)[1]]), axis=0)
            return (data_, wcs_3)

    def read_fits_partial_data(self, filepath, ra, dec, size_arcmin, mode="partial"):
        """Return data (image array and wcs) from tile.

        Parameters
        ----------
        ra : float
            Equatorial coordinate of center of tile.
        dec : float
            Equatorial coordinate of center of tile.
        size_arcmin : float
            Size of cutout in arcmin.
        tile_name : str
            Name of tile where total or part of the cutout image resides.
        band : str
            Band of image.
        path : str
            Path to folder where the FITS files are stored.
        mode : str, optional
            Mode of cutout. See:
            https://docs.astropy.org/en/stable/api/astropy.nddata.Cutout2D.html
            By default set to 'partial'.

        Returns
        -------
        arrays
            Two arrays, one with image data and other with WCS astropy object.
        """
        # Esta funcao me parece ser especifica para o DES
        # Por que está lendo os Headers do HDU 1
        # e os dados do HDU 0
        # Outros surveis podem ter essas informações em HDUs diferentes.
        with fits.open(str(filepath)) as hdul:
            wcs = WCS(hdul[1].header)
            cutout = Cutout2D(
                hdul[0].data,
                (SkyCoord(ra=ra * u.degree, dec=dec * u.degree, frame="icrs")),
                size_arcmin * u.arcmin,
                wcs=wcs,
                mode=mode,
            )

        return cutout.data, cutout.wcs.to_header()

    def get_fits_files(self, verts: SkyCoord, band: str) -> list[Path]:
        # Tile paths para os fits que contem os dados para esta coordenada.
        tile_paths = self.get_tiles(verts)

        fits_files = []
        for p in tile_paths:
            # Filenames montado a partir do path
            parts = p.split("/")
            filename = f"{parts[2]}_{parts[1]}{parts[3]}_{band}.fits.fz"
            filepath = self.path_to_fits.joinpath(p).joinpath(filename)

            fits_files.append(filepath)

        return fits_files

    def get_tiles(self, verts: SkyCoord) -> list[str]:
        """Read information about tiles.
        TODO: read more information about the vertices of tiles in
        order to have a correct overlap in case cutouts are in the
        edge of tiles.

        Parameters
        ----------
        verts : SkyCoord astropy object
            Object with information about coordinates of vertices.
        Returns
        -------
        list
            List of tiles where the vertices of cutout reside.
        """
        ra_ll, dec_ll, ra_ur, dec_ur = np.loadtxt(
            self.tile_list_path, usecols=(1, 2, 3, 4), delimiter=";", unpack=True, skiprows=1
        )
        tile_names, paths = np.loadtxt(
            self.tile_list_path, usecols=(0, 5), delimiter=";", dtype=str, unpack=True, skiprows=1
        )

        ra = verts.ra.deg
        dec = verts.dec.deg

        idx_ = []
        for j in range(4):
            idx_.append(np.argwhere((ra_ll < ra[j]) & (ra_ur > ra[j]) & (dec_ll < dec[j]) & (dec_ur > dec[j]))[0][0])

        tile_match = [tile_names[k] for k in idx_]
        tile_paths = [paths[k] for k in idx_]

        # Tiles unicas usando np
        # tile_un, ind = np.unique(tile_match[:], return_index=True)
        # tile_un = tile_un[np.argsort(ind)]
        # return tile_un

        # Retorna os tilename unicas usando set
        # return list(set(tile_match))

        return list(set(tile_paths))

    def funpack(self, compressed: Path, uncompressed: Path):
        # funpack -O <uncompressed> <compressed>
        process = subprocess.Popen(["funpack", "-O", str(uncompressed), str(compressed)])
        process.wait()


# if __name__ == "__main__":
#     cutouts = [
#         {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g", "format": "fits"},  # 1 - Tile
#         {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "gri", "format": "png"},  # 1 - Tile
#         {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g", "format": "fits"},  # 2 - Tile
#         {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "gri", "format": "png"},  # 2 - Tile
#         # {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile
#     ]

#     dc = DesCutout()

#     for c in cutouts:
#         if c["format"] == "fits":
#             filename = "{:.5f}_{:.5f}_{}.fits".format(round(c["ra"], 5), round(c["dec"], 5), c["band"])
#             resultfile = Path("/data/results").joinpath(filename)

#             result = dc.single_cutout_fits(
#                 ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
#             )
#             print(result)

#         if c["format"] == "png":
#             filename = "{:.5f}_{:.5f}.png".format(round(c["ra"], 5), round(c["dec"], 5))
#             resultfile = Path("/data/results").joinpath(filename)

#             result = dc.single_cutout_png(
#                 ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
#             )
#             print(result)
