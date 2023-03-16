import numpy as np
from cutout.cutout import (get_fits_data,
                           cutout_lupton,
                           write_cutout_file,
                           cutout_verts,
                           tiles_from_cat)
import os                        

# Reading input data
RA, DEC, size = np.loadtxt('coords.dat', usecols=(0, 1, 2), unpack=True)
band, request = np.loadtxt(
    'coords.dat', usecols=(3, 4), dtype=str, unpack=True)

# Set the path where the FITS files are stored
path_to_fits = 'tiles'

# Calculates the cutout's vertices to access tiles
verts = cutout_verts(RA, DEC, size)

# Set tiles from vertices
tiles = tiles_from_cat(
    verts, 'coaddtiles-20121015.csv')

# Now make cutouts:
for i in range(np.shape(tiles)[0]):

    if request[i] == 'FITS':
        data, wcs_ = get_fits_data(
            RA[i], DEC[i], size[i], tiles[i], band[i], path_to_fits)
        filename = '{:.5f}_{:.5f}_{}.fits'.format(
            round(RA[i], 5), round(DEC[i], 5), band[i])
        filepath = os.path.join(path_to_fits, filename)
        write_cutout_file(data, wcs_, filepath)
    elif request[i] == 'PNG':
        data_g, wcs_g = get_fits_data(
            RA[i], DEC[i], size[i], tiles[i], band[i][0], path_to_fits)
        data_r, wcs_r = get_fits_data(
            RA[i], DEC[i], size[i], tiles[i], band[i][1], path_to_fits)
        data_i, wcs_i = get_fits_data(
            RA[i], DEC[i], size[i], tiles[i], band[i][2], path_to_fits)
        filename = '{:.5f}_{:.5f}_{}.png'.format(
            round(RA[i], 5), round(DEC[i], 5), band[i])
        filepath = os.path.join(path_to_fits, filename)            
        cutout_lupton(data_g, data_r, data_i, 0.05, 10, 0.5, filepath)
