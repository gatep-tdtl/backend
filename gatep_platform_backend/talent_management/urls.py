
from django.urls import path
from talent_management.views import (
    CulturalPreparationAPIView, MockInterviewReportView, MockInterviewStartView, MockInterviewSubmitAnswerView, MockInterviewVerifyIdentityView, ResumeBuilderAPIView, ResumeReviewAPIView, SalaryInsightsAPIView , SkillGapAnalysisAPIView , CareerRoadmapAPIView, TrendingSkillsListView )
# from employer_management.views import (ApplicationListCreateView, ApplicationDetailView,
#                                         SaveJobView, UnsaveJobView, ListSavedJobsView, JobPostingListCreateView,JobListWithMatchingScoreAPIView)

urlpatterns = [
    # 🔹 Resume Builder
    path('resume-builder/', ResumeBuilderAPIView.as_view(), name='resume-builder'),
    #############vaishnavi#######33
    path('resume/review/', ResumeReviewAPIView.as_view(), name='resume_review'),
    path('resume/skill-gap/', SkillGapAnalysisAPIView.as_view(), name='skill_gap_analysis'),
    path('resume/career-roadmap/', CareerRoadmapAPIView.as_view(), name='career_roadmap'),

    path('trending-skills/', TrendingSkillsListView.as_view(), name='trending-skills-list'),
    path('cultural-preparation/', CulturalPreparationAPIView.as_view(), name='cultural-preparation'),
    # 🔹 AI Salary Insight
    path('ai/salary-insights/', SalaryInsightsAPIView.as_view(), name='ai-salary-insights'),

###################### interview bot urls ##########################333
    path('mock-interview/start/', MockInterviewStartView.as_view(), name='mock-interview-start'),
    path('mock-interview/verify-identity/', MockInterviewVerifyIdentityView.as_view(), name='mock-interview-verify-identity'),
    path('mock-interview/submit-answer/', MockInterviewSubmitAnswerView.as_view(), name='mock-interview-submit-answer'),
    path('mock-interview/report/<int:pk>/', MockInterviewReportView.as_view(), name='mock-interview-report'), # To retrieve final report

]
