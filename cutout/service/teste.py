import glob
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata.utils import Cutout2D
from astropy.visualization import make_lupton_rgb
from astropy.wcs import WCS


def cutout_verts(RA_center, DEC_center, size_arcmin):
    """Defines the position of vertices in each cutout.
    See the pos_angle where the vertices are sorted.

    Parameters
    ----------
    RA_center : float
        Equatorial coordinate of center of cutout.
    DEC_center : float
        Equatorial coordinate of center of cutout.
    size_arcmin : float
        Size (length of each side) of cutout, in arcmin.

    Returns
    -------
    SkyCoord astropy object
        Location of vertices of cutout.
    """
    pos_angle = [45, 315, 225, 135] * u.deg
    c1 = SkyCoord(RA_center * u.deg, DEC_center * u.deg, frame="icrs")
    sep = 0.5 * np.sqrt(2.0) * size_arcmin * u.arcmin
    RA = c1.directional_offset_by(pos_angle, sep).ra.deg
    DEC = c1.directional_offset_by(pos_angle, sep).dec.deg
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

    idx_ = []
    for j in range(4):
        idx_.append(np.argwhere((ra_ll < ra[j]) & (ra_ur > ra[j]) & (dec_ll < dec[j]) & (dec_ur > dec[j]))[0][0])
    tile_match = [tile_names[k] for k in idx_]
    #  TODO: Remover tiles duplicadas
    return tile_match


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
    # file_name_ = glob.glob(path + "/" + tile_name + "_*_" + band + ".fits")
    # file_name = file_name_[0]
    # TODO: Ter o tilename completo.
    fits_filepath = path.joinpath(f"{tile_name}_r4920p01_{band}.fits")
    f = fits.open(fits_filepath)
    wcs = WCS(f[1].header)
    print(fits_filepath)
    cutout1 = Cutout2D(
        fits.getdata(fits_filepath, ext=0),
        (SkyCoord(ra=RA_center * u.degree, dec=DEC_center * u.degree, frame="icrs")),
        size_arcmin * u.arcmin,
        wcs=wcs,
        mode=mode,
    )

    return cutout1.data, cutout1.wcs.to_header()


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


if __name__ == "__main__":
    cutout_1_tile = {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g"}
    cutout_2_tile = {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g"}
    cutout_3_tiles = {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g"}

    cutout = cutout_2_tile

    ra = cutout["ra"]
    dec = cutout["dec"]
    size = cutout["size"]
    band = cutout["band"]
    # Calculates the cutout's vertices to access tiles
    verts = cutout_verts(ra, dec, size)
    print(verts)
    # Set tiles from vertices
    tile_list = Path("/app/cutout/service/coaddtiles-20121015.csv")
    tiles = tiles_from_cat(verts, tile_list)
    print(tiles)

    # Cutout Fits:
    path_to_fits = Path("/data/tiles")
    data, wcs_ = get_fits_data(ra, dec, size, tiles, band, path_to_fits)
    # print(data)

    # Exemplo Cutout FITS
    # result_path = Path("/data/results")
    # filename = "{:.5f}_{:.5f}_{}.fits".format(round(ra, 5), round(dec, 5), band)
    # filepath = result_path.joinpath(filename)
    # if filepath.exists():
    #     filepath.unlink()
    # write_cutout_file(data, wcs_, filepath)

    # Exemplo Cutout PNG
    # Usando 3 bandas, primeiro faz 3 cutouts fits em g, r, i
    # Depois gera a png.
    result_path = Path("/data/results")
    filename = "{:.5f}_{:.5f}.png".format(round(ra, 5), round(dec, 5))
    filepath = result_path.joinpath(filename)
    if filepath.exists():
        filepath.unlink()
    print(filepath)
    # Fits g, r, i
    data_g, wcs_g = get_fits_data(ra, dec, size, tiles, "g", path_to_fits)
    data_r, wcs_r = get_fits_data(ra, dec, size, tiles, "r", path_to_fits)
    data_i, wcs_i = get_fits_data(ra, dec, size, tiles, "i", path_to_fits)

    cutout_lupton(data_g, data_r, data_i, 0.05, 10, 0.5, filepath)
