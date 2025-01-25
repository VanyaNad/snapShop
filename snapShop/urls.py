from django.contrib import admin
from django.urls import path, include
from shop.views import ProductListView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', ProductListView.as_view(), name='product_list'),
    path('custom-admin/', include('shop.urls')),
]
