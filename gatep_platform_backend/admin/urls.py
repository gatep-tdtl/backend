from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, get_filter_choices

router = DefaultRouter()
router.register(r'admin/users', UserViewSet, basename='admin-users')

urlpatterns = [
    path('', include(router.urls)),
    path('admin/users/filters/', get_filter_choices),
]

