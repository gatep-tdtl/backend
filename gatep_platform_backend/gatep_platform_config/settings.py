# File: gatep_platform_backend/gatep_platform_config/settings.py

import os
from pathlib import Path
# ... other settings ...
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv() # This loads environment variables from .env
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-k)ai!jgwt66@6m8^t5pe#&3^y+%6er4bf+#isst%59oyad*j_2'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist', # For JWT logout functionality
    'talent_management',  # Your custom user app
    'auth_management',    # Your authentication API app
    'employer_management',
    'admin_management',   # Your admin management app
    'chatbot',  # Your chatbot app
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    'django.middleware.csrf.CsrfViewMiddleware',
]

# Ensure ROOT_URLCONF and WSGI_APPLICATION refer to the new config folder name
ROOT_URLCONF = 'gatep_platform_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Ensure WSGI_APPLICATION refers to the new config folder name
WSGI_APPLICATION = 'gatep_platform_config.wsgi.application'


#Database - Using user's provided values from the image and explicit request
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'gatep_platform_db',
        'USER': 'dbmasteruser',
        'PASSWORD': 'database9014',
        'HOST': 'ls-f8259bafe38561c18d0d411f37aefbfabc0ff7bf.citdgny2wnek.ap-south-1.rds.amazonaws.com',  # or your database host
        'PORT': '3306',# or your database port
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
        },
    }
}


# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'gatep_platform_db',
#         'USER': 'root',
#         'PASSWORD': 'manager',
#         'HOST': 'localhost',  # or your database host
#         'PORT': '3306',# or your database port
#         'OPTIONS': {
#             'init_command': "SET sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
#         },
#     }
# }

# Password validation (standard Django validators)
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Custom User Model - point to your CustomUser in 'talent_management'
AUTH_USER_MODEL = 'talent_management.CustomUser'


# Email Configuration for OTP sending - MODIFIED to use SMTP
# For development, 'django.core.mail.backends.console.EmailBackend' prints emails to the console.
# UNCOMMENT THE LINE BELOW AND COMMENT OUT THE CONSOLE BACKEND LINE TO SEND REAL EMAILS
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' # Changed to SMTP backend
# # EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' # Comment out or remove this line

# EMAIL_HOST = 'smtp.gmail.com' # Your email provider's SMTP host
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'rctemp19@gmail.com' # Your actual sending email address
# EMAIL_HOST_PASSWORD = 'nkli finf mjfi tear' # Your email password or app-specific password

# DEFAULT_FROM_EMAIL = 'rctemp19@gmail.com' # Your default 'from' email address

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.hostinger.com'
EMAIL_PORT = 587  # Change to the appropriate port
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'support@thedatatechlabs.com'
EMAIL_HOST_PASSWORD = 'Tdtl@2025#'
DEFAULT_FROM_EMAIL = 'support@thedatatechlabs.com'




HFF_TOKEN = os.environ.get("HFF_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


# Django REST Framework settings to use JWT as the default authentication
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

# Simple JWT specific settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=5),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': 'tdtl',
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# Media files (for uploads like resume PDFs)
MEDIA_URL = '/media/'
# BASE_MEDIA_URL = 'https://tdtlworld.com/gatep-backend/media/'  # Change to your actual media URL in production
BASE_MEDIA_URL = 'http://127.0.1:8000/media/'  # Change to your actual media URL in production
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# CORS_ALLOW_ALL_ORIGINS = True

# # CORS_ALLOWED_ORIGINS = [
# #     "http://localhost:3000",
# #     "http://127.0.0.1:3000",
# #     "http://your-production-domain.com",
# # ]

# CORS_ALLOW_CREDENTIALS = True


# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:8000",
#     "http://127.0.0.1:8000",
#     "http://127.0.0.1:5500", # Common port for VS Code Live Server
#     "http://localhost:3000",
#     "https://tdtlworld.com/"
#     "null",
# ]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5500", # Common port for VS Code Live Server
    "http://localhost:3000",
    "https://tdtlworld.com",
    "null",
]



# This is the key setting that allows the browser to send cookies.
CORS_ALLOW_CREDENTIALS = True

# Allow the headers your frontend will be sending. 'Authorization' is for JWT.
CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# 2. COOKIES: Configure cookies for cross-site requests.
# The browser will only send cookies cross-site if SameSite is 'None'.
SESSION_COOKIE_SAMESITE = 'None'
# The browser also REQUIRES that a cookie with SameSite='None' be 'Secure'.
SESSION_COOKIE_SECURE = True

# This is needed for Django to trust the 'X-Forwarded-Proto' header from a proxy
# if you are running behind something like Nginx in production. It's safe to set.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')