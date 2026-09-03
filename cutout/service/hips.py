from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_GET

from cutout.service.bands import assert_path_under_root
from cutout.service.policies import can_request_cutout
from cutout.service.surveys import LSST_DP1_ID


def _hips_root() -> Path:
    return Path(settings.CUTOUT_HIPS_LSST_DP1_ROOT)


@require_GET
def lsst_dp1_hips(request, relpath: str):
    """Serve LSST DP1 HiPS tiles on the Cutout origin (same session as the UI)."""
    if not can_request_cutout(user=request.user, survey_id=LSST_DP1_ID):
        return HttpResponseForbidden("Forbidden")

    relative = Path(relpath)
    if relative.is_absolute() or ".." in relative.parts:
        raise Http404("Invalid HiPS path")

    root = _hips_root()
    if not root.is_dir():
        raise Http404("HiPS root is not mounted")

    try:
        target = assert_path_under_root(root / relative, root, label="hips root")
    except ValueError:
        raise Http404("Invalid HiPS path") from None

    if not target.is_file():
        raise Http404("HiPS file not found")

    content_type, _encoding = mimetypes.guess_type(str(target))
    if relpath.endswith("properties"):
        content_type = "text/plain"
    return FileResponse(target.open("rb"), content_type=content_type or "application/octet-stream")
