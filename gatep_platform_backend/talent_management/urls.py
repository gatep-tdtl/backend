
from django.urls import path
from talent_management.views import (
    ResumeBuilderAPIView, ResumeReviewAPIView , SkillGapAnalysisAPIView , CareerRoadmapAPIView )
# from employer_management.views import (ApplicationListCreateView, ApplicationDetailView,
#                                         SaveJobView, UnsaveJobView, ListSavedJobsView, JobPostingListCreateView,JobListWithMatchingScoreAPIView)

urlpatterns = [
    # 🔹 Resume Builder
    path('resume-builder/', ResumeBuilderAPIView.as_view(), name='resume-builder'),
    #############vaishnavi#######33
    path('resume/review/', ResumeReviewAPIView.as_view(), name='resume_review'),
    path('resume/skill-gap/', SkillGapAnalysisAPIView.as_view(), name='skill_gap_analysis'),
    path('resume/career-roadmap/', CareerRoadmapAPIView.as_view(), name='career_roadmap'),

    # 🔹 Applications (Talent-side submission)
    # path('applications/', ApplicationListCreateView.as_view(), name='application-list-create'),
    # path('applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),

   
    # path('job-postings/', JobPostingListCreateView.as_view(), name='jobposting-list-create'),
    # path('job-postings/ai-score/', JobListWithMatchingScoreAPIView.as_view(), name='jobposting-ai-score'),

]
