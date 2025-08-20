from django.urls import path
from employer_management.views import (
    ApplicationDeleteView, ApplicationStatusUpdateView, CloseJobPostingView, CombinedDashboardView, CompanyListCreateView, CompanyDetailView, EmployerAnalyticsDemographicAPIView, EmployerAnalyticsTrendsAPIView, EmployerCompanyUpdateView, EmployerDashboardAPIView, EmployerTalentJobMatchScoreAPIView, HiringAnalyticsDashboardViewSet, InterviewFeedbackView, InterviewStatusUpdateView,
    JobPostingListCreateView, JobPostingDetailView,
    ApplicationListCreateView, ApplicationDetailView,
    InterviewListCreateView, InterviewDetailView, PotentialCandidateMatchView, PublishJobPostingView,
    SaveJobView, TalentInterviewListView, UnsaveJobView, ListSavedJobsView,
    EmployerApplicationListForJobView, EmployerApplicationDetailView,
    JobListWithMatchingScoreAPIView,
    EmployerCompanyView , EmployerCompanyDetailView
)

urlpatterns = [
    # Company Management
    path('companies/', CompanyListCreateView.as_view(), name='company-list-create'),
    path('companies/<int:pk>/', CompanyDetailView.as_view(), name='company-detail'),
    path('mycompany/' , EmployerCompanyDetailView.as_view(), name='my-company-detail'),
    path('update-company/', EmployerCompanyUpdateView.as_view(), name='update-company'),

    # Job Postings
    path('job-postings/', JobPostingListCreateView.as_view(), name='jobposting-list-create'),
    path('job-postings/<int:pk>/', JobPostingDetailView.as_view(), name='jobposting-detail'),

    # Application Management (for talents)
    path('applications/', ApplicationListCreateView.as_view(), name='application-list-create'),
    path('applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),
    path('applications/<int:pk>/update-status/', ApplicationStatusUpdateView.as_view(), name='application-update-status'),
    path('applications/<int:pk>/delete/', ApplicationDeleteView.as_view(), name='application-delete'),

    # Employer-Specific Applications
    path('job-postings/<int:job_posting_id>/applications/', EmployerApplicationListForJobView.as_view(), name='employer-job-applications-list'),
    path('job-postings/<int:job_posting_id>/applications/<int:pk>/', EmployerApplicationDetailView.as_view(), name='employer-job-application-detail'),
    path('jobpostings/<int:pk>/publish/', PublishJobPostingView.as_view(), name='jobposting-publish'),
    path('jobpostings/<int:pk>/close/', CloseJobPostingView.as_view(), name='jobposting-close'),
    path('job-postings/<int:job_posting_id>/potential-candidates/', PotentialCandidateMatchView.as_view(), name='job-potential-candidates'),
    # Interviews
    path('interviews/', InterviewListCreateView.as_view(), name='interview-list-create'),
    path('interviews/<int:pk>/', InterviewDetailView.as_view(), name='interview-detail'),
    path('talent/interviews/', TalentInterviewListView.as_view(), name='talent-interview-list'),
    path('interviews/<int:pk>/update-status/', InterviewStatusUpdateView.as_view(), name='interview-update-status'),
    path('interviews/<int:interview_pk>/submit-feedback/', InterviewFeedbackView.as_view(), name='submit-interview-feedback'),
    path('interviews/<int:interview_pk>/feedback/', InterviewFeedbackView.as_view(), name='interview-feedback'),
   # 🔹 Saved Jobs
    path('saved-jobs/', ListSavedJobsView.as_view(), name='saved-jobs-list'),
    path('saved-jobs/save/', SaveJobView.as_view(), name='save-job'),
    path('saved-jobs/unsave/', UnsaveJobView.as_view(), name='unsave-job'),

    # this is for talent 
    path('job-postings/ai-score/', JobListWithMatchingScoreAPIView.as_view(), name='jobposting-ai-score'),
  
    # AI Score to Talent
     path('job-postings/ai-score-totalent/<int:job_posting_id>/<int:application_id>/', EmployerTalentJobMatchScoreAPIView.as_view(),  name='job-application-ai-score'),

    # Employer Company
    path('my-company/', EmployerCompanyView.as_view(), name='employer-company'),


    path('hiring-analytics/combined-dashboard/', CombinedDashboardView.as_view(),name='hiring-analytics-combined-dashboard'),
    path('hiring-analytics/top-matching-candidates/',HiringAnalyticsDashboardViewSet.as_view({'get': 'top_matching_candidates'}),name='hiring-analytics-top-candidates'),
    path('employer-dashboard/', EmployerDashboardAPIView.as_view(), name='employer-dashboard'),
    path('employer-analytics/demographic/', EmployerAnalyticsDemographicAPIView.as_view(), name='employer-analytics-demographic'),
    path('employer-analytics/trends', EmployerAnalyticsTrendsAPIView.as_view(), name='employer-analytics-job-posting-performance')
]
    