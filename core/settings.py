"""
Django settings for eapts_backend project.
"""

from pathlib import Path
from decouple import config
import socket
import os

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# ============================================
# SERVER CONFIGURATION - SINGLE SOURCE OF TRUTH
# ============================================
SERVER_IP = config("SERVER_IP", default="localhost")
SERVER_PORT = config("SERVER_PORT", default="8000")
BASE_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
FRONTEND_URL = config("APP_URL", default=f"http://{SERVER_IP}:80")

# Security and Debug
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)

# Get the server's actual IP addresses
def get_server_ips():
    """Get all IP addresses of the server"""
    ips = []
    try:
        hostname = socket.gethostname()
        ips.append(socket.gethostbyname(hostname))
        
        # Get all network interfaces
        try:
            import netifaces
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr:
                            ips.append(addr['addr'])
        except ImportError:
            # netifaces not installed, just use basic IP
            pass
    except Exception as e:
        print(f"Error getting server IPs: {e}")
    
    return list(set(ips))  # Remove duplicates

SERVER_IPS = get_server_ips()

# Allowed hosts - FIXED: Add all possible IPs
ALLOWED_HOSTS = [
    SERVER_IP,
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    socket.gethostname(),
    socket.gethostbyname(socket.gethostname()),
    *SERVER_IPS,
]

# ============================================
# DHIS2 CONFIGURATION
# ============================================
DHIS2_BASE_URL = config("DHIS2_BASE_URL", default="https://dhisanalytics.moh.gov.et/api/40")
DHIS2_USERNAME = config("DHIS2_USERNAME", default="EthioDHIS")
DHIS2_PASSWORD = config("DHIS2_PASSWORD", default="EthioDHIS_pass")
DHIS2_DEFAULT_DATATYPE = config("DHIS2_DEFAULT_DATATYPE", default=1, cast=int)
DHIS2_MAPPING_SOURCE = config("DHIS2_MAPPING_SOURCE", default=2, cast=int)
DHIS2_DATA_ELEMENT_CLASS = config("DHIS2_DATA_ELEMENT_CLASS", default=1, cast=int)
DHIS2_PARENT_DATA_ELEMENT = config("DHIS2_PARENT_DATA_ELEMENT", default=167, cast=int)
DHIS2_PARENT_INDICATOR = config("DHIS2_PARENT_INDICATOR", default=168, cast=int)

# ============================================
# DHIS2 VALUE SERVICE CONFIGURATION
# ============================================
DHIS2_TIMEOUT = config("DHIS2_TIMEOUT", default=30, cast=int)
DHIS2_CACHE_TTL = config("DHIS2_CACHE_TTL", default=300, cast=int)
DHIS2_CACHE_MAX_ENTRIES = config("DHIS2_CACHE_MAX_ENTRIES", default=1000, cast=int)

# ============================================
# CACHE CONFIGURATION
# ============================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'data-element-value-cache',
        'TIMEOUT': DHIS2_CACHE_TTL,
        'OPTIONS': {
            'MAX_ENTRIES': DHIS2_CACHE_MAX_ENTRIES
        }
    }
}

# Optional: Use Redis for better performance in production
if not DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/1',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }

# ============================================
# LOGGING CONFIGURATION
# ============================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'dhis2_values.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.data_element.services': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True,
        },
        'apps.data_element.views': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True,
        },
    },
}

# Create logs directory if it doesn't exist
logs_dir = BASE_DIR / 'logs'
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# Installed Apps
INSTALLED_APPS = [
    # Core
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'rest_framework.authtoken',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',

    # Your Apps
    'apps.inventory',
    'apps.locations',
    'apps.person',
    'apps.data_element',
    'apps.aggregate',
    'apps.encounter',
    'apps.address',
]

# Middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ============================================
# CORS CONFIGURATION - FIXED
# ============================================
def get_cors_origins():
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1:80",
        FRONTEND_URL,
        BASE_URL,
    ]
    
    # Add frontend URLs from environment if available
    frontend_urls = config("FRONTEND_URLS", default="").split(",")
    for url in frontend_urls:
        if url.strip():
            origins.append(url.strip())
    
    # Add all server IP variations
    for ip in SERVER_IPS:
        origins.append(f"http://{ip}:3000")  # React dev server
        origins.append(f"http://{ip}:80")     # Production frontend
        origins.append(f"http://{ip}")         # Just the IP
        origins.append(f"http://{ip}:{SERVER_PORT}")  # Backend
    
    # Remove duplicates and None values
    origins = [origin for origin in origins if origin]
    return list(set(origins))

CORS_ALLOWED_ORIGINS = get_cors_origins()
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only in debug mode
CORS_ALLOW_CREDENTIALS = True  # CRITICAL: This allows cookies

CORS_ALLOW_METHODS = [
    'DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]

CORS_EXPOSE_HEADERS = ['content-type', 'x-csrftoken', 'set-cookie']  # Added set-cookie
CORS_PREFLIGHT_MAX_AGE = 86400

# ============================================
# CSRF CONFIGURATION - FIXED
# ============================================
CSRF_TRUSTED_ORIGINS = [
    BASE_URL,
    FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1:80",
]

# Add ALL IP variations to CSRF trusted origins
for ip in SERVER_IPS:
    CSRF_TRUSTED_ORIGINS.append(f"http://{ip}:8000")  # Backend
    CSRF_TRUSTED_ORIGINS.append(f"http://{ip}:3000")  # Frontend dev
    CSRF_TRUSTED_ORIGINS.append(f"http://{ip}:80")    # Frontend prod
    CSRF_TRUSTED_ORIGINS.append(f"http://{ip}")       # Just IP

# Remove duplicates
CSRF_TRUSTED_ORIGINS = list(set(CSRF_TRUSTED_ORIGINS))

# CSRF cookie settings - FIXED for IP addresses
CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript to read it
CSRF_COOKIE_SECURE = False     # Set to True only with HTTPS
CSRF_COOKIE_SAMESITE = 'Lax'   # Changed from 'None' to 'Lax' for better compatibility
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
CSRF_COOKIE_DOMAIN = None      # Don't set domain for IP addresses - CRITICAL!

# Session settings - FIXED for IP addresses
SESSION_COOKIE_SECURE = False  # Set to True only with HTTPS
SESSION_COOKIE_SAMESITE = 'Lax'  # Changed from 'None' to 'Lax'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_DOMAIN = None    # Don't set domain for IP addresses - CRITICAL!
SESSION_COOKIE_AGE = 1209600    # 2 weeks in seconds
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session expiry on each request

# URLs
ROOT_URLCONF = 'core.urls'

# ============================================
# REST FRAMEWORK CONFIGURATION
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.OrderingFilter',
    ],
    
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'authentication': '5/minute',
        'user_actions': '10/minute',
    },
}

# Swagger/OpenAPI configuration
SPECTACULAR_SETTINGS = {
    'TITLE': 'Health‑Dosé Backend API',
    'DESCRIPTION': 'Health‑Dosé is the unified, intelligent, and completely interoperable Digital Health Ecosystem.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# Templates
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

# WSGI
WSGI_APPLICATION = 'core.wsgi.application'

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST"),
        "PORT": config("POSTGRES_PORT"),
    }
}

# Custom user model
AUTH_USER_MODEL = 'person.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# DEBUG OUTPUT
# ============================================
if DEBUG:
    print("\n" + "="*50)
    print("SERVER CONFIGURATION")
    print("="*50)
    print(f"SERVER_IP: {SERVER_IP}")
    print(f"BASE_URL: {BASE_URL}")
    print(f"FRONTEND_URL: {FRONTEND_URL}")
    print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
    print(f"CORS_ALLOWED_ORIGINS: {CORS_ALLOWED_ORIGINS}")
    print(f"CSRF_TRUSTED_ORIGINS: {CSRF_TRUSTED_ORIGINS}")
    print("="*50 + "\n")