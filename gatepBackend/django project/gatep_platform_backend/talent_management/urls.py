from django.urls import path
from talent_management.views import (
    ResumeBuilderAPIView,)
from employer_management.views import (ApplicationListCreateView, ApplicationDetailView,
                                        SaveJobView, UnsaveJobView, ListSavedJobsView, JobPostingListCreateView,JobListWithMatchingScoreAPIView)

urlpatterns = [
    # 🔹 Resume Builder
    path('resume-builder/', ResumeBuilderAPIView.as_view(), name='resume-builder'),

    # 🔹 Applications (Talent-side submission)
    path('applications/', ApplicationListCreateView.as_view(), name='application-list-create'),
    path('applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),

    # 🔹 Saved Jobs
    path('saved-jobs/', ListSavedJobsView.as_view(), name='saved-jobs-list'),
    path('saved-jobs/save/', SaveJobView.as_view(), name='save-job'),
    path('saved-jobs/unsave/', UnsaveJobView.as_view(), name='unsave-job'),
    path('job-postings/', JobPostingListCreateView.as_view(), name='jobposting-list-create'),
    path('job-postings/ai-score/', JobListWithMatchingScoreAPIView.as_view(), name='jobposting-ai-score'),
]
