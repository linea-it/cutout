import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home_mounts_cutout_root(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="cutout-root"' in content
    assert "frontend/assets/main.js" in content
    assert 'data-authenticated="false"' in content
