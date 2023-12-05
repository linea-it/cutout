import glob

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata.utils import Cutout2D
from astropy.visualization import make_lupton_rgb
from astropy.wcs import WCS


def get_fits_data(RA, DEC, size, tiles, band, path):
    """Access data (image and wcs) from FITS files.

    Parameters
    ----------
    RA : float
        Equatorial coordinate of the center of cutout (degrees).
    DEC : float
        Equatorial coordinate of the center of cutout (degrees).
    size : float
        Size of cutout (arcmin).
    tiles : list
        List with the tiles where the vertices of cutout reside.
        Sorted by: Upper left, Upper right, Lower right, Lower left.
    band : str
        Band of cutout.
    path : str
        Path to folder with the FITS files.
    """

    tile_un, ind = np.unique(tiles[:], return_index=True)
    tile_un = tile_un[np.argsort(ind)]

    if len(tile_un) == 1:
        data_, wcs_ = cutout_fits(RA, DEC, size, tiles[0], band, path)
        return (data_, wcs_)

    elif len(tile_un) == 2:
        data_1, wcs_1 = cutout_fits(RA, DEC, size, tile_un[0], band, path, "trim")
        data_2, wcs_2 = cutout_fits(RA, DEC, size, tile_un[1], band, path, "trim")

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

    elif len(tile_un) == 3:
        data_1, wcs_1 = cutout_fits(RA, DEC, size, tile_un[0], band, path, "trim")
        data_2, wcs_2 = cutout_fits(RA, DEC, size, tile_un[1], band, path, "trim")
        data_3, wcs_3 = cutout_fits(RA, DEC, size, tile_un[2], band, path, "trim")

        # Biggest at bottom:
        if np.shape(data_1)[1] < np.shape(data_3)[1]:
            data_12 = np.concatenate((data_1[118:, :-118], data_2[118:, 118:]), axis=1)
            data_ = np.concatenate((data_3[:-118, :], data_12[:, 0 : np.shape(data_3)[1]]), axis=0)
        # Biggest at top:
        else:
            data_23 = np.concatenate((data_2[:-118, 118:], data_3[:-118, :-118]), axis=1)
            data_ = np.concatenate((data_23, data_1[118:, 0 : np.shape(data_23)[1]]), axis=0)
        return (data_, wcs_3)


def cutout_lupton(g_data, r_data, i_data, minimum, stretch, Q, filename):
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

    rgb_default = make_lupton_rgb(i_data, r_data, g_data, minimum=minimum, stretch=stretch, Q=Q, filename=filename)


def write_cutout_file(data, wcs, filename):
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
    hdu.writeto(filename, overwrite=True)


def cutout_fits(RA_center, DEC_center, size_arcmin, tile_name, band, path, mode="partial"):
    """Return data (image array and wcs) from tile.

    Parameters
    ----------
    RA_center : float
        Equatorial coordinate of center of tile.
    DEC_center : float
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
    file_name_ = glob.glob(path + "/" + tile_name + "_*_" + band + ".fits")
    file_name = file_name_[0]
    f = fits.open(file_name)
    wcs = WCS(f[1].header)

    cutout1 = Cutout2D(
        fits.getdata(file_name, ext=0),
        (SkyCoord(ra=RA_center * u.degree, dec=DEC_center * u.degree, frame="icrs")),
        size_arcmin * u.arcmin,
        wcs=wcs,
        mode=mode,
    )

    return cutout1.data, cutout1.wcs.to_header()


def cutout_verts(RA_center, DEC_center, size_arcmin):
    """Defines the position of vertices in each cutout.
    See the pos_angle where the vertices are sorted.

    Parameters
    ----------
    RA_center : float
        Equatorial coordinate of center of tile.
    DEC_center : float
        Equatorial coordinate of center of tile.
    size_arcmin : float
        Size (length of each side) of cutout, in arcmin.

    Returns
    -------
    SkyCoord astropy object
        Location of vertices of cutout.
    """
    pos_angle = [45, 315, 225, 135] * u.deg
    RA, DEC = [], []
    for i, j in enumerate(RA_center):
        c1 = SkyCoord(RA_center[i] * u.deg, DEC_center[i] * u.deg, frame="icrs")
        sep = 0.5 * np.sqrt(2.0) * size_arcmin[i] * u.arcmin
        RA.append(list(c1.directional_offset_by(pos_angle, sep).ra.deg))
        DEC.append(list(c1.directional_offset_by(pos_angle, sep).dec.deg))
    return SkyCoord(RA * u.deg, DEC * u.deg, frame="icrs")


def tiles_from_cat(cat, file_path):
    """Read information about tiles.
    TODO: read more information about the vertices of tiles in
    order to have a correct overlap in case cutouts are in the
    edge of tiles.

    Parameters
    ----------
    cat : SkyCoord astropy object
        Object with information about coordinates of vertices.
    file_path : str
        File with tile's information.

    Returns
    -------
    list
        List of tiles where the vertices of cutout reside.
    """
    ra_ll, dec_ll, ra_ul, dec_ul, ra_ur, dec_ur, ra_lr, dec_lr = np.loadtxt(
        file_path, usecols=(9, 10, 11, 12, 13, 14, 15, 16), delimiter=",", unpack=True
    )
    tile_names = np.loadtxt(file_path, usecols=(2), delimiter=",", dtype=str, unpack=True)

    ra = cat.ra.deg
    dec = cat.dec.deg

    tile_match = []

    for i in range(np.shape(ra)[0]):
        idx_ = []
        for j in range(4):
            idx_.append(
                np.argwhere((ra_ll < ra[i][j]) & (ra_ur > ra[i][j]) & (dec_ll < dec[i][j]) & (dec_ur > dec[i][j]))[0][
                    0
                ]
            )
        tile_match.append([tile_names[k] for k in idx_])
    return tile_match
