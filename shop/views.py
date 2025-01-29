from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.timezone import now
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.generic import ListView, TemplateView, View, CreateView, UpdateView, FormView
from .models import Product, Purchase, ReturnRequest, User
from .forms import ReturnRequestForm, RegisterForm, ProductForm, PurchaseForm, DeleteProductForm, \
    ReturnRequestActionForm
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin


class SuperuserRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict access to superuser only views
    """
    def test_func(self) -> bool:
        return self.request.user.is_superuser


class CreatePurchaseView(LoginRequiredMixin, CreateView):
    """
    Handles the creation of purchases for logged-in users using CreateView.
    """
    model = Purchase
    form_class = PurchaseForm
    success_url = reverse_lazy('purchase_list')

    def form_valid(self, form: PurchaseForm) -> HttpResponseRedirect:
        """
        Handles the logic when the form is valid.
        """
        product: Product = get_object_or_404(Product, id=self.kwargs['product_id'])
        quantity: int = form.cleaned_data['quantity']

        try:
            with transaction.atomic():
                purchase = product.purchase_product(self.request.user, quantity)

            messages.success(
                self.request,
                settings.MESSAGES.get('purchase_success').format(quantity=quantity, product=product.name)
            )

            return redirect(self.success_url)

        except ValueError as e:
            messages.error(self.request, str(e))
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
        return_requests = ReturnRequest.objects.filter(purchase__user=user)

        return {
            'purchased_products': user.purchases.exclude(quantity=0),
            'pending_requests': return_requests.filter(status='pending'),
            'returned_products': return_requests.filter(status='approved'),
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


class DeleteProductView(SuperuserRequiredMixin, FormView):
    """
    Allows admin to delete a product
    """
    form_class = DeleteProductForm
    success_url = reverse_lazy('manage_products')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'product_id': self.kwargs['pk']})
        return kwargs

    def form_valid(self, form):
        """
        Handle valid form
        """
        product = form.cleaned_data['product']
        product_name = product.name
        product.delete()
        messages.success(
            self.request,
            settings.MESSAGES.get(
                'product_deleted',
                f'Product "{product_name}" deleted successfully.'
            )
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        """
        Handle invalid form
        """
        for error in form.errors.values():
            messages.error(self.request, error)
        return redirect(self.success_url)


class ManageReturnRequestsView(SuperuserRequiredMixin, ListView, FormView):
    """
    Displays and manages the list of return requests for admin users
    """
    model = ReturnRequest
    template_name = 'shop/manage_return_requests.html'
    context_object_name = 'return_requests'
    paginate_by = settings.RETURN_REQUESTS_PAGINATION
    form_class = ReturnRequestActionForm

    def get_queryset(self):
        return ReturnRequest.objects.filter(status='pending').order_by('-created_at')

    def form_valid(self, form):
        """
        Handle valid form
        """
        action = form.cleaned_data['action']
        return_request = form.cleaned_data['return_request']

        if action == 'approve':
            return self.handle_approve(return_request)
        elif action == 'reject':
            return self.handle_reject(return_request)

    def handle_approve(self, return_request: ReturnRequest):
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

        messages.success(self.request, settings.MESSAGES['return_approved'].format(quantity=return_request.quantity))
        return redirect('manage_return_requests')

    def handle_reject(self, return_request: ReturnRequest):
        """
        Rejects the return request and restores the purchase quantity.
        """
        purchase = return_request.purchase
        purchase.quantity += return_request.quantity
        purchase.save()

        return_request.status = 'rejected'
        return_request.save()

        messages.info(self.request, settings.MESSAGES['return_rejected'].format(quantity=return_request.quantity))
        return redirect('manage_return_requests')

    def form_invalid(self, form):
        """
        Handles invalid cases such as missing data or invalid actions.
        """
        messages.error(self.request, "Invalid action or data.")
        return redirect('manage_return_requests')
