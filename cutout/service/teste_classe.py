from pathlib import Path

from celery import group

# from cutout.lib.cutout import Cutout
# from cutout.lib.des_cutout import DesCutout
# from cutout.service.policy import ImageCutoutPolicy
# from cutout.service.uws.models import JobParameter
# from cutout.service.uws.service import JobService
# from cutout.users.models import User

if __name__ == "__main__":
    from cutout.service.tasks import task_1, task_completed

    header = [task_1.s(1, 2), task_1.s(3, 4)]

    g = group(header)
    gresult = g.apply_async()
    print(gresult.get())

    # params = []
    # teste_params = {
    #     "id": "des_dr2",
    #     "runid": "MeujobCutout",
    #     "band": "g",
    #     "format": "fits",
    #     "pos": "CIRCLE 36.30911 -10.18749 2",
    # }
    # for key, value in teste_params.items():
    #     if key.lower() == "runid":
    #         run_id = value
    #     else:
    #         params.append(JobParameter(parameter_id=key.lower(), value=value, is_post=False))
    # user = User.objects.get(pk=1)
    # policy = ImageCutoutPolicy()
    # job_service = JobService(policy=policy)
    # job = job_service.create(user=user, params=params, run_id=run_id)
    # job_service.start(user, job_id=job.id)
    # cutouts = [
    #     {
    #         "id": "des_dr2",
    #         "stencil": {"type": "circle", "center": {"ra": 36.30911, "dec": -10.18749}, "radius": 2.0},
    #         "band": "g",
    #         "format": "fits",
    #     }
    # ]
    # for c in cutouts:
    #     dc = Cutout(source_id=c["id"], stencil=c["stencil"], band=c["band"], format=c["format"])
    #     # filename = "{:.5f}_{:.5f}_{}.fits".format(round(c["stencil"]["center"]["ra"], 5), round(c["stencil"]["center"]["dec"], 5), c["band"])
    #     filename = "teste.fits"
    #     resultfile = Path("/data/results").joinpath(filename)
    #     dc.create(path=resultfile)
    # cutouts = [
    #     {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "g", "format": "fits"},  # 1 - Tile
    #     # {"ra": 36.30911, "dec": -10.18749, "size": 2.0, "band": "gri", "format": "png"},  # 1 - Tile
    #     # {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "g", "format": "fits"},  # 2 - Tile
    #     # {"ra": 36.15801, "dec": -10.33579, "size": 2.0, "band": "gri", "format": "png"},  # 2 - Tile
    #     # {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile
    #     # {"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "gri", "format": "png"},  # 3 - Tile
    # ]
    # dc = DesCutout()
    # for c in cutouts:
    #     if c["format"] == "fits":
    #         filename = "{:.5f}_{:.5f}_{}.fits".format(round(c["ra"], 5), round(c["dec"], 5), c["band"])
    #         resultfile = Path("/data/results").joinpath(filename)
    #         result = dc.single_cutout_fits(
    #             ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
    #         )
    #         print(result)
    #     if c["format"] == "png":
    #         filename = "{:.5f}_{:.5f}.png".format(round(c["ra"], 5), round(c["dec"], 5))
    #         resultfile = Path("/data/results").joinpath(filename)
    #         result = dc.single_cutout_png(
    #             ra=c["ra"], dec=c["dec"], size_arcmin=c["size"], band=c["band"], path=resultfile
    #         )
    #         print(result)
