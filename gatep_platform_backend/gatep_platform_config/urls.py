from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Import CustomLogoutView from auth_management.views
from auth_management.views import CustomLogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Include auth_management app URLs
    path('api/', include('auth_management.urls')),
    path('api/', include('talent_management.urls')),
    path('api/', include('employer_management.urls')),

    # JWT Authentication Endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/logout/', CustomLogoutView.as_view(), name='token_blacklist'), # Using CustomLogoutView
]
from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)