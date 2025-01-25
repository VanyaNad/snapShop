from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Product, User, ReturnRequest


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


class PurchaseForm(forms.Form):
    """
    Form for validating purchase quantities.
    """
    quantity = forms.IntegerField(min_value=1, error_messages={
        'required': "Please enter a quantity.",
        'min_value': "Quantity must be at least 1."
    })
