"""
Base settings to build other settings files upon.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# cutout/
APPS_DIR = BASE_DIR / "cutout"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
LOGGING_LEVEL = env.str("DJANGO_LOG_LEVEL", "INFO")
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('pt-br', _('Português')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.humanize", # Handy template tags
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "cutout.users",
    "cutout.service",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "cutout.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "home"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "cutout.users.context_processors.allauth_settings",
                "django_settings_export.settings_export",
            ],
        },
    }
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Daniel Roy Greenfeld""", "daniel-roy-greenfeld@cutout.linea.org.br")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOG_DIR = Path("/logs")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(message)s"},
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": LOGGING_LEVEL,
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR.joinpath("django.log"),
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
        "django_db": {
            "level": LOGGING_LEVEL,
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR.joinpath("django_db.log"),
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
        "cutout": {
            "level": LOGGING_LEVEL,
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR.joinpath("cutout.log"),
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
        "djangosaml2": {
            "level": LOGGING_LEVEL,
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR.joinpath("djangosaml2.log"),
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
    },
    "root": {"level": LOGGING_LEVEL, "handlers": ["console"]},
    "loggers": {
        "django": {
            "level": LOGGING_LEVEL,
            "handlers": ["file"],
            "propagate": False,
        },
        "django.db.backends": {
            "level": LOGGING_LEVEL,
            "handlers": ["django_db"],
            "propagate": False,
        },
        "cutout": {
            "level": LOGGING_LEVEL,
            "handlers": ["cutout", "console"],
            "propagate": False,
        },
        "djangosaml2": {
            "level": LOGGING_LEVEL,
            "handlers": ["djangosaml2", "console"],
            "propagate": False,
        },
    },
}

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_TIME_LIMIT = 5 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_SOFT_TIME_LIMIT = 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT = True
# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_AUTHENTICATION_METHOD = "username"
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_EMAIL_REQUIRED = True
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# https://django-allauth.readthedocs.io/en/latest/configuration.html
ACCOUNT_ADAPTER = "cutout.users.adapters.AccountAdapter"
# https://django-allauth.readthedocs.io/en/latest/forms.html
ACCOUNT_FORMS = {"signup": "cutout.users.forms.UserSignupForm"}
# https://django-allauth.readthedocs.io/en/latest/configuration.html
SOCIALACCOUNT_ADAPTER = "cutout.users.adapters.SocialAccountAdapter"
# https://django-allauth.readthedocs.io/en/latest/forms.html
SOCIALACCOUNT_FORMS = {"signup": "cutout.users.forms.UserSocialSignupForm"}
# django-compressor
# ------------------------------------------------------------------------------
# https://django-compressor.readthedocs.io/en/latest/quickstart/#installation
INSTALLED_APPS += ["compressor"]
STATICFILES_FINDERS += ["compressor.finders.CompressorFinder"]
# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),  # Disable Brownsable API
    "URL_FORMAT_OVERRIDE": None,  # Disable format parameter behavior https://www.django-rest-framework.org/api-guide/format-suffixes/#query-parameter-formats
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
CORS_URLS_REGEX = r"^/api/.*$"

# By Default swagger ui is available only to admin user(s). You can change permission classes to change that
# See more configuration options at https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS = {
    "TITLE": "cutout API",
    "DESCRIPTION": "Documentation of API endpoints of cutout",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}
# Your stuff...
# ------------------------------------------------------------------------------
# Autenticação Django SAML2 (djangosaml2)
# ------------------------------------------------------------------------------
# SAML não pode ser testado localmente. Com a flag desligada (default) nada de
# SAML é carregado e o login continua pelo admin/allauth.
AUTH_SAML2_ENABLED = env.bool("AUTH_SAML2_ENABLED", default=False)

# URLs de login com SAML2/CILogon. Exemplo:
# https://cutout.linea.org.br/saml2/login/?idp=https://satosa.linea.org.br/linea/proxy/aHR0cHM6Ly9jaWxvZ29uLm9yZw==
LINEA_LOGIN_URL = env.str("LINEA_LOGIN_URL", default="/admin/login/?next=/")
RUBIN_LOGIN_URL = env.str("RUBIN_LOGIN_URL", default="/admin/login/?next=/")

# URL de registro para os diferentes IdPs.
LINEA_REGISTER_URL = env.str(
    "LINEA_REGISTER_URL",
    default="https://register-dev.linea.org.br/Shibboleth.sso/Login?SAMLDS=1&target=https://register-dev.linea.org.br/registry/co_petitions/start/coef:155&entityID=https://satosa.linea.org.br/linea/proxy/aHR0cHM6Ly9jaWxvZ29uLm9yZw==",  # noqa: E501
)
RUBIN_REGISTER_URL = env.str(
    "RUBIN_REGISTER_URL",
    default="https://register-dev.linea.org.br/Shibboleth.sso/Login?SAMLDS=1&target=https://register-dev.linea.org.br/registry/co_petitions/start/coef:231&entityID=https://satosa-dev.linea.org.br/linea_saml_mirror/proxy/aHR0cHM6Ly9kYXRhLmxzc3QuY2xvdWQ=",  # noqa: E501
)

# Grupos gerenciados no Django admin que o sync de grupos SAML nunca remove.
INTERNAL_GROUPS = env.list("INTERNAL_GROUPS", default=[])

# ------------------------------------------------------------------------------
# AppBar — links externos configuráveis por ambiente (dev/staging/prod).
# ------------------------------------------------------------------------------
NAVBAR_IDAC_URL = env.str("NAVBAR_IDAC_URL", default="https://scienceplatform-dev.linea.org.br/idac")
NAVBAR_DATA_URL = env.str("NAVBAR_DATA_URL", default="https://data.linea.org.br/")
NAVBAR_DOCS_URL = env.str("NAVBAR_DOCS_URL", default="https://docs.linea.org.br/")

# django-settings-export: todos os nomes precisam existir com a flag on ou off.
SETTINGS_EXPORT = [
    "AUTH_SAML2_ENABLED",
    "LINEA_LOGIN_URL",
    "LINEA_REGISTER_URL",
    "RUBIN_LOGIN_URL",
    "RUBIN_REGISTER_URL",
    "NAVBAR_IDAC_URL",
    "NAVBAR_DATA_URL",
    "NAVBAR_DOCS_URL",
]

if AUTH_SAML2_ENABLED:
    import saml2

    # FQDN — exemplo: https://cutout.linea.org.br (sem barra final)
    SITE_URL = env.str("SITE_URL")
    FQDN = SITE_URL
    SAML_SP_NAME = env.str("SAML_SP_NAME", default="SP Cutout Service")
    CERT_DIR = BASE_DIR / "config" / "certificates"
    ATTR_DIR = BASE_DIR / "config" / "attribute-maps"

    INSTALLED_APPS += ["djangosaml2"]
    # Backend SAML2 customizado da LIneA
    AUTHENTICATION_BACKENDS += ["cutout.users.saml2.LineaSaml2Backend"]
    MIDDLEWARE += ["djangosaml2.middleware.SamlSessionMiddleware"]

    # Tratamento customizado de falha no ACS SAML2
    # https://djangosaml2.readthedocs.io/contents/developer.html#custom-error-handler
    SAML_ACS_FAILURE_RESPONSE_FUNCTION = "cutout.users.views.saml2_template_failure"
    # Configurações do cookie de sessão
    SAML_SESSION_COOKIE_NAME = "saml_session"
    SESSION_COOKIE_SECURE = True

    # Qualquer view que exige usuário autenticado redireciona o navegador para esta URL
    LOGIN_URL = "/login/"

    # Encerra a sessão quando o usuário fecha o navegador
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False

    # Tipo de binding utilizado
    SAML_DEFAULT_BINDING = saml2.BINDING_HTTP_POST
    SAML_IGNORE_LOGOUT_ERRORS = True

    # Cria usuário Django a partir da asserção SAML se ainda não existir
    SAML_CREATE_UNKNOWN_USER = True

    # https://djangosaml2.readthedocs.io/contents/security.html#content-security-policy
    SAML_CSP_HANDLER = ""

    # LOGIN_REDIRECT_URL permanece "home" (djangosaml2 resolve URL nomeada)

    SAML_ATTRIBUTE_MAPPING = {
        "eduPersonUniqueId": ("username",),
        "cn": ("first_name",),
        "sn": ("last_name",),
        "email": ("email",),
    }

    SAML_CONFIG = {
        # Biblioteca usada para assinatura e criptografia
        "xmlsec_binary": "/usr/bin/xmlsec1",
        "entityid": FQDN + "/saml2/metadata/",
        # Diretório contendo os esquemas de mapeamento de atributo
        "attribute_map_dir": str(ATTR_DIR),
        "description": SAML_SP_NAME,
        "service": {
            "sp": {
                "name": SAML_SP_NAME,
                "ui_info": {
                    "display_name": {"text": SAML_SP_NAME, "lang": "en"},
                    "description": {"text": SAML_SP_NAME, "lang": "en"},
                    "information_url": {"text": FQDN, "lang": "en"},
                    "privacy_statement_url": {"text": FQDN, "lang": "en"},
                },
                "name_id_format": [
                    "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
                    "urn:oasis:names:tc:SAML:2.0:nameid-format:transient",
                ],
                # Indica os endpoints dos serviços fornecidos
                "endpoints": {
                    "assertion_consumer_service": [
                        (FQDN + "/saml2/acs/", saml2.BINDING_HTTP_POST),
                    ],
                    "single_logout_service": [
                        (FQDN + "/saml2/ls/", saml2.BINDING_HTTP_REDIRECT),
                        (FQDN + "/saml2/ls/post", saml2.BINDING_HTTP_POST),
                    ],
                },
                "force_authn": False,
                "name_id_format_allow_create": False,
                # Indica que as respostas de autenticação para este SP devem ser assinadas
                "want_response_signed": True,
                # Indica se as solicitações de autenticação enviadas por este SP devem ser assinadas
                "authn_requests_signed": True,
                # Indica se este SP deseja que o IdP envie as asserções assinadas
                "want_assertions_signed": False,
                "only_use_keys_in_metadata": True,
                "allow_unsolicited": False,
            },
        },
        # Indica onde os metadados podem ser encontrados
        "metadata": {
            "remote": [
                {
                    "url": "https://www.linea.org.br/static/metadata/satosa-prod-frontend-cilogon.xml",
                    "cert": None,
                },
                {
                    "url": "https://www.linea.org.br/static/metadata/satosa-prod-frontend-rubin.xml",
                    "cert": None,
                },
                {
                    "url": "https://www.linea.org.br/static/metadata/satosa-dev-frontend-cilogon.xml",
                    "cert": None,
                },
                {
                    "url": "https://www.linea.org.br/static/metadata/satosa-dev-frontend-rubin.xml",
                    "cert": None,
                },
            ],
        },
        # 1 = mais informações de depuração
        "debug": 1,
        # Assinatura
        "key_file": str(CERT_DIR / "mykey.pem"),  # chave privada
        "cert_file": str(CERT_DIR / "mycert.pem"),  # certificado público
        # Criptografia
        "encryption_keypairs": [
            {
                "key_file": str(CERT_DIR / "mykey.pem"),  # chave privada
                "cert_file": str(CERT_DIR / "mycert.pem"),  # certificado público
            }
        ],
        "contact_person": [
            {
                "given_name": "Service",
                "sur_name": "Desk",
                "company": "LIneA",
                "email_address": "helpdesk@linea.org.br",
                "contact_type": "technical",
            },
        ],
        # Descreve a organização responsável pelo serviço
        "organization": {
            "name": [("LIneA", "pt-br")],
            "display_name": [("LIneA", "pt-br")],
            "url": [("https://www.linea.org.br", "pt-br")],
        },
    }
