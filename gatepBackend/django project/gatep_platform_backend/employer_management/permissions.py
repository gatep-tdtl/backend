# employer_management/permissions.py

from rest_framework import permissions
from talent_management.models import UserRole, TalentProfile
from .models import Company, JobPosting, Application, Interview

class IsEmployerUser(permissions.BasePermission):
    """
    Allows access only to users with the EMPLOYER role.
    """
    def has_permission(self, request, view):
        return hasattr(request.user, 'user_role') and request.user.user_role == UserRole.EMPLOYER

class IsCompanyOwner(permissions.BasePermission):
    """
    Allows access only to the owner of the company.
    """
    def has_object_permission(self, request, view, obj):
        # obj is a Company instance
        return obj.user == request.user

class IsJobPostingOwner(permissions.BasePermission):
    """
    Allows access only to the owner of the job posting (the employer who owns the company).
    """
    def has_object_permission(self, request, view, obj):
        # obj is a JobPosting instance
        return hasattr(request.user, 'employer_company') and obj.company == request.user.employer_company

class IsApplicationOwnerOrJobOwner(permissions.BasePermission):
    """
    Allows access to the talent who owns the application or the employer who owns the job posting.
    """
    def has_object_permission(self, request, view, obj):
        # obj is an Application instance
        if hasattr(request.user, 'user_role'):
            if request.user.user_role == UserRole.TALENT:
                # For talent, check if they are the applicant
                return obj.talent == request.user
            elif request.user.user_role == UserRole.EMPLOYER:
                # For employer, check if they own the company for the job posting
                return hasattr(request.user, 'employer_company') and obj.job_posting.company == request.user.employer_company
        return False

class IsInterviewParticipantOrJobOwner(permissions.BasePermission):
    """
    Allows access to the interviewer, the talent, or the employer who owns the job posting.
    """
    def has_object_permission(self, request, view, obj):
        # obj is an Interview instance
        if hasattr(request.user, 'user_role'):
            if request.user.user_role == UserRole.TALENT:
                # For talent, check if they are the applicant
                return obj.application.talent == request.user
            elif request.user.user_role == UserRole.EMPLOYER:
                # For employer, check if they own the company for the job posting
                return hasattr(request.user, 'employer_company') and obj.application.job_posting.company == request.user.employer_company
        # Also allow the interviewer themselves
        return obj.interviewer == request.user
