import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.urls import reverse

from cutout.users.models import User
from cutout.users.saml2 import LineaSaml2Backend
from cutout.users.views import saml2_template_failure

pytestmark = pytest.mark.django_db


def dummy_get_response(request: HttpRequest):
    return None


def make_request_with_session(rf: RequestFactory, **session_data):
    request = rf.get("/saml2/acs/")
    SessionMiddleware(dummy_get_response).process_request(request)
    for key, value in session_data.items():
        request.session[key] = value
    return request


class TestLineaSaml2Backend:
    def test_clean_user_main_attribute(self):
        backend = LineaSaml2Backend()
        assert backend.clean_user_main_attribute("john.doe") == "john_doe"
        assert backend.clean_user_main_attribute("johndoe") == "johndoe"

    @pytest.mark.parametrize(
        "attributes,expected",
        [
            ({"uid": ["john.doe"]}, "john_doe"),
            ({"uid": ["johndoe"]}, "johndoe"),
            ({}, None),
            ({"uid": []}, None),
            ({"uid": ["None"]}, None),
            ({"uid": [""]}, None),
            ({"uid": "not-a-list"}, None),
        ],
    )
    def test_get_user_identifier(self, attributes, expected):
        backend = LineaSaml2Backend()
        assert backend.get_user_identifier(attributes) == expected

    def test_extract_user_identifier_params(self):
        backend = LineaSaml2Backend()
        assert backend._extract_user_identifier_params({}, {"uid": ["john.doe"]}, {}) == ("username", "john_doe")
        assert backend._extract_user_identifier_params({}, {}, {}) == ("username", None)

    def test_is_authorized(self):
        backend = LineaSaml2Backend()
        assert backend.is_authorized({"uid": ["john.doe"]}, {}, "idp", {}) is True
        assert backend.is_authorized({}, {}, "idp", {}) is False

    def test_user_can_authenticate(self, user: User):
        backend = LineaSaml2Backend()
        assert backend.user_can_authenticate(user) is True
        user.is_active = False
        assert backend.user_can_authenticate(user) is False

    def test_authenticate_without_session_info(self, rf: RequestFactory):
        backend = LineaSaml2Backend()
        request = make_request_with_session(rf)
        assert backend.authenticate(request, session_info=None, attribute_mapping={}) is None

    def test_authenticate_without_ava(self, rf: RequestFactory):
        backend = LineaSaml2Backend()
        request = make_request_with_session(rf)
        assert backend.authenticate(request, session_info={"issuer": "idp"}, attribute_mapping={}) is None

    def test_authenticate_without_uid_sets_needs_registration(self, rf: RequestFactory):
        backend = LineaSaml2Backend()
        request = make_request_with_session(rf)
        session_info = {"issuer": "idp", "ava": {"schacProjectMembership": ["rubin_oidc"]}}

        assert backend.authenticate(request, session_info=session_info, attribute_mapping={}) is None
        assert request.session["needs_registration"] is True
        assert request.session["idp_name"] == "rubin_oidc"

    def test_setup_groups_syncs_saml_groups(self, user: User):
        backend = LineaSaml2Backend()
        user.groups.add(Group.objects.create(name="old-group"))

        backend.setup_groups(user, {"member": ["des-collaboration"]})

        group_names = set(user.groups.values_list("name", flat=True))
        assert group_names == {"saml2", "des-collaboration"}

    @override_settings(INTERNAL_GROUPS=["Editors"])
    def test_setup_groups_keeps_internal_groups(self, user: User):
        backend = LineaSaml2Backend()
        user.groups.add(Group.objects.create(name="Editors"))
        user.groups.add(Group.objects.create(name="old-group"))

        backend.setup_groups(user, {"member": []})

        group_names = set(user.groups.values_list("name", flat=True))
        assert group_names == {"saml2", "Editors"}


class TestSaml2TemplateFailure:
    def test_linea_need_registration(self, rf: RequestFactory):
        request = make_request_with_session(rf, needs_registration=True, idp_name="cilogon")
        response = saml2_template_failure(request)
        assert response.status_code == 403
        assert b"LIneA Account Required" in response.content

    def test_rubin_need_registration(self, rf: RequestFactory):
        request = make_request_with_session(rf, needs_registration=True, idp_name="rubin_oidc")
        response = saml2_template_failure(request)
        assert response.status_code == 403
        assert b"Vera Rubin Users" in response.content

    @pytest.mark.parametrize("user_status", ["PendingApproval", "Pending"])
    def test_waiting_approval(self, rf: RequestFactory, user_status):
        request = make_request_with_session(rf, user_status=user_status)
        response = saml2_template_failure(request)
        assert response.status_code == 403
        assert b"Waiting Approval" in response.content

    def test_login_error_fallback(self, rf: RequestFactory):
        request = make_request_with_session(rf)
        response = saml2_template_failure(request)
        assert response.status_code == 403
        assert b"Login Error" in response.content

    def test_empty_session_does_not_raise(self, rf: RequestFactory):
        # Regressão: sessão sem idp_name (ACS falhou antes do backend rodar) não pode dar KeyError.
        request = rf.get("/saml2/acs/")
        SessionMiddleware(dummy_get_response).process_request(request)
        response = saml2_template_failure(request)
        assert response.status_code == 403


class TestSamlDisabledWiring:
    def test_saml_not_in_settings(self):
        assert settings.AUTH_SAML2_ENABLED is False
        assert "djangosaml2" not in settings.INSTALLED_APPS
        assert "cutout.users.saml2.LineaSaml2Backend" not in settings.AUTHENTICATION_BACKENDS
        assert "djangosaml2.middleware.SamlSessionMiddleware" not in settings.MIDDLEWARE

    def test_saml_urls_not_mounted(self, client):
        assert client.get("/saml2/metadata/").status_code == 404
        assert client.get("/login/").status_code == 404

    def test_allauth_login_still_available(self, client):
        response = client.get(reverse("account_login"))
        assert response.status_code == 200

    def test_settings_export_context_processor(self, client):
        # A home renderiza com o processor django_settings_export sem levantar exceção.
        response = client.get(reverse("home"))
        assert response.status_code == 200
        assert response.context["settings"]["AUTH_SAML2_ENABLED"] is False
