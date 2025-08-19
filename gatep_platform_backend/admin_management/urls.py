# File: gatep_platform_backend/admin_management/urls.py

from django.urls import path # Corrected 'rom' to 'from'
# No need to import DefaultRouter if you're not using it

from .views import (
    
    AdminDashboardAPIView,
    GlobalOverviewAPIView,
    TalentHeatmapAPIView,
    TalentHeatmapDashboardRoleAndCertification,
    TalentHeatmapInstituteWiseAPIView,
    UserDashboardAPIView,
    
      # Your ViewSet
)

app_name = 'admin_management' # Good practice for namespacing

urlpatterns = [
    # Dashboard Summary APIView
    # path('dashboard/summary/', DashboardSummaryAPIView.as_view(), name='dashboard-summary'),###not working
   # path('dashboard/analytics/', AdminDashboardAnalyticsView.as_view(), name='admin_dashboard_analytics'),
    # Global Dashboard Overview APIView
    path('dashboard/global-overview/', GlobalOverviewAPIView.as_view(), name='global-dashboard-overview'),
    
   #path('dashboard/filter-options/', DashboardFilterOptionsAPIView.as_view(), name='dashboard-filter-options'),
    path('dashboard/admin/', AdminDashboardAPIView.as_view(), name='admin-dashboard'),
    # User Management APIView (for listing/creating and retrieving/updating/deleting)
    path('users/', UserDashboardAPIView.as_view(), name='user-list-create'),
    path('users/<int:pk>/', UserDashboardAPIView.as_view(), name='user-detail'),
   # path('api/dashboard/',dashboard_api, name='dashboard-api'),
    path('talent-heatmap/', TalentHeatmapAPIView.as_view(), name='talent-heatmap'), # not working because of userrole not found
    path('talent_heatmap/RoleAndCertifications/' , TalentHeatmapDashboardRoleAndCertification.as_view(), name='talent-heatmap-role-and-certifications'),
    path('talent-heatmap-institute-wise/', TalentHeatmapInstituteWiseAPIView.as_view(), name='talent-heatmap-institute-wise') , # done
   # path('admin/analytics-dashboard/', AdminAnalyticsDashboardAPIView.as_view(), name='admin-analytics-dashboard'),  # Added AdminAnalyticsDashboardAPIView
 # Renamed for clarity
    # System Health Status ViewSet - Manually defined URLs for list/create and detail operations
    # For listing all system health statuses (GET) and creating a new one (POST)
   


    # For retrieving a single system health status (GET), updating (PUT),
    # partial updating (PATCH), and deleting (DELETE)
    
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



