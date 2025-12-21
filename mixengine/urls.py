from django.urls import path
from rest_framework.routers import DefaultRouter

from mixengine.views import ProductOrderViewSet, SampleUploadView, ProductMixResultViewSet

router = DefaultRouter()
router.register(r'orders', ProductOrderViewSet, basename='orders')
router.register(r'mix-results', ProductMixResultViewSet, basename='mix-results')

urlpatterns = router.urls + [
    path('upload-samples/', SampleUploadView.as_view(), name='upload-samples'),
]
