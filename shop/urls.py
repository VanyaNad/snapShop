from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from .views import (
    ProductListView,
    PurchaseListView,
    CreatePurchaseView,
    RequestReturnView,
    ReturnRequestsListView,
    RegisterView,
    AdminDashboardView,
    ManageProductsView,
    ManageReturnRequestsView,
    EditProductView,
    AddProductView,
    DeleteProductView,
)

urlpatterns = [
    path('', ProductListView.as_view(), name='product_list'),
    path('purchases/', PurchaseListView.as_view(), name='purchase_list'),
    path('purchase/<int:product_id>/', CreatePurchaseView.as_view(), name='create_purchase'),
    path('return/<int:purchase_id>/', RequestReturnView.as_view(), name='request_return'),
    path('admin/return_requests/', ReturnRequestsListView.as_view(), name='return_requests'),
    path('login/', LoginView.as_view(template_name='shop/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('custom-admin/', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('custom-admin/products/', ManageProductsView.as_view(), name='manage_products'),
    path('custom-admin/add-product/', AddProductView.as_view(), name='add_product'),
    path('custom-admin/edit-product/<int:pk>/', EditProductView.as_view(), name='edit_product'),
    path('custom-admin/manage-return', ManageReturnRequestsView.as_view(), name='manage_return_requests'),
    path('custom-admin/products/delete/<int:pk>/', DeleteProductView.as_view(), name='delete_product'),

]
