# cutout

---
# Cutout

This is a project to produce cutouts in astronomical images, mainly for Dark
Energy Survey tiles.

## Project Description

The code was developed to start from a table (txt file) with information about the
center of cutout (position of target), size (in arcmin), band and request's type
('FITS' for cutouts in FITS files and PNG for RGB images as PNG files).

## How to Install and Run the Project

The project was developed in Python 3.X.
Requested packages are Numpy 1.20.3 and Astropy 5.1.

## How to Use the Project

Basically clone the repository, download FITS images (g, r and i bands) from the following tiles:

DES0219-1041
DES0222-1041
DES0225-1041
DES0221-0958
DES0224-0958.

Use the __[desportal](https://desportal2.cosmology.illinois.edu/)__ to download full FITS image of tiles.

Extract the *.fits.fz files to *.fits files using __[FITSIO](https://heasarc.gsfc.nasa.gov/fitsio/)__ and command:

`funpack tile_name.fits.fz`

and store the FITS files in folder called 'tiles'.

After that, run the code:

`python cutout.py`

The cutouts will be produced in the same folder of the project.