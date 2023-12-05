# LIneA Cutout Service

[Requisitos](docs/definicao_requisitos/Requisitos.md)

Tiles do DES para teste: [Sample Tiles](https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz)

## Desenvolvimento

Este repositóro está configurado com devcontainer podendo ser utilizado com vscode + extensão devcontainer.

quando utilizado com devcontainer todas as dependencias e extensões já estão configuradas.

Clone do repositório

```bash
git clone https://github.com/linea-it/cutout.git
```

Acesse a pasta e abra com vscode

```bash
cd cutout && code .
```

Na primeira execução a extensão devcontainer vai perguntar se deseja fazer o build do container, aceite fazer o build ou aperte F1 e execute o comando `Rebuild and open in container` o vscode vai criar o container e abrir o repositório dentro dele.

Estando dentro do container é necessário fazer o download dos dados que serão usados para teste.
acesse a pasta /workspaces/cutout/tiles e execute o script `download_sample_tiles.sh`

Este script vai fazer o download de algumas imagens do DES e descompactar no diretório tiles.

com as imagens baixadas e descompactadas o ambiente está pronto.

Execute o script de teste `cutout.py` na raiz do repositório `/workspaces/cutout`
Os cutouts gerados ficam na pasta tiles.


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

[Install Funpack](https://command-not-found.com/funpack)
Extract the *.fits.fz files to *.fits files using __[FITSIO](https://heasarc.gsfc.nasa.gov/fitsio/)__ and command:

`funpack tile_name.fits.fz`

`for z in *.fits.fz; do funpack "$z"; done`

and store the FITS files in folder called 'tiles'.

After that, run the code:

`python cutout.py`

The cutouts will be produced in the same folder of the tiles.
