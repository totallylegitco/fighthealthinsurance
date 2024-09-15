import io
import json
from rest_framework.views import APIView
from rest_framework.response import Response

from fighthealthinsurance.common_view_logic import *
from fighthealthinsurance.rest_serializers import *


class RemoveData(APIView):
    def delete(self, request):
        pythondata = json.loads(request.body)
        # in below line convert python data to complex data type :- de-serialization
        serializer=DeleteDataSerializer(data=pythondata) 
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            RemoveDataHelper.remove_data_for_email(email)
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
