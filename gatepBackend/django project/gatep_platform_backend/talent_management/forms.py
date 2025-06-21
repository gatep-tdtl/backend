# talent_management/forms.py
from django import forms

class ResumeForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)
    summary = forms.CharField(widget=forms.Textarea)
    skills = forms.CharField(widget=forms.Textarea)
    experience = forms.CharField(widget=forms.Textarea)
    certifications = forms.CharField(widget=forms.Textarea)
    preferences = forms.CharField(widget=forms.Textarea)
    resume_pdf = forms.FileField()
