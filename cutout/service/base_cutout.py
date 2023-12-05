from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.visualization import make_lupton_rgb


class BaseCutout(ABC):
    def cutout_circle(
        self, ra: float, dec: float, size_arcmin: float, band: str, format: str, path: Path | str
    ) -> Path:
        if isinstance(path, str):
            path = Path(path)

        if format == "fits":
            return self.single_cutout_fits(ra, dec, size_arcmin, band, path)
        elif format == "png":
            return self.single_cutout_png(ra, dec, size_arcmin, band, path)

    def single_cutout_fits(self, ra: float, dec: float, size_arcmin: float, band: str, path: Path) -> Path:
        # TODO: Tratar retorno da função quando o cutout falhar.
        data, wcs = self.get_fits_data(ra, dec, size_arcmin, band)
        self.write_cutout_fits(data, wcs, path, overwrite=True)

        return path

    def single_cutout_png(self, ra: float, dec: float, size_arcmin: float, band: str, path: Path) -> Path:
        # TODO: Tratar retorno da função quando o cutout falhar.
        # TODO: Tratar as bandas por enquanto estao fixas.
        fits_data = {
            "g": [],
            "r": [],
            "i": [],
        }
        for b in band:
            data, wcs = self.get_fits_data(ra=ra, dec=dec, size_arcmin=size_arcmin, band=b)
            fits_data[b] = data

        self.write_cutout_lupton(
            fits_data["i"],
            fits_data["r"],
            fits_data["g"],
            minimum=0.05,
            stretch=10,
            q=0.5,
            filepath=path,
            overwrite=True,
        )

        return path

    @abstractmethod
    def get_fits_data(self, ra: float, dec: float, size_arcmin: float, band: str) -> tuple:
        pass

    def write_cutout_lupton(self, image_r, image_g, image_b, minimum, stretch, q, filepath, overwrite=True):
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
        print(f"TESTE")
        make_lupton_rgb(
            image_r=image_r, image_g=image_g, image_b=image_b, minimum=minimum, stretch=stretch, Q=q, filename=filepath
        )

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

        pos_angle = [45, 315, 225, 135] * u.deg  # type: ignore
        c1 = SkyCoord(ra * u.deg, dec * u.deg, frame="icrs")  # type: ignore
        sep = 0.5 * np.sqrt(2.0) * size_arcmin * u.arcmin
        ra_offset = c1.directional_offset_by(pos_angle, sep).ra.deg  # type: ignore
        dec_offset = c1.directional_offset_by(pos_angle, sep).dec.deg  # type: ignore
        return SkyCoord(ra_offset * u.deg, dec_offset * u.deg, frame="icrs")  # type: ignore
