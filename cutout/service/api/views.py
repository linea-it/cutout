from pathlib import Path
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.http import FileResponse
from django.utils.encoding import escape_uri_path
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from cutout.service.models import Job
from cutout.service.policy import ImageCutoutPolicy
from cutout.service.tasks import des_cutout_circle
from cutout.service.uws.models import JobParameter
from cutout.service.uws.service import JobService

from .serializers import JobRequestSerializer

User = get_user_model()


class JobRequestViewSet(ModelViewSet):
    serializer_class = JobRequestSerializer
    queryset = Job.objects.all()

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)

        data = self.get_serializer(instance=instance).data
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """ """
        owner = self.request.user
        return serializer.save(owner=owner)


from rest_framework.response import Response


class CutoutView(APIView):
    """
    # Home da API deve retornar os metadados do serviço.
    """

    # authentication_classes = [authentication.TokenAuthentication]
    # permission_classes = [permissions.IsAdminUser]

    def get(self, request, format=None):
        """
        Return a list of all users.
        """
        return Response({"message": "Hello, world!"})


# https://github.com/lsst-sqre/vo-cutouts/blob/main/src/vocutouts/handlers/external.py#L204
cutout_schema = extend_schema(
    parameters=[
        OpenApiParameter(
            name="id",
            # title="Source ID",
            description=("Identifiers of images from which to make a cutout. This parameter is mandatory."),
            type=str,
            default="des_dr2",
            many=False,
        ),
        OpenApiParameter(
            name="pos",
            type=str,
            allow_blank=True,
            many=False,
            default="CIRCLE 36.30911 -10.18749 2",
            # default="RANGE 12 14 34 36",
            # default="POLYGON 12 34 14 34 14 36 12 36",
            description=(
                "Positions to cut out. Supported parameters are RANGE followed"
                " by min and max ra and min and max dec; CIRCLE followed by"
                " ra, dec, and radius; and POLYGON followed by a list of"
                " ra/dec positions for vertices. Arguments must be separated"
                " by spaces and parameters are double-precision floating point"
                " numbers expressed as strings."
            ),
        ),
        # OpenApiParameter(
        #     name="circle",
        #     type=str,
        #     allow_blank=True,
        #     many=True,
        #     # title="Cutout positions",
        #     description=(
        #         "Circles to cut out. The value must be the ra and dec of the"
        #         " center of the circle and then the radius, as"
        #         " double-precision floating point numbers expressed as"
        #         " strings and separated by spaces."
        #     ),
        # ),
        # OpenApiParameter(
        #     name="polygon",
        #     type=str,
        #     allow_blank=True,
        #     many=True,
        #     # title="Cutout positions",
        #     description=(
        #         "Polygons to cut out. The value must be ra/dec pairs for each"
        #         " vertex, ordered so that the polygon winding direction is"
        #         " counter-clockwise (when viewed from the origin towards the"
        #         " sky). These parameters are double-precision floating point"
        #         " numbers expressed as strings and separated by spaces."
        #     ),
        # ),
        OpenApiParameter(
            name="runid",
            type=str,
            allow_blank=True,
            many=False,
            description=(
                "An opaque string that is returned in the job metadata and"
                " job listings. Maybe used by the client to associate jobs"
                " with specific larger operations."
            ),
        ),
        OpenApiParameter(
            name="format",
            type=str,
            allow_blank=False,
            many=False,
            default="fits",
            description=("fits or png"),
        ),
        OpenApiParameter(
            name="band",
            type=str,
            allow_blank=False,
            many=False,
            description=("One of grizY"),
        )
        # TODO: Band estudar a implementacao do parametro BAND. IVOA/SODA/WD-SODA 3.2.2
    ],
)


@extend_schema_view(get=cutout_schema, post=cutout_schema)
class SyncCutoutView(APIView):
    """Synchronously request a cutout. This will wait for the cutout to be
    completed and return the resulting image as a FITS file.
    (The image will be returned via a redirect to a URL at the underlying object store.)
    """

    # authentication_classes = [authentication.TokenAuthentication]
    # permission_classes = [permissions.IsAdminUser]

    def sync_cutout(self, user: User, params: List[JobParameter], run_id: Optional[str]):
        # policy = ImageCutoutPolicy()
        job_service = JobService()
        job = job_service.create(user=user, params=params, run_id=run_id)
        job_service.start(user, job_id=job.id)

        # from cutout.service.cutout_parameters import CutoutParameters
        # from cutout.service.models import Job
        # from cutout.service.uws.models import _convert_job

        # sqljob = Job.objects.get(pk=3)

        # job = _convert_job(sqljob)
        # print(job)

        # cutout_params = CutoutParameters.from_job_parameters(job.parameters)
        # print(cutout_params)

        # TODO: Criar a classe ImageCutoutPolicy para ser usada no Job Service.
        # Criar o metodo dispath
        # https://github.com/lsst-sqre/vo-cutouts/blob/56ca1ba7a0bb3a85dfb873c0f9153c70e52adbce/src/vocutouts/policy.py#L12

        #     format = params.get("format", "fits")

        #     if params["id"] == "des_dr2":
        #         pos_params = self.parse_pos_param(params["pos"])
        #         pos_params = pos_params[0]

        #         band = params.get("band", "g")
        #         # TODO: png coloridas com banda fixa gri.
        #         if format == "png":
        #             band = "gri"
        #         else:
        #             allowed_bands = ["g", "r", "i", "z", "Y"]
        #             if band not in allowed_bands:
        #                 raise ParseError(f"Band parameter must be one of {', '.join(allowed_bands)}")

        #         if pos_params["shape"] == "circle":
        #             filename = "{:.5f}_{:.5f}_{}.{}".format(
        #                 round(pos_params["ra"], 5), round(pos_params["dec"], 5), band, format
        #             )
        #             filepath = Path("/data/results").joinpath(filename)

        #             result = des_cutout_circle.delay(
        #                 ra=pos_params["ra"],
        #                 dec=pos_params["dec"],
        #                 size_arcmin=pos_params["size"],
        #                 band=band,
        #                 format=format,
        #                 path=str(filepath),
        #             )
        #             result.wait(timeout=25)  # seconds
        #             resultfile = Path(result.get())

        #         mimetype = "application/fits"
        #         if params["format"] == "png":
        #             mimetype = "image/x-png"

        #         fp = open(resultfile, "rb")
        #         response = FileResponse(fp, content_type=mimetype, as_attachment=True)
        #         response["Content-Length"] = resultfile.stat().st_size
        #         response["Content-Disposition"] = f"attachment; filename={escape_uri_path(resultfile.name)}"
        #         return response
        # parameters = [p.to_dict() for p in params]
        return Response({"success": True})

    def get(self, request, format=None):
        """
        Sync cutout get
        """
        # Todos os parametros pra lower case.
        params = []
        run_id = None
        for key, value in request.query_params.items():
            if key.lower() == "runid":
                run_id = value
            else:
                params.append(JobParameter(parameter_id=key.lower(), value=value, is_post=False))

        return self.sync_cutout(user=request.user, params=params, run_id=run_id)


# @extend_schema_view(get=cutout_schema, post=cutout_schema)
# class SyncCutoutView(APIView):
#     """Synchronously request a cutout. This will wait for the cutout to be
#     completed and return the resulting image as a FITS file.
#     (The image will be returned via a redirect to a URL at the underlying object store.)
#     """

#     # authentication_classes = [authentication.TokenAuthentication]
#     # permission_classes = [permissions.IsAdminUser]

#     # Yield successive n-sized
#     # chunks from l.
#     def divide_chunks(self, l, n):
#         # looping till length l
#         for i in range(0, len(l), n):
#             yield l[i : i + n]

#     # def create_task(self, params):
#     def parse_pos_param(self, pos: str) -> list[dict]:
#         shape = pos.split()[0]
#         pos = pos.replace(shape, "")
#         shape = shape.lower()
#         positions = pos.split(",")
#         result = []

#         if shape == "circle":
#             for p in positions:
#                 params = p.strip().split()
#                 result.append(
#                     {"shape": shape, "ra": float(params[0]), "dec": float(params[1]), "size": float(params[2])}
#                 )
#         elif shape == "range":
#             for p in positions:
#                 params = p.strip().split()
#                 result.append({"shape": shape, "ra": [params[0], params[1]], "dec": [params[2], params[3]]})
#         elif shape == "polygon":
#             for p in positions:
#                 params = [float(value) for value in p.strip().split()]
#                 x = list(self.divide_chunks(params, 2))
#                 # cada elemento é um par [ra, dec]
#                 result.append({"shape": shape, "positions": x})

#         else:
#             raise ParseError("POS xtype can take one of the three values circle, range and polygon")
#         return result

#     def sync_cutout(self, user, params):
#         format = params.get("format", "fits")

#         if params["id"] == "des_dr2":
#             pos_params = self.parse_pos_param(params["pos"])
#             pos_params = pos_params[0]

#             band = params.get("band", "g")
#             # TODO: png coloridas com banda fixa gri.
#             if format == "png":
#                 band = "gri"
#             else:
#                 allowed_bands = ["g", "r", "i", "z", "Y"]
#                 if band not in allowed_bands:
#                     raise ParseError(f"Band parameter must be one of {', '.join(allowed_bands)}")

#             if pos_params["shape"] == "circle":
#                 filename = "{:.5f}_{:.5f}_{}.{}".format(
#                     round(pos_params["ra"], 5), round(pos_params["dec"], 5), band, format
#                 )
#                 filepath = Path("/data/results").joinpath(filename)

#                 result = des_cutout_circle.delay(
#                     ra=pos_params["ra"],
#                     dec=pos_params["dec"],
#                     size_arcmin=pos_params["size"],
#                     band=band,
#                     format=format,
#                     path=str(filepath),
#                 )
#                 result.wait(timeout=25)  # seconds
#                 resultfile = Path(result.get())

#             mimetype = "application/fits"
#             if params["format"] == "png":
#                 mimetype = "image/x-png"

#             fp = open(resultfile, "rb")
#             response = FileResponse(fp, content_type=mimetype, as_attachment=True)
#             response["Content-Length"] = resultfile.stat().st_size
#             response["Content-Disposition"] = f"attachment; filename={escape_uri_path(resultfile.name)}"
#             return response

#         # source_id = params["id"]
#         # band = params["band"]
#         # format = params.get("format", "fits")
#         # runid = params.get("runid", None)

#         # return Response(
#         #     {
#         #         "user": user.username,
#         #         "params": params,
#         #         # "source_id": source_id,
#         #         # "band": band,
#         #         # "format": format,
#         #         # "runid": runid,
#         #         "message": "Hello, world!",
#         #     }
#         # )

#     def get(self, request, format=None):
#         """
#         Sync cutout get
#         """
#         return self.sync_cutout(request.user, request.query_params)

#         # return Response(self.parse_pos_param(request.query_params["pos"]))

#     # TODO: Implementar o mesmo metodo usando post
#     # def post(self, request):
#     #     """
#     #     Sync cutout post
#     #     """
#     #     print(request)
#     #     print(request.data)
#     #     return self.sync_cutout(request.user, request.data)


# @api_view(["GET", "POST"])
# def hello_world(request):
#     if request.method == "POST":
#         return Response({"message": "Got some data!", "data": request.data})
#     return Response({"message": "Hello, world!"})


# class TesteView(generics.ListAPIView):
#     """
#     View to list all users in the system.

#     * Requires token authentication.
#     * Only admin users are able to access this view.
#     """

#     authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         return

#     def get_serializer_class(self):
#         return

#     def get(self, request, format=None):
#         """
#         Return a list of all users.
#         """
#         # usernames = [user.username for user in User.objects.all()]
#         return Response({"teste": True})
