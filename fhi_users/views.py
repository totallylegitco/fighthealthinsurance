from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

class PasswordResetFinishView(APIView):
    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        try:
            reset_token = ResetToken.objects.get(token=token)
            user = reset_token.user

            # Check if new password is same as current
            if user.check_password(new_password):
                return Response(
                    {"status": "failure", "message": "New password must be different from current password"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate password strength
            try:
                validate_password(new_password)
            except ValidationError as e:
                return Response(
                    {"status": "failure", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Rest of your existing code...

        except ResetToken.DoesNotExist:
            return Response(
                {"status": "failure", "message": "Invalid reset token"},
                status=status.HTTP_400_BAD_REQUEST
            )

class PasswordResetRequestView(APIView):
    def post(self, request):
        username = request.data.get('username')
        domain_name = request.data.get('domain')
        phone = request.data.get('phone')

        try:
            user = get_user_by_username_and_domain_or_phone(username, domain_name, phone)
            
            if not user.is_active:
                return Response(
                    {"status": "failure", "message": "Account is inactive"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Rest of your existing code...

        except User.DoesNotExist:
            return Response(
                {"status": "failure", "message": "User not found"},
                status=status.HTTP_400_BAD_REQUEST
            ) 