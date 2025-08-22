from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _
 
class BeaconTokenAuthentication(JWTAuthentication):
    """
    A custom JWT authentication class for Django REST Framework.
 
    This class extends the standard JWTAuthentication to allow JWT tokens to be
    passed via a query parameter, specifically for use cases like the browser's
    `navigator.sendBeacon()` API, which cannot send custom Authorization headers.
 
    Authentication Process:
    1. It first attempts to extract the token from the 'auth_token' query
       parameter in the request URL.
    2. If a token is found in the query parameter, it attempts to validate it.
       If validation is successful, the user is authenticated.
    3. If no token is found in the query parameter (or if it's empty), it
       falls back to the default behavior of `JWTAuthentication`, which is to
       look for the token in the 'Authorization' HTTP header.
 
    This dual approach ensures that the endpoint remains compatible with both
    standard API clients and beacon-style requests.
    """
 
    def authenticate(self, request):
        """
        The entry point for the authentication process.
        """
        # Attempt to get the token from the 'auth_token' query parameter
        token_from_query = request.query_params.get('auth_token')
 
        # If a token is present in the query parameter, use it for authentication
        if token_from_query:
            try:
                # Use the parent class's method to validate the raw token
                validated_token = self.get_validated_token(token_from_query)
               
                # Use the parent class's method to get the user from the validated token
                user = self.get_user(validated_token)
               
                if not user:
                    # This case should ideally not be hit if get_user is standard
                    raise AuthenticationFailed(_("User not found"), code="user_not_found")
                   
                # Return the authenticated user and the token
                return (user, validated_token)
 
            except (InvalidToken, TokenError) as e:
                # If the token is invalid for any reason, raise an authentication error
                raise AuthenticationFailed(
                    _("Token is invalid or expired (from query parameter)"),
                    code="token_not_valid",
                ) from e
       
        # If no token was found in the query parameter, proceed with the default
        # authentication method (which checks the Authorization header).
        # The `super().authenticate(request)` call handles the header-based logic.
        return super().authenticate(request)