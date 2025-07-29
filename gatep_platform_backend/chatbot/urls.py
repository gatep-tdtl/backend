# chatbot/urls.py
from django.urls import path
from .views import ChatbotAPIView

urlpatterns = [
    path('query/', ChatbotAPIView.as_view(), name='chatbot_query'),
]
