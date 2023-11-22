from pathlib import Path

from cutout.service.des_cutout import DesCutout

if __name__ == "__main__":
    cutouts = [
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g", "format": "fits"},  # 1 - Tile
        {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "gri", "format": "png"},  # 1 - Tile
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g", "format": "fits"},  # 2 - Tile
        {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "gri", "format": "png"},  # 2 - Tile
        # {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile
    ]

    dc = DesCutout()

    for c in cutouts:
        if c["format"] == "fits":
            filename = "{:.5f}_{:.5f}_{}.fits".format(round(c["ra"], 5), round(c["dec"], 5), c["band"])
            resultfile = Path("/data/results").joinpath(filename)

            result = dc.single_cutout_fits(
                ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
            )
            print(result)

        if c["format"] == "png":
            filename = "{:.5f}_{:.5f}.png".format(round(c["ra"], 5), round(c["dec"], 5))
            resultfile = Path("/data/results").joinpath(filename)

            result = dc.single_cutout_png(
                ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
            )
            print(result)
