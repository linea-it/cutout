import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView

User = get_user_model()


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        assert self.request.user.is_authenticated  # for mypy to know that the user is authenticated
        return self.request.user.get_absolute_url()

    def get_object(self):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("users:detail", kwargs={"username": self.request.user.username})


user_redirect_view = UserRedirectView.as_view()


def linea_login(request):
    """Página de login LIneA / Rubin (escolha do IdP)."""
    return render(request, "pages/linea_login.html")


def saml2_template_failure(request, exception=None, status=403, **kwargs):
    """Renderiza template simples com mensagem de erro SAML2."""
    logger = logging.getLogger("djangosaml2")
    logger.info("saml2_template_failure()")
    logger.info(f"exception: {exception}")

    idp_name = request.session.get("idp_name")
    needs_registration = request.session.get("needs_registration", False)
    user_status = request.session.get("user_status")

    logger.info(f"idp_name: {idp_name} needs_registration: {needs_registration} user_status: {user_status}")

    # Se o usuário não tem uid LIneA, encaminha para a página de registro
    if needs_registration:
        if idp_name == "rubin_oidc":
            logger.info("Redirecting to Rubin registration page.")
            return render(
                request,
                "djangosaml2/rubin_need_registration.html",
                {"exception": exception},
                status=status,
            )

        logger.info("Redirecting to LIneA registration page.")
        return render(
            request,
            "djangosaml2/linea_need_registration.html",
            {"exception": exception},
            status=status,
        )

    # Se o cadastro ainda não foi aprovado, encaminha para a página de aguardando aprovação
    if user_status in ["PendingApproval", "Pending"]:
        logger.info(f"User status is {user_status}. Redirecting to waiting approval error page.")
        return render(
            request,
            "djangosaml2/waiting_approval.html",
            {"exception": exception},
            status=status,
        )

    return render(request, "djangosaml2/login_error.html", {"exception": exception}, status=status)
