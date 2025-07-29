from django.shortcuts import render

# Create your views here.
# chatbot/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .services import ChatbotService

class ChatbotAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # --- MODIFICATION START ---
        user_query = request.data.get('query')
        # Get the language from the request, default to 'English' if not provided
        language = request.data.get('language', 'English') 
        # --- MODIFICATION END ---

        if not user_query:
            return Response(
                {"error": "Query parameter is missing."},
                status=status.HTTP_400_BAD_REQUEST
            )

        current_user = request.user

        try:
            bot_service = ChatbotService(user=current_user)
            # --- MODIFICATION START ---
            # Pass the language to the service method
            bot_response = bot_service.handle_conversation(user_query, language)
            # --- MODIFICATION END ---
            
            return Response(bot_response, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error in ChatbotAPIView: {e}")
            return Response(
                {"error": "An unexpected error occurred on the server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )