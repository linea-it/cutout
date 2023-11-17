from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from service.models import JobRequest

from .serializers import JobRequestSerializer


class JobRequestViewSet(ModelViewSet):
    serializer_class = JobRequestSerializer
    queryset = JobRequest.objects.all()

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)

        # Neste ponto executar a função

        data = self.get_serializer(instance=instance).data
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """ """
        owner = self.request.user
        return serializer.save(owner=owner)
