from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Product, User, ReturnRequest, Purchase


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'image', 'stock']


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']


class ReturnRequestForm(forms.ModelForm):
    def __init__(self, *args, max_quantity=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity'].widget.attrs.update({'max': max_quantity, 'min': 1})

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity <= 0:
            raise forms.ValidationError("You must return at least one item.")
        return quantity

    class Meta:
        model = ReturnRequest
        fields = ['quantity', 'reason']


class PurchaseForm(forms.ModelForm):
    """
    Form for validating purchase quantities.
    """
    class Meta:
        model = Purchase
        fields = ['quantity']


class DeleteProductForm(forms.Form):
    def __init__(self, *args, product_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id = product_id

    def clean(self):
        cleaned_data = super().clean()
        if self.product_id is None:
            raise forms.ValidationError("Product ID is required.")
        try:
            product = Product.objects.get(pk=self.product_id)
        except Product.DoesNotExist:
            raise forms.ValidationError("Product not found.")

        # Check for pending
        if ReturnRequest.objects.filter(purchase__product=product, status='pending').exists():
            raise forms.ValidationError("Cannot delete product with pending return requests.")

        cleaned_data['product'] = product
        return cleaned_data


class ReturnRequestActionForm(forms.Form):
    action = forms.ChoiceField(choices=[('approve', 'Approve'), ('reject', 'Reject')])
    return_request_id = forms.IntegerField()

    def clean(self):
        """
        Validate return request ID and add the return request object to the for
        """
        cleaned_data = super().clean()
        return_request_id = cleaned_data.get('return_request_id')

        if not return_request_id:
            raise forms.ValidationError("Return request ID is required.")

        try:
            cleaned_data['return_request'] = ReturnRequest.objects.get(id=return_request_id)
        except ReturnRequest.DoesNotExist:
            raise forms.ValidationError("Return request not found.")

        return cleaned_data
