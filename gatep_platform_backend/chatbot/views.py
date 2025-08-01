from django.shortcuts import render

# Create your views here.
# chatbot/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .services import ChatbotService

# class ChatbotAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, *args, **kwargs):
#         # --- MODIFICATION START ---
#         user_query = request.data.get('query')
#         # Get the language from the request, default to 'English' if not provided
#         language = request.data.get('language', 'English') 
#         # --- MODIFICATION END ---

#         if not user_query:
#             return Response(
#                 {"error": "Query parameter is missing."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         current_user = request.user

#         try:
#             bot_service = ChatbotService(user=current_user)
#             # --- MODIFICATION START ---
#             # Pass the language to the service method
#             bot_response = bot_service.handle_conversation(user_query, language)
#             # --- MODIFICATION END ---
            
#             return Response(bot_response, status=status.HTTP_200_OK)
#         except Exception as e:
#             print(f"Error in ChatbotAPIView: {e}")
#             return Response(
#                 {"error": "An unexpected error occurred on the server."},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )



from groq import APIStatusError 
class ChatbotAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user_query = request.data.get('query')
        language = request.data.get('language', 'English')

        if not user_query:
            return Response(
                {"error": "Query parameter is missing."},
                status=status.HTTP_400_BAD_REQUEST
            )

        current_user = request.user

        try:
            bot_service = ChatbotService(user=current_user)
            bot_response = bot_service.handle_conversation(user_query, language)
            return Response(bot_response, status=status.HTTP_200_OK)

        # --- MODIFICATION STARTS HERE ---
        except APIStatusError as e:
            # This will catch specific errors from the Groq API
            print(f"Groq API Error in ChatbotAPIView: {e.status_code} - {e.response}")
            
            # Check for the specific restriction error
            if e.status_code == 400 and 'organization_restricted' in str(e.response):
                 return Response(
                    {"error": "The chatbot service is temporarily unavailable due to an account issue. Please contact support."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE # 503 is more appropriate here
                )
            
            # For other API errors, return a generic message
            return Response(
                {"error": "The chatbot service returned an error. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY # 502 indicates an issue with an upstream server
            )
        # --- MODIFICATION ENDS HERE ---

        except Exception as e:
            # This is a catch-all for any other unexpected errors in your code
            print(f"General Error in ChatbotAPIView: {e}")
            return Response(
                {"error": "An unexpected error occurred on the server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )