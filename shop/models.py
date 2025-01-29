from datetime import timedelta
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import now
from snapShop import settings


class User(AbstractUser):
    wallet = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=settings.DEFAULT_USER_WALLET_BALANCE
    )


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    stock = models.PositiveIntegerField()

    def __str__(self):
        return self.name

    def purchase_product(self, user, quantity):
        if quantity > self.stock:
            raise ValueError(settings.MESSAGES.get('insufficient_stock').format(stock=self.stock))

        total_price = quantity * self.price
        if total_price > user.wallet:
            raise ValueError(settings.MESSAGES.get('insufficient_funds'))

        with transaction.atomic():
            self.stock -= quantity
            self.save()

            user.wallet -= total_price
            user.save()

            return Purchase.objects.create(user=user, product=self, quantity=quantity)


class Purchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return self.product.price * self.quantity

    @property
    def can_return(self):
        expiration_period = timedelta(seconds=settings.RETURN_REQUEST_EXPIRATION)
        return (now() - self.created_at).total_seconds() <= expiration_period.total_seconds()

    class Meta:
        ordering = ['-created_at']


class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return Request for {self.purchase.product.name}"

    class Meta:
        ordering = ['-created_at']
