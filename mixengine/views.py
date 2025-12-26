import pandas as pd
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import cloudinary.uploader
from rest_framework.viewsets import ModelViewSet

from mixengine.models import ProductOrder, Sample, ProductMixResult
from mixengine.serializers import ProductOrderSerializer, ProductOrderCreateSerializer, ProductMixResultSerializer, \
    SampleSerializer, ProductOrderDetailSerializer
from mixengine.tasks import process_sample_upload
from utility.pagination import SamplePagination


class SampleViewSet(ModelViewSet):
    queryset = Sample.objects.all().order_by('-last_updated')
    serializer_class = SampleSerializer
    pagination_class = SamplePagination

    permission_classes = [IsAuthenticated]

    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'lot_number']
    ordering_fields = ['name', 'cp', 'last_updated']


class ProductOrderViewSet(viewsets.ViewSet):
    """
    Handles:
    - GET /api/orders/         -> List all orders
    - GET /api/orders/{id}/    -> Retrieve single order
    - POST /api/orders/optimize/ -> Custom action to optimize mix
    - PATCH /api/orders/{id}/  -> Update an order (target_cp or total_bags)
    - DELETE /api/orders/{id}/ -> Delete an order
    """
    permission_classes = [IsAuthenticated, ]

    def list(self, request):
        orders = ProductOrder.objects.all().order_by('-created_at')
        serializer = ProductOrderSerializer(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        try:
            order = ProductOrder.objects.get(pk=pk)
        except ProductOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        serializer = ProductOrderDetailSerializer(order)

        return Response({
            "order_id": order.id,
            "total_bags": order.total_bags,
            "targets": order.targets,
            "final_values": order.final_values,
            "variances": order.variances,
            "mix": serializer.data["mix"],
        })

    def partial_update(self, request, pk=None):
        try:
            order = ProductOrder.objects.get(pk=pk)
        except ProductOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        serializer = ProductOrderSerializer(order, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def destroy(self, request, pk=None):
        try:
            order = ProductOrder.objects.get(pk=pk)
            order.delete()
            return Response({"message": "Order deleted successfully."}, status=204)
        except ProductOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

    @action(detail=False, methods=['post'], url_path='optimize')
    def optimize(self, request):
        """
        Custom POST endpoint:
        POST /api/orders/optimize/
        Input: { "target_cp": 58.0, "total_bags": 100 }
        """
        serializer = ProductOrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            result_data = serializer.save()  # optimization + saving logic in serializer
            return Response(result_data, status=201)
        return Response(serializer.errors, status=400)


class ProductMixResultViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling CRUD operations on ProductMixResult model.
    Provides endpoints for listing, retrieving, creating, updating, and deleting
    ProductMixResult instances, which represent the optimized sample mix for a product order.
    """
    queryset = ProductMixResult.objects.all()
    serializer_class = ProductMixResultSerializer

    permission_classes = [IsAuthenticated]  # Restrict access to authenticated users

    def get_queryset(self):
        """
        Optionally filter ProductMixResult instances by order_id if provided in query params.
        Example: GET /api/mix-results/?order_id=2
        """
        queryset = super().get_queryset()
        order_id = self.request.query_params.get('order_id')
        if order_id:
            queryset = queryset.filter(order__id=order_id)
        return queryset


class SampleUploadView(APIView):
    """
    Upload CSV or Excel sheet to populate Sample data
    - Updates existing samples if name and lot number match
    - Creates new samples otherwise
    - Uses transaction to ensure atomicity
    """

    def get(self, request):
        """
        Download a template CSV file with required columns and example rows
        """
        # Define the required columns in exact order
        columns = [
            'Sample', 'Date', 'Lot.No', 'M', 'CP', 'FAT',
            'TVBN', 'Ash', 'FFA', 'Bags', 'Fiber'
        ]

        # Optional: Add a few example rows to help users
        example_data = [
            {
                'Sample': 'Fish Meal Local',
                'Date': '23.12.2025',  # format: DD.MM.YYYY
                'Lot.No': 'FM-2025-001',
                'M': 10.2,  # Moisture
                'CP': 64.5,  # Crude Protein
                'FAT': 11.8,
                'TVBN': 135.0,
                'Ash': 19.5,
                'FFA': 9.2,
                'Bags': 80,
                'Fiber': 1.8
            },
            {
                'Sample': 'Hypro Fish',
                'Date': '20.12.2025',
                'Lot.No': 'HYPRO-DEC01',
                'M': 9.8,
                'CP': 70.0,
                'FAT': 15.0,
                'TVBN': 100.0,
                'Ash': 16.0,
                'FFA': 5.0,
                'Bags': 50,
                'Fiber': 1.0
            },
            # Add more examples if you want, or leave empty
        ]

        # Create DataFrame
        df = pd.DataFrame(example_data, columns=columns)

        # If you want completely empty (just headers), use:
        # df = pd.DataFrame(columns=columns)

        # Create HTTP response with CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sample_upload_template.csv"'

        df.to_csv(path_or_buf=response, index=False, encoding='utf-8')

        return response

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file uploaded"}, status=400)

        MAX_UPLOAD_SIZE = 50 * 1024 * 1024
        if file.size > MAX_UPLOAD_SIZE:
            return Response({"error": "File too large"}, status=400)

        # Upload to Cloudinary as RAW file
        upload_result = cloudinary.uploader.upload(
            file,
            resource_type="raw",
            folder="mixengine_uploads"
        )

        file_url = upload_result["secure_url"]

        # Send URL to Celery (NOT local path)
        task = process_sample_upload.delay(file_url)

        return Response({
            "message": "Upload received. Processing in background.",
            "task_id": task.id
        }, status=202)
