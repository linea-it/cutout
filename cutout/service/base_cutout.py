from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.visualization import make_lupton_rgb


class BaseCutout(ABC):
    def single_cutout_fits(self, ra: float, dec: float, size_arcmin: float, band: str, path: Path) -> Path:
        # TODO: Tratar retorno da função quando o cutout falhar.
        data, wcs = self.get_fits_data(ra, dec, size_arcmin, band)
        self.write_cutout_fits(data, wcs, path, overwrite=True)

        if path.exists():
            return path

    def single_cutout_png(self, ra: float, dec: float, size_arcmin: float, band: str, path: Path) -> Path:
        # TODO: Tratar retorno da função quando o cutout falhar.

        fits_data = {
            "g": [],
            "r": [],
            "i": [],
        }
        for b in band:
            data, wcs = self.get_fits_data(ra, dec, size_arcmin, b)
            fits_data[b] = data

        self.write_cutout_lupton(
            g_data=fits_data["g"],
            r_data=fits_data["r"],
            i_data=fits_data["i"],
            minimum=0.05,
            stretch=10,
            q=0.5,
            filepath=path,
            overwrite=True,
        )

        if path.exists():
            return path

    @abstractmethod
    def get_fits_data(self):
        pass

    def write_cutout_lupton(self, g_data, r_data, i_data, minimum, stretch, q, filepath, overwrite=True):
        """Make RGB image and saves as png or jpg files using Lupton method.
        TODO: Improve quality of image for cutout with saturated data.

        Parameters
        ----------
        g_data : array
            Cutout data from first band.
        r_data : array
            Cutout data from second band.
        i_data : array
            Cutout data from third band.
        filename : str
            Name of file to be saved.
        """
        if overwrite and filepath.exists():
            filepath.unlink()
        make_lupton_rgb(i_data, r_data, g_data, minimum=minimum, stretch=stretch, Q=q, filename=filepath)

    def write_cutout_fits(self, data, wcs, filepath, overwrite=True):
        """Saves cutout file.

        Parameters
        ----------
        data : array
            Array with image data.
        wcs : astropy object
            Information about world coordinate system of cutout.
        filename : str
            Name of file to be saved.
        """
        hdu = fits.PrimaryHDU(data)
        hdu.header.update(wcs)
        hdu.writeto(filepath, overwrite=overwrite)

    def get_cutout_verts(self, ra: float, dec: float, size_arcmin: float) -> SkyCoord:
        """Defines the position of vertices in each cutout.
        See the pos_angle where the vertices are sorted.

        Parameters
        ----------
        ra : float
            Equatorial coordinate of center of cutout.
        dec : float
            Equatorial coordinate of center of cutout.
        size_arcmin : float
            Size (length of each side) of cutout, in arcmin.

        Returns
        -------
        SkyCoord astropy object
            Location of vertices of cutout.
        """
        pos_angle = [45, 315, 225, 135] * u.deg
        c1 = SkyCoord(ra * u.deg, dec * u.deg, frame="icrs")
        sep = 0.5 * np.sqrt(2.0) * size_arcmin * u.arcmin
        ra_offset = c1.directional_offset_by(pos_angle, sep).ra.deg
        dec_offset = c1.directional_offset_by(pos_angle, sep).dec.deg
        return SkyCoord(ra_offset * u.deg, dec_offset * u.deg, frame="icrs")
