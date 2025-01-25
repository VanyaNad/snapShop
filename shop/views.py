from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.timezone import now
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.generic import ListView, TemplateView, View, CreateView, UpdateView, FormView
from .models import Product, Purchase, ReturnRequest, User
from .forms import ReturnRequestForm, RegisterForm, ProductForm, PurchaseForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin


class SuperuserRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict access to superuser only views
    """
    def test_func(self) -> bool:
        return self.request.user.is_superuser


class CreatePurchaseView(FormView):
    """
    Handles the creation of purchases for logged-in users using FormView.
    """
    form_class = PurchaseForm
    success_url = reverse_lazy('purchase_list')

    def form_valid(self, form: PurchaseForm) -> HttpResponseRedirect:
        """
        Handles the logic when the form is valid.
        """
        product: Product = get_object_or_404(Product, id=self.kwargs['product_id'])
        quantity: int = form.cleaned_data['quantity']

        if not self.request.user.is_authenticated:
            messages.error(self.request, settings.MESSAGES.get('login_required'))
            return redirect('login')

        if quantity > product.stock:
            messages.error(self.request, settings.MESSAGES.get('insufficient_stock').format(stock=product.stock))
            return redirect(self.success_url)

        total_price: float = quantity * product.price
        if total_price > self.request.user.wallet:
            messages.error(self.request, settings.MESSAGES.get('insufficient_funds'))
            return redirect(self.success_url)

        # Update product stock and user's wallet
        product.stock -= quantity
        product.save()
        self.request.user.wallet -= total_price
        self.request.user.save()

        # Create purchase record
        Purchase.objects.create(user=self.request.user, product=product, quantity=quantity)
        messages.success(
            self.request,
            settings.MESSAGES.get('purchase_success').format(quantity=quantity, product=product.name)
        )
        return super().form_valid(form)

    def form_invalid(self, form: PurchaseForm) -> HttpResponseRedirect:
        """
        Handles the logic when the form is invalid.
        """
        messages.error(self.request, settings.MESSAGES.get('invalid_quantity', "Invalid quantity selected."))
        return redirect(self.success_url)


class RequestReturnView(LoginRequiredMixin, FormView):
    """
    Handles the return request for purchases.
    """
    template_name = 'shop/return_form.html'
    form_class = ReturnRequestForm

    def get_form_kwargs(self):
        """
        Provide additional arguments to the form, including max_quantiy for validation.
        """
        kwargs = super().get_form_kwargs()
        self.purchase = get_object_or_404(Purchase, id=self.kwargs['purchase_id'], user=self.request.user)
        kwargs['max_quantity'] = self.purchase.quantity
        return kwargs

    def get_context_data(self, **kwargs):
        """
        Add the purchase to the template context
        """
        context = super().get_context_data(**kwargs)
        context['purchase'] = self.purchase
        return context

    def form_valid(self, form):
        """
        Process a valid form submission by creating a return request.
        """
        if (now() - self.purchase.created_at).seconds > settings.RETURN_REQUEST_EXPIRATION:
            messages.error(self.request, settings.MESSAGES.get('return_expired', "Return period has expired."))
            return HttpResponseRedirect(reverse_lazy('purchase_list'))

        # Create the return request and update the purchase
        return_request = form.save(commit=False)
        return_request.purchase = self.purchase
        return_request.status = 'pending'
        return_request.save()

        self.purchase.quantity -= return_request.quantity
        self.purchase.save()

        messages.success(
            self.request,
            settings.MESSAGES.get('return_request_success', "Return request submitted.")
            .format(quantity=return_request.quantity),
        )
        return HttpResponseRedirect(reverse_lazy('purchase_list'))

    def form_invalid(self, form):
        """
        Handle invalid form submission by redirecting back to the purchase list with an error message.
        """
        messages.error(self.request, settings.MESSAGES.get('invalid_quantity', "Invalid quantity."))
        return self.render_to_response(self.get_context_data(form=form))


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
    Allows admin to delete a product
    """
    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)

        if self.has_pending_return_requests(product):
            return self.form_invalid(request, product)
        return self.form_valid(request, product)

    def has_pending_return_requests(self, product: Product) -> bool:
        """
        Check if the product has any pending return requests.
        """
        return ReturnRequest.objects.filter(purchase__product=product, status='pending').exists()

    def form_valid(self, request: HttpRequest, product: Product) -> HttpResponseRedirect:
        """
        Handle the valid case where the product can be deleted.
        """
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

    def form_invalid(self, request: HttpRequest, product: Product) -> HttpResponseRedirect:
        """
        Handle the invalid case where the product cannot be deleted due to pending return requests.
        """
        messages.error(
            request,
            settings.MESSAGES.get(
                'product_delete_error',
                "Cannot delete product with pending return requests."
            )
        )
        return redirect('manage_products')


class ManageReturnRequestsView(SuperuserRequiredMixin, ListView):
    """
    Displays and manages the list of return requests for admin users
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

        if not action or action not in ['approve', 'reject']:
            return self.form_invalid(request, error_message="Invalid action specified.")

        if not return_request_id:
            return self.form_invalid(request, error_message="Return request ID is missing.")

        try:
            return_request = get_object_or_404(ReturnRequest, id=return_request_id)
        except ReturnRequest.DoesNotExist:
            return self.form_invalid(request, error_message="Return request not found.")

        if action == 'approve':
            return self.handle_approve(request, return_request)
        elif action == 'reject':
            return self.handle_reject(request, return_request)

        return redirect('manage_return_requests')

    def handle_approve(self, request: HttpRequest, return_request: ReturnRequest) -> HttpResponseRedirect:
        """
        Approves the return request and adjusts the stock, wallet, and purchase quantities.
        """
        purchase = return_request.purchase
        purchase.product.stock += return_request.quantity
        purchase.product.save()

        purchase.user.wallet += return_request.quantity * purchase.product.price
        purchase.user.save()

        purchase.quantity = max(0, purchase.quantity - return_request.quantity)
        purchase.save()

        return_request.status = 'approved'
        return_request.save()

        messages.success(request, settings.MESSAGES['return_approved'].format(quantity=return_request.quantity))
        return redirect('manage_return_requests')

    def handle_reject(self, request: HttpRequest, return_request: ReturnRequest) -> HttpResponseRedirect:
        """
        Rejects the return request and restores the purchase quantity.
        """
        purchase = return_request.purchase
        purchase.quantity += return_request.quantity
        purchase.save()

        return_request.status = 'rejected'
        return_request.save()

        messages.info(request, settings.MESSAGES['return_rejected'].format(quantity=return_request.quantity))
        return redirect('manage_return_requests')

    def form_invalid(self, request: HttpRequest, error_message: str) -> HttpResponseRedirect:
        """
        Handles invalid cases such as missing data or invalid actions.
        """
        messages.error(request, error_message)
        return redirect('manage_return_requests')

