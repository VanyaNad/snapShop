from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.timezone import now
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.generic import ListView, TemplateView, View, CreateView, UpdateView
from .models import Product, Purchase, ReturnRequest, User
from .forms import ReturnRequestForm, RegisterForm, ProductForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin


class SuperuserRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict access to superuser-only views.
    """
    def test_func(self) -> bool:
        return self.request.user.is_superuser


class CreatePurchaseView(View):
    """
    Handles the creation of purchases for logged-in users.
    """
    def post(self, request: HttpRequest, product_id: int) -> HttpResponseRedirect:
        if not request.user.is_authenticated:
            messages.error(request, settings.MESSAGES.get('login_required', "You must be logged in to make a purchase."))
            return redirect('login')

        product = get_object_or_404(Product, id=product_id)
        quantity = int(request.POST.get('quantity', 0))

        if quantity <= 0:
            messages.error(request, settings.MESSAGES.get('invalid_quantity', "Invalid quantity selected."))
        elif quantity > product.stock:
            messages.error(request, settings.MESSAGES.get('insufficient_stock', "Not enough stock available.")
                           .format(stock=product.stock))
        elif (total_price := quantity * product.price) > request.user.wallet:
            messages.error(request, settings.MESSAGES.get('insufficient_funds', "Insufficient funds."))
        else:
            product.stock -= quantity
            product.save()
            request.user.wallet -= total_price
            request.user.save()
            Purchase.objects.create(user=request.user, product=product, quantity=quantity)
            messages.success(request, settings.MESSAGES.get('purchase_success', "Purchase successful.")
                             .format(quantity=quantity, product=product.name))
        return redirect('purchase_list')


class RequestReturnView(View):
    """
    Handles the return request process for purchases.
    """
    def get(self, request: HttpRequest, purchase_id: int) -> HttpResponse:
        purchase = get_object_or_404(Purchase, id=purchase_id, user=request.user)
        form = ReturnRequestForm(max_quantity=purchase.quantity)
        return render(request, 'shop/return_form.html', {'form': form, 'purchase': purchase})

    def post(self, request: HttpRequest, purchase_id: int) -> HttpResponseRedirect:
        purchase = get_object_or_404(Purchase, id=purchase_id, user=request.user)

        if (now() - purchase.created_at).seconds > settings.RETURN_REQUEST_EXPIRATION + 180:
            messages.error(request, settings.MESSAGES.get('return_expired', "Return period has expired."))
            return redirect('purchase_list')

        form = ReturnRequestForm(request.POST, max_quantity=purchase.quantity)
        if form.is_valid():
            return_request = form.save(commit=False)
            return_request.purchase = purchase
            return_request.status = 'pending'
            return_request.save()
            purchase.quantity -= return_request.quantity
            purchase.save()
            messages.success(
                request,
                settings.MESSAGES.get('return_request_success', "Return request submitted.")
                .format(quantity=return_request.quantity),
            )
        else:
            messages.error(request, settings.MESSAGES.get('invalid_quantity', "Invalid quantity."))
        return redirect('purchase_list')


class ReturnRequestsListView(SuperuserRequiredMixin, ListView):
    """
    Displays pending return requests for admin users.
    """
    model = ReturnRequest
    template_name = 'shop/manage_return_requests.html'
    context_object_name = 'return_requests'
    paginate_by = settings.RETURN_REQUESTS_PAGINATION

    def get_queryset(self):
        # Only fetch return requests with status pending
        return ReturnRequest.objects.filter(status='pending')


class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
    """
    Admin Dashboard with links to manage products and return requests.
    """
    template_name = 'shop/admin_dashboard.html'


class RegisterView(CreateView):
    """
    Handles user registration.
    """
    model = User
    form_class = RegisterForm
    template_name = 'shop/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form: RegisterForm) -> HttpResponseRedirect:
        response = super().form_valid(form)
        self.object.wallet = settings.DEFAULT_USER_WALLET_BALANCE or 10000
        self.object.save()
        return response


class ProductListView(ListView):
    """
    Displays the list of products for users.
    """
    model = Product
    template_name = 'shop/product_list.html'
    context_object_name = 'products'
    paginate_by = settings.ADMIN_DASHBOARD_PAGINATION


class PurchaseListView(LoginRequiredMixin, TemplateView):
    """
    Displays the list of user purchases, pending return requests, and returned products.
    """
    template_name = 'shop/purchase_list.html'

    def get_context_data(self, **kwargs) -> dict:
        user = self.request.user
        purchased_products = Purchase.objects.filter(user=user).exclude(quantity=0)
        for purchase in purchased_products:
            return_expired = (now() - purchase.created_at).seconds > settings.RETURN_REQUEST_EXPIRATION
            purchase.can_return = not return_expired

        return {
            'purchased_products': purchased_products,
            'pending_requests': ReturnRequest.objects.filter(purchase__user=user, status='pending'),
            'returned_products': ReturnRequest.objects.filter(purchase__user=user, status='approved'),
        }


class ManageProductsView(SuperuserRequiredMixin, ListView):
    """
    Displays the list of products for admin management.
    """
    model = Product
    template_name = 'shop/manage_products.html'
    context_object_name = 'products'
    paginate_by = settings.ADMIN_DASHBOARD_PAGINATION

    def get_queryset(self):
        return Product.objects.all().order_by('name')


class AddProductView(SuperuserRequiredMixin, CreateView):
    """
    Allows admin to add new products.
    """
    model = Product
    form_class = ProductForm
    template_name = 'shop/add_product.html'
    success_url = reverse_lazy('manage_products')

    def form_valid(self, form: ProductForm) -> HttpResponseRedirect:
        messages.success(
            self.request,
            settings.MESSAGES.get('product_added', "Product added successfully.")
        )
        return super().form_valid(form)


class EditProductView(SuperuserRequiredMixin, UpdateView):
    """
    Allows admin to edit existing products.
    """
    model = Product
    form_class = ProductForm
    template_name = 'shop/edit_product.html'
    success_url = reverse_lazy('manage_products')

    def form_valid(self, form: ProductForm) -> HttpResponseRedirect:
        messages.success(
            self.request,
            settings.MESSAGES.get('product_updated', "Product updated successfully.")
        )
        return super().form_valid(form)


class DeleteProductView(SuperuserRequiredMixin, View):
    """
    Allows admin to delete a product, provided there are no pending return requests.
    """
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)

        # Check if the product has pending return requests
        if ReturnRequest.objects.filter(purchase__product=product, status='pending').exists():
            messages.error(
                request,
                settings.MESSAGES.get(
                    'product_delete_error',
                    "Cannot delete product with pending return requests."
                )
            )
        else:
            product_name = product.name
            product.delete()
            messages.success(
                request,
                settings.MESSAGES.get(
                    'product_deleted',
                    f'Product "{product_name}" deleted successfully.'
                )
            )
        return redirect('manage_products')


class ManageReturnRequestsView(SuperuserRequiredMixin, ListView):
    """
    Displays and manages the list of return requests for admin users.
    """
    model = ReturnRequest
    template_name = 'shop/manage_return_requests.html'
    context_object_name = 'return_requests'
    paginate_by = settings.RETURN_REQUESTS_PAGINATION

    def get_queryset(self):
        """
        Fetch all return requests sorted by creation date.
        """
        return ReturnRequest.objects.filter(status='pending').order_by('-created_at')

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponseRedirect:
        """
        Handles the approval or rejection of a return request.
        """
        action = request.POST.get('action')
        return_request_id = request.POST.get('return_request_id')

        if action in ['approve', 'reject'] and return_request_id:
            return_request = get_object_or_404(ReturnRequest, id=return_request_id)
            purchase = return_request.purchase

            if action == 'approve':
                # Approve logic
                purchase.product.stock += return_request.quantity
                purchase.product.save()
                purchase.user.wallet += return_request.quantity * purchase.product.price
                purchase.user.save()
                purchase.quantity = max(0, purchase.quantity - return_request.quantity)
                return_request.status = 'approved'
                messages.success(request, settings.MESSAGES['return_approved'].format(quantity=return_request.quantity))

            elif action == 'reject':
                # Reject logic
                purchase.quantity += return_request.quantity
                purchase.save()
                return_request.status = 'rejected'
                messages.info(request, settings.MESSAGES['return_rejected'].format(quantity=return_request.quantity))

            return_request.save()

        return redirect('manage_return_requests')
