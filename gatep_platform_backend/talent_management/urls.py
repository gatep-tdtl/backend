
from django.urls import path
from talent_management.views import (
     AudioTranscriptionView, CulturalPreparationAPIView, FullInterviewPhotoCheckAPIView, MalpracticeDetectionView, MockInterviewReportListView, MockInterviewReportView, MockInterviewStartView, MockInterviewSubmitAnswerView, MockInterviewVerifyIdentityView, RecommendedSkillsView, ResumeBuilderAPIView, ResumeDocumentAPIView, ResumeReviewAPIView, SalaryInsightsAPIView , SkillGapAnalysisAPIView , CareerRoadmapAPIView )
# from employer_management.views import (ApplicationListCreateView, ApplicationDetailView,
#                                         SaveJobView, UnsaveJobView, ListSavedJobsView, JobPostingListCreateView,JobListWithMatchingScoreAPIView)
from talent_management import views
urlpatterns = [
    # 🔹 Resume Builder
    path('resume-builder/', ResumeBuilderAPIView.as_view(), name='resume-builder'),
    #############vaishnavi#######33
    path('resume/review-talent/', ResumeReviewAPIView.as_view(), name='resume_review'),
    path('resume/skill-gap/', SkillGapAnalysisAPIView.as_view(), name='skill_gap_analysis'),
    path('resume/career-roadmap/', CareerRoadmapAPIView.as_view(), name='career_roadmap'),
    path("upload-cert-photo/", views.upload_certification_photo, name="upload_cert_photo"),
    path("resume-documents/",  ResumeDocumentAPIView.as_view(), name="get_resume_documents"),
    path("resume-documents/<int:pk>/", ResumeDocumentAPIView.as_view(), name="get_resume_document_by_id"),

    path('trending-skills/', RecommendedSkillsView.as_view(), name='trending-skills-list'),
    path('ai/cultural-preparation/', CulturalPreparationAPIView.as_view(), name='cultural-preparation'),
    # 🔹 AI Salary Insight
    path('ai/salary-insights/', SalaryInsightsAPIView.as_view(), name='ai-salary-insights'),

###################### interview bot urls ##########################
    path('mock-interview/start/', MockInterviewStartView.as_view(), name='mock-interview-start'),
    path('mock-interview/verify-identity/', MockInterviewVerifyIdentityView.as_view(), name='mock-interview-verify-identity'),
    path('mock-interview/submit-answer/', MockInterviewSubmitAnswerView.as_view(), name='mock-interview-submit-answer'),
    path('mock-interview/report/<int:pk>/', MockInterviewReportView.as_view(), name='mock-interview-report'), # To retrieve final report
    path('mock-interview/malpractice/', MalpracticeDetectionView.as_view(), name='mock_interview_malpractice'),
    path('transcribe-audio/', AudioTranscriptionView.as_view(), name='transcribe-audio'),
    path('malpractice-check/' , FullInterviewPhotoCheckAPIView.as_view(), name='malpractice-check'),
    path('mock-interview/reports/', MockInterviewReportListView.as_view(), name='mock-interview-report-list'),
]
