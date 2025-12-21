import pandas as pd
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from mixengine.models import ProductOrder, Sample, ProductMixResult
from mixengine.serializers import ProductOrderSerializer, ProductOrderCreateSerializer, ProductMixResultSerializer


class ProductOrderViewSet(viewsets.ViewSet):
    """
    Handles:
    - GET /api/orders/         -> List all orders
    - GET /api/orders/{id}/    -> Retrieve single order
    - POST /api/orders/optimize/ -> Custom action to optimize mix
    - PATCH /api/orders/{id}/  -> Update an order (target_cp or total_bags)
    - DELETE /api/orders/{id}/ -> Delete an order
    """
    permission_classes = [IsAuthenticated,]

    def list(self, request):
        orders = ProductOrder.objects.all().order_by('-created_at')
        serializer = ProductOrderSerializer(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        try:
            order = ProductOrder.objects.get(pk=pk)
        except ProductOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        serializer = ProductOrderSerializer(order)
        return Response(serializer.data)

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

    # permission_classes = [IsAuthenticated]  # Restrict access to authenticated users

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

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file uploaded."}, status=400)

        try:
            # Read file
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            elif file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            else:
                return Response({"error": "Unsupported file format. Use CSV or Excel."}, status=400)

            required_columns = [
                'Sample', "Date", "Lot.No", "M", 'CP', 'FAT',
                'TVBN', 'Ash', 'FFA', 'Bags', 'Fiber'
            ]
            for col in required_columns:
                if col not in df.columns:
                    return Response({"error": f"Missing required column: {col}"}, status=400)

            created = 0
            updated = 0

            with transaction.atomic():
                for _, row in df.iterrows():
                    # Convert date to datetime, handling NaT
                    date_value = pd.to_datetime(row['Date'], format='%d.%m.%Y', errors='coerce')
                    production_date = None if pd.isna(date_value) else date_value

                    obj, is_created = Sample.objects.update_or_create(
                        name=row['Sample'],
                        lot_number=row['Lot.No'],   # ✅ match both name & lot
                        defaults={
                            'production_date': production_date,
                            'moisture': row['M'],
                            'cp': row['CP'],
                            'fat': row['FAT'],
                            'tvbn': row['TVBN'],
                            'ash': row['Ash'],
                            'ffa': row['FFA'],
                            'bags_available': row['Bags'],
                            'fiber': row['Fiber']      # ✅ new column added
                        }
                    )
                    if is_created:
                        created += 1
                    else:
                        updated += 1

            return Response({
                "message": "Upload successful.",
                "created": created,
                "updated": updated
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

