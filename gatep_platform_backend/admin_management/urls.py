# File: gatep_platform_backend/admin_management/urls.py

from django.urls import path # Corrected 'rom' to 'from'
# No need to import DefaultRouter if you're not using it

from .views import (
    UserDashboardAPIView,
    DashboardSummaryAPIView,GlobalDashboardOverviewAPIView,
    SystemHealthStatuSViewSet,dashboard_api  # Your ViewSet
)

app_name = 'admin_management' # Good practice for namespacing

urlpatterns = [
    # Dashboard Summary APIView
    path('dashboard/summary/', DashboardSummaryAPIView.as_view(), name='dashboard-summary'),

    # Global Dashboard Overview APIView
    path('dashboard/global-overview/',GlobalDashboardOverviewAPIView.as_view(), name='global-dashboard-overview'),

    # User Management APIView (for listing/creating and retrieving/updating/deleting)
    path('users/', UserDashboardAPIView.as_view(), name='user-list-create'),
    path('users/<int:pk>/', UserDashboardAPIView.as_view(), name='user-detail'),
    path('api/dashboard/',dashboard_api, name='dashboard-api'),
 # Renamed for clarity

    # System Health Status ViewSet - Manually defined URLs for list/create and detail operations
    # For listing all system health statuses (GET) and creating a new one (POST)
    path('system-health/', SystemHealthStatuSViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='system-health-list'),


    # For retrieving a single system health status (GET), updating (PUT),
    # partial updating (PATCH), and deleting (DELETE)
    path('system-health/<int:pk>/', SystemHealthStatuSViewSet.as_view({ # Removed stray 'lpatterns = [' and ']'
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='system-health-detail'),
]













# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from .views import UserViewSet, get_filter_choices

# router = DefaultRouter()
# router.register(r'admin/users', UserViewSet, basename='admin-users')

# urlpatterns = [
#     path('', include(router.urls)),
#     path('admin/users/filters/', get_filter_choices),
# ]



