import pytest
from django.contrib.auth.models import Group
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from cutout.service.hips import lsst_dp1_hips
from cutout.service.surveys import LSST_DP1_GROUP

pytestmark = pytest.mark.django_db


def _url(relpath: str = "properties") -> str:
    return reverse("hips-lsst-dp1", kwargs={"relpath": relpath})


def test_hips_anonymous_forbidden(client, settings, tmp_path):
    settings.CUTOUT_HIPS_LSST_DP1_ROOT = str(tmp_path)
    (tmp_path / "properties").write_text("ok")
    response = client.get(_url())
    assert response.status_code == 403


def test_hips_authenticated_without_group_forbidden(user, settings, tmp_path):
    settings.CUTOUT_HIPS_LSST_DP1_ROOT = str(tmp_path)
    (tmp_path / "properties").write_text("ok")
    request = RequestFactory().get(_url())
    request.user = user
    response = lsst_dp1_hips(request, "properties")
    assert response.status_code == 403


def test_hips_with_group_serves_file(user, settings, tmp_path):
    settings.CUTOUT_HIPS_LSST_DP1_ROOT = str(tmp_path)
    (tmp_path / "properties").write_text("hips ok")
    group, _ = Group.objects.get_or_create(name=LSST_DP1_GROUP)
    user.groups.add(group)
    request = RequestFactory().get(_url())
    request.user = user
    response = lsst_dp1_hips(request, "properties")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"hips ok"


def test_hips_rejects_path_traversal(user, settings, tmp_path):
    settings.CUTOUT_HIPS_LSST_DP1_ROOT = str(tmp_path)
    (tmp_path.parent / "secret.txt").write_text("nope")
    group, _ = Group.objects.get_or_create(name=LSST_DP1_GROUP)
    user.groups.add(group)
    request = RequestFactory().get(_url("../secret.txt"))
    request.user = user
    with pytest.raises(Http404):
        lsst_dp1_hips(request, "../secret.txt")
